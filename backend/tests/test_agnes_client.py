import json

import httpx
import pytest

from app.core.config import Settings
from app.integrations.agnes.client import AgnesClient
from app.integrations.models import EvidenceMoment
from app.services.evidence.models import PreparedEvidenceImage


def moment():
    return EvidenceMoment(
        id="ev_test", start_seconds=1.0, end_seconds=2.0,
        primary_timestamp_seconds=1.5, category="observation", severity="medium",
        deterministic_reason="visibility_loss=0.5",
        deterministic_metrics={"visibility_loss": 0.5},
    )


def image():
    return PreparedEvidenceImage(
        image_bytes=b"jpeg", sha256="a" * 64, width=100, height=80,
        timestamp_seconds=1.5,
    )


def settings(**overrides):
    values = dict(
        agnes_api_key="test-key", agnes_base_url="https://example.test/v1",
        agnes_model="agnes-2.5-flash",
    )
    values.update(overrides)
    return Settings(**values)


@pytest.mark.asyncio
async def test_missing_configuration_is_truthful():
    client = AgnesClient(settings(agnes_api_key=""))
    assert await client.review(moment(), [image()]) is None
    assert client.last_run.status == "not_configured"


@pytest.mark.asyncio
async def test_valid_structured_review_uses_derived_image_only():
    async def handler(request):
        payload = json.loads(request.content)
        content = payload["messages"][1]["content"]
        assert any(item.get("image_url", {}).get("url", "").startswith("data:image/jpeg;base64,") for item in content)
        return httpx.Response(200, headers={"x-request-id": "req_1"}, json={
            "choices": [{"message": {"content": json.dumps({
                "summary": "The dancer is partly outside the frame.",
                "visible_differences": ["The right arm is cropped."],
                "limitations": ["Timing cannot be assessed from this still."],
                "confidence": 0.8,
            })}}]
        })
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AgnesClient(settings(), http)
    review = await client.review(moment(), [image()])
    await http.aclose()
    assert review is not None
    assert review.confidence == 0.8
    assert client.last_run.status == "completed"
    assert client.last_run.request_id == "req_1"


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["not-json", '{"summary":"","confidence":2}', '{"summary":"She looks injured","confidence":0.8}'])
async def test_invalid_or_prohibited_output_falls_back(content):
    async def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AgnesClient(settings(), http)
    assert await client.review(moment(), [image()]) is None
    await http.aclose()
    assert client.last_run.status == "failed"
    assert client.last_run.fallback_reason
