"""Optional OpenAI Async client wrapper and context builders for coaching agents.

This module owns:
- ``LLMClient``: thin wrapper that short-circuits when no API key is configured.
- ``parse_agent_insight``: robust JSON parser into ``AgentInsight``.
- Context builders (``build_formation_context``, ``build_timing_context``, etc.)
  that produce compact, data-grounded strings for LLM prompts.

No network calls are made unless ``LLMClient.available`` is True.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import get_settings
from app.schemas.session import AgentInsight, CoachIssue

logger = logging.getLogger("lesmeilleurs")


# ── LLM Client ───────────────────────────────────────────────────────────────


class LLMClient:
    """Optional OpenAI Async client wrapper.

    If no API key is configured, ``available`` is ``False`` and all
    ``chat_completion`` calls return ``None`` without making network requests.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key: str = settings.llm_api_key
        self._model: str = settings.llm_model
        self._temperature: float = settings.llm_temperature
        self._client: Any = None
        if self._api_key:
            try:
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(api_key=self._api_key)
            except Exception:
                logger.warning("Failed to initialise OpenAI client", exc_info=True)

    @property
    def available(self) -> bool:
        """Whether the underlying client is ready to make network calls."""
        return self._client is not None

    async def chat_completion(self, messages: list[dict[str, Any]]) -> str | None:
        """Call the LLM chat completion endpoint.

        Returns the response content as a string, or ``None`` on failure.
        """
        if not self._client:
            return None
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=self._temperature,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            return content if content else None
        except Exception:
            logger.exception("LLM chat completion failed")
            return None


# ── Parsing ──────────────────────────────────────────────────────────────────


def parse_agent_insight(
    raw: str | None,
    agent_name: str,
    fallback_data: dict[str, Any] | None = None,
) -> AgentInsight:
    """Parse an LLM JSON response string into an ``AgentInsight``.

    Handles malformed JSON, missing fields, out-of-range confidence, and
    ``None`` input without raising. Falls back to a descriptive
    ``AgentInsight`` with ``confidence=0.0`` when parsing fails.
    """
    if not raw:
        return _make_fallback(agent_name, "No response from LLM.", fallback_data)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _make_fallback(agent_name, "LLM response was not valid JSON.", fallback_data)

    if not isinstance(data, dict):
        return _make_fallback(agent_name, "LLM response was not a JSON object.", fallback_data)

    summary = _normalize_str(data.get("summary"), agent_name)
    strengths_raw = data.get("strengths") or ()
    issues_raw = data.get("issues") or ()
    suggestions_raw = data.get("suggestions") or ()
    confidence = _clamp_confidence(data.get("confidence"))

    strengths = [
        _normalize_str(s, "") for s in (strengths_raw if isinstance(strengths_raw, list) else [])
    ]
    suggestions = [
        _normalize_str(s, "")
        for s in (suggestions_raw if isinstance(suggestions_raw, list) else [])
    ]

    issues: list[CoachIssue] = []
    if isinstance(issues_raw, list):
        for issue in issues_raw:
            if not isinstance(issue, dict):
                continue
            desc = _normalize_str(issue.get("description"), "")
            sev = str(issue.get("severity", "medium")).lower().strip()
            if sev not in ("low", "medium", "high"):
                sev = "medium"
            issues.append(CoachIssue(description=desc, severity=sev))

    return AgentInsight(
        agent_name=agent_name,
        summary=summary,
        strengths=strengths,
        issues=issues,
        suggestions=suggestions,
        confidence=confidence,
    )


def _normalize_str(value: Any, default: str) -> str:
    if isinstance(value, str):
        return value.strip()
    return default


def _clamp_confidence(value: Any) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, v))


def _make_fallback(
    agent_name: str,
    reason: str,
    _data: dict[str, Any] | None = None,
) -> AgentInsight:
    return AgentInsight(
        agent_name=agent_name,
        summary=f"Analysis unavailable: {reason}",
        strengths=[],
        issues=[CoachIssue(description="Insufficient data for analysis", severity="medium")],
        suggestions=["Ensure the video has adequate lighting and visible dancers."],
        confidence=0.0,
    )


# ── Context builders ─────────────────────────────────────────────────────────


