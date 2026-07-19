import asyncio
import shutil
import tempfile
from pathlib import Path
from typing import Any, BinaryIO, Callable
from uuid import UUID

from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.db.session import AsyncSessionLocal
from app.models import AnalysisJob, AnalysisResult, AnalysisSession, StoredMedia
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


async def _set_progress(job_id: UUID, status: str, progress: int) -> None:
    async with AsyncSessionLocal() as db:
        job = await db.get(AnalysisJob, job_id)
        if job is None:
            return
        job.status = status
        job.progress = progress
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
        session = await db.get(AnalysisSession, job.session_id)
        if session:
            session.status = "failed"
        await db.commit()


def _copy_stream(source: BinaryIO, destination: str) -> None:
    source.seek(0)
    with open(destination, "wb") as output:
        shutil.copyfileobj(source, output)


def build_pipeline(
    settings: Settings, calibration: dict | None = None
) -> FramePosePipeline:
    """Construct lightweight pipeline components; model assets load on first inference."""
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
                weights_path=settings.yolo_model_path,
                tracker_name=settings.tracker_name,
                confidence=settings.tracker_low_confidence,
                high_confidence=settings.tracker_high_confidence,
                max_persons=settings.max_persons,
                device=settings.ml_device,
            ),
            buffer_frames=settings.tracker_buffer_frames or 0,
            iou_threshold=settings.tracker_iou_threshold,
        ),
        pose_estimator=MediaPipePoseEstimator(
            asset_path=settings.pose_model_path,
            padding=settings.crop_padding,
        ),
        frame_stride=settings.frame_stride,
        target_fps=settings.sample_fps,
        tracker_name=settings.tracker_name,
        tracker_buffer_seconds=settings.tracker_buffer_seconds,
        tracker_buffer_frames=settings.tracker_buffer_frames,
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
) -> dict:
    source = await storage.download(media.object_key)
    suffix = Path(media.original_filename).suffix or ".video"
    with tempfile.NamedTemporaryFile(suffix=suffix) as temporary_file:
        try:
            await asyncio.to_thread(_copy_stream, source, temporary_file.name)
        finally:
            source.close()
        if calibration is not None:
            pipeline = pipeline_factory(settings, calibration=calibration)
        else:
            pipeline = pipeline_factory(settings)
        return await asyncio.to_thread(pipeline.run, temporary_file.name, progress_callback)


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
        if session:
            session.status = "processing"
        await db.commit()

        storage_service = storage or get_storage(settings)
        factory = pipeline_factory or build_pipeline
        event_loop = asyncio.get_running_loop()

        def progress_callback(event: ProgressEvent) -> None:
            future = asyncio.run_coroutine_threadsafe(
                _set_progress(job_id, "processing", event.progress), event_loop
            )
            future.result()

        if job.mode == "comparison":
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

            reference_result = await _run_pipeline_for_media(
                settings, reference_media, storage_service, session.calibration, factory, reference_progress
            )
            attempt_result = await _run_pipeline_for_media(
                settings, attempt_media, storage_service, session.calibration, factory, attempt_progress
            )
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
            await _set_progress(job_id, "processing", 95)
        else:
            if media is None:
                raise RuntimeError(f"No stored media is associated with analysis job {job_id}.")
            result_metadata = await _run_pipeline_for_media(
                settings,
                media,
                storage_service,
                session.calibration if session is not None else None,
                factory,
                progress_callback,
            )

        existing_result = (
            await db.execute(select(AnalysisResult).where(AnalysisResult.job_id == job_id))
        ).scalar_one_or_none()
        if existing_result:
            existing_result.result_metadata = result_metadata
        else:
            db.add(AnalysisResult(job_id=job_id, result_metadata=result_metadata))
        job.status = "completed"
        job.progress = 100
        job.error_message = None
        if session:
            session.status = "completed"
        await db.commit()


async def _run_job(job_id: UUID) -> None:
    try:
        await _process_job(job_id)
    except Exception as exc:
        await _set_failed(job_id, str(exc))
        raise


@celery_app.task(bind=True, name="analysis.run")
def run_analysis(self, job_id: str) -> None:
    """Run frame-level detection and pose estimation for one stored video."""
    asyncio.run(_run_job(UUID(job_id)))
