"""Bounded orchestration for selected Agnes evidence moments."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.core.config import Settings
from app.integrations.agnes.client import AgnesClient
from app.integrations.models import EvidenceFrame, EvidenceMoment, IntegrationRun
from app.services.evidence.frames import prepare_evidence_images
from app.services.evidence.models import EvidenceMedia


async def review_evidence_with_agnes(
    moments: list[EvidenceMoment], media: EvidenceMedia, settings: Settings,
) -> tuple[list[EvidenceMoment], IntegrationRun]:
    if not AgnesClient(settings).available:
        return moments, IntegrationRun(
            provider="agnes", product="visual-evidence", model=settings.agnes_model or None,
            status="not_configured", fallback_reason="missing_configuration",
        )
    if settings.agnes_max_evidence_moments == 0:
        return moments, IntegrationRun(
            provider="agnes", product="visual-evidence", model=settings.agnes_model,
            status="fallback", fallback_reason="disabled_by_evidence_limit",
        )

    started = datetime.now(timezone.utc)
    # Agnes capacity is variable; serialize calls to avoid burst-driven 503s.
    semaphore = asyncio.Semaphore(1)
    selected = moments[: settings.agnes_max_evidence_moments]

    async def one(moment: EvidenceMoment) -> tuple[EvidenceMoment, IntegrationRun | None]:
        images = await asyncio.to_thread(prepare_evidence_images, moment, media, settings)
        if not images:
            return moment, IntegrationRun(
                provider="agnes", product="visual-evidence", model=settings.agnes_model,
                status="fallback", fallback_reason="frame_extraction_failed",
                metadata={"evidence_id": moment.id},
            )
        async with semaphore:
            moment_client = AgnesClient(settings)
            review = await moment_client.review(moment, images)
        assets: list[EvidenceFrame] = []
        for image in images:
            assets.append(EvidenceFrame(
                role="attempt", timestamp_seconds=image.timestamp_seconds,
                width=image.width, height=image.height, sha256=image.sha256,
            ))
            if image.reference_image:
                ref = image.reference_image
                assets.append(EvidenceFrame(
                    role="reference", timestamp_seconds=ref.timestamp_seconds,
                    width=ref.width, height=ref.height, sha256=ref.sha256,
                ))
        return moment.model_copy(update={"frame_assets": assets, "visual_review": review}), moment_client.last_run

    reviewed = await asyncio.gather(*(one(moment) for moment in selected))
    output = [item[0] for item in reviewed]
    runs = [item[1] for item in reviewed if item[1] is not None]
    completed = sum(run.status == "completed" for run in runs)
    if completed == len(output) and output:
        status, reason = "completed", None
    elif completed:
        status, reason = "fallback", "partial_visual_review"
    else:
        status, reason = "failed", "visual_review_unavailable"
    return output, IntegrationRun(
        provider="agnes", product="visual-evidence", model=settings.agnes_model,
        status=status, started_at=started, completed_at=datetime.now(timezone.utc),
        fallback_reason=reason,
        metadata={"selected_count": len(selected), "reviewed_count": completed},
    )
