"""Coaching orchestrator: runs agents concurrently, produces ``CoachingReport``.

Entry points
------------
- ``run_coaching()`` — async function, preferred for direct use.
- ``CoachOrchestrator`` — class wrapper for dependency injection.

Deterministic fallback
----------------------
When no API key is configured, or when an individual agent LLM call fails, a
data-driven deterministic insight is generated from the context summary so that
the feature remains useful in local / dev environments.  No agent failure
cascades — each agent fails independently.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.schemas.session import AgentInsight, CoachIssue, CoachingReport
from app.services.coaching.base import LLMClient, build_agent_contexts, parse_agent_insight

logger = logging.getLogger("lesmeilleurs")

# ── Prompts ──────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a dance coaching analyst. Analyse the provided data and respond with a JSON object.

IMPORTANT RULES:
- Base ALL observations strictly on the supplied numeric data. NEVER invent measurements or observations that are not present in the data.
- Use the coordinate data, dancer counts, and timing information provided.
- Format your response as a JSON object with these exact keys:
  - "summary": A concise 1-2 sentence summary of findings.
  - "strengths": A list of positive observations (strings).
  - "issues": A list of objects with "description" (string) and "severity" ("low", "medium", or "high").
  - "suggestions": A list of actionable improvement suggestions (strings).
  - "confidence": A float between 0.0 and 1.0 indicating confidence in the analysis.
"""

_AGENT_PROMPTS: dict[str, str] = {
    "formation": (
        "You are a formation analyst. Focus on dancer positioning, spacing, "
        "group arrangements, and how the formation evolves over time. "
        "Use the grid occupancy data provided."
    ),
    "timing": (
        "You are a timing analyst. Focus on rhythm, synchronisation, tempo "
        "consistency, and movement timing across dancers. "
        "Use the active dancer counts and timestamps provided."
    ),
    "spatial": (
        "You are a spatial analyst. Focus on individual dancer trajectories, "
        "stage coverage, movement ranges, and spatial patterns. "
        "Use the per-dancer position statistics provided."
    ),
    "comparison": (
        "You are a comparison analyst. Focus on differences between the "
        "reference and attempt performances, deviation patterns, and matching "
        "quality. Use the DTW costs, distances, and scores provided."
    ),
}


# ── Deterministic fallbacks (data-driven, no LLM) ───────────────────────────


def _deterministic_formation_insight(context: str) -> AgentInsight:
    """Deterministic fallback formation insight parsed from the context."""
    dancer_match = re.search(r"Total unique dancers detected: (\d+)", context)
    dancer_count = int(dancer_match.group(1)) if dancer_match else 0

    strengths: list[str] = []
    issues: list[CoachIssue] = []
    suggestions: list[str] = []

    if dancer_count > 0:
        strengths.append(f"{dancer_count} dancers were tracked across the stage.")
        suggestions.append("Work on maintaining consistent spacing between dancers.")
        suggestions.append("Vary formation patterns to improve visual impact.")
    else:
        issues.append(
            CoachIssue(description="No dancers detected in the video.", severity="high")
        )
        suggestions.append("Ensure all dancers are visible and within the camera frame.")

    summary = (
        f"Detected {dancer_count} dancer(s) on stage."
        if dancer_count
        else "No dancers detected."
    )

    return AgentInsight(
        agent_name="formation",
        summary=summary,
        strengths=strengths,
        issues=issues,
        suggestions=suggestions,
        confidence=0.6 if dancer_count else 0.0,
    )


