from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.integrations.openai.agents import run_agentic_coaching
from app.integrations.openai.models import SpecialistOutput, SynthesisOutput
from app.services.coaching.context import CoachingContext, FormationContext, ObservationContext, TimingContext


def healthy_context(is_group=False):
    return CoachingContext(
        observation=ObservationContext(
            total_frames=10, frames_with_detections=10, frames_with_poses=10,
            max_persons_per_frame=3 if is_group else 1, total_tracks=3 if is_group else 1,
            max_concurrent_tracks=3 if is_group else 1, is_group=is_group,
            expected_dancer_count=3 if is_group else 1,
        ),
        timing=TimingContext(available=True, sample_count=10, pulse_consistency=.8),
        formation=FormationContext(enabled=is_group, available=is_group, tracked_dancers=3 if is_group else 0),
    )


@pytest.mark.asyncio
async def test_missing_key_skips_sdk():
    result = await run_agentic_coaching(
        uuid4(), healthy_context(), [], is_group=False,
        settings=Settings(openai_api_key="", llm_api_key=""),
    )
    assert result.agents == []
    assert result.integrations[0].status == "not_configured"


@pytest.mark.asyncio
async def test_observation_gate_prevents_provider_call(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("Runner must not be called")
    monkeypatch.setattr("app.integrations.openai.agents.Runner.run", forbidden)
    ctx = healthy_context()
    ctx.observation.frames_with_detections = 0
    result = await run_agentic_coaching(
        uuid4(), ctx, [], is_group=False,
        settings=Settings(openai_api_key="test", openai_model="gpt-5.4-nano"),
    )
    assert result.integrations[0].status == "fallback"
    assert result.integrations[0].fallback_reason == "observation_gate_failed"


@pytest.mark.asyncio
async def test_typed_specialists_and_synthesis(monkeypatch):
    calls = []
    async def fake_run(agent, prompt, **kwargs):
        calls.append(agent.name)
        if agent.name == "Coach Synthesis Agent":
            return SimpleNamespace(final_output=SynthesisOutput(
                overall_summary="Strong visibility; refine pulse consistency.",
                next_actions=["Repeat the transition slowly."],
            ))
        return SimpleNamespace(final_output=SpecialistOutput(
            summary=f"{agent.name} summary", strengths=["Measured baseline is usable."],
            suggestions=["Repeat once with the same framing."], confidence=.8,
        ))
    monkeypatch.setattr("app.integrations.openai.agents.Runner.run", fake_run)
    result = await run_agentic_coaching(
        uuid4(), healthy_context(), [], is_group=False,
        settings=Settings(openai_api_key="test", openai_model="gpt-5.4-nano"),
    )
    assert calls.count("Formation Agent") == 0
    assert set(calls) == {"Observation Agent", "Timing Agent", "Coach Synthesis Agent"}
    assert result.integrations[0].status == "completed"
    assert result.trace_id


@pytest.mark.asyncio
async def test_one_specialist_failure_preserves_siblings(monkeypatch):
    async def fake_run(agent, prompt, **kwargs):
        if agent.name == "Timing Agent":
            raise RuntimeError("timeout")
        if agent.name == "Coach Synthesis Agent":
            return SimpleNamespace(final_output=SynthesisOutput(overall_summary="Safe summary.", next_actions=["Retry timing."]))
        return SimpleNamespace(final_output=SpecialistOutput(summary="Visible.", confidence=.9))
    monkeypatch.setattr("app.integrations.openai.agents.Runner.run", fake_run)
    result = await run_agentic_coaching(
        uuid4(), healthy_context(), [], is_group=False,
        settings=Settings(openai_api_key="test", openai_model="gpt-5.4-nano"),
    )
    assert result.agents[0].source == "llm"
    assert result.agents[1].source == "deterministic"
    assert result.integrations[0].status == "fallback"
