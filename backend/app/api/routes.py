import uuid
from pathlib import Path
from typing import BinaryIO, Literal, cast
from uuid import UUID

from app.core.logger import logger

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_storage_service, get_task_dispatcher
from app.core.config import get_settings
from app.db.session import get_db
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
    session.calibration = {"points": [list(point) for point in payload.points]}
    await db.commit()
    logger.api("POST", f"/sessions/{session_id}/calibration", "calibration saved")
    return CalibrationResponse(session_id=session_id, points=payload.points)


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
    db: AsyncSession = Depends(get_db),
    storage: Storage = Depends(get_storage_service),
    dispatcher: TaskDispatcher = Depends(get_task_dispatcher),
) -> UploadResponse:
    session = await db.get(AnalysisSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    media = await _store_video(session_id, video, db, storage)
    job = AnalysisJob(session_id=session_id, media_id=media.id, status="pending", progress=0)
    session.status = "queued"
    db.add_all([media, job])
    await db.commit()
    await db.refresh(job)
    logger.api("POST", f"/sessions/{session_id}/upload", f"media_id={media.id} job_id={job.id}")
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

@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: UUID, db: AsyncSession = Depends(get_db)) -> TaskStatusResponse:
    query = (
        select(AnalysisJob)
        .options(selectinload(AnalysisJob.result))
        .where(AnalysisJob.id == task_id)
    )
    job = (await db.execute(query)).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return TaskStatusResponse(
        task_id=job.id,
        session_id=job.session_id,
        status=job.status,
        progress=job.progress,
        error=job.error_message,
        result=job.result.result_metadata if job.result else None,
    )
