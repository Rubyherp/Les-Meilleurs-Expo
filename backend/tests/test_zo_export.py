import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.integrations.models import EvidenceMoment, IntegrationRun
from app.integrations.zo.client import ZoClient
from app.integrations.zo.exporter import build_zo_artifact
from app.integrations.zo.models import ZoExportRequest
from app.schemas.coaching import CoachAgent, CoachingReport


def report():
    return CoachingReport(
        session_id=uuid4(), mode="single", overall_summary="Good practice.",
        agents=[CoachAgent(agent_id=1, name="Observation", available=True,
            source="deterministic", summary="Visible.", suggestions=["Keep framing wide."], confidence=.8)],
        generated_at=datetime.now(timezone.utc),
        evidence_moments=[EvidenceMoment(
            id="ev_1", start_seconds=1, end_seconds=2, primary_timestamp_seconds=1.5,
            category="observation", severity="medium", deterministic_reason="visibility_loss=.4",
            deterministic_metrics={"visibility_loss": .4}, legacy_confidence=.7,
        )],
        integrations=[IntegrationRun(provider="openai", product="agents", status="fallback")],
    )


def test_artifact_is_compact_truthful_and_idempotent():
    value = report()
    first = build_zo_artifact(value.session_id, value)
    second = build_zo_artifact(value.session_id, value)
    assert first.idempotency_key == second.idempotency_key
    assert first.evidence[0].timestamp_seconds == 1.5
    assert first.provider_statuses == {"openai": "fallback"}
    serialized = json.dumps(first.model_dump(mode="json"))
    for forbidden in ("api_key", "object_key", "trace_id", "image_url"):
        assert forbidden not in serialized


def test_public_visibility_rejected():
    with pytest.raises(ValidationError):
        ZoExportRequest(visibility="public")


def test_reminder_requires_time_and_timezone():
    with pytest.raises(ValidationError):
        ZoExportRequest(schedule_reminder=True)


@pytest.mark.asyncio
async def test_missing_key_is_not_configured():
    value = report()
    artifact = build_zo_artifact(value.session_id, value)
    response = await ZoClient(Settings(zo_api_key="")).export_to_zo(value.session_id, artifact)
    assert response.status == "not_configured"
    assert response.integration.status == "not_configured"


@pytest.mark.asyncio
async def test_documented_ask_endpoint_confirms_save():
    calls = []
    async def handler(request):
        calls.append(request)
        assert request.url.path == "/zo/ask"
        payload = json.loads(request.content)
        assert payload["output_format"]
        return httpx.Response(200, json={"output": {
            "saved": True, "export_id": "report-1", "url": None, "message": "Saved"
        }, "conversation_id": "conv-1"})
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    value = report()
    artifact = build_zo_artifact(value.session_id, value)
    response = await ZoClient(Settings(zo_api_key="test"), http).export_to_zo(value.session_id, artifact)
    await http.aclose()
    assert response.status == "completed"
    assert response.export_id == "report-1"
    assert response.integration.request_id == "conv-1"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_full_ask_endpoint_is_not_appended_twice():
    async def handler(request):
        assert request.url.path == "/zo/ask"
        return httpx.Response(200, json={"output": {
            "saved": True, "export_id": "report-1", "url": None, "message": "Saved"
        }, "conversation_id": "conv-1"})
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    value = report()
    artifact = build_zo_artifact(value.session_id, value)
    client = ZoClient(Settings(
        zo_api_key="test", zo_api_url="https://api.zo.computer/zo/ask"
    ), http)
    response = await client.export_to_zo(value.session_id, artifact)
    await http.aclose()
    assert response.status == "completed"


@pytest.mark.asyncio
async def test_unconfirmed_save_fails_without_leaking_body():
    async def handler(request):
        return httpx.Response(500, text="provider-secret-body")
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    value = report()
    artifact = build_zo_artifact(value.session_id, value)
    response = await ZoClient(Settings(zo_api_key="test"), http).export_to_zo(value.session_id, artifact)
    await http.aclose()
    assert response.status == "failed"
    assert "provider-secret-body" not in response.message


@pytest.mark.asyncio
async def test_reminder_is_only_created_when_explicit():
    count = 0
    async def handler(request):
        nonlocal count
        count += 1
        if count == 1:
            output = {"saved": True, "export_id": "report-1", "url": None, "message": "Saved"}
        else:
            output = {"created": True, "reminder_id": "rem-1"}
        return httpx.Response(200, json={"output": output, "conversation_id": f"conv-{count}"})
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    value = report()
    artifact = build_zo_artifact(value.session_id, value)
    request = ZoExportRequest(
        schedule_reminder=True, reminder_at=datetime.now(timezone.utc) + timedelta(days=1),
        timezone="Asia/Singapore",
    )
    response = await ZoClient(Settings(zo_api_key="test"), http).export_to_zo(value.session_id, artifact, request)
    await http.aclose()
    assert count == 2
    assert response.status == "completed"
    assert response.reminder_id == "rem-1"
