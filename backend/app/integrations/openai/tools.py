"""Read-only, context-scoped tools exposed to coaching specialists."""

from dataclasses import asdict

from agents import RunContextWrapper, function_tool

from app.integrations.openai.models import AgentRunContext


@function_tool
def get_observation_metrics(ctx: RunContextWrapper[AgentRunContext]) -> dict:
    """Return visibility and detection measurements for this session."""
    return asdict(ctx.context.coaching.observation)


@function_tool
def get_tracking_quality(ctx: RunContextWrapper[AgentRunContext]) -> dict:
    """Return tracking reliability measurements for this session."""
    return asdict(ctx.context.coaching.tracking)


@function_tool
def get_timing_metrics(ctx: RunContextWrapper[AgentRunContext]) -> dict:
    """Return timing and movement-pulse measurements for this session."""
    return asdict(ctx.context.coaching.timing)


@function_tool
def get_beat_metrics(ctx: RunContextWrapper[AgentRunContext]) -> dict:
    """Return audio beat fields, including explicit availability."""
    timing = ctx.context.coaching.timing
    return {
        "has_audio": timing.has_audio,
        "tempo_bpm": timing.tempo_bpm,
        "beat_count": timing.beat_count,
        "mean_beat_lag": timing.mean_beat_lag,
        "beat_consistency": timing.beat_consistency,
    }


@function_tool
def get_formation_metrics(ctx: RunContextWrapper[AgentRunContext]) -> dict:
    """Return group-only formation measurements for this session."""
    return asdict(ctx.context.coaching.formation)


@function_tool
def get_trajectory_deviations(ctx: RunContextWrapper[AgentRunContext]) -> dict:
    """Return bounded spatial comparison metrics for this session."""
    return asdict(ctx.context.coaching.comparison)


@function_tool
def get_visual_evidence(
    ctx: RunContextWrapper[AgentRunContext], category: str
) -> list[dict]:
    """Return persisted evidence summaries in one allowed category."""
    allowed = {"observation", "timing", "formation", "comparison", "tracking"}
    if category not in allowed:
        return []
    return [
        {
            "id": item.id,
            "timestamp_seconds": item.primary_timestamp_seconds,
            "category": item.category,
            "reason": item.deterministic_reason,
            "metrics": item.deterministic_metrics,
            "visual_review": item.visual_review.model_dump() if item.visual_review else None,
        }
        for item in ctx.context.evidence
        if item.category == category
    ][:3]
