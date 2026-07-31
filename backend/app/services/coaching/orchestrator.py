"""Fallback-safe coaching orchestration."""

from datetime import datetime, timezone
from uuid import UUID

from app.core.config import Settings, get_settings
from app.integrations.gmi.client import GmiInferenceClient
from app.integrations.models import EvidenceMoment, IntegrationRun
from app.integrations.openai.agents import run_agentic_coaching
from app.schemas.coaching import CoachingReport
from app.services.coaching.context import extract_coaching_context
from app.services.coaching.deterministic import generate_deterministic_report
from app.services.evidence.selector import select_evidence


async def run_coaching(
    session_id: UUID,
    mode: str,
    result: dict,
    *,
    is_group: bool = False,
    expected_dancer_count: int = 1,
    settings: Settings | None = None,
    evidence_moments: list[EvidenceMoment] | None = None,
    extra_integrations: list[IntegrationRun] | None = None,
) -> CoachingReport:
    """Build a report while keeping deterministic measurements authoritative."""
    settings = settings or get_settings()
    context = extract_coaching_context(
        result, mode, is_group=is_group, expected_dancer_count=expected_dancer_count
    )
    duration = result.get("duration_seconds")
    evidence = evidence_moments if evidence_moments is not None else select_evidence(
        result, mode=mode, is_group=is_group,
        max_moments=settings.agnes_max_evidence_moments,
        duration_seconds=float(duration) if isinstance(duration, (int, float)) else None,
    )
    provider_result = await run_agentic_coaching(
        session_id, context, evidence, is_group=is_group, settings=settings
    )
    integrations: list[IntegrationRun] = []
    for raw in result.get("integrations") or []:
        try:
            integrations.append(IntegrationRun.model_validate(raw))
        except Exception:
            continue
    integrations.extend(extra_integrations or [])
    integrations.extend(provider_result.integrations)

    if provider_result.agents:
        agents = provider_result.agents
        overall = provider_result.overall_summary
        notes = provider_result.coordination_notes
        model = settings.openai_model if any(a.source == "llm" for a in agents) else None
    else:
        fallback = generate_deterministic_report(session_id, mode, context, is_group=is_group)
        agents = fallback.agents
        overall = fallback.overall_summary
        notes = fallback.coordination_notes
        model = None

    gmi_agent, gmi_run = await GmiInferenceClient(settings).audit(
        context,
        evidence,
        agents,
        agent_id=max((agent.agent_id for agent in agents), default=0) + 1,
    )
    integrations.append(gmi_run)
    if gmi_agent is not None:
        agents = [*agents, gmi_agent]
        notes = [*notes, "GMI independently audited the draft against aggregate measurements."]
        model = model or settings.gmi_model

    return CoachingReport(
        session_id=session_id, report_version=4, mode=mode,
        practice_type="group" if is_group else "solo",
        overall_summary=overall, agents=agents, coordination_notes=notes,
        generated_at=datetime.now(timezone.utc), llm_model_used=model,
        evidence_moments=evidence, integrations=integrations,
        trace_id=provider_result.trace_id,
    )
