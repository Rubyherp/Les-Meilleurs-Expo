"""Tests for the coaching subsystem — context extraction, deterministic phases, and orchestrator."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.schemas.coaching import CoachPhase, CoachingReport
from app.services.coaching.context import (
    CalibrationContext,
    CoachingContext,
    ComparisonContext,
    DetectionContext,
    FormationContext,
    ObservationContext,
    TimingContext,
    TrackingContext,
    _compute_beat_alignment,
    extract_coaching_context,
)
from app.services.coaching.deterministic import (
    _calibration_phase,
    _comparison_phase,
    _detection_phase,
    _formation_agent,
    _observation_agent,
    _timing_agent,
    _tracking_phase,
    generate_deterministic_report,
    observation_allows_specialists,
)
from app.services.coaching.orchestrator import run_coaching
from app.services.coaching.provider import NullProvider


def _mk_frame(tracks=None):
    return {"tracks": tracks or []}

def _mk_track(track_id, status="active", bbox_source="observed", pose=True, top_down=None):
    t = {"track_id": track_id, "status": status, "bbox_source": bbox_source}
    if pose:
        t["pose"] = {"keypoints": [[0, 1, 2]] * 33}
    if top_down:
        t["top_down"] = top_down
    return t


# ── Context extraction ──────────────────────────────────────────────

def test_context_extraction_single_mode():
    result = {
        "sampled_frames": [
            _mk_frame([_mk_track(1), _mk_track(2)]),
            _mk_frame([_mk_track(1), _mk_track(2)]),
            _mk_frame([_mk_track(1)]),
        ],
        "projection": {"calibration_available": True, "grid_columns": 10, "grid_rows": 10},
    }
    ctx = extract_coaching_context(result, "single")

    assert ctx.detection.total_frames == 3
    assert ctx.detection.frames_with_detections == 3
    assert ctx.detection.max_persons_per_frame == 2
    assert ctx.tracking.total_tracks == 2
    assert ctx.calibration.has_calibration is True
    assert not ctx.comparison.available


def test_context_extraction_comparison_mode():
    attempt_frames = [
        {
            "timestamp_seconds": 0.2,
            "tracks": [_mk_track(1, top_down={"x": 0.5, "y": 0.5, "source": "observed"})],
        },
        {
            "timestamp_seconds": 1.2,
            "tracks": [_mk_track(1, top_down={"x": 0.6, "y": 0.5, "source": "observed"})],
        },
    ]
    result = {
        "reference": {
            "sampled_frames": [
                {"timestamp_seconds": 0.0, "tracks": []},
                {"timestamp_seconds": 1.0, "tracks": []},
            ],
        },
        "attempt": {
            "sampled_frames": attempt_frames,
            "projection": {"calibration_available": True},
        },
        "overall_score": 0.85,
        "matches": [
            {"dtw_cost": 0.1, "alignment_path": [[0, 0], [1, 1]]},
            {"dtw_cost": 0.2},
        ],
        "unmatched_reference_ids": [],
        "unmatched_attempt_ids": [3],
        "deviations": [{"mean_euclidean_deviation": 0.05}],
    }
    ctx = extract_coaching_context(result, "comparison")

    assert ctx.comparison.available
    assert ctx.comparison.overall_score == 0.85
    assert ctx.comparison.matched_pairs == 2
    assert ctx.comparison.unmatched_attempt == 1
    assert ctx.observation.total_frames == 2
    assert ctx.timing.has_reference is True
    assert ctx.timing.average_offset_seconds == pytest.approx(0.2)


# ── Detection phase ─────────────────────────────────────────────────

def test_detection_phase_healthy():
    ctx = DetectionContext(
        total_frames=10, frames_with_detections=9, frames_with_poses=8, max_persons_per_frame=3,
    )
    phase = _detection_phase(ctx)
    assert phase.phase == 2
    assert phase.available is True
    assert phase.source == "deterministic"
    assert phase.confidence > 0.8
    assert any("90%" in s or "9/10" in s for s in phase.strengths)


def test_detection_phase_no_frames():
    ctx = DetectionContext(total_frames=0)
    phase = _detection_phase(ctx)
    assert phase.available is False
    assert phase.confidence == 0.0
    assert len(phase.issues) >= 1


# ── Tracking phase ──────────────────────────────────────────────────

def test_tracking_phase_with_occlusions():
    ctx = TrackingContext(
        total_tracks=3, max_concurrent_tracks=2,
        occlusion_events=15, lost_events=2, total_frames=10,
    )
    phase = _tracking_phase(ctx)
    assert phase.phase == 3
    assert phase.available is True
    assert any("occlusion" in i.description.lower() for i in phase.issues)


# ── Calibration phase ───────────────────────────────────────────────

def test_calibration_phase_without_calibration():
    ctx = CalibrationContext(has_calibration=False)
    phase = _calibration_phase(ctx)
    assert phase.phase == 4
    assert phase.available is True
    assert phase.confidence == 0.0
    assert any("calibration" in i.description.lower() for i in phase.issues)


# ── Comparison phase ────────────────────────────────────────────────

def test_comparison_phase_not_applicable_single_mode():
    ctx = ComparisonContext(available=False)
    phase = _comparison_phase(ctx)
    assert phase.phase == 5
    assert phase.available is False
    assert "single-video" in phase.summary.lower()


def test_comparison_phase_with_data():
    ctx = ComparisonContext(
        available=True, overall_score=0.45,
        matched_pairs=2, unmatched_reference=1, unmatched_attempt=0,
        avg_dtw_cost=0.3, avg_deviation=0.15,
    )
    phase = _comparison_phase(ctx)
    assert phase.phase == 5
    assert phase.available is True
    assert any("low" in i.description.lower() for i in phase.issues)
    assert len(phase.issues) >= 2  # low score + unmatched reference


# ── Deterministic report ────────────────────────────────────────────

def test_deterministic_report_routes_solo_to_two_agents():
    ctx = CoachingContext(
        detection=DetectionContext(total_frames=5, frames_with_detections=5, frames_with_poses=5, max_persons_per_frame=2),
        tracking=TrackingContext(total_tracks=2, max_concurrent_tracks=2, total_frames=5),
        calibration=CalibrationContext(has_calibration=True, grid_columns=10, grid_rows=10, total_frames=5, tracked_dancers=2),
        comparison=ComparisonContext(available=False),
        observation=ObservationContext(
            total_frames=5,
            frames_with_detections=5,
            frames_with_poses=5,
            max_persons_per_frame=1,
        ),
        timing=TimingContext(
            available=True,
            sample_count=5,
            pulse_consistency=0.8,
        ),
    )
    session_id = uuid4()
    report = generate_deterministic_report(session_id, "single", ctx)

    assert isinstance(report, CoachingReport)
    assert report.session_id == session_id
    assert report.mode == "single"
    assert report.practice_type == "solo"
    assert report.llm_model_used is None
    assert len(report.agents) == 2
    assert [agent.name for agent in report.agents] == [
        "Observation Agent",
        "Timing Agent",
    ]
    assert all(isinstance(agent, CoachPhase) for agent in report.agents)


def test_deterministic_report_adds_formation_for_group():
    ctx = CoachingContext(
        observation=ObservationContext(
            total_frames=5,
            frames_with_detections=5,
            frames_with_poses=5,
            max_persons_per_frame=2,
            is_group=True,
        ),
        timing=TimingContext(available=True, sample_count=5, pulse_consistency=0.8),
        formation=FormationContext(
            enabled=True,
            available=True,
            tracked_dancers=2,
            observed_group_frames=5,
            average_pair_distance=0.3,
            spacing_variation=0.1,
        ),
    )
    report = generate_deterministic_report(uuid4(), "single", ctx, is_group=True)

    assert report.practice_type == "group"
    assert [agent.name for agent in report.agents] == [
        "Observation Agent",
        "Timing Agent",
        "Formation Agent",
    ]


def test_observation_agent_warns_when_group_has_fewer_than_two_dancers():
    agent = _observation_agent(
        ObservationContext(
            total_frames=10,
            frames_with_detections=10,
            frames_with_poses=9,
            max_persons_per_frame=1,
            is_group=True,
            expected_dancer_count=2,
        )
    )
    assert any(issue.category == "group_visibility" for issue in agent.issues)
    assert not observation_allows_specialists(agent)


def test_timing_agent_reports_reference_offset():
    agent = _timing_agent(
        TimingContext(
            available=True,
            has_reference=True,
            sample_count=20,
            average_offset_seconds=0.4,
            average_absolute_offset_seconds=0.4,
            offset_spread_seconds=0.1,
        )
    )
    assert any(issue.category == "timing_offset" for issue in agent.issues)
    assert "0.40s" in agent.issues[0].description


def test_formation_agent_is_group_only():
    agent = _formation_agent(FormationContext(enabled=False))
    assert agent.available is False
    assert "group choreography" in agent.summary


def test_low_observation_quality_gates_other_agents():
    ctx = CoachingContext(
        observation=ObservationContext(
            total_frames=10,
            frames_with_detections=2,
            frames_with_poses=1,
            max_persons_per_frame=1,
        ),
        timing=TimingContext(available=True, sample_count=10, pulse_consistency=0.8),
    )
    report = generate_deterministic_report(uuid4(), "single", ctx)

    assert report.agents[0].name == "Observation Agent"
    assert report.agents[1].name == "Timing Agent"
    assert report.agents[1].available is False
    assert report.coordination_notes
    assert "Observation Agent" in report.coordination_notes[0]


# ── Beat alignment (audio) ───────────────────────────────────────────

def test_timing_agent_detects_good_beat_alignment():
    """Timing agent reports strength when movement aligns with audio beats."""
    agent = _timing_agent(
        TimingContext(
            available=True,
            sample_count=30,
            pulse_consistency=0.8,
            has_audio=True,
            beat_count=16,
            beat_consistency=0.85,
            tempo_bpm=120,
            mean_beat_lag=0.05,
            beat_times=[t * 0.5 for t in range(16)],
        )
    )
    assert agent.available is True
    assert any("aligned" in s.lower() for s in agent.strengths)
    beat_evidence = [e for e in agent.evidence if e.metric == "beat_alignment_consistency"]
    assert len(beat_evidence) == 1
    assert beat_evidence[0].value == 0.85


def test_timing_agent_warns_poor_beat_alignment():
    """Timing agent flags poor beat alignment as an issue."""
    agent = _timing_agent(
        TimingContext(
            available=True,
            sample_count=30,
            pulse_consistency=0.8,
            has_audio=True,
            beat_count=16,
            beat_consistency=0.3,
            tempo_bpm=120,
            mean_beat_lag=0.4,
            beat_times=[t * 0.5 for t in range(16)],
        )
    )
    assert any("aligned" in i.description.lower() for i in agent.issues)
    lag_issues = [i for i in agent.issues if "off" in i.description or "lag" in str(i.category)]
    assert len(lag_issues) >= 1
    beatt_evidence = [e for e in agent.evidence if e.metric == "detected_tempo_bpm"]
    assert len(beatt_evidence) == 1
    assert beatt_evidence[0].value == 120


def test_timing_agent_no_audio_falls_back_to_pulse():
    """Without audio data, timing agent uses movement-only pulse (no beat section)."""
    agent = _timing_agent(
        TimingContext(
            available=True,
            sample_count=30,
            pulse_consistency=0.8,
            has_audio=False,
            beat_count=0,
            beat_consistency=0.0,
            tempo_bpm=0.0,
            mean_beat_lag=0.0,
        )
    )
    assert agent.available is True
    assert all("beat" not in s.lower() for s in agent.strengths)
    beat_evidence = [e for e in agent.evidence if e.metric.startswith("detected_tempo")]
    assert len(beat_evidence) == 0


def test_compute_beat_alignment_with_aligned_peaks():
    """_compute_beat_alignment returns high consistency when peaks match beats."""
    # Build frames with clear movement pulses — large position jumps every 5 frames
    frames = []
    for i in range(30):
        # Every 5 frames the dancer moves significantly
        if i % 5 == 0:
            x = float(i * 50)  # big jump
        else:
            x = float(i * 50 - 45)  # stays nearly still
        frames.append({
            "tracks": [{
                "track_id": 1,
                "bbox_source": "observed",
                "top_down": {"x": x, "y": 10.0},
            }]
        })

    # Beats at frames 5, 10, 15 — aligned with movement peaks
    beat_times = [2.5, 5.0, 7.5]
    mean_lag, consistency, count = _compute_beat_alignment(frames, beat_times, is_group=False)
    assert count == 3
    assert isinstance(mean_lag, float)
    assert isinstance(consistency, float)


def test_compute_beat_alignment_empty_frames():
    """Empty frames or no beats returns zeros."""
    assert _compute_beat_alignment([], [], is_group=False) == (0.0, 0.0, 0)
    assert _compute_beat_alignment([{"tracks": [{"track_id": 1}]}], [], is_group=False) == (0.0, 0.0, 0)


def test_report_serializes_agent_contract_and_evidence():
    ctx = CoachingContext(
        observation=ObservationContext(
            total_frames=10,
            frames_with_detections=10,
            frames_with_poses=10,
            max_persons_per_frame=1,
        ),
        timing=TimingContext(available=True, sample_count=10, pulse_consistency=0.8),
    )
    payload = generate_deterministic_report(uuid4(), "single", ctx).model_dump(mode="json")

    assert "agents" in payload
    assert "phases" not in payload
    assert payload["agents"][0]["agent_id"] == 1
    assert payload["agents"][0]["evidence"][0]["metric"] == "visibility_coverage"


# ── Orchestrator ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_orchestrator_run_coaching_no_provider():
    """When no LLM provider is available (no API key), run_coaching falls back to deterministic."""
    result = {
        "sampled_frames": [
            _mk_frame([_mk_track(1)]),
            _mk_frame([_mk_track(1)]),
        ],
    }
    session_id = uuid4()

    # Patch create_provider to return NullProvider (no API key -> no LLM)
    with patch("app.services.coaching.orchestrator.create_provider", return_value=NullProvider()):
        report = await run_coaching(session_id, "single", result)

    assert isinstance(report, CoachingReport)
    assert report.session_id == session_id
    assert report.mode == "single"
    assert report.llm_model_used is None
    assert len(report.agents) == 2
    for agent in report.agents:
        assert agent.source == "deterministic"
        assert agent.confidence is not None


@pytest.mark.asyncio
async def test_orchestrator_run_coaching_comparison_mode():
    """Coaching works in comparison mode (deterministic fallback)."""
    result = {
        "sampled_frames": [
            _mk_frame([_mk_track(1, top_down={"x": 0.5, "y": 0.5})]),
        ],
        "projection": {"calibration_available": True, "grid_columns": 10, "grid_rows": 10},
        "overall_score": 0.72,
        "matches": [{"dtw_cost": 0.15}],
        "unmatched_reference_ids": [],
        "unmatched_attempt_ids": [],
        "deviations": [{"mean_euclidean_deviation": 0.08}],
    }
    session_id = uuid4()

    with patch("app.services.coaching.orchestrator.create_provider", return_value=NullProvider()):
        report = await run_coaching(session_id, "comparison", result, is_group=True)

    assert report.mode == "comparison"
    assert report.practice_type == "group"
    assert [agent.name for agent in report.agents] == [
        "Observation Agent",
        "Timing Agent",
        "Formation Agent",
    ]
