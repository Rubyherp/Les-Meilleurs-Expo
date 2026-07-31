"""GMI serverless inference client for independent coaching audits."""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.integrations.gmi.models import GmiAuditOutput
from app.integrations.models import EvidenceMoment, IntegrationRun
from app.schemas.coaching import CoachAgent, CoachIssue

if TYPE_CHECKING:
    from app.services.coaching.context import CoachingContext

_SYSTEM_PROMPT = """You are an independent evidence-grounding auditor for a
dance-practice coaching report. Use only the supplied aggregate machine
measurements, deterministic evidence descriptions, and draft coaching text.
Never claim that you watched the video. Do not identify anyone or infer health,
injury, emotion, age, gender, ethnicity, or overall skill level. Treat missing
or low-coverage measurements as limitations. Return one JSON object with
exactly these keys and types: summary (string), strengths (array of strings),
cautions (array of strings), suggestions (array of strings), and confidence
(number from 0 to 1). Keep every list to at most three short items."""


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


class GmiInferenceClient:
    def __init__(
        self, settings: Settings, http_client: httpx.AsyncClient | None = None
    ) -> None:
        self.settings = settings
        self._http_client = http_client

    @property
    def available(self) -> bool:
        return bool(
            self.settings.gmi_api_key
            and self.settings.gmi_base_url
            and self.settings.gmi_model
        )

    async def audit(
        self,
        context: CoachingContext,
        evidence: list[EvidenceMoment],
        draft_agents: list[CoachAgent],
        *,
        agent_id: int,
    ) -> tuple[CoachAgent | None, IntegrationRun]:
        model = self.settings.gmi_model
        if not self.available:
            return None, IntegrationRun(
                provider="gmi", product="serverless-inference-audit", model=model or None,
                status="not_configured", fallback_reason="missing_configuration",
            )

        started_at = datetime.now(timezone.utc)
        started = time.monotonic()
        client = self._http_client or httpx.AsyncClient(
            timeout=self.settings.gmi_timeout_seconds
        )
        close_client = self._http_client is None
        try:
            payload = {
                "measurements": asdict(context),
                "evidence": [
                    {
                        "id": item.id,
                        "category": item.category,
                        "severity": item.severity,
                        "reason": item.deterministic_reason,
                        "metrics": item.deterministic_metrics,
                    }
                    for item in evidence[:3]
                ],
                "draft_agents": [
                    {
                        "name": item.name,
                        "summary": item.summary,
                        "strengths": item.strengths[:3],
                        "suggestions": item.suggestions[:3],
                        "confidence": item.confidence,
                    }
                    for item in draft_agents
                ],
            }
            response = await client.post(
                self.settings.gmi_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.gmi_api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(payload, sort_keys=True)},
                    ],
                    "response_format": {"type": "json_object"},
                    "stream": False,
                },
            )
            response.raise_for_status()
            body = response.json()
            raw = body["choices"][0]["message"]["content"]
            output = GmiAuditOutput.model_validate(_decode_json(raw))
            usage = body.get("usage") or {}
            agent = CoachAgent(
                agent_id=agent_id,
                name="GMI Evidence Auditor",
                available=True,
                source="gmi",
                summary=output.summary,
                strengths=output.strengths,
                issues=[
                    CoachIssue(description=value, severity="low", category="grounding")
                    for value in output.cautions
                ],
                suggestions=output.suggestions,
                confidence=output.confidence,
            )
            return agent, IntegrationRun(
                provider="gmi",
                product="serverless-inference-audit",
                model=str(body.get("model") or model),
                status="completed",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                latency_ms=int((time.monotonic() - started) * 1000),
                request_id=str(body.get("id")) if body.get("id") else None,
                metadata={
                    "input_scope": "aggregate_measurements_and_draft_text",
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                },
            )
        except (
            httpx.HTTPError,
            KeyError,
            TypeError,
            json.JSONDecodeError,
            ValidationError,
        ) as exc:
            if isinstance(exc, httpx.HTTPStatusError):
                reason = f"http_{exc.response.status_code}"
            elif isinstance(exc, httpx.HTTPError):
                reason = "transport_error"
            elif isinstance(exc, ValidationError):
                reason = "invalid_audit_schema"
            else:
                reason = "malformed_response"
            return None, IntegrationRun(
                provider="gmi", product="serverless-inference-audit", model=model,
                status="failed", started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                latency_ms=int((time.monotonic() - started) * 1000),
                fallback_reason=reason,
            )
        finally:
            if close_client:
                await client.aclose()
