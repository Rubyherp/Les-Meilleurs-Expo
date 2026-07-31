"""OpenAI-compatible Agnes adapter that sends only bounded derived frames."""

from __future__ import annotations

import asyncio
import base64
import json
import random
import re
import time
from typing import Protocol

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logger import logger
from app.integrations.agnes.models import AgnesStructuredReview
from app.integrations.models import EvidenceMoment, IntegrationRun, VisualReview
from app.services.evidence.models import PreparedEvidenceImage

_SYSTEM_PROMPT = """You review dance-practice evidence frames. Use only what is
visibly supported by the supplied image or image pair and measurement context.
Do not identify people or infer health, injury, emotion, age, gender, ethnicity,
or skill level. Do not claim to measure timing from a still image. If anything
is occluded, state that it is unverifiable. Return JSON with summary,
visible_differences, limitations, and confidence. Keep the summary under two
sentences."""

_SENSITIVE = re.compile(
    r"\b(identity|identified as|diagnos(?:e|is)|injur(?:y|ed)|emotion|angry|sad|"
    r"gender|ethnicity|race|pregnan|disabled|medical condition|age is)\b",
    re.IGNORECASE,
)
_SAFE_LIMITATION = re.compile(
    r"\b(cannot|can't|should not|not possible|unable to)\b.{0,40}\b"
    r"(infer\w*|determin\w*|assess\w*|verif\w*|identif\w*|diagnos\w*)\b|"
    r"\b(unverifiable|unknown)\b",
    re.IGNORECASE,
)
_RETRYABLE_STATUS = {429, 500, 502, 503, 520}


