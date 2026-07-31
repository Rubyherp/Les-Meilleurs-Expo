"""Zo export routes — isolated from the main API router.

- POST  /sessions/{session_id}/exports/zo — create export
- GET   /sessions/{session_id}/exports/zo — retrieve persisted export

Requires a completed analysis/report.  Persists export metadata in JSONB on the
latest AnalysisResult.  Reminder failure does not affect local report success.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logger import logger
from app.db.session import get_db
from app.integrations.zo.client import ZoClient
from app.integrations.zo.exporter import build_zo_artifact
from app.integrations.zo.models import ZoExportRequest, ZoExportResponse
from app.models import AnalysisJob, AnalysisResult, AnalysisSession
from app.schemas.coaching import CoachingReport

zo_router = APIRouter()


def _get_zo_client() -> ZoClient:
    """Factory for ZoClient with current settings."""
    return ZoClient(get_settings())


async def _resolve_latest_report(
    session_id: UUID,
    db: AsyncSession,
) -> tuple[AnalysisResult, AnalysisJob, CoachingReport]:
    """Resolve the latest completed analysis result and parse its coaching report.

    Raises 404 if the session or result is missing.
    Raises 400 if no coaching report is available (no analysis completed).
    """
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
        raise HTTPException(
            status_code=400,
            detail="No analysis result found for this session. Complete an analysis first.",
        )
    result, job = row

    # Try to load coaching report from result_metadata
    report_data = result.result_metadata.get("coaching_report")
    if not report_data:
        raise HTTPException(
            status_code=400,
            detail="No coaching report available. Run coaching before export.",
        )

    report = CoachingReport(**report_data)
    return result, job, report


@zo_router.post("/sessions/{session_id}/exports/zo", response_model=ZoExportResponse)
async def create_zo_export(
    session_id: UUID,
    request: ZoExportRequest | None = None,
    db: AsyncSession = Depends(get_db),
    zo_client: ZoClient = Depends(_get_zo_client),
) -> ZoExportResponse:
    """Create a versioned compact Zo export artifact and persist its metadata.

    Uses idempotency key (session ID + report version + content hash + artifact
    version + visibility) — repeated requests return the existing successful
    export when the key matches.
    """
    result, job, report = await _resolve_latest_report(session_id, db)
    request = request or ZoExportRequest()
    visibility = request.visibility or get_settings().zo_export_visibility

    existing = result.result_metadata.get("zo_export")

    # Build compact artifact
    artifact = build_zo_artifact(
        session_id=session_id,
        report=report,
        visibility=visibility,
    )

    # Idempotency check against existing export
    if existing and existing.get("idempotency_key") == artifact.idempotency_key:
        logger.task("zo", f"idempotent hit for session {session_id}")
        return ZoExportResponse(
            session_id=session_id,
            status=existing.get("status", "completed"),
            export_id=existing.get("export_id"),
            idempotency_key=artifact.idempotency_key,
            created_at=(
                datetime.fromisoformat(existing["created_at"])
                if existing.get("created_at")
                else None
            ),
            message=existing.get("message", ""),
        url=existing.get("url"),
        reminder_id=existing.get("reminder_id"),
        )

    # Attempt export via client boundary
    if request.schedule_reminder:
        response = await zo_client.export_to_zo(session_id, artifact, request=request)
    else:
        response = await zo_client.export_to_zo(session_id, artifact)

    # Persist export metadata regardless of outcome (reminder isolation)
    now = datetime.now(timezone.utc)
    export_meta = {
        "session_id": str(session_id),
        "status": response.status,
        "export_id": response.export_id,
        "idempotency_key": response.idempotency_key,
        "created_at": response.created_at.isoformat() if response.created_at else now.isoformat(),
        "artifact_version": artifact.artifact_version,
        "visibility": artifact.visibility,
        "message": response.message,
        "url": response.url,
        "reminder_id": response.reminder_id,
    }
    result.result_metadata = {**result.result_metadata, "zo_export": export_meta}
    await db.commit()

    logger.api("POST", f"/sessions/{session_id}/exports/zo", f"status={response.status}")
    return response


@zo_router.get("/sessions/{session_id}/exports/zo", response_model=ZoExportResponse)
async def get_zo_export(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ZoExportResponse:
    """Retrieve a previously persisted Zo export for a session.

    Returns 404 if no export has been created yet.
    """
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
        raise HTTPException(status_code=404, detail="No analysis result found for this session.")

    result, job = row
    export_data = result.result_metadata.get("zo_export")
    if not export_data:
        raise HTTPException(status_code=404, detail="No Zo export found for this session.")

    return ZoExportResponse(
        session_id=session_id,
        status=export_data.get("status", "not_configured"),
        export_id=export_data.get("export_id"),
        idempotency_key=export_data.get("idempotency_key", ""),
        created_at=(
            datetime.fromisoformat(export_data["created_at"])
            if export_data.get("created_at")
            else None
        ),
        message=export_data.get("message", ""),
        url=export_data.get("url"),
        reminder_id=export_data.get("reminder_id"),
    )
