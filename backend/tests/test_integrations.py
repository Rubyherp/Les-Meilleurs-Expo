"""Tests for shared integration contracts — models, health, and schema extensions."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

# When models exist, imports will succeed.
# Before implementation, these imports fail (expected in TDD Step 2).
from app.core.config import Settings
from app.integrations.health import get_integration_health
from app.integrations.models import (
    EvidenceFrame,
    EvidenceMoment,
    IntegrationHealth,
    IntegrationRun,
    VisualReview,
)
from app.schemas.coaching import CoachingReport


# ── Helpers ───────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def legacy_report_payload():
    """Payload matching the pre-integration CoachingReport schema (version 3)."""
    return {
        "session_id": str(uuid4()),
        "report_version": 3,
        "mode": "single",
        "practice_type": "solo",
        "overall_summary": "Good job",
        "agents": [
            {
                "agent_id": 1,
                "name": "Observation Agent",
                "available": True,
                "source": "deterministic",
                "summary": "All clear",
                "strengths": [],
                "issues": [],
                "suggestions": [],
                "evidence": [],
                "confidence": 0.9,
            }
        ],
        "coordination_notes": [],
        "generated_at": _now().isoformat(),
    }


# ── IntegrationRun contract ───────────────────────────────────────────────

def test_integration_run_rejects_invalid_status():
    """Only literal status values are accepted."""
    with pytest.raises(ValidationError):
        IntegrationRun(provider="agnes", product="vision", status="done")  # not a valid status


def test_integration_run_valid_pending():
    run = IntegrationRun(provider="agnes", product="vision", status="pending")
    assert run.status == "pending"


def test_integration_run_valid_completed():
    run = IntegrationRun(provider="agnes", product="vision", status="completed")
    assert run.status == "completed"


def test_integration_run_valid_failed():
    run = IntegrationRun(provider="agnes", product="vision", status="failed")
    assert run.status == "failed"


def test_integration_run_valid_not_configured():
    run = IntegrationRun(provider="agnes", product="vision", status="not_configured")
    assert run.status == "not_configured"


def test_integration_run_valid_running_and_fallback():
    assert IntegrationRun(provider="openai", product="agents", status="running").status == "running"
    run = IntegrationRun(provider="agnes", product="vision", status="fallback", fallback_reason="timeout")
    assert run.fallback_reason == "timeout"


def test_integration_run_requires_provider():
    with pytest.raises(ValidationError):
        IntegrationRun(product="vision", status="pending")


def test_integration_run_accepts_openai_provider():
    run = IntegrationRun(provider="openai", product="llm", status="completed")
    assert run.provider == "openai"


def test_integration_run_rejects_agl_provider():
    """'agl' was a typo in the original implementation — must be rejected."""
    with pytest.raises(ValidationError):
        IntegrationRun(provider="agl", product="vision", status="pending")


def test_integration_run_timestamps_non_negative():
    now = _now()
    good = IntegrationRun(provider="agnes", product="vision", status="completed", started_at=now, finished_at=now)
    assert good.started_at == now
    assert good.finished_at == now

    # Negative Unix seconds is nonsensical
    with pytest.raises(ValidationError):
        IntegrationRun(provider="agnes", product="vision", status="completed", started_at=datetime(1969, 1, 1, tzinfo=timezone.utc))


def test_integration_run_metadata_dict():
    run = IntegrationRun(provider="zo", product="export", status="completed", metadata={"export_id": "abc123"})
    assert run.metadata == {"export_id": "abc123"}

    # Default metadata should be empty dict
    run2 = IntegrationRun(provider="zo", product="export", status="pending")
    assert run2.metadata == {}


# ── EvidenceMoment contract ────────────────────────────────────────────────

def test_evidence_moment_valid():
    now = _now()
    moment = EvidenceMoment(
        category="timing",
        severity="medium",
        description="Slight delay detected",
        timestamp=now,
        confidence=0.85,
        frames=[EvidenceFrame(seconds=1.0, annotation="off-beat")],
    )
    assert moment.category == "timing"
    assert moment.severity == "medium"
    assert len(moment.frames) == 1
    assert moment.confidence == 0.85


def test_evidence_moment_invalid_category():
    with pytest.raises(ValidationError):
        EvidenceMoment(category="unknown_cat", severity="low", description="x", timestamp=_now())


def test_evidence_moment_invalid_severity():
    with pytest.raises(ValidationError):
        EvidenceMoment(category="formation", severity="critical", description="x", timestamp=_now())


def test_evidence_moment_invalid_confidence_high():
    with pytest.raises(ValidationError):
        EvidenceMoment(category="timing", severity="low", description="x", timestamp=_now(), confidence=1.5)


def test_evidence_moment_invalid_confidence_negative():
    with pytest.raises(ValidationError):
        EvidenceMoment(category="timing", severity="low", description="x", timestamp=_now(), confidence=-0.1)


def test_evidence_moment_timestamp_non_negative():
    with pytest.raises(ValidationError):
        EvidenceMoment(category="timing", severity="low", description="x", timestamp=datetime(1969, 1, 1, tzinfo=timezone.utc))


def test_evidence_moment_default_frames():
    moment = EvidenceMoment(category="timing", severity="low", description="x", timestamp=_now())
    assert moment.frames == []
    assert moment.visual_review is None


# ── EvidenceFrame contract ─────────────────────────────────────────────────

def test_evidence_frame_valid():
    frame = EvidenceFrame(seconds=2.5, annotation="misalignment at peak")
    assert frame.seconds == 2.5
    assert frame.annotation == "misalignment at peak"


def test_evidence_frame_rejects_negative_seconds():
    with pytest.raises(ValidationError):
        EvidenceFrame(seconds=-0.1, annotation="bad")


def test_evidence_frame_default_empty_string():
    frame = EvidenceFrame(seconds=0.0)
    assert frame.annotation == ""


# ── VisualReview contract ──────────────────────────────────────────────────

def test_visual_review_valid():
    now = _now()
    review = VisualReview(
        provider="agnes",
        image_url="https://example.com/frame.jpg",
        caption="Dancer positions look good",
        confidence=0.92,
        generated_at=now,
    )
    assert review.provider == "agnes"
    assert review.caption == "Dancer positions look good"
    assert review.confidence == 0.92


def test_visual_review_rejects_invalid_confidence():
    with pytest.raises(ValidationError):
        VisualReview(provider="agnes", image_url="https://example.com/f.jpg", caption="test", confidence=2.0, generated_at=_now())


# ── IntegrationHealth contract ─────────────────────────────────────────────

def test_integration_health_all_not_configured():
    health = IntegrationHealth()
    assert health.overall == "not_configured"
    assert health.providers == {}
    assert "no providers configured" in health.message.lower()


def test_integration_health_with_providers():
    health = IntegrationHealth(
        overall="partial",
        providers={"agnes": "configured", "zo": "not_configured"},
        message="1 of 2 providers active",
    )
    assert health.overall == "partial"
    assert health.providers["agnes"] == "configured"
    assert health.providers["zo"] == "not_configured"


def test_integration_health_rejects_invalid_overall():
    with pytest.raises(ValidationError):
        IntegrationHealth(overall="broken")


# ── get_integration_health direct tests ──────────────────────────────────

def test_get_integration_health_all_empty():
    """All keys empty → all not_configured, overall not_configured."""
    settings = Settings(
        openai_api_key="",
        agnes_api_key="",
        zo_api_key="",
        gmi_enabled=False,
    )
    health = get_integration_health(settings)
    assert health.overall == "not_configured"
    assert health.providers["openai"] == "not_configured"
    assert health.providers["agnes"] == "not_configured"
    assert health.providers["zo"] == "not_configured"
    assert health.providers["gmi"] == "not_configured"
    assert "no providers configured" in health.message.lower()


def test_get_integration_health_all_configured():
    """All keys set → all configured, overall healthy."""
    settings = Settings(
        openai_api_key="sk-test",
        agnes_api_key="ak-test",
        zo_api_key="zk-test",
        gmi_enabled=True,
    )
    health = get_integration_health(settings)
    assert health.overall == "healthy"
    assert health.providers["openai"] == "configured"
    assert health.providers["agnes"] == "configured"
    assert health.providers["zo"] == "configured"
    assert health.providers["gmi"] == "configured"
    assert "all 4 providers configured" in health.message.lower()


def test_get_integration_health_partial():
    """Three configured → partial (≥ half)."""
    settings = Settings(
        openai_api_key="sk-test",
        agnes_api_key="ak-test",
        zo_api_key="zk-test",
        gmi_enabled=False,
    )
    health = get_integration_health(settings)
    assert health.overall == "partial"
    assert health.providers["openai"] == "configured"
    assert health.providers["agnes"] == "configured"
    assert health.providers["zo"] == "configured"
    assert health.providers["gmi"] == "not_configured"
    assert "3 of 4" in health.message


def test_gmi_inference_key_configures_gmi_without_gpu_compute():
    settings = Settings(
        openai_api_key="", agnes_api_key="", zo_api_key="",
        gmi_api_key="gmi-test", gmi_enabled=False,
    )
    health = get_integration_health(settings)
    assert health.providers["gmi"] == "configured"


def test_get_integration_health_degraded():
    """One configured → degraded (< half)."""
    settings = Settings(
        openai_api_key="sk-test",
        agnes_api_key="",
        zo_api_key="",
        gmi_enabled=False,
    )
    health = get_integration_health(settings)
    assert health.overall == "degraded"
    assert health.providers["openai"] == "configured"
    assert health.providers["agnes"] == "not_configured"
    assert health.providers["zo"] == "not_configured"
    assert health.providers["gmi"] == "not_configured"
    assert "only 1 of 4" in health.message.lower()


def test_get_integration_health_status_transitions():
    """Adding keys one at a time transitions through the correct states."""
    # Start: nothing configured
    s0 = Settings(openai_api_key="", agnes_api_key="", zo_api_key="", gmi_enabled=False)
    assert get_integration_health(s0).overall == "not_configured"

    # One configured → degraded
    s1 = Settings(openai_api_key="sk-test", agnes_api_key="", zo_api_key="", gmi_enabled=False)
    assert get_integration_health(s1).overall == "degraded"

    # Two configured → partial (exactly half)
    s2 = Settings(openai_api_key="sk-test", agnes_api_key="ak-test", zo_api_key="", gmi_enabled=False)
    assert get_integration_health(s2).overall == "partial"

    # Three → partial
    s3 = Settings(openai_api_key="sk-test", agnes_api_key="ak-test", zo_api_key="zk-test", gmi_enabled=False)
    assert get_integration_health(s3).overall == "partial"

    # Four → healthy
    s4 = Settings(openai_api_key="sk-test", agnes_api_key="ak-test", zo_api_key="zk-test", gmi_enabled=True)
    assert get_integration_health(s4).overall == "healthy"


def test_get_integration_health_no_secrets_exposed():
    """Health output must not contain API keys or raw URLs."""
    settings = Settings(
        openai_api_key="sk-secret-key-do-not-leak",
        agnes_api_key="ak-super-secret",
        zo_api_key="zk-another-secret",
        zo_api_url="https://zo.example.com/v1",
        agnes_base_url="https://agnes.internal:8443/api",
        gmi_enabled=True,
        gmi_region="us-central1",
        gmi_instance_label="prod-worker",
    )
    health = get_integration_health(settings)
    # Serialise to check all string fields
    data = health.model_dump()
    all_text = str(data)
    # Secrets must not appear
    assert "sk-secret-key-do-not-leak" not in all_text
    assert "ak-super-secret" not in all_text
    assert "zk-another-secret" not in all_text
    # URLs must not appear
    assert "zo.example.com" not in all_text
    assert "agnes.internal" not in all_text
    # Non-secret hostnames/regions must not appear either (conservative)
    assert "8443" not in all_text


def test_get_integration_health_default_settings():
    """Default Settings() yields consistent not_configured health."""
    health = get_integration_health(Settings())
    assert health.overall in ("healthy", "partial", "degraded", "not_configured")
    # providers dict must have all four keys
    assert set(health.providers.keys()) == {"openai", "agnes", "zo", "gmi"}
    for state in health.providers.values():
        assert state in ("configured", "not_configured")


# ── CoachingReport backward compat ─────────────────────────────────────────

def test_legacy_report_defaults_new_fields():
    """Legacy CoachingReport (version 3, no new fields provided) gets empty defaults."""
    report = CoachingReport(**legacy_report_payload())
    assert report.evidence_moments == []
    assert report.integrations == []
    assert report.trace_id is None


def test_coaching_report_with_new_fields():
    """CoachingReport accepts new optional fields."""
    now = _now()
    payload = legacy_report_payload()
    payload["report_version"] = 4
    payload["evidence_moments"] = [
        {
            "category": "timing",
            "severity": "low",
            "description": "minor drift",
            "timestamp": now.isoformat(),
            "confidence": 0.7,
            "frames": [{"seconds": 1.0, "annotation": "test"}],
        }
    ]
    payload["integrations"] = [
        {
            "provider": "agnes",
            "product": "vision",
            "status": "completed",
            "started_at": now.isoformat(),
            "finished_at": now.isoformat(),
        }
    ]
    payload["trace_id"] = str(uuid4())

    report = CoachingReport(**payload)
    assert report.report_version == 4
    assert len(report.evidence_moments) == 1
    assert report.evidence_moments[0].category == "timing"
    assert len(report.integrations) == 1
    assert report.integrations[0].provider == "agnes"
    assert report.trace_id is not None
