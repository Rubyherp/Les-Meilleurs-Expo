import asyncio
import json
from datetime import datetime, timezone
from uuid import UUID

from app.schemas.coaching import CoachIssue, CoachPhase, CoachingReport
from app.services.coaching.context import CoachingContext, extract_coaching_context
from app.services.coaching.deterministic import generate_deterministic_report
from app.services.coaching.provider import create_provider

_PHASE_NAMES = {2: "Detection & Pose", 3: "Tracking & Continuity", 4: "Calibration & Space", 5: "Reference Comparison"}

_SYSTEM_PROMPT = """You are a dance coaching analyst. Analyse only the provided data.\nReturn a JSON object with: summary (1-2 sentences), strengths (list of strings), issues (list of {description, severity: low|medium|high, category: string|null}), suggestions (list of strings), confidence (float 0-1). Never invent data not present. Base severity on data quality impact."""

_PHASE_PROMPTS = {
    2: "You are a detection analyst. Focus on person detection coverage and pose estimation quality.",
    3: "You are a tracking analyst. Focus on identity continuity, occlusion rates, and track loss.",
    4: "You are a calibration analyst. Focus on top-down projection quality and spatial coverage.",
    5: "You are a comparison analyst. Focus on reference-vs-attempt similarity scores and deviation patterns.",
}

def _parse_llm_phase(raw: str | None, phase_num: int, ctx) -> CoachPhase:
    """Parse LLM JSON response into CoachPhase. Fall back to deterministic on ANY failure."""
    if not raw:
        return _get_deterministic_phase(phase_num, ctx)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _get_deterministic_phase(phase_num, ctx)
    if not isinstance(data, dict):
        return _get_deterministic_phase(phase_num, ctx)
    
    # Clamp confidence
    conf = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
    
    return CoachPhase(
        phase=phase_num,
        name=_PHASE_NAMES[phase_num],
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

def _get_deterministic_phase(phase_num, ctx) -> CoachPhase:
    """Get deterministic phase from the existing module."""
    from app.services.coaching.deterministic import (
        _detection_phase, _tracking_phase, _calibration_phase, _comparison_phase,
    )
    mapping = {2: _detection_phase, 3: _tracking_phase, 4: _calibration_phase, 5: _comparison_phase}
    sub_ctxs = {2: ctx.detection, 3: ctx.tracking, 4: ctx.calibration, 5: ctx.comparison}
    fn = mapping.get(phase_num)
    if fn:
        return fn(sub_ctxs[phase_num])
    return CoachPhase(phase=phase_num, name=_PHASE_NAMES.get(phase_num, "Unknown"), available=False, source="error", summary="Unknown phase", confidence=0.0)

def _format_context_for_llm(phase_num: int, ctx: CoachingContext) -> str:
    """Render structured context as a compact string for the LLM prompt."""
    if phase_num == 2:
        d = ctx.detection
        return f"Detection: {d.frames_with_detections}/{d.total_frames} frames with detections, {d.frames_with_poses}/{d.total_frames} with poses, max {d.max_persons_per_frame} concurrent."
    elif phase_num == 3:
        t = ctx.tracking
        return f"Tracking: {t.total_tracks} tracks, max {t.max_concurrent_tracks} concurrent, {t.occlusion_events} occlusions, {t.lost_events} lost over {t.total_frames} frames."
    elif phase_num == 4:
        c = ctx.calibration
        return f"Calibration: {'active' if c.has_calibration else 'inactive'}, {c.grid_columns}x{c.grid_rows} grid, {c.frames_with_projection}/{c.total_frames} frames projected, {c.tracked_dancers} dancers, avg trajectory {c.avg_trajectory_length:.1f}."
    elif phase_num == 5:
        c_comp = ctx.comparison
        if not c_comp.available:
            return "Comparison not available (single-video mode)."
        return f"Comparison: score={c_comp.overall_score:.4f}, {c_comp.matched_pairs} matched, {c_comp.unmatched_reference} unmatched ref, {c_comp.unmatched_attempt} unmatched att, avg DTW cost={c_comp.avg_dtw_cost:.4f}, avg deviation={c_comp.avg_deviation:.4f}."
    return ""

async def _try_llm_phase(provider, phase_num: int, ctx: CoachingContext) -> CoachPhase:
    """Try LLM for one phase. Falls back deterministically on any failure."""
    if not provider.available:
        return _get_deterministic_phase(phase_num, ctx)
    context_str = _format_context_for_llm(phase_num, ctx)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"{_PHASE_PROMPTS.get(phase_num, '')}\n\nData:\n{context_str}\n\nRespond with a JSON object."},
    ]
    try:
        raw = await asyncio.wait_for(provider.chat(messages), timeout=30.0)
    except (asyncio.TimeoutError, Exception):
        return _get_deterministic_phase(phase_num, ctx)
    return _parse_llm_phase(raw, phase_num, ctx)

async def run_coaching(session_id: UUID, mode: str, result: dict) -> CoachingReport:
    """Run coaching with LLM if available, fall back to deterministic per phase."""
    ctx = extract_coaching_context(result, mode)
    provider = create_provider()

    if not provider.available:
        return generate_deterministic_report(session_id, mode, ctx)
    
    # Run all 4 phases concurrently — each fails independently
    phases = list(await asyncio.gather(*[
        _try_llm_phase(provider, p, ctx) for p in (2, 3, 4, 5)
    ]))
    
    # Handle phase 5 availability for single mode
    if mode != "comparison" and phases[3].source == "llm":
        # Override with deterministic not-applicable if LLM didn't know
        from app.services.coaching.deterministic import _comparison_phase as det_comp
        phases[3] = _get_deterministic_phase(5, ctx)
    
    summaries = [p.summary for p in phases]
    overall = f"AI coaching analysis of {mode} session. " + " ".join(summaries)
    
    return CoachingReport(
        session_id=session_id,
        report_version=1,
        mode=mode,
        overall_summary=overall,
        phases=phases,
        generated_at=datetime.now(timezone.utc),
        llm_model_used=provider.model_name if provider.available else None,
    )
