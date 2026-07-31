import asyncio
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import BinaryIO, Literal, cast
from uuid import UUID

from app.core.logger import logger

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_storage_service, get_task_dispatcher
from app.core.config import get_settings
from app.db.session import get_db
from app.integrations.health import get_integration_health
from app.integrations.models import EvidenceMoment, IntegrationHealth
from app.integrations.agnes.reviewer import review_evidence_with_agnes
from app.models import AnalysisJob, AnalysisResult, AnalysisSession, StoredMedia
from app.schemas.session import (
    CalibrationRequest,
    CalibrationResponse,
    ComparisonRequest,
    ComparisonResponse,
    RoleMediaResponse,
    SessionCreateResponse,
    SessionResultResponse,
    TaskStatusResponse,
    UploadResponse,
)
from app.services.storage import Storage
from app.schemas.coaching import CoachingReport, CoachingRequest, CoachingResponse
from app.services.coaching.orchestrator import run_coaching
from app.services.evidence.models import EvidenceMedia
from app.services.evidence.selector import select_evidence
from app.services.tasks import TaskDispatcher
from app.services.uploads import UploadValidationError, validate_and_buffer_upload

router = APIRouter()


async def _store_video(
    session_id: UUID,
    video: UploadFile,
    db: AsyncSession,
    storage: Storage,
    role: Literal["reference", "attempt"] | None = None,
) -> StoredMedia:
    try:
        buffered = await validate_and_buffer_upload(video, get_settings())
    except UploadValidationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    media_id = uuid.uuid4()
    extension = Path(video.filename or "video").suffix.lower()
    object_key = f"sessions/{session_id}/media/{media_id}{extension}"
    try:
        stored = await storage.upload(
            cast(BinaryIO, buffered.file_obj), object_key, video.content_type or ""
        )
    finally:
        buffered.file_obj.close()
    return StoredMedia(
        id=media_id,
        session_id=session_id,
        role=role,
        object_key=stored.object_key,
        original_filename=video.filename or "video",
        content_type=video.content_type or "application/octet-stream",
        size_bytes=buffered.size_bytes,
        checksum_sha256=buffered.checksum_sha256,
    )
@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/integrations", response_model=IntegrationHealth)
async def integration_health() -> IntegrationHealth:
    """Return sanitised provider configuration state (no paid calls)."""
    return get_integration_health(get_settings())