def _deterministic_timing_insight(context: str) -> AgentInsight:
    """Deterministic fallback timing insight parsed from the context."""
    duration_match = re.search(r"Total duration: ([\d.]+)s", context)
    frame_match = re.search(r"over (\d+) frames", context)
    duration = float(duration_match.group(1)) if duration_match else 0.0
    frame_count = int(frame_match.group(1)) if frame_match else 0

    strengths: list[str] = []
    issues: list[CoachIssue] = []
    suggestions: list[str] = []

    if frame_count > 0:
        strengths.append(f"Analysis covers {frame_count} frames over {duration:.1f} seconds.")
        suggestions.append("Focus on synchronising movements across the group.")
    else:
        issues.append(
            CoachIssue(
                description="Insufficient timing data for analysis.",
                severity="high",
            )
        )
        suggestions.append("Ensure the video captures the entire dance routine.")

    summary = (
        f"Analysis duration: {duration:.1f}s across {frame_count} frames."
        if frame_count
        else "No timing data available."
    )

    return AgentInsight(
        agent_name="timing",
        summary=summary,
        strengths=strengths,
        issues=issues,
        suggestions=suggestions,
        confidence=0.6 if frame_count else 0.0,
    )


def _deterministic_spatial_insight(context: str) -> AgentInsight:
    """Deterministic fallback spatial insight parsed from the context."""
    dancer_lines = re.findall(
        r"#(\d+): avg=\(([\d.-]+), ([\d.-]+)\), spread=\(([\d.-]+), ([\d.-]+)\)",
        context,
    )

    strengths: list[str] = []
    issues: list[CoachIssue] = []
    suggestions: list[str] = []

    if dancer_lines:
        strengths.append(
            f"{len(dancer_lines)} dancer(s) tracked with spatial coverage data."
        )
        for tid_str, ax, ay, sx, sy in dancer_lines:
            spread = max(float(sx), float(sy))
            if spread < 0.1:
                issues.append(
                    CoachIssue(
                        description=(
                            f"Dancer #{tid_str} has minimal movement "
                            f"(spread={spread:.2f})."
                        ),
                        severity="low",
                    )
                )
        suggestions.append("Consider varying spatial positioning to improve stage coverage.")
    else:
        issues.append(
            CoachIssue(
                description="No spatial trajectory data available.",
                severity="high",
            )
        )
        suggestions.append("Ensure calibration is complete for spatial analysis.")

    summary = (
        f"Spatial data for {len(dancer_lines)} dancer(s) tracked."
        if dancer_lines
        else "No spatial data available."
    )

    return AgentInsight(
        agent_name="spatial",
        summary=summary,
        strengths=strengths,
        issues=issues,
        suggestions=suggestions,
        confidence=0.6 if dancer_lines else 0.0,
    )


def _deterministic_comparison_insight(context: str) -> AgentInsight:
    """Deterministic fallback comparison insight parsed from the context."""
    score_match = re.search(r"overall_score=([\d.]+)", context)
    match_count_match = re.search(r"Matched dancer pairs: (\d+)", context)
    overall_score = float(score_match.group(1)) if score_match else 0.0
    match_count = int(match_count_match.group(1)) if match_count_match else 0

    strengths: list[str] = []
    issues: list[CoachIssue] = []
    suggestions: list[str] = []

    if match_count > 0:
        if overall_score > 0.8:
            strengths.append(
                "High overall similarity between reference and attempt performances."
            )
        elif overall_score > 0.5:
            strengths.append("Moderate similarity between reference and attempt.")
        else:
            issues.append(
                CoachIssue(
                    description=(
                        f"Low overall similarity score ({overall_score:.2f})."
                    ),
                    severity="high",
                )
            )
        suggestions.append(
            "Focus on matching the reference dancer positions more precisely."
        )
    else:
        issues.append(
            CoachIssue(
                description="No matched dancer pairs found.",
                severity="high",
            )
        )
        suggestions.append(
            "Ensure both videos are properly calibrated for comparison."
        )

    summary = (
        f"Comparison: {match_count} matched pair(s), "
        f"overall score={overall_score:.3f}."
    )

    return AgentInsight(
        agent_name="comparison",
        summary=summary,
        strengths=strengths,
        issues=issues,
        suggestions=suggestions,
        confidence=0.6 if match_count else 0.0,
    )


_DeterministicFn = Callable[..., AgentInsight]
_DETERMINISTIC_DISPATCH: dict[str, _DeterministicFn] = {
    "formation": _deterministic_formation_insight,
    "timing": _deterministic_timing_insight,
    "spatial": _deterministic_spatial_insight,
    "comparison": _deterministic_comparison_insight,
}