class _AttemptError(Exception):
    def __init__(
        self, reason: str, *, retryable: bool, retry_after: float | None = None
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable
        self.retry_after = retry_after


def _decode_json(raw: str) -> dict:
    value = raw.strip()
    if value.startswith("```") and value.endswith("```"):
        value = value[3:-3].strip()
        if value.lower().startswith("json"):
            value = value[4:].lstrip()
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        start = value.find("{")
        if start < 0:
            raise
        decoded, _ = json.JSONDecoder().raw_decode(value[start:])
    if not isinstance(decoded, dict):
        raise TypeError("expected_object")
    return decoded


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(0.0, min(5.0, float(value)))
    except ValueError:
        return None


def _contains_prohibited_claim(parts: list[str]) -> bool:
    for part in parts:
        if _SENSITIVE.search(part) and not _SAFE_LIMITATION.search(part):
            return True
    return False


class VisualEvidenceProvider(Protocol):
    @property
    def available(self) -> bool: ...

    async def review(
        self, moment: EvidenceMoment, images: list[PreparedEvidenceImage]
    ) -> VisualReview | None: ...


class AgnesClient:
    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._http_client = http_client
        self.last_run: IntegrationRun | None = None

    @property
    def available(self) -> bool:
        return bool(
            self.settings.agnes_api_key
            and self.settings.agnes_base_url
            and self.settings.agnes_model
        )

    async def review(
        self, moment: EvidenceMoment, images: list[PreparedEvidenceImage]
    ) -> VisualReview | None:
        started = time.monotonic()
        if not self.available:
            self.last_run = IntegrationRun(
                provider="agnes", product="visual-evidence", model=self.settings.agnes_model or None,
                status="not_configured", fallback_reason="missing_configuration",
            )
            return None
        if not images:
            self.last_run = IntegrationRun(
                provider="agnes", product="visual-evidence", model=self.settings.agnes_model,
                status="fallback", fallback_reason="no_prepared_images",
            )
            return None

        client = self._http_client or httpx.AsyncClient(
            timeout=self.settings.agnes_timeout_seconds
        )
        close_client = self._http_client is None
        attempted_models: list[str] = []
        last_error = _AttemptError("request_not_attempted", retryable=False)
        try:
            for attempt in range(self.settings.agnes_max_retries + 1):
                model = self.settings.agnes_model
                if attempt > 0 and self.settings.agnes_fallback_model:
                    model = self.settings.agnes_fallback_model
                attempted_models.append(model)
                try:
                    review, request_id, served_model = await self._request(
                        client, moment, images, model
                    )
                    self.last_run = IntegrationRun(
                        provider="agnes", product="visual-evidence", model=served_model,
                        status="completed",
                        latency_ms=int((time.monotonic() - started) * 1000),
                        request_id=request_id,
                        metadata={
                            "evidence_id": moment.id,
                            "image_count": len(images),
                            "attempt_count": len(attempted_models),
                            "attempted_models": attempted_models,
                            "fallback_model_used": model != self.settings.agnes_model,
                        },
                    )
                    return review
                except _AttemptError as exc:
                    last_error = exc
                    if not exc.retryable or attempt >= self.settings.agnes_max_retries:
                        break
                    base = self.settings.agnes_retry_base_seconds * (2 ** attempt)
                    delay = exc.retry_after if exc.retry_after is not None else base
                    delay += random.uniform(0.0, base * 0.25)
                    if delay > 0:
                        await asyncio.sleep(min(5.0, delay))

            self.last_run = IntegrationRun(
                provider="agnes", product="visual-evidence",
                model=attempted_models[-1] if attempted_models else self.settings.agnes_model,
                status="failed", latency_ms=int((time.monotonic() - started) * 1000),
                fallback_reason=last_error.reason,
                metadata={
                    "evidence_id": moment.id,
                    "image_count": len(images),
                    "attempt_count": len(attempted_models),
                    "attempted_models": attempted_models,
                },
            )
            return None
        finally:
            if close_client:
                await client.aclose()

    async def _request(
        self,
        client: httpx.AsyncClient,
        moment: EvidenceMoment,
        images: list[PreparedEvidenceImage],
        model: str,
    ) -> tuple[VisualReview, str | None, str]:
        try:
            response = await client.post(
                self.settings.agnes_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.agnes_api_key}"},
                json={
                    "model": model,
                    "temperature": 0.1,
                    "max_tokens": self.settings.agnes_max_output_tokens,
                    "chat_template_kwargs": {"enable_thinking": False},
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": self._content(moment, images)},
                    ],
                },
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            raise _AttemptError(
                f"http_{status}", retryable=status in _RETRYABLE_STATUS,
                retry_after=_retry_after_seconds(exc.response),
            ) from None
        except httpx.HTTPError:
            raise _AttemptError("transport_error", retryable=True) from None

        try:
            body = response.json()
            raw = body["choices"][0]["message"]["content"]
            if not isinstance(raw, str):
                raise TypeError("content_not_string")
            parsed = AgnesStructuredReview.model_validate(_decode_json(raw))
        except json.JSONDecodeError as exc:
            logger.task(
                "agnes",
                "invalid model JSON "
                f"length={len(raw)} has_object={'{' in raw and '}' in raw} "
                f"finish_reason={body.get('choices', [{}])[0].get('finish_reason')} "
                f"error={exc.msg}@{exc.pos}",
            )
            raise _AttemptError("invalid_model_json", retryable=True) from None
        except ValidationError:
            raise _AttemptError("invalid_review_schema", retryable=True) from None
        except (KeyError, IndexError, TypeError):
            raise _AttemptError("malformed_response", retryable=True) from None

        if _contains_prohibited_claim(
            [parsed.summary, *parsed.visible_differences, *parsed.limitations]
        ):
            raise _AttemptError("prohibited_claim", retryable=False)
        served_model = str(body.get("model") or model)
        request_id = response.headers.get("x-request-id") or body.get("id")
        return VisualReview(
            summary=parsed.summary,
            visible_differences=parsed.visible_differences,
            limitations=parsed.limitations,
            confidence=parsed.confidence,
            model=served_model,
        ), str(request_id) if request_id is not None else None, served_model

    @staticmethod
    def _content(moment: EvidenceMoment, images: list[PreparedEvidenceImage]) -> list[dict]:
        content: list[dict] = [{
            "type": "text",
            "text": json.dumps({
                "evidence_id": moment.id,
                "category": moment.category,
                "timestamp_seconds": moment.primary_timestamp_seconds,
                "deterministic_reason": moment.deterministic_reason,
                "deterministic_metrics": moment.deterministic_metrics,
            }, sort_keys=True),
        }]
        for image in images:
            candidates = [("attempt", image)]
            if image.reference_image:
                candidates.insert(0, ("reference", image.reference_image))
            for role, candidate in candidates:
                encoded = base64.b64encode(candidate.image_bytes).decode("ascii")
                content.append({"type": "text", "text": f"{role} frame"})
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{encoded}", "detail": "low"},
                })
        return content
