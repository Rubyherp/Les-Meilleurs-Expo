"""Zo Computer `/zo/ask` client with explicit, isolated reminder creation."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from uuid import UUID

import httpx

from app.core.config import Settings
from app.integrations.models import IntegrationRun
from app.integrations.zo.models import ZoExportArtifact, ZoExportRequest, ZoExportResponse

_WRITE_SCHEMA = {
    "type": "object",
    "properties": {
        "written": {"type": "boolean"},
        "file_path": {"type": "string"},
        "url": {"type": "string"},
        "message": {"type": "string"},
    },
    "required": ["written", "file_path", "url", "message"],
    "additionalProperties": False,
}
_VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "exists": {"type": "boolean"},
        "file_path": {"type": "string"},
        "sha256": {"type": "string"},
    },
    "required": ["exists", "file_path", "sha256"],
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
            report_json = json.dumps(
                artifact.model_dump(mode="json"), sort_keys=True,
                separators=(",", ":"),
            ) + "\n"
            expected_sha256 = hashlib.sha256(report_json.encode("utf-8")).hexdigest()
            export_id = artifact.idempotency_key[:16]
            file_path = (
                "/home/workspace/les-meilleurs/practice-reports/"
                f"{session_id}-{export_id}.json"
            )
            written = await self._ask(client, {
                "input": (
                    "Create the parent directory if needed, then write the exact UTF-8 bytes "
                    f"between REPORT_JSON markers to {file_path}. The file is private and must "
                    "not be published. Preserve the single trailing newline. Return written=true "
                    "only after the write command succeeds. Return an empty string for url if no "
                    "authenticated browser URL is available.\nREPORT_JSON_START\n"
                    f"{report_json}REPORT_JSON_END"
                ),
                "output_format": _WRITE_SCHEMA,
                "stream": False,
            })
            conversation_id = written.get("conversation_id")
            if not written.get("written") or written.get("file_path") != file_path:
                raise ValueError("unconfirmed_save")
            verified = await self._ask(client, {
                "input": (
                    f"Read {file_path} without modifying it. Confirm whether it exists and compute "
                    "the SHA-256 of its exact bytes. Return only the required structured result."
                ),
                "output_format": _VERIFY_SCHEMA,
                "stream": False,
            })
            if (
                not verified.get("exists")
                or verified.get("file_path") != file_path
                or verified.get("sha256") != expected_sha256
            ):
                raise ValueError("readback_verification_failed")
            reminder_id = None
            if request.schedule_reminder:
                reminder_id = await self._create_reminder(
                    client, artifact, request, written.get("url") or file_path
                )
            run = IntegrationRun(
                provider="zo", product="practice-report", status="completed",
                latency_ms=int((time.monotonic() - started) * 1000),
                request_id=verified.get("conversation_id") or conversation_id,
                metadata={
                    "visibility": artifact.visibility,
                    "reminder_requested": request.schedule_reminder,
                    "readback_verified": True,
                    "file_path": file_path,
                    "content_sha256": expected_sha256,
                },
            )
            return ZoExportResponse(
                session_id=session_id, status="completed", export_id=export_id,
                file_path=file_path, url=written.get("url") or None,
                idempotency_key=artifact.idempotency_key,
                created_at=datetime.now(timezone.utc),
                message=written.get("message", "Saved and verified in Zo."),
                reminder_id=reminder_id, integration=run,
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            if isinstance(exc, httpx.HTTPStatusError):
                reason = f"http_{exc.response.status_code}"
            elif isinstance(exc, httpx.HTTPError):
                reason = "transport_error"
            elif str(exc) in {"unconfirmed_save", "readback_verification_failed"}:
                reason = str(exc)
            else:
                reason = "invalid_response"
            run = IntegrationRun(
                provider="zo", product="practice-report", status="failed",
                latency_ms=int((time.monotonic() - started) * 1000),
                fallback_reason=reason,
            )
            return ZoExportResponse(
                session_id=session_id, status="failed", idempotency_key=artifact.idempotency_key,
                message=f"Zo report save failed ({reason.replace('_', ' ')}).",
                integration=run,
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
