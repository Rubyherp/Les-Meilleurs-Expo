import asyncio
import copy
import hashlib
import inspect
import json
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, BinaryIO, Callable
from uuid import UUID

from app.core.logger import logger

from sqlalchemy import delete, select

from app.core.config import Settings, get_settings
from app.db.session import AsyncSessionLocal, engine as db_engine
from app.models import (
    AnalysisAttempt,
    AnalysisCache,
    AnalysisJob,
    AnalysisResult,
    AnalysisSession,
    StoredMedia,
)
from app.services.analysis_control.controller import AdaptiveAnalysisController
from app.services.analysis_control.models import (
    AnalysisProfile,
    AnalysisSegment,
    ControlledAnalysisResult,
)
from app.services.pipeline import FramePosePipeline, ProgressEvent
from app.services.pose import MediaPipePoseEstimator
from app.services.comparison import compare_result_metadata
from app.services.projection import HomographyProjector, validate_calibration_points
from app.services.storage import Storage, get_storage
from app.services.tracking import (
    UltralyticsByteTrack,
    UltralyticsByteTrackAdapter,
)
from app.services.video import OpenCVVideoDecoder
from app.tasks.celery_app import celery_app


class ProgressThrottle:
    """Limit blocking database writes while preserving monotonic progress."""

    def __init__(
        self,
        *,
        initial_progress: int = 0,
        min_interval_seconds: float = 0.5,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._last_progress = initial_progress
        self._last_write_at = float("-inf")
        self._min_interval_seconds = min_interval_seconds
        self._clock = clock

    def next_progress(self, progress: int) -> int | None:
        bounded_progress = max(0, min(100, progress))
        if bounded_progress <= self._last_progress:
            return None

        now = self._clock()
        if (
            bounded_progress < 100
            and now - self._last_write_at < self._min_interval_seconds
        ):
            return None

        self._last_progress = bounded_progress
        self._last_write_at = now
        return bounded_progress


async def _set_progress(
    job_id: UUID,
    status: str,
    progress: int,
    *,
    stage: str | None = None,
    sampled_frames: int = 0,
) -> None:
    async with AsyncSessionLocal() as db:
        job = await db.get(AnalysisJob, job_id)
        if job is None:
            return
        job.status = status
        job.progress = progress
        if stage is not None:
            job.control_state = {
                "stage": stage,
                "progress": progress,
                "sampled_frames": sampled_frames,
            }
        session = await db.get(AnalysisSession, job.session_id)
        if session and status == "processing":
            session.status = "processing"
        await db.commit()


async def _set_failed(job_id: UUID, message: str) -> None:
    async with AsyncSessionLocal() as db:
        job = await db.get(AnalysisJob, job_id)
        if job is None:
            return
        job.status = "failed"
        job.error_message = message
        job.control_state = {
            "stage": "failed",
            "progress": job.progress,
            "error": message,
        }
        session = await db.get(AnalysisSession, job.session_id)
        if session:
            session.status = "failed"
        await db.commit()


def _copy_stream(source: BinaryIO, destination: str) -> None:
    source.seek(0)
    with open(destination, "wb") as output:
        shutil.copyfileobj(source, output)


def build_pipeline(
    settings: Settings,
    calibration: dict | None = None,
    *,
    profile: AnalysisProfile | None = None,
    expected_dancer_count: int = 1,
) -> FramePosePipeline:
    """Construct lightweight pipeline components; model assets load on first inference."""
    if profile is None:
        from app.services.analysis_control.profiles import ProfileRegistry

        profile = ProfileRegistry(settings, expected_dancer_count).balanced()
    projector = None
    if calibration is not None:
        points = calibration.get("points")
        if points is None:
            raise ValueError("Stored calibration is missing points.")
        projector = HomographyProjector(
            validate_calibration_points(points),
            grid_columns=settings.grid_columns,
            grid_rows=settings.grid_rows,
        )
    return FramePosePipeline(
        decoder=OpenCVVideoDecoder(),
        detector=None,
        tracker=UltralyticsByteTrack(
            adapter=UltralyticsByteTrackAdapter(
                weights_path=profile.yolo_model_path,
                tracker_name=profile.tracker_name,
                confidence=profile.low_confidence,
                high_confidence=profile.high_confidence,
                max_persons=profile.max_persons,
                device=settings.ml_device,
                image_size=profile.image_size,
            ),
            buffer_frames=profile.tracker_buffer_frames or 0,
            iou_threshold=profile.tracker_iou_threshold,
        ),
        pose_estimator=MediaPipePoseEstimator(
            asset_path=profile.pose_model_path,
            padding=profile.crop_padding,
            min_detection_confidence=profile.pose_min_detection_confidence,
            min_presence_confidence=profile.pose_min_presence_confidence,
            min_tracking_confidence=profile.pose_min_tracking_confidence,
        ),
        frame_stride=profile.frame_stride,
        target_fps=profile.target_fps,
        tracker_name=profile.tracker_name,
        tracker_buffer_seconds=profile.tracker_buffer_seconds,
        tracker_buffer_frames=profile.tracker_buffer_frames,
        projector=projector,
        grid_columns=settings.grid_columns,
        grid_rows=settings.grid_rows,
    )


async def _run_pipeline_for_media(
    settings: Settings,
    media: StoredMedia,
    storage: Storage,
    calibration: dict | None,
    pipeline_factory: Callable[..., Any],
    progress_callback: Callable[[ProgressEvent], None],
    *,
    expected_dancer_count: int = 1,
) -> ControlledAnalysisResult:
    source = await storage.download(media.object_key)
    suffix = Path(media.original_filename).suffix or ".video"
    with tempfile.NamedTemporaryFile(suffix=suffix) as temporary_file:
        try:
            await asyncio.to_thread(_copy_stream, source, temporary_file.name)
        finally:
            source.close()

        def execute(
            profile: AnalysisProfile,
            segments: tuple[AnalysisSegment, ...],
            callback: Callable[[ProgressEvent], None] | None,
            applied_calibration: dict | None,
        ) -> dict:
            pipeline = _construct_pipeline(
                pipeline_factory,
                settings,
                calibration=applied_calibration,
                profile=profile,
                expected_dancer_count=expected_dancer_count,
            )
            run = pipeline.run
            kwargs: dict[str, Any] = {}
            if segments and _accepts_keyword(run, "segments"):
                kwargs["segments"] = [
                    (segment.start_seconds, segment.end_seconds)
                    for segment in segments
                ]
            # Extract audio beats before running the vision pipeline
            try:
                from app.services.audio import extract_beats
                audio_info = extract_beats(temporary_file.name)
            except Exception:
                audio_info = {"tempo": 0.0, "beats": [], "duration": 0.0, "error": "extraction_failed"}

            result = run(temporary_file.name, callback, **kwargs)
            result["audio"] = audio_info
            return result

        controller = AdaptiveAnalysisController(
            settings, expected_dancer_count=expected_dancer_count
        )
        return await asyncio.to_thread(
            controller.run,
            temporary_file.name,
            calibration=calibration,
            executor=execute,
            progress_callback=progress_callback,
        )


def _accepts_keyword(callable_object: Callable[..., Any], keyword: str) -> bool:
    try:
        signature = inspect.signature(callable_object)
    except (TypeError, ValueError):
        return False
    return keyword in signature.parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )


