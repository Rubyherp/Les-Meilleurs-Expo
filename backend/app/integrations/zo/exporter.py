"""Zo artifact exporter — builds a versioned compact artifact from a coaching report.

Omission rules:
- No API keys, credentials, or secrets
- No raw media (object_keys, buckets, frame images)
- No expiring URLs (presigned links, signed URLs)
- No full traces (trace_id, provider URLs, hostnames)
- Evidence is reduced to {timestamp, category, confidence} only
"""

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from app.integrations.models import IntegrationRun
from app.integrations.zo.models import (
    ZoEvidenceEntry,
    ZoExportArtifact,
)
from app.schemas.coaching import CoachingReport


def compute_idempotency_key(
    session_id: UUID,
    report_version: int,
    content: dict,
    artifact_version: int,
    visibility: str,
) -> str:
    """Derive a deterministic idempotency key.

    Compound of: session ID + report version + canonical JSON of content
    + artifact version + visibility.
    """
    ingredients = f"{session_id}|{report_version}|{_canonical_json(content)}|{artifact_version}|{visibility}"
    return hashlib.sha256(ingredients.encode("utf-8")).hexdigest()


def _canonical_json(obj: object) -> str:
    """Canonical JSON string with sorted keys for deterministic hashing."""
    return json.dumps(obj, sort_keys=True, default=str)


def build_zo_artifact(
    session_id: UUID,
    report: CoachingReport,
    *,
    visibility: str = "private",
    artifact_version: int = 1,
) -> ZoExportArtifact:
    """Build a versioned compact Zo artifact from a CoachingReport.

    Strips: secrets, raw frames, expiring URLs, full traces, provider URLs.
    Includes: session summary, next actions, evidence (timestamp/category/confidence),
    provider statuses, visibility, idempotency key.
    """
    # ── Summary ────────────────────────────────────────────────────────
    session_summary = report.overall_summary or ""

    # ── Next actions ────────────────────────────────────────────────────
    next_actions: list[str] = []
    for agent in (report.agents or []):
        next_actions.extend(agent.suggestions or [])

    # ── Compact evidence (timestamp, category, confidence only) ──────────
    evidence: list[ZoEvidenceEntry] = []
    for moment in (report.evidence_moments or []):
        evidence.append(ZoEvidenceEntry(
            timestamp_seconds=moment.primary_timestamp_seconds,
            category=moment.category,
            summary=(moment.visual_review.summary if moment.visual_review else moment.deterministic_reason),
            confidence=moment.confidence,
        ))

    # ── Provider statuses preserve truthful run outcomes ─────────────
    provider_statuses: dict[str, str] = {}
    for run in (report.integrations or []):
        key = run.provider
        provider_statuses[key] = run.status

    # ── Build content payload for idempotency key ────────────────────────
    content = {
        "summary": session_summary,
        "next_actions": sorted(next_actions),
        "evidence_count": len(evidence),
        "provider_statuses": dict(sorted(provider_statuses.items())),
    }

    idempotency_key = compute_idempotency_key(
        session_id=session_id,
        report_version=report.report_version,
        content=content,
        artifact_version=artifact_version,
        visibility=visibility,
    )

    now = datetime.now(timezone.utc)

    return ZoExportArtifact(
        artifact_version=artifact_version,
        session_id=session_id,
        session_summary=session_summary,
        next_actions=next_actions,
        evidence=evidence,
        provider_statuses=provider_statuses,
        visibility=visibility,
        created_at=now,
        idempotency_key=idempotency_key,
    )
