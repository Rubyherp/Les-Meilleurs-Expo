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
        assert payload["chat_template_kwargs"] == {"enable_thinking": False}
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
async def test_markdown_fenced_json_is_accepted():
    async def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": """```json
{"summary":"The frame is usable.","visible_differences":[],"limitations":["Timing is not visible."],"confidence":0.7}
```"""}}]})
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AgnesClient(settings(), http)
    review = await client.review(moment(), [image()])
    await http.aclose()
    assert review is not None
    assert client.last_run.status == "completed"


@pytest.mark.asyncio
async def test_json_object_wrapped_in_model_text_is_accepted():
    async def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": """Review result:
{"summary":"The frame is usable.","visible_differences":[],"limitations":["Timing is not visible."],"confidence":0.7}
End of review."""}}]})
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AgnesClient(settings(), http)
    review = await client.review(moment(), [image()])
    await http.aclose()
    assert review is not None
    assert client.last_run.status == "completed"


@pytest.mark.asyncio
async def test_compatible_agnes_field_names_are_normalized():
    async def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
            "visual_summary": "The full body is visible.",
            "observations": [{"description": "The right arm is raised."}],
            "caveats": "Timing cannot be assessed from a still.",
            "confidence_score": "78%",
        })}}]})
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AgnesClient(settings(), http)
    review = await client.review(moment(), [image()])
    await http.aclose()
    assert review is not None
    assert review.summary == "The full body is visible."
    assert review.visible_differences == ["The right arm is raised."]
    assert review.confidence == 0.78
    assert client.last_run.status == "completed"


@pytest.mark.asyncio
async def test_retryable_primary_failure_uses_compatibility_model():
    requested_models = []

    async def handler(request):
        payload = json.loads(request.content)
        requested_models.append(payload["model"])
        if len(requested_models) == 1:
            return httpx.Response(503, headers={"retry-after": "0"})
        return httpx.Response(200, headers={"x-request-id": "req_fallback"}, json={
            "model": "agnes-2.0-flash",
            "choices": [{"message": {"content": json.dumps({
                "summary": "The frame is usable for a bounded review.",
                "visible_differences": [],
                "limitations": ["Timing is not visible."],
                "confidence": 0.75,
            })}}],
        })

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AgnesClient(settings(
        agnes_fallback_model="agnes-2.0-flash",
        agnes_max_retries=1,
        agnes_retry_base_seconds=0,
    ), http)
    review = await client.review(moment(), [image()])
    await http.aclose()

    assert review is not None
    assert requested_models == ["agnes-2.5-flash", "agnes-2.0-flash"]
    assert client.last_run.status == "completed"
    assert client.last_run.model == "agnes-2.0-flash"
    assert client.last_run.metadata["fallback_model_used"] is True
    assert client.last_run.metadata["attempt_count"] == 2


@pytest.mark.asyncio
async def test_sensitive_topic_disclaimer_is_allowed_as_limitation():
    async def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
            "summary": "Only visible posture can be described.",
            "visible_differences": [],
            "limitations": ["Injury cannot be inferred from this frame."],
            "confidence": 0.6,
        })}}]})
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = AgnesClient(settings(), http)
    review = await client.review(moment(), [image()])
    await http.aclose()
    assert review is not None
    assert client.last_run.status == "completed"


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