# ── Overall summary ─────────────────────────────────────────────────────────


def _generate_overall_summary(insights: list[AgentInsight], mode: str) -> str:
    """Concise deterministic overall summary from agent results.

    This is assembled from the agent summaries directly — no extra LLM call.
    """
    parts = [insight.summary for insight in insights if insight.confidence > 0]
    if not parts:
        return "Coaching analysis could not be completed for any agent."
    prefix = (
        "Comparison coaching analysis: "
        if mode == "comparison"
        else "Single-video coaching analysis: "
    )
    return prefix + " | ".join(parts)


# ── Public API ───────────────────────────────────────────────────────────────


async def run_coaching(
    session_id: UUID,
    mode: str,
    result: dict[str, Any],
) -> CoachingReport:
    """Run all coaching agents concurrently and produce a ``CoachingReport``.

    Parameters
    ----------
    session_id:
        The analysis session UUID.
    mode:
        ``"single"`` or ``"comparison"``.
    result:
        The full analysis result metadata (from
        ``AnalysisResult.result_metadata``).

    Returns
    -------
    CoachingReport
        A filled report with all agent insights and an overall summary.
    """
    client = LLMClient()
    contexts = build_agent_contexts(result, mode=mode)

    agent_names = ["formation", "timing", "spatial"]
    if mode == "comparison":
        agent_names.append("comparison")

    async def _run_agent(agent_name: str) -> AgentInsight:
        context = contexts.get(agent_name, "")

        # --- deterministic path (no LLM configured) ---
        if not client.available:
            handler = _DETERMINISTIC_DISPATCH.get(agent_name)
            if handler is not None:
                return handler(context)
            return AgentInsight(
                agent_name=agent_name,
                summary="Analysis unavailable.",
                strengths=[],
                issues=[],
                suggestions=[],
                confidence=0.0,
            )

        # --- LLM path ---
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"{_AGENT_PROMPTS.get(agent_name, '')}\n\n"
                    f"Data:\n{context}\n\n"
                    "Respond with a JSON object."
                ),
            },
        ]

        try:
            raw = await asyncio.wait_for(
                client.chat_completion(messages), timeout=30.0
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Agent '%s' timed out; using deterministic fallback",
                agent_name,
            )
            handler = _DETERMINISTIC_DISPATCH.get(agent_name)
            if handler is not None:
                return handler(context)
            return AgentInsight(
                agent_name=agent_name,
                summary=f"{agent_name} analysis unavailable.",
                strengths=[],
                issues=[],
                suggestions=[],
                confidence=0.0,
            )

        if raw is None:
            logger.warning(
                "LLM returned None for agent '%s'; using deterministic fallback",
                agent_name,
            )
            handler = _DETERMINISTIC_DISPATCH.get(agent_name)
            if handler is not None:
                return handler(context)
            return AgentInsight(
                agent_name=agent_name,
                summary=f"{agent_name} analysis unavailable.",
                strengths=[],
                issues=[],
                suggestions=[],
                confidence=0.0,
            )

        return parse_agent_insight(raw, agent_name)

    # Run agents concurrently — a single failure does not block others.
    tasks = [_run_agent(name) for name in agent_names]
    insights = list(await asyncio.gather(*tasks))

    overall_summary = _generate_overall_summary(insights, mode)

    return CoachingReport(
        session_id=session_id,
        mode=mode,
        overall_summary=overall_summary,
        agents=insights,
        generated_at=datetime.now(timezone.utc),
    )


class CoachOrchestrator:
    """Convenience wrapper around ``run_coaching``.

    Usage::

        orchestrator = CoachOrchestrator()
        report = await orchestrator.generate(session_id, mode, result)
    """

    async def generate(
        self,
        session_id: UUID,
        mode: str,
        result: dict[str, Any],
    ) -> CoachingReport:
        """Generate a coaching report. Delegates to ``run_coaching``."""
        return await run_coaching(session_id, mode, result)