@router.post("/sessions", response_model=SessionCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_session(db: AsyncSession = Depends(get_db)) -> SessionCreateResponse:
    session = AnalysisSession()
    db.add(session)
    await db.commit()
    await db.refresh(session)
    logger.api("POST", f"/sessions/{session.id}", "session created")
    return SessionCreateResponse(
        session_id=session.id,
        status=session.status,
        created_at=session.created_at,
    )


@router.post("/sessions/{session_id}/calibration", response_model=CalibrationResponse)
async def set_calibration(
    session_id: UUID,
    payload: CalibrationRequest,
    db: AsyncSession = Depends(get_db),
) -> CalibrationResponse:
    session = await db.get(AnalysisSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    source = payload.source
    calibration_status = {
        "human": "verified",
        "approximate": "provisional",
        "agent": "proposed",
    }[source]
    session.calibration = {
        "points": [list(point) for point in payload.points],
        "source": source,
        "status": calibration_status,
    }
    await db.commit()
    logger.api("POST", f"/sessions/{session_id}/calibration", "calibration saved")
    return CalibrationResponse(
        session_id=session_id,
        points=payload.points,
        source=source,
        status=session.calibration["status"],
    )


@router.get("/sessions/{session_id}/results", response_model=SessionResultResponse)
async def get_session_results(
    session_id: UUID, db: AsyncSession = Depends(get_db)
) -> SessionResultResponse:
    if await db.get(AnalysisSession, session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    query = (
        select(AnalysisResult, AnalysisJob)
        .join(AnalysisJob, AnalysisJob.id == AnalysisResult.job_id)
        .where(AnalysisJob.session_id == session_id)
        .order_by(AnalysisResult.created_at.desc())
        .limit(1)
    )
    row = (await db.execute(query)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="No analysis result found for session.")
    result, job = row
    return SessionResultResponse(
        session_id=session_id,
        task_id=job.id,
        created_at=result.created_at,
        metadata=result.result_metadata,
    )


@router.post(
    "/sessions/{session_id}/reference",
    response_model=RoleMediaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def store_reference_video(
    session_id: UUID,
    video: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    storage: Storage = Depends(get_storage_service),
) -> RoleMediaResponse:
    if await db.get(AnalysisSession, session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    media = await _store_video(session_id, video, db, storage, role="reference")
    db.add(media)
    await db.commit()
    logger.api("POST", f"/sessions/{session_id}/reference", f"media_id={media.id}")
    return RoleMediaResponse(session_id=session_id, media_id=media.id, role="reference")


@router.post(
    "/sessions/{session_id}/attempt",
    response_model=RoleMediaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def store_attempt_video(
    session_id: UUID,
    video: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    storage: Storage = Depends(get_storage_service),
) -> RoleMediaResponse:
    if await db.get(AnalysisSession, session_id) is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    media = await _store_video(session_id, video, db, storage, role="attempt")
    db.add(media)
    await db.commit()
    logger.api("POST", f"/sessions/{session_id}/attempt", f"media_id={media.id}")
    return RoleMediaResponse(session_id=session_id, media_id=media.id, role="attempt")


@router.post(
    "/sessions/{session_id}/compare",
    response_model=ComparisonResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_comparison(
    session_id: UUID,
    payload: ComparisonRequest,
    db: AsyncSession = Depends(get_db),
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),
) -> ComparisonResponse:
    session = await db.get(AnalysisSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    if session.calibration is None:
        raise HTTPException(status_code=400, detail="Calibration is required before comparison.")

    async def resolve_media(role: Literal["reference", "attempt"], media_id: UUID | None) -> StoredMedia:
        if media_id is not None:
            media = await db.get(StoredMedia, media_id)
            if media is None or media.session_id != session_id or media.role != role:
                raise HTTPException(status_code=400, detail=f"Invalid {role} media for session.")
            return media
        query = (
            select(StoredMedia)
            .where(StoredMedia.session_id == session_id, StoredMedia.role == role)
            .order_by(StoredMedia.created_at.desc())
            .limit(1)
        )
        media = (await db.execute(query)).scalar_one_or_none()
        if media is None:
            raise HTTPException(status_code=404, detail=f"No {role} media found for session.")
        return media

    reference = await resolve_media("reference", payload.reference_media_id)
    attempt = await resolve_media("attempt", payload.attempt_media_id)
    job = AnalysisJob(
        session_id=session_id,
        mode="comparison",
        reference_media_id=reference.id,
        attempt_media_id=attempt.id,
        expected_dancer_count=payload.expected_dancer_count,
        status="pending",
        progress=0,
    )
    session.status = "queued"
    db.add(job)
    await db.commit()
    await db.refresh(job)
    logger.api("POST", f"/sessions/{session_id}/compare", f"job_id={job.id} mode={job.mode}")
    comparison_task_id = job.id
    comparison_mode = job.mode
    task_status = job.status
    try:
        job.celery_task_id = dispatcher.enqueue(job.id)
        job.status = "queued"
        task_status = job.status
        await db.commit()
    except Exception as exc:
        job.status = "failed"
        logger.error("compare enqueue", str(exc))
        job.error_message = f"Enqueue failed: {exc}"
        session.status = "failed"
        task_status = job.status
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enqueue comparison task: {exc}",
        )

    return ComparisonResponse(
        session_id=session_id,
        task_id=comparison_task_id,
        status=task_status,
        mode=comparison_mode,
        reference_media_id=reference.id,
        attempt_media_id=attempt.id,
    )
@router.post("/sessions/{session_id}/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_video(
    session_id: UUID,
    video: UploadFile = File(...),
    expected_dancer_count: int = Form(1, ge=1, le=24),
    db: AsyncSession = Depends(get_db),
    storage: Storage = Depends(get_storage_service),
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),
) -> UploadResponse:
    session = await db.get(AnalysisSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    media = await _store_video(session_id, video, db, storage)
    db.add(media)
    await db.flush()
    logger.api("POST", f"/sessions/{session_id}/upload", f"media_id={media.id}")

    job = AnalysisJob(
        session_id=session_id,
        media_id=media.id,
        expected_dancer_count=expected_dancer_count,
        status="pending",
        progress=0,
    )
    session.status = "queued"
    db.add(job)
    await db.commit()
    await db.refresh(job)
    stored_media_id = media.id
    task_id = job.id
    task_status = job.status

    try:
        celery_task_id = dispatcher.enqueue(job.id)
        job.celery_task_id = celery_task_id
        job.status = "queued"
        task_status = job.status
        await db.commit()
    except Exception as exc:
        job.status = "failed"
        logger.error("upload enqueue", str(exc))
        job.error_message = f"Enqueue failed: {exc}"
        session.status = "failed"
        task_status = job.status
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enqueue analysis task: {exc}",
        )

    return UploadResponse(session_id=session_id, media_id=stored_media_id, task_id=task_id, status=task_status)

@router.get(
    "/tasks/{task_id}",
    response_model=TaskStatusResponse,
    response_model_exclude_unset=True,
)
async def get_task_status(task_id: UUID, db: AsyncSession = Depends(get_db)) -> TaskStatusResponse:
    query = (
        select(AnalysisJob)
        .options(selectinload(AnalysisJob.result))
        .where(AnalysisJob.id == task_id)
    )
    job = (await db.execute(query)).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    response = {
        "task_id": job.id,
        "session_id": job.session_id,
        "status": job.status,
        "progress": job.progress,
        "error": job.error_message,
        "result": job.result.result_metadata if job.result else None,
    }
    if job.control_state is not None:
        response["control"] = job.control_state
    return TaskStatusResponse(
        **response
    )


@router.post("/sessions/{session_id}/coach", response_model=CoachingResponse)
async def request_coaching(
    session_id: UUID,
    payload: CoachingRequest | None = None,
    db: AsyncSession = Depends(get_db),
    storage: Storage = Depends(get_storage_service),
) -> CoachingResponse:
    session = await db.get(AnalysisSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    
    # Find latest completed analysis result
    query = (
        select(AnalysisResult, AnalysisJob)
        .join(AnalysisJob, AnalysisJob.id == AnalysisResult.job_id)
        .where(AnalysisJob.session_id == session_id)
        .order_by(AnalysisResult.created_at.desc())
        .limit(1)
    )
    row = (await db.execute(query)).first()
    if row is None:
        return CoachingResponse(
            session_id=session_id, status="no_data",
            message="No analysis result found for this session."
        )
    result, job = row

    mode = job.mode if job.mode else "single"
    settings = get_settings()
    payload = payload or CoachingRequest()
    cache_key = {
        "version": 1,
        "mode": mode,
        "is_group": payload.is_group,
        "expected_dancer_count": payload.expected_dancer_count,
        "openai_model": settings.openai_model if settings.openai_api_key else None,
        "agnes_model": settings.agnes_model if settings.agnes_api_key else None,
        "gmi_model": settings.gmi_model if settings.gmi_api_key else None,
    }
    cached = result.result_metadata.get("coaching_report")
    retriable_products = {
        "visual-evidence", "agents-coaching", "serverless-inference-audit",
    }
    cached_has_provider_failure = any(
        run.get("product") in retriable_products
        and run.get("status") in {"failed", "fallback"}
        for run in (cached or {}).get("integrations", [])
        if isinstance(run, dict)
    )
    if (
        cached
        and not cached_has_provider_failure
        and result.result_metadata.get("coaching_cache_key") == cache_key
    ):
        return CoachingResponse(
            session_id=session_id, report=CoachingReport(**cached), status="completed"
        )

    is_group = payload.is_group
    evidence = select_evidence(
        result.result_metadata, mode=mode, is_group=is_group,
        max_moments=settings.agnes_max_evidence_moments,
        duration_seconds=(float(result.result_metadata["duration_seconds"]) if isinstance(result.result_metadata.get("duration_seconds"), (int, float)) else None),
    )
    reviewed_evidence = evidence
    agnes_runs = []
    if evidence:
        attempt_id = job.attempt_media_id or job.media_id
        attempt_media = await db.get(StoredMedia, attempt_id) if attempt_id else None
        reference_media = await db.get(StoredMedia, job.reference_media_id) if job.reference_media_id else None
        if attempt_media:
            with tempfile.TemporaryDirectory(prefix="les-evidence-") as directory:
                attempt_path = str(Path(directory) / "attempt.video")
                attempt_stream = await storage.download(attempt_media.object_key)
                try:
                    await asyncio.to_thread(_copy_to_path, attempt_stream, attempt_path)
                finally:
                    attempt_stream.close()
                reference_path = None
                if reference_media:
                    reference_path = str(Path(directory) / "reference.video")
                    reference_stream = await storage.download(reference_media.object_key)
                    try:
                        await asyncio.to_thread(_copy_to_path, reference_stream, reference_path)
                    finally:
                        reference_stream.close()
                reviewed_evidence, agnes_run = await review_evidence_with_agnes(
                    evidence, EvidenceMedia(attempt_path, reference_path), settings
                )
                agnes_runs.append(agnes_run)
        else:
            from app.integrations.models import IntegrationRun
            agnes_runs.append(IntegrationRun(
                provider="agnes", product="visual-evidence", model=settings.agnes_model,
                status="fallback", fallback_reason="source_media_unavailable",
            ))

    report = await run_coaching(
        session_id,
        mode,
        result.result_metadata,
        is_group=is_group,
        expected_dancer_count=payload.expected_dancer_count,
        settings=settings,
        evidence_moments=reviewed_evidence,
        extra_integrations=agnes_runs,
    )
    
    # Store report back in result_metadata for GET caching
    result.result_metadata = {
        **result.result_metadata,
        "coaching_report": report.model_dump(mode="json"),
        "coaching_cache_key": cache_key,
    }
    await db.commit()
    
    return CoachingResponse(session_id=session_id, report=report, status="completed")


def _copy_to_path(source: BinaryIO, destination: str) -> None:
    source.seek(0)
    with open(destination, "wb") as output:
        shutil.copyfileobj(source, output)


@router.get("/sessions/{session_id}/evidence", response_model=list[EvidenceMoment])
async def get_session_evidence(
    session_id: UUID, db: AsyncSession = Depends(get_db)
) -> list[EvidenceMoment]:
    """Return only persisted, session-scoped evidence from the cached report."""
    session = await db.get(AnalysisSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    query = (
        select(AnalysisResult)
        .join(AnalysisJob, AnalysisJob.id == AnalysisResult.job_id)
        .where(AnalysisJob.session_id == session_id)
        .order_by(AnalysisResult.created_at.desc())
        .limit(1)
    )
    result = (await db.execute(query)).scalar_one_or_none()
    if result is None:
        return []
    cached = result.result_metadata.get("coaching_report") or {}
    return [
        EvidenceMoment.model_validate(item)
        for item in cached.get("evidence_moments") or []
    ]

@router.get("/sessions/{session_id}/coach", response_model=CoachingResponse)
async def get_coaching(session_id: UUID, db: AsyncSession = Depends(get_db)) -> CoachingResponse:
    session = await db.get(AnalysisSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    
    query = (
        select(AnalysisResult, AnalysisJob)
        .join(AnalysisJob, AnalysisJob.id == AnalysisResult.job_id)
        .where(AnalysisJob.session_id == session_id)
        .order_by(AnalysisResult.created_at.desc())
        .limit(1)
    )
    row = (await db.execute(query)).first()
    if row is None:
        return CoachingResponse(
            session_id=session_id, status="no_data",
            message="No analysis result found for this session."
        )
    result, _ = row
    
    cached = result.result_metadata.get("coaching_report")
    if cached:
        return CoachingResponse(
            session_id=session_id,
            report=CoachingReport(**cached),
            status="completed"
        )
    
    return CoachingResponse(
        session_id=session_id, status="no_data",
        message="Coaching has not been generated yet. Use POST to trigger."
    )
