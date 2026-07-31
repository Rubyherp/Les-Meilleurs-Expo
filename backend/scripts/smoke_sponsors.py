"""Opt-in, low-cost live connectivity checks for sponsor providers.

The script prints only sanitized status, model, and latency information. It
does not print credentials, prompts, model output, URLs, or response bodies.
"""

from __future__ import annotations

import asyncio
import os
import time
import cv2
import httpx
import numpy as np
from pydantic import BaseModel

from app.core.config import Settings
from app.integrations.agnes.client import AgnesClient
from app.integrations.gmi.client import GmiInferenceClient
from app.integrations.gmi.health import inspect_gmi_runtime
from app.integrations.models import EvidenceMoment
from app.schemas.coaching import CoachAgent
from app.services.coaching.context import CoachingContext
from app.services.evidence.models import PreparedEvidenceImage


class SmokeOutput(BaseModel):
    ok: bool


def _settings() -> Settings:
    env_file = os.environ.get("SPONSOR_ENV_FILE", ".env")
    return Settings(_env_file=env_file)


def _status(provider: str, status: str, *, model: str | None = None, latency_ms: int | None = None, reason: str | None = None) -> None:
    fields = [f"provider={provider}", f"status={status}"]
    if model:
        fields.append(f"model={model}")
    if latency_ms is not None:
        fields.append(f"latency_ms={latency_ms}")
    if reason:
        fields.append(f"reason={reason}")
    print(" ".join(fields), flush=True)


async def smoke_agnes(settings: Settings) -> bool:
    if not settings.agnes_api_key:
        _status("agnes", "skipped", reason="not_configured")
        return False
    frame = np.zeros((16, 16, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", frame)
    if not ok:
        _status("agnes", "failed", reason="fixture_encoding_failed")
        return False
    image_bytes = encoded.tobytes()
    image = PreparedEvidenceImage(
        image_bytes=image_bytes,
        sha256="live-smoke-fixture",
        width=16,
        height=16,
        timestamp_seconds=0.0,
    )
    moment = EvidenceMoment(
        id="live_smoke_fixture",
        start_seconds=0.0,
        end_seconds=0.5,
        primary_timestamp_seconds=0.0,
        category="observation",
        severity="low",
        deterministic_reason="Synthetic blank frame for connectivity testing only.",
    )
    observed_status: int | None = None

    async def capture_status(response: httpx.Response) -> None:
        nonlocal observed_status
        observed_status = response.status_code

    async with httpx.AsyncClient(
        timeout=settings.agnes_timeout_seconds,
        event_hooks={"response": [capture_status]},
    ) as http_client:
        client = AgnesClient(settings, http_client)
        review = await client.review(moment, [image])
    run = client.last_run
    reason = run.fallback_reason if run else "missing_run_status"
    if reason and observed_status is not None and not reason.endswith(f"http_{observed_status}"):
        reason = f"{reason}_http_{observed_status}"
    _status(
        "agnes",
        run.status if run else "failed",
        model=run.model if run else settings.agnes_model,
        latency_ms=run.latency_ms if run else None,
        reason=reason,
    )
    return review is not None and run is not None and run.status == "completed"


async def smoke_openai(settings: Settings) -> bool:
    key = settings.openai_api_key or settings.llm_api_key
    model = settings.openai_model or settings.llm_model
    if not key:
        _status("openai", "skipped", model=model, reason="not_configured")
        return False
    from agents import Agent, RunConfig, Runner

    previous = os.environ.get("OPENAI_API_KEY")
    os.environ["OPENAI_API_KEY"] = key
    started = time.monotonic()
    try:
        agent = Agent(
            name="Les Meilleurs connectivity check",
            instructions="Return ok=true. Do not use tools and do not add commentary.",
            model=model,
            output_type=SmokeOutput,
        )
        result = await asyncio.wait_for(
            Runner.run(
                agent,
                "Perform the connectivity check.",
                run_config=RunConfig(
                    workflow_name="les-meilleurs-live-smoke",
                    trace_include_sensitive_data=False,
                ),
            ),
            timeout=settings.openai_timeout_seconds,
        )
        parsed = SmokeOutput.model_validate(result.final_output)
        elapsed = int((time.monotonic() - started) * 1000)
        _status("openai", "completed" if parsed.ok else "failed", model=model, latency_ms=elapsed)
        return parsed.ok
    except Exception as exc:
        _status(
            "openai", "failed", model=model,
            latency_ms=int((time.monotonic() - started) * 1000),
            reason=type(exc).__name__,
        )
        return False
    finally:
        if previous is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = previous


async def smoke_zo(settings: Settings) -> bool:
    if not settings.zo_api_key:
        _status("zo", "skipped", reason="not_configured")
        return False
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=settings.zo_timeout_seconds) as client:
            base = (settings.zo_api_url or "https://api.zo.computer").rstrip("/")
            endpoint = base if base.endswith("/zo/ask") else base + "/zo/ask"
            response = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {settings.zo_api_key}"},
                json={
                    "input": (
                        "Connectivity check only: return ok=true using the requested structured "
                        "format. Do not create or edit files, conversations, automations, reminders, "
                        "sites, services, or integrations."
                    ),
                    "output_format": {
                        "type": "object",
                        "properties": {"ok": {"type": "boolean"}},
                        "required": ["ok"],
                        "additionalProperties": False,
                    },
                    "stream": False,
                },
            )
            response.raise_for_status()
            output = response.json().get("output")
            parsed = SmokeOutput.model_validate(output)
        _status("zo", "completed" if parsed.ok else "failed", latency_ms=int((time.monotonic() - started) * 1000))
        return parsed.ok
    except Exception as exc:
        reason = type(exc).__name__
        if isinstance(exc, httpx.HTTPStatusError):
            reason = f"http_{exc.response.status_code}"
        _status(
            "zo", "failed", latency_ms=int((time.monotonic() - started) * 1000),
            reason=reason,
        )
        return False


async def smoke_gmi(settings: Settings) -> bool:
    draft = CoachAgent(
        agent_id=1,
        name="Connectivity Fixture",
        available=True,
        source="deterministic",
        summary="No video was supplied; this is a connectivity check only.",
        confidence=1.0,
    )
    agent, run = await GmiInferenceClient(settings).audit(
        CoachingContext(), [], [draft], agent_id=2
    )
    _status(
        "gmi",
        run.status,
        model=run.model or settings.gmi_model,
        latency_ms=run.latency_ms,
        reason=run.fallback_reason,
    )
    return agent is not None and run.status == "completed"


async def main() -> int:
    if os.environ.get("SPONSOR_LIVE_SMOKE_TEST", "").lower() != "true":
        print("Live smoke tests disabled. Set SPONSOR_LIVE_SMOKE_TEST=true.")
        return 2
    settings = _settings()
    checks = {
        "agnes": smoke_agnes,
        "openai": smoke_openai,
        "zo": smoke_zo,
        "gmi": smoke_gmi,
    }
    requested = {
        item.strip().lower()
        for item in os.environ.get("SPONSOR_SMOKE_PROVIDERS", "agnes,openai,zo,gmi").split(",")
        if item.strip()
    }
    unknown = requested.difference(checks)
    if unknown:
        print("Unknown provider selection.")
        return 2
    results = await asyncio.gather(*(checks[name](settings) for name in checks if name in requested))
    if settings.gmi_enabled:
        compute = inspect_gmi_runtime(settings)
        _status(
            "gmi_compute",
            "completed" if compute.gpu_available else "failed",
            reason=compute.failure_reason,
        )
    return 0 if results and all(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
