import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID

from app.schemas.coaching import CoachIssue, CoachPhase, CoachingReport
from app.services.coaching.context import CoachingContext, extract_coaching_context
from app.services.coaching.deterministic import generate_deterministic_report
from app.services.coaching.provider import create_provider

_AGENT_NAMES = {1: "Observation Agent", 2: "Timing Agent", 3: "Formation Agent"}

_SYSTEM_PROMPT = """You are one specialist in a collaborative dance-coaching team. Use warm, encouraging, simple language with no technical jargon. Analyse only the provided structured measurements. Return a JSON object with: summary (1-2 sentences), strengths (list of strings), issues (list of {description, severity: low|medium|high, category: string|null}), suggestions (list of actionable tips), confidence (float 0-1). Never invent observations or imply that you measured music beats when no reference was provided."""

_AGENT_PROMPTS = {
    1: "You are the Observation Agent. Judge camera visibility, pose readability, occlusion, and tracking reliability.",
    2: "You are the Timing Agent. Judge reference timing offset when a reference exists; otherwise discuss only movement-pulse consistency.",
    3: "You are the Formation Agent for group choreography. Judge relative spacing, crowding, and spatial match.",
}

def _parse_llm_agent(raw: str | None, agent_num: int, ctx) -> CoachPhase:
    """Parse an LLM specialist response, falling back on any failure."""
    if not raw:
        return _get_deterministic_agent(agent_num, ctx)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _get_deterministic_agent(agent_num, ctx)
    if not isinstance(data, dict):
        return _get_deterministic_agent(agent_num, ctx)
    
    # Clamp confidence
    conf = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
    
    return CoachPhase(
        phase=agent_num,
        name=_AGENT_NAMES[agent_num],
        available=True,
        source="llm",
        summary=str(data.get("summary", "")).strip(),
        strengths=[str(s) for s in (data.get("strengths") or []) if isinstance(s, str)],
        issues=[CoachIssue(
            description=str(i.get("description", "")),
            severity=str(i.get("severity", "medium")),
            category=str(i.get("category")) if i.get("category") else None,
        ) for i in (data.get("issues") or []) if isinstance(i, dict)],
        suggestions=[str(s) for s in (data.get("suggestions") or []) if isinstance(s, str)],
        confidence=round(conf, 2),
    )

def _get_deterministic_agent(agent_num: int, ctx: CoachingContext) -> CoachPhase:
    from app.services.coaching.deterministic import (
        _formation_agent,
        _observation_agent,
        _timing_agent,
    )
    mapping = {
        1: (_observation_agent, ctx.observation),
        2: (_timing_agent, ctx.timing),
        3: (_formation_agent, ctx.formation),
    }
    entry = mapping.get(agent_num)
    if entry is None:
        return CoachPhase(
            phase=agent_num,
            name=_AGENT_NAMES.get(agent_num, "Unknown Agent"),
            available=False,
            source="error",
            summary="Unknown coaching agent.",
            confidence=0.0,
        )
    fn, sub_ctx = entry
    if fn:
        return fn(sub_ctx)
    raise AssertionError("Agent mapping is incomplete.")

def _format_context_for_llm(agent_num: int, ctx: CoachingContext) -> str:
    """Render structured context as a compact string for the LLM prompt."""
    if agent_num == 1:
        observation = ctx.observation
        return (
            f"Observation: group={observation.is_group}, "
            f"visible_frames={observation.frames_with_detections}/{observation.total_frames}, "
            f"pose_frames={observation.frames_with_poses}/{observation.total_frames}, "
            f"max_people={observation.max_persons_per_frame}, tracks={observation.total_tracks}, "
            f"occlusions={observation.occlusion_events}, lost={observation.lost_events}."
        )
    if agent_num == 2:
        timing = ctx.timing
        return (
            f"Timing: has_reference={timing.has_reference}, samples={timing.sample_count}, "
            f"mean_signed_offset_seconds={timing.average_offset_seconds:.3f}, "
            f"mean_absolute_offset_seconds={timing.average_absolute_offset_seconds:.3f}, "
            f"offset_spread_seconds={timing.offset_spread_seconds:.3f}, "
            f"pulse_consistency={timing.pulse_consistency:.3f}, "
            f"group_sync_score={timing.group_sync_score}."
        )
    if agent_num == 3:
        formation = ctx.formation
        return (
            f"Formation: dancers={formation.tracked_dancers}, "
            f"group_frames={formation.observed_group_frames}, "
            f"average_pair_distance={formation.average_pair_distance:.3f}, "
            f"spacing_variation={formation.spacing_variation:.3f}, "
            f"close_spacing_rate={formation.close_spacing_rate:.3f}, "
            f"reference_match_score={formation.reference_match_score}."
        )
    return ""

async def _try_llm_agent(provider, agent_num: int, ctx: CoachingContext) -> CoachPhase:
    """Try an LLM specialist and fall back deterministically on any failure."""
    deterministic = _get_deterministic_agent(agent_num, ctx)
    if not deterministic.available:
        return deterministic
    if not provider.available:
        return deterministic
    context_str = _format_context_for_llm(agent_num, ctx)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"{_AGENT_PROMPTS.get(agent_num, '')}\n\nData:\n{context_str}\n\nRespond with a JSON object."},
    ]
    try:
        raw = await asyncio.wait_for(provider.chat(messages), timeout=30.0)
    except (asyncio.TimeoutError, Exception):
        return deterministic
    return _parse_llm_agent(raw, agent_num, ctx)

async def run_coaching(
    session_id: UUID,
    mode: str,
    result: dict,
    *,
    is_group: bool = False,
) -> CoachingReport:
    """Run the applicable specialists through the existing AI coach."""
    ctx = extract_coaching_context(result, mode, is_group=is_group)
    provider = create_provider()

    if not provider.available:
        return generate_deterministic_report(
            session_id,
            mode,
            ctx,
            is_group=is_group,
        )
    
    agent_numbers = [1, 2, 3] if is_group else [1, 2]
    phases = list(
        await asyncio.gather(
            *[_try_llm_agent(provider, agent_num, ctx) for agent_num in agent_numbers]
        )
    )
    summaries = [agent.summary for agent in phases if agent.available]
    practice_label = "Group" if is_group else "Solo"
    overall = f"{practice_label} coaching team report. " + " ".join(summaries)
    
    return CoachingReport(
        session_id=session_id,
        report_version=2,
        mode=mode,
        practice_type="group" if is_group else "solo",
        overall_summary=overall,
        phases=phases,
        generated_at=datetime.now(timezone.utc),
        llm_model_used=provider.model_name if provider.available else None,
    )
