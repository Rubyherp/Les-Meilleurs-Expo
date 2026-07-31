"""Zo Computer `/zo/ask` client with explicit, isolated reminder creation."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from uuid import UUID

import httpx

from app.core.config import Settings
from app.integrations.models import IntegrationRun
from app.integrations.zo.models import ZoExportArtifact, ZoExportRequest, ZoExportResponse

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "saved": {"type": "boolean"},
        "export_id": {"type": "string"},
        "url": {"type": ["string", "null"]},
        "message": {"type": "string"},
    },
    "required": ["saved", "export_id", "url", "message"],
    "additionalProperties": False,
}


class ZoClient:
    def __init__(self, settings: Settings, http_client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._http_client = http_client

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.zo_api_key)

    async def export_to_zo(
        self, session_id: UUID, artifact: ZoExportArtifact,
        request: ZoExportRequest | None = None,
    ) -> ZoExportResponse:
        request = request or ZoExportRequest(visibility=artifact.visibility)
        if not self.is_configured:
            run = IntegrationRun(provider="zo", product="practice-report", status="not_configured", fallback_reason="missing_api_key")
            return ZoExportResponse(session_id=session_id, status="not_configured", idempotency_key=artifact.idempotency_key, integration=run)
        started = time.monotonic()
        client = self._http_client or httpx.AsyncClient(timeout=self.settings.zo_timeout_seconds)
        close_client = self._http_client is None
        try:
            output = await self._ask(client, {
                "input": (
                    "Save the following Les Meilleurs practice report as a durable JSON file "
                    f"in my private Zo workspace. Visibility must be {artifact.visibility}. "
                    "Do not publish it publicly. Use the idempotency key as the filename suffix. "
                    "Return the required structured confirmation only.\nREPORT:\n" +
                    json.dumps(artifact.model_dump(mode="json"), sort_keys=True)
                ),
                "output_format": _OUTPUT_SCHEMA,
                "stream": False,
            })
            if not output.get("saved") or not output.get("export_id"):
                raise ValueError("unconfirmed_save")
            reminder_id = None
            if request.schedule_reminder:
                reminder_id = await self._create_reminder(client, artifact, request, output.get("url"))
            run = IntegrationRun(
                provider="zo", product="practice-report", status="completed",
                latency_ms=int((time.monotonic() - started) * 1000),
                request_id=output.get("conversation_id"),
                metadata={"visibility": artifact.visibility, "reminder_requested": request.schedule_reminder},
            )
            return ZoExportResponse(
                session_id=session_id, status="completed", export_id=output["export_id"],
                url=output.get("url"), idempotency_key=artifact.idempotency_key,
                created_at=datetime.now(timezone.utc), message=output.get("message", "Saved to Zo."),
                reminder_id=reminder_id, integration=run,
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            run = IntegrationRun(
                provider="zo", product="practice-report", status="failed",
                latency_ms=int((time.monotonic() - started) * 1000),
                fallback_reason="zo_request_failed",
            )
            return ZoExportResponse(
                session_id=session_id, status="failed", idempotency_key=artifact.idempotency_key,
                message="Zo could not confirm that the report was saved.", integration=run,
            )
        finally:
            if close_client:
                await client.aclose()

    async def _ask(self, client: httpx.AsyncClient, payload: dict) -> dict:
        base = (self.settings.zo_api_url or "https://api.zo.computer").rstrip("/")
        endpoint = base if base.endswith("/zo/ask") else base + "/zo/ask"
        response = await client.post(
            endpoint,
            headers={"Authorization": f"Bearer {self.settings.zo_api_key}"}, json=payload,
        )
        response.raise_for_status()
        data = response.json()
        output = data.get("output")
        if not isinstance(output, dict):
            raise ValueError("invalid_structured_output")
        output["conversation_id"] = data.get("conversation_id")
        return output

    async def _create_reminder(self, client, artifact, request, url) -> str | None:
        reminder_schema = {
            "type": "object", "properties": {
                "created": {"type": "boolean"}, "reminder_id": {"type": "string"},
            }, "required": ["created", "reminder_id"], "additionalProperties": False,
        }
        output = await self._ask(client, {
            "input": (
                f"Create a one-time practice reminder for {request.reminder_at.isoformat()} "
                f"in timezone {request.timezone}. Mention the report {url or artifact.idempotency_key}. "
                "This reminder was explicitly requested by the user."
            ),
            "output_format": reminder_schema, "stream": False,
        })
        return output.get("reminder_id") if output.get("created") else None