def build_formation_context(result: dict[str, Any]) -> str:
    """Compact formation summary: grid occupancy counts across sampled frames.

    Uses at most 20 evenly-spaced frames to keep the context bounded.
    All values come directly from the analysis result; no observations are
    invented.
    """
    frames = result.get("sampled_frames") or ()
    projection = result.get("projection") or {}
    grid_cols = projection.get("grid_columns", 10)
    grid_rows = projection.get("grid_rows", 10)

    if not frames:
        return "No frame data available."

    step = max(1, len(frames) // 20)
    sampled = frames[::step]

    lines: list[str] = [
        f"Formation analysis over {len(sampled)} sampled frames "
        f"(grid: {grid_cols}x{grid_rows}):"
    ]

    dancer_ids: set[int] = set()
    for frame in sampled:
        tracks = frame.get("tracks") or ()
        positions: list[tuple[int, float, float]] = []
        for t in tracks:
            td = t.get("top_down")
            if isinstance(td, dict):
                x, y = td.get("x"), td.get("y")
                if x is not None and y is not None:
                    tid = int(t.get("track_id", -1))
                    dancer_ids.add(tid)
                    positions.append((tid, float(x), float(y)))

        ts = frame.get("timestamp_seconds", 0)
        if positions:
            dancer_str = ", ".join(f"#{tid}" for tid, _, _ in positions)
            lines.append(f"  t={ts:.1f}s: {len(positions)} dancer(s) at {dancer_str}")
        else:
            lines.append(f"  t={ts:.1f}s: 0 dancers")

    lines.append(f"\nTotal unique dancers detected: {len(dancer_ids)}")
    return "\n".join(lines)


def build_timing_context(result: dict[str, Any]) -> str:
    """Compact timing summary: frame timestamps and active dancer counts.

    Samples up to 20 frames evenly. Reports total duration and frame count.
    """
    frames = result.get("sampled_frames") or ()
    if not frames:
        return "No frame data available."

    step = max(1, len(frames) // 20)
    sampled = frames[::step]

    lines: list[str] = [
        f"Timing analysis over {len(sampled)} sampled frames "
        f"(of {len(frames)} total):"
    ]

    for frame in sampled:
        tracks = frame.get("tracks") or ()
        ts = frame.get("timestamp_seconds", 0)
        active = sum(
            1
            for t in tracks
            if t.get("status") == "active" and t.get("top_down") is not None
        )
        lines.append(f"  t={ts:.1f}s: {active} active dancer(s)")

    timestamps = [f.get("timestamp_seconds", 0) for f in frames]
    if len(timestamps) >= 2:
        duration = timestamps[-1] - timestamps[0]
        lines.append(f"\nTotal duration: {duration:.1f}s over {len(frames)} frames.")
    else:
        lines.append(f"\nTotal frames: {len(frames)}.")

    return "\n".join(lines)


def build_spatial_context(result: dict[str, Any]) -> str:
    """Compact spatial summary: per-dancer trajectory statistics.

    Computes average position, x/y spread, and sample count for each dancer
    across all frames with valid ``top_down`` coordinates.
    """
    frames = result.get("sampled_frames") or ()
    if not frames:
        return "No frame data available."

    dancer_trajs: dict[int, list[tuple[float, float, float]]] = {}
    for frame in frames:
        ts = frame.get("timestamp_seconds", 0.0)
        for t in frame.get("tracks") or ():
            td = t.get("top_down")
            if isinstance(td, dict):
                x, y = td.get("x"), td.get("y")
                if x is not None and y is not None:
                    tid = int(t.get("track_id", -1))
                    dancer_trajs.setdefault(tid, []).append((ts, float(x), float(y)))

    if not dancer_trajs:
        return "No spatial trajectory data available."

    lines: list[str] = [f"Spatial analysis for {len(dancer_trajs)} dancer(s):"]
    for tid in sorted(dancer_trajs):
        pts = dancer_trajs[tid]
        xs = [p[1] for p in pts]
        ys = [p[2] for p in pts]
        avg_x = sum(xs) / len(xs)
        avg_y = sum(ys) / len(ys)
        spread_x = max(xs) - min(xs)
        spread_y = max(ys) - min(ys)
        lines.append(
            f"  #{tid}: avg=({avg_x:.2f}, {avg_y:.2f}), "
            f"spread=({spread_x:.2f}, {spread_y:.2f}), "
            f"samples={len(pts)}"
        )

    return "\n".join(lines)


def build_comparison_context(comparison_result: dict[str, Any]) -> str:
    """Compact comparison summary: match costs, deviations, overall score.

    Limits to 10 deviation entries to keep the context bounded.
    """
    matches = comparison_result.get("matches") or ()
    deviations = comparison_result.get("deviations") or ()
    overall_score = comparison_result.get("overall_score", 0.0)
    unmatched_ref = comparison_result.get("unmatched_reference_ids") or ()
    unmatched_att = comparison_result.get("unmatched_attempt_ids") or ()

    lines: list[str] = [
        f"Comparison overview: overall_score={overall_score:.3f}",
        f"Matched dancer pairs: {len(matches)}",
        f"Unmatched reference dancers: {len(unmatched_ref)} IDs={unmatched_ref}",
        f"Unmatched attempt dancers: {len(unmatched_att)} IDs={unmatched_att}",
    ]

    for idx, dev in enumerate(deviations):
        if idx >= 10:
            lines.append(f"  ... ({len(deviations) - 10} more pairs omitted)")
            break
        ref_id = dev.get("reference_id", "?")
        att_id = dev.get("attempt_id", "?")
        mean_d = dev.get("mean_distance", 0.0)
        max_d = dev.get("max_distance", 0.0)
        cost = dev.get("normalized_dtw_cost", 0.0)
        lines.append(
            f"  #{ref_id}->#{att_id}: mean_dist={mean_d:.3f}, "
            f"max_dist={max_d:.3f}, dtw_cost={cost:.3f}"
        )

    return "\n".join(lines)


def build_agent_contexts(
    result: dict[str, Any],
    mode: str = "single",
) -> dict[str, str]:
    """Build compact contexts for all agents from the analysis result.

    Returns a dict keyed by agent name with a plain-text summary as value.

    In ``"single"`` mode, all agents are built from *result* directly.
    In ``"comparison"`` mode, formation/timing/spatial use the **attempt**
    sub-result (so they analyse the dancer's performance) while the
    ``comparison`` agent uses the top-level comparison fields.  If no
    attempt sub-result is nested, the outer dict is used as-is.
    """
    if mode == "comparison":
        attempt = (
            result.get("attempt_result")
            or result.get("attempt")
            or result
        )
        contexts: dict[str, str] = {
            "formation": build_formation_context(attempt),
            "timing": build_timing_context(attempt),
            "spatial": build_spatial_context(attempt),
            "comparison": build_comparison_context(result),
        }
    else:
        contexts = {
            "formation": build_formation_context(result),
            "timing": build_timing_context(result),
            "spatial": build_spatial_context(result),
        }
    return contexts
