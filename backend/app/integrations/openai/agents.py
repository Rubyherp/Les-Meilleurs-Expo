"""Deterministically gated specialist workflow using the OpenAI Agents SDK."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from uuid import UUID

from agents import Agent, ModelSettings, RunConfig, Runner, gen_trace_id
from openai.types.shared import Reasoning

from app.core.config import Settings
from app.integrations.models import EvidenceMoment, IntegrationRun
from app.integrations.openai.models import (
    AgenticCoachingResult, AgentRunContext, SpecialistOutput, SynthesisOutput,
)
from app.integrations.openai.prompts import FORMATION, OBSERVATION, SYNTHESIS, TIMING
from app.integrations.openai.tools import (
    get_beat_metrics, get_formation_metrics, get_observation_metrics,
    get_timing_metrics, get_tracking_quality, get_trajectory_deviations,
    get_visual_evidence,
)
from app.schemas.coaching import CoachAgent
from app.services.coaching.deterministic import (
    _formation_agent, _gated_agent, _observation_agent, _timing_agent,
    observation_allows_specialists,
)
from app.services.coaching.context import CoachingContext


def _agent(name: str, instructions: str, tools: list, model: str) -> Agent:
    return Agent(
        name=name, instructions=instructions, tools=tools, model=model,
        output_type=SpecialistOutput,
        model_settings=ModelSettings(
            reasoning=Reasoning(effort="none"), verbosity="low"
        ),
    )


def _to_coach(agent_id: int, output: SpecialistOutput, baseline: CoachAgent) -> CoachAgent:
    valid_ids = set(output.cited_evidence_ids)
    return CoachAgent(
        agent_id=agent_id, name=baseline.name, available=True, source="llm",
        summary=output.summary, strengths=output.strengths, issues=output.issues,
        suggestions=output.suggestions,
        evidence=baseline.evidence, confidence=output.confidence,
    )


async def run_agentic_coaching(
    session_id: UUID,
    ctx: CoachingContext,
    evidence: list[EvidenceMoment],
    *,
    is_group: bool,
    settings: Settings,
) -> AgenticCoachingResult:
    key = settings.openai_api_key or settings.llm_api_key
    model = settings.openai_model or settings.llm_model
    baseline_observation = _observation_agent(ctx.observation)
    if not key or not model:
        return AgenticCoachingResult(
            agents=[], overall_summary="", integrations=[IntegrationRun(
                provider="openai", product="agents-coaching", model=model or None,
                status="not_configured", fallback_reason="missing_configuration",
            )]
        )

    if not observation_allows_specialists(baseline_observation):
        reason = "Paused because the Observation Agent could not verify the video reliably."
        agents = [baseline_observation, _gated_agent(2, reason)]
        if is_group:
            agents.append(_gated_agent(3, reason))
        return AgenticCoachingResult(
            agents=agents,
            overall_summary=" ".join(a.summary for a in agents if a.available),
            coordination_notes=[reason],
            integrations=[IntegrationRun(
                provider="openai", product="agents-coaching", model=model,
                status="fallback", fallback_reason="observation_gate_failed",
            )],
        )

    # The SDK reads OPENAI_API_KEY. Set it only in process memory for this run.
    import os
    previous_key = os.environ.get("OPENAI_API_KEY")
    os.environ["OPENAI_API_KEY"] = key
    trace_id = gen_trace_id()
    run_config = RunConfig(
        workflow_name="les-meilleurs-coaching", group_id=str(session_id),
        trace_id=trace_id,
        trace_metadata={"mode": "group" if is_group else "solo", "report_version": 4, "evidence_count": len(evidence)},
        trace_include_sensitive_data=settings.openai_agents_trace_include_sensitive_data,
    )
    runtime = AgentRunContext(str(session_id), ctx, tuple(evidence[:3]))
    specifications = [
        (1, _agent("Observation Agent", OBSERVATION, [get_observation_metrics, get_tracking_quality, get_visual_evidence], model), baseline_observation),
        (2, _agent("Timing Agent", TIMING, [get_timing_metrics, get_beat_metrics, get_visual_evidence], model), _timing_agent(ctx.timing)),
    ]
    if is_group:
        specifications.append((3, _agent("Formation Agent", FORMATION, [get_formation_metrics, get_trajectory_deviations, get_visual_evidence], model), _formation_agent(ctx.formation)))

    started = time.monotonic()
    fallback_count = 0
    try:
        async def run_one(item):
            nonlocal fallback_count
            agent_id, specialist, baseline = item
            try:
                result = await asyncio.wait_for(
                    Runner.run(specialist, "Use your tools, then produce the coaching output.", context=runtime, run_config=run_config),
                    timeout=settings.openai_timeout_seconds,
                )
                output = SpecialistOutput.model_validate(result.final_output)
                return _to_coach(agent_id, output, baseline)
            except Exception:
                fallback_count += 1
                return baseline

        agents = list(await asyncio.gather(*(run_one(item) for item in specifications)))
        synthesis = Agent(
            name="Coach Synthesis Agent", instructions=SYNTHESIS, model=model,
            output_type=SynthesisOutput,
            model_settings=ModelSettings(
                reasoning=Reasoning(effort="none"), verbosity="low"
            ),
        )
        try:
            synth_result = await asyncio.wait_for(
                Runner.run(synthesis, json.dumps([a.model_dump(mode="json") for a in agents]), run_config=run_config),
                timeout=settings.openai_timeout_seconds,
            )
            overall = SynthesisOutput.model_validate(synth_result.final_output).overall_summary
        except Exception:
            fallback_count += 1
            overall = " ".join(a.summary for a in agents if a.available)
        status = "completed" if fallback_count == 0 else "fallback"
        return AgenticCoachingResult(
            agents=agents, overall_summary=overall, trace_id=trace_id,
            integrations=[IntegrationRun(
                provider="openai", product="agents-coaching", model=model, status=status,
                completed_at=datetime.now(timezone.utc),
                latency_ms=int((time.monotonic() - started) * 1000), trace_id=trace_id,
                fallback_reason=(f"{fallback_count}_stage_fallbacks" if fallback_count else None),
                metadata={"specialist_count": len(specifications)},
            )],
        )
    finally:
        if previous_key is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = previous_key