def _construct_pipeline(
    pipeline_factory: Callable[..., Any],
    settings: Settings,
    *,
    calibration: dict | None,
    profile: AnalysisProfile,
    expected_dancer_count: int,
) -> Any:
    kwargs: dict[str, Any] = {}
    if calibration is not None and _accepts_keyword(pipeline_factory, "calibration"):
        kwargs["calibration"] = calibration
    if _accepts_keyword(pipeline_factory, "profile"):
        kwargs["profile"] = profile
    if _accepts_keyword(pipeline_factory, "expected_dancer_count"):
        kwargs["expected_dancer_count"] = expected_dancer_count
    return pipeline_factory(settings, **kwargs)


def _analysis_cache_key(
    settings: Settings,
    media: StoredMedia,
    calibration: dict | None,
    expected_dancer_count: int,
) -> str:
    from app.services.analysis_control.profiles import ProfileRegistry

    base_profile = ProfileRegistry(settings, expected_dancer_count).balanced()
    payload = {
        "version": 1,
        "media_checksum": media.checksum_sha256,
        "calibration": calibration,
        "expected_dancer_count": expected_dancer_count,
        "base_profile": base_profile.fingerprint,
        "recovery_model": _path_signature(
            settings.analysis_recovery_yolo_model_path
        ),
        "recovery_pose": _path_signature(
            settings.analysis_recovery_pose_model_path
        ),
        "control": {
            "mode": settings.analysis_control_mode,
            "max_attempts": settings.analysis_max_attempts,
            "quality_threshold": settings.analysis_min_quality_score,
            "minimum_improvement": settings.analysis_min_improvement,
            "scout_fps": settings.analysis_scout_fps,
            "scout_max_frames": settings.analysis_scout_max_frames,
            "recovery_fps": settings.analysis_recovery_sample_fps,
            "recovery_image_size": settings.analysis_recovery_image_size,
            "segment_padding": settings.analysis_segment_padding_seconds,
            "retry_budget": settings.analysis_max_retry_seconds,
            "auto_calibration": settings.analysis_auto_calibration_enabled,
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _path_signature(path_value: str | None) -> dict[str, Any] | None:
    if not path_value:
        return None
    path = Path(path_value)
    try:
        stat = path.stat()
    except OSError:
        return {"path": path_value, "status": "missing"}
    return {
        "path": path_value,
        "size": stat.st_size,
        "modified_ns": stat.st_mtime_ns,
    }


async def _persist_attempts(
    db: Any,
    *,
    job_id: UUID,
    media_id: UUID,
    controlled: ControlledAnalysisResult,
) -> None:
    for outcome in controlled.attempts:
        db.add(
            AnalysisAttempt(
                job_id=job_id,
                media_id=media_id,
                attempt_number=outcome.plan.attempt_number,
                state=outcome.plan.state,
                profile_id=outcome.plan.profile.profile_id,
                reason_codes=list(outcome.plan.reason_codes),
                segments=[
                    segment.to_dict() for segment in outcome.plan.segments
                ],
                metrics=outcome.quality.to_dict(),
                model_provenance=outcome.plan.profile.to_dict(),
                accepted=outcome.accepted,
                runtime_seconds=outcome.runtime_seconds,
            )
        )


async def _process_job(
    job_id: UUID,
    storage: Storage | None = None,
    pipeline_factory: Callable[..., Any] | None = None,
) -> None:
    settings = get_settings()
    async with AsyncSessionLocal() as db:
        job = await db.get(AnalysisJob, job_id)
        if job is None:
            return
        session = await db.get(AnalysisSession, job.session_id)
        media = await db.get(StoredMedia, job.media_id) if job.media_id else None
        if media is None and job.mode != "comparison":
            media_query = (
                select(StoredMedia)
                .where(StoredMedia.session_id == job.session_id)
                .order_by(StoredMedia.created_at.desc())
                .limit(1)
            )
            media = (await db.execute(media_query)).scalar_one_or_none()
        if media is None and job.mode != "comparison":
            raise RuntimeError(f"No stored media is associated with analysis job {job_id}.")

        job.status = "processing"
        job.progress = 5
        job.control_state = {"stage": "starting", "progress": 5}
        await db.execute(
            delete(AnalysisAttempt).where(AnalysisAttempt.job_id == job_id)
        )
        if session:
            session.status = "processing"
        await db.commit()
        logger.task("run_analysis", f"job {job_id} started — mode={job.mode}")

        storage_service = storage or get_storage(settings)
        factory = pipeline_factory or build_pipeline
        event_loop = asyncio.get_running_loop()
        progress_throttle = ProgressThrottle(initial_progress=job.progress)

        def progress_callback(event: ProgressEvent) -> None:
            progress = progress_throttle.next_progress(event.progress)
            if progress is None:
                return
            future = asyncio.run_coroutine_threadsafe(
                _set_progress(
                    job_id,
                    "processing",
                    progress,
                    stage=event.stage,
                    sampled_frames=event.sampled_frames,
                ),
                event_loop,
            )
            future.result()

        if job.mode == "comparison":
            logger.phase("starting reference pipeline")
            if session is None or session.calibration is None:
                raise RuntimeError("Calibration is required before comparison.")
            reference_media = (
                await db.get(StoredMedia, job.reference_media_id)
                if job.reference_media_id
                else None
            )
            attempt_media = (
                await db.get(StoredMedia, job.attempt_media_id)
                if job.attempt_media_id
                else None
            )
            if reference_media is None or attempt_media is None:
                raise RuntimeError("Comparison job is missing reference or attempt media.")

            def reference_progress(event: ProgressEvent) -> None:
                progress_callback(
                    ProgressEvent(event.stage, 5 + int(event.progress * 0.4), event.sampled_frames)
                )

            def attempt_progress(event: ProgressEvent) -> None:
                progress_callback(
                    ProgressEvent(event.stage, 45 + int(event.progress * 0.4), event.sampled_frames)
                )

            cache_key = _analysis_cache_key(
                settings,
                reference_media,
                session.calibration,
                job.expected_dancer_count,
            )
            cached = (
                await db.get(AnalysisCache, cache_key)
                if settings.analysis_cache_enabled
                else None
            )
            reference_controlled: ControlledAnalysisResult | None = None
            if cached is not None:
                reference_result = copy.deepcopy(cached.result_metadata)
                reference_result.setdefault("analysis_control", {})["cache_hit"] = True
                reference_progress(ProgressEvent("reference_cache_hit", 100, 0))
            else:
                reference_controlled = await _run_pipeline_for_media(
                    settings,
                    reference_media,
                    storage_service,
                    session.calibration,
                    factory,
                    reference_progress,
                    expected_dancer_count=job.expected_dancer_count,
                )
                reference_result = reference_controlled.result
                await _persist_attempts(
                    db,
                    job_id=job_id,
                    media_id=reference_media.id,
                    controlled=reference_controlled,
                )
                if settings.analysis_cache_enabled:
                    accepted = next(
                        (
                            item
                            for item in reversed(reference_controlled.attempts)
                            if item.accepted
                        ),
                        reference_controlled.attempts[0],
                    )
                    db.add(
                        AnalysisCache(
                            cache_key=cache_key,
                            media_checksum_sha256=reference_media.checksum_sha256,
                            profile_fingerprint=accepted.plan.profile.fingerprint,
                            result_metadata=copy.deepcopy(reference_result),
                        )
                    )
            logger.phase("reference complete → starting attempt pipeline")
            attempt_controlled = await _run_pipeline_for_media(
                settings,
                attempt_media,
                storage_service,
                session.calibration,
                factory,
                attempt_progress,
                expected_dancer_count=job.expected_dancer_count,
            )
            attempt_result = attempt_controlled.result
            await _persist_attempts(
                db,
                job_id=job_id,
                media_id=attempt_media.id,
                controlled=attempt_controlled,
            )
            logger.phase("attempt complete → running comparison")
            result_metadata = compare_result_metadata(
                reference_result,
                attempt_result,
                max_dancers=settings.comparison_max_dancers,
                min_coverage=settings.comparison_min_coverage,
                max_cost=settings.comparison_max_cost,
                unmatched_penalty=settings.comparison_unmatched_penalty,
                include_predicted=settings.comparison_include_predicted,
                predicted_weight=settings.comparison_predicted_weight,
            )
            result_metadata["analysis_control"] = {
                "version": 1,
                "state": (
                    "accept"
                    if reference_result.get("analysis_control", {}).get("state")
                    == "accept"
                    and attempt_result.get("analysis_control", {}).get("state")
                    == "accept"
                    else "human_review"
                ),
                "reference": reference_result.get("analysis_control"),
                "attempt": attempt_result.get("analysis_control"),
            }
            await _set_progress(
                job_id, "processing", 95, stage="comparing", sampled_frames=0
            )
            logger.phase("comparison complete → writing results")
        else:
            if media is None:
                raise RuntimeError(f"No stored media is associated with analysis job {job_id}.")
            controlled = await _run_pipeline_for_media(
                settings,
                media,
                storage_service,
                session.calibration if session is not None else None,
                factory,
                progress_callback,
                expected_dancer_count=job.expected_dancer_count,
            )
            result_metadata = controlled.result
            await _persist_attempts(
                db, job_id=job_id, media_id=media.id, controlled=controlled
            )

        logger.phase(f"writing results for job {job_id}")
        existing_result = (
            await db.execute(select(AnalysisResult).where(AnalysisResult.job_id == job_id))
        ).scalar_one_or_none()
        if existing_result:
            existing_result.result_metadata = result_metadata
        else:
            db.add(AnalysisResult(job_id=job_id, result_metadata=result_metadata))
        job.status = "completed"
        job.progress = 100
        job.control_state = {
            "stage": result_metadata.get("analysis_control", {}).get(
                "state", "completed"
            ),
            "progress": 100,
            "quality": result_metadata.get("analysis_control", {}).get(
                "final_quality"
            ),
        }
        job.error_message = None
        if session:
            session.status = "completed"
        await db.commit()
        logger.task("run_analysis", f"job {job_id} completed successfully")


async def _run_job(job_id: UUID) -> None:
    try:
        await _process_job(job_id)
    except Exception as exc:
        logger.error(f"run_analysis job {job_id}", str(exc))
        await _set_failed(job_id, str(exc))
        raise
    finally:
        await db_engine.dispose()


@celery_app.task(bind=True, name="analysis.run")
def run_analysis(self, job_id: str) -> None:
    """Run frame-level detection and pose estimation for one stored video."""
    asyncio.run(_run_job(UUID(job_id)))
