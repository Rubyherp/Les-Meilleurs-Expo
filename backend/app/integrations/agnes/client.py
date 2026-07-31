"""OpenAI-compatible Agnes adapter that sends only bounded derived frames."""

from __future__ import annotations

import base64
import json
import re
import time
from typing import Protocol

import httpx
from pydantic import ValidationError

from app.core.config import Settings
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

_PROHIBITED = re.compile(
    r"\b(identity|identified as|diagnos(?:e|is)|injur(?:y|ed)|emotion|angry|sad|"
    r"gender|ethnicity|race|pregnan|disabled|medical condition|age is)\b",
    re.IGNORECASE,
)


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
        try:
            response = await client.post(
                self.settings.agnes_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.agnes_api_key}"},
                json={
                    "model": self.settings.agnes_model,
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": self._content(moment, images)},
                    ],
                },
            )
            response.raise_for_status()
            request_id = response.headers.get("x-request-id")
            raw = response.json()["choices"][0]["message"]["content"]
            parsed = AgnesStructuredReview.model_validate(json.loads(raw))
            combined = " ".join(
                [parsed.summary, *parsed.visible_differences, *parsed.limitations]
            )
            if _PROHIBITED.search(combined):
                raise ValueError("prohibited_claim")
            review = VisualReview(
                summary=parsed.summary,
                visible_differences=parsed.visible_differences,
                limitations=parsed.limitations,
                confidence=parsed.confidence,
                model=self.settings.agnes_model,
            )
            self.last_run = IntegrationRun(
                provider="agnes", product="visual-evidence", model=self.settings.agnes_model,
                status="completed", latency_ms=int((time.monotonic() - started) * 1000),
                request_id=request_id, metadata={"evidence_id": moment.id, "image_count": len(images)},
            )
            return review
        except (httpx.HTTPError, KeyError, TypeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            if str(exc) == "prohibited_claim":
                reason = "prohibited_claim"
            elif isinstance(exc, httpx.HTTPStatusError):
                reason = f"http_{exc.response.status_code}"
            elif isinstance(exc, httpx.HTTPError):
                reason = "transport_error"
            elif isinstance(exc, json.JSONDecodeError):
                reason = "invalid_model_json"
            elif isinstance(exc, ValidationError):
                reason = "invalid_review_schema"
            else:
                reason = "malformed_response"
            self.last_run = IntegrationRun(
                provider="agnes", product="visual-evidence", model=self.settings.agnes_model,
                status="failed", latency_ms=int((time.monotonic() - started) * 1000),
                fallback_reason=reason,
            )
            return None
        finally:
            if close_client:
                await client.aclose()

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
