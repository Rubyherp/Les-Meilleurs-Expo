import json

import httpx
import pytest

from app.core.config import Settings
from app.integrations.gmi.client import GmiInferenceClient
from app.schemas.coaching import CoachAgent
from app.services.coaching.context import CoachingContext


def draft_agent() -> CoachAgent:
    return CoachAgent(
        agent_id=1,
        name="Observation Agent",
        available=True,
        source="deterministic",
        summary="Detection coverage is measurable.",
        confidence=0.8,
    )


@pytest.mark.asyncio
async def test_missing_gmi_inference_key_is_not_configured():
    agent, run = await GmiInferenceClient(Settings(gmi_api_key="")).audit(
        CoachingContext(), [], [draft_agent()], agent_id=2
    )
    assert agent is None
    assert run.status == "not_configured"
    assert run.product == "serverless-inference-audit"


@pytest.mark.asyncio
async def test_gmi_inference_returns_grounded_auditor():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        payload = json.loads(request.content)
        assert payload["model"] == "openai/gpt-5.4-nano"
        assert payload["response_format"] == {"type": "json_object"}
        serialized = json.dumps(payload)
        assert "image_url" not in serialized
        assert "object_key" not in serialized
        return httpx.Response(200, json={
            "id": "chatcmpl-gmi-test",
            "model": "openai/gpt-5.4-nano",
            "choices": [{"message": {"content": """```json
{"summary":"The draft matches the supplied coverage metrics.","strengths":["Coverage is quantified."],"cautions":["No direct visual review was supplied."],"suggestions":["Keep framing consistent."],"confidence":0.82}
```"""}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 40},
        })

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        gmi_api_key="gmi-test",
        gmi_base_url="https://api.gmi-serving.com/v1",
        gmi_model="openai/gpt-5.4-nano",
    )
    agent, run = await GmiInferenceClient(settings, http).audit(
        CoachingContext(), [], [draft_agent()], agent_id=2
    )
    await http.aclose()

    assert agent is not None
    assert agent.name == "GMI Evidence Auditor"
    assert agent.source == "gmi"
    assert run.status == "completed"
    assert run.request_id == "chatcmpl-gmi-test"
    assert run.metadata["completion_tokens"] == 40


@pytest.mark.asyncio
async def test_gmi_failure_is_sanitized_and_fallback_safe():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="provider-secret-body")

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(gmi_api_key="gmi-test")
    agent, run = await GmiInferenceClient(settings, http).audit(
        CoachingContext(), [], [draft_agent()], agent_id=2
    )
    await http.aclose()

    assert agent is None
    assert run.status == "failed"
    assert run.fallback_reason == "http_503"
    assert "provider-secret-body" not in str(run.model_dump())
