"""Pure-function deterministic reports for the coaching specialists."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.schemas.coaching import (
    CoachAgent,
    CoachEvidence,
    CoachIssue,
    CoachPhase,
    CoachingReport,
)
from app.services.coaching.context import (
    CalibrationContext,
    CoachingContext,
    ComparisonContext,
    DetectionContext,
    FormationContext,
    ObservationContext,
    TimingContext,
    TrackingContext,
)

__all__ = [
    "generate_deterministic_report",
    "_observation_agent",
    "_timing_agent",
    "_formation_agent",
    "_gated_agent",
    "observation_allows_specialists",
]


_PHASE_NAMES: dict[int, str] = {
    2: "Camera & Visibility",
    3: "Movement Flow",
    4: "Space Usage",
    5: "Performance Match",
}

_AGENT_NAMES: dict[int, str] = {
    1: "Observation Agent",
    2: "Timing Agent",
    3: "Formation Agent",
}

_OBSERVATION_GATE_THRESHOLD = 0.55


def observation_allows_specialists(observation: CoachAgent) -> bool:
    blocking_categories = {"visibility", "tracking", "group_visibility"}
    has_blocking_issue = any(
        issue.severity == "high" and issue.category in blocking_categories
        for issue in observation.issues
    )
    return (
        observation.available
        and observation.confidence >= _OBSERVATION_GATE_THRESHOLD
        and not has_blocking_issue
    )


def _gated_agent(agent_num: int, reason: str) -> CoachPhase:
    return CoachPhase(
        phase=agent_num,
        name=_AGENT_NAMES[agent_num],
        available=False,
        source="deterministic",
        summary=reason,
        suggestions=["Improve camera visibility, then run the coaching team again."],
        confidence=0.0,
    )


def _observation_agent(ctx: ObservationContext) -> CoachPhase:
    if ctx.total_frames == 0:
        return CoachPhase(
            phase=1,
            name=_AGENT_NAMES[1],
            available=False,
            source="deterministic",
            summary="There were no sampled frames for the observation agent to inspect.",
            issues=[CoachIssue(description="No visual observations were available.")],
            suggestions=["Record another take with the dancers fully visible."],
            confidence=0.0,
        )

    detection_coverage = ctx.frames_with_detections / max(1, ctx.total_frames)
    pose_coverage = ctx.frames_with_poses / max(1, ctx.total_frames)
    observation_slots = ctx.total_frames * max(1, ctx.max_concurrent_tracks)
    occlusion_rate = ctx.occlusion_events / max(1, observation_slots)
    loss_rate = ctx.lost_events / max(1, observation_slots)
    strengths: list[str] = []
    issues: list[CoachIssue] = []
    suggestions: list[str] = []

    if detection_coverage >= 0.85:
        strengths.append(f"Dancers stayed visible in {detection_coverage:.0%} of sampled moments.")
    elif detection_coverage < 0.6:
        issues.append(
            CoachIssue(
                description=f"Camera visibility dropped to {detection_coverage:.0%}.",
                severity="high",
                category="visibility",
            )
        )
        suggestions.append("Use a wider, steadier camera angle with even lighting.")

    if pose_coverage >= 0.75:
        strengths.append(f"Body movement was readable in {pose_coverage:.0%} of sampled moments.")
    elif pose_coverage < 0.4:
        issues.append(
            CoachIssue(
                description=f"Full-body movement was readable in only {pose_coverage:.0%} of moments.",
                severity="medium",
                category="pose",
            )
        )
        suggestions.append("Keep heads and feet inside the frame and reduce dancer overlap.")

    if ctx.is_group and ctx.max_persons_per_frame < ctx.expected_dancer_count:
        missing_count = ctx.expected_dancer_count - ctx.max_persons_per_frame
        issues.append(
            CoachIssue(
                description=(
                    f"Expected {ctx.expected_dancer_count} dancers, but only "
                    f"{ctx.max_persons_per_frame} were visible together "
                    f"({missing_count} missing)."
                ),
                severity="high",
                category="group_visibility",
            )
        )
        suggestions.append("Reframe the camera so every expected dancer remains visible.")
    elif ctx.is_group:
        strengths.append(f"Observed up to {ctx.max_persons_per_frame} dancers together.")

    if occlusion_rate > 0.25:
        issues.append(
            CoachIssue(
                description=f"Dancers overlapped in {occlusion_rate:.0%} of tracked observations.",
                severity="medium",
                category="occlusion",
            )
        )
        suggestions.append("Raise or widen the camera angle to reduce dancers blocking one another.")

    if loss_rate > 0.1:
        issues.append(
            CoachIssue(
                description=f"Tracking was lost in {loss_rate:.0%} of observations.",
                severity="high" if loss_rate > 0.2 else "medium",
                category="tracking",
            )
        )
        suggestions.append("Keep lighting and camera position stable throughout the take.")

    if not issues:
        suggestions.append("Observation quality is strong enough for dependable coaching feedback.")

    confidence = (
        0.45 * detection_coverage
        + 0.35 * pose_coverage
        + 0.2 * max(0.0, 1.0 - min(1.0, occlusion_rate + loss_rate))
    )
    return CoachPhase(
        phase=1,
        name=_AGENT_NAMES[1],
        available=True,
        source="deterministic",
        summary=(
            f"Visibility {detection_coverage:.0%}, body-read coverage {pose_coverage:.0%}, "
            f"with up to {ctx.max_persons_per_frame} dancer(s) visible together."
        ),
        strengths=strengths,
        issues=issues,
        suggestions=suggestions,
        evidence=[
            CoachEvidence(
                metric="visibility_coverage",
                value=round(detection_coverage, 3),
                unit="ratio",
            ),
            CoachEvidence(
                metric="pose_coverage",
                value=round(pose_coverage, 3),
                unit="ratio",
            ),
            CoachEvidence(
                metric="max_visible_dancers",
                value=ctx.max_persons_per_frame,
                unit="dancers",
            ),
        ],
        confidence=round(max(0.0, min(1.0, confidence)), 2),
    )


def _timing_agent(ctx: TimingContext) -> CoachPhase:
    if not ctx.available:
        return CoachPhase(
            phase=2,
            name=_AGENT_NAMES[2],
            available=False,
            source="deterministic",
            summary="There was not enough continuous movement data to estimate timing.",
            issues=[CoachIssue(description="Timing needs a longer stretch of visible movement.")],
            suggestions=["Record a longer take with continuous full-body visibility."],
            confidence=0.0,
        )

    strengths: list[str] = []
    issues: list[CoachIssue] = []
    suggestions: list[str] = []

    if ctx.has_reference:
        offset = ctx.average_offset_seconds
        absolute_offset = ctx.average_absolute_offset_seconds
        if absolute_offset <= 0.12:
            strengths.append("Movement checkpoints stayed closely aligned with the reference.")
        elif absolute_offset >= 0.35:
            direction = "behind" if offset > 0.08 else "ahead of" if offset < -0.08 else "around"
            issues.append(
                CoachIssue(
                    description=f"Movement landed about {absolute_offset:.2f}s {direction} the reference.",
                    severity="high",
                    category="timing_offset",
                )
            )
            suggestions.append("Rehearse at reduced speed, then return to full tempo.")
        else:
            direction = "late" if offset > 0.08 else "early" if offset < -0.08 else "variable"
            issues.append(
                CoachIssue(
                    description=f"Timing was {direction}, averaging {absolute_offset:.2f}s from the reference.",
                    severity="medium",
                    category="timing_offset",
                )
            )
            suggestions.append("Mark the main movement accents and aim to land each one with the reference.")

        if ctx.offset_spread_seconds <= 0.15:
            strengths.append("Timing stayed consistent across the analysed sequence.")
        elif ctx.offset_spread_seconds > 0.35:
            issues.append(
                CoachIssue(
                    description=f"Timing varied by about {ctx.offset_spread_seconds:.2f}s across the routine.",
                    severity="medium",
                    category="timing_consistency",
                )
            )
            suggestions.append("Loop the least consistent phrase before running the full take.")
    else:
        if ctx.pulse_consistency >= 0.7:
            strengths.append("Movement accents repeated at a steady pace.")
        elif ctx.pulse_consistency < 0.45:
            issues.append(
                CoachIssue(
                    description="Movement accents varied noticeably in pace.",
                    severity="medium",
                    category="pulse_consistency",
                )
            )
            suggestions.append("Practice with a count or metronome to make movement accents more even.")
        else:
            suggestions.append("Add a reference take to measure early and late timing directly.")

    if ctx.group_sync_score is not None:
        if ctx.group_sync_score >= 0.75:
            strengths.append("The group changed speed together.")
        elif ctx.group_sync_score < 0.5:
            issues.append(
                CoachIssue(
                    description="Dancers accelerated and slowed at different moments.",
                    severity="medium",
                    category="group_sync",
                )
            )
            suggestions.append("Choose shared count landmarks for starts, stops, and direction changes.")

    # ---- Beat-aware timing feedback (new) ----
    if ctx.has_audio and ctx.beat_count > 0:
        if ctx.beat_consistency >= 0.7:
            strengths.append(
                f"Movement peaks aligned with {ctx.beat_consistency:.0%} of the detected beats "
                f"(tempo: {ctx.tempo_bpm:.0f} BPM)."
            )
        elif ctx.beat_consistency >= 0.4:
            suggestions.append(
                "Practice hitting the main accents on the beat — "
                "about half the movement peaks lined up with the music."
            )
        else:
            issues.append(
                CoachIssue(
                    description=(
                        f"Only {ctx.beat_consistency:.0%} of movement peaks "
                        f"aligned with the music beats (tempo: {ctx.tempo_bpm:.0f} BPM)."
                    ),
                    severity="medium",
                    category="beat_alignment",
                )
            )
            suggestions.append(
                "Count the music out loud first, then match your accents to the downbeats."
            )

        if ctx.mean_beat_lag > 0.25:
            issues.append(
                CoachIssue(
                    description=(
                        f"Movement was about {ctx.mean_beat_lag:.2f}s off from the nearest beat."
                    ),
                    severity="medium",
                    category="beat_lag",
                )
            )
            suggestions.append("Try tapping along with the beat before dancing full-out.")

    confidence = min(1.0, 0.45 + min(ctx.sample_count, 30) / 60)
    if not ctx.has_reference:
        confidence = min(confidence, 0.75)
    return CoachPhase(
        phase=2,
        name=_AGENT_NAMES[2],
        available=True,
        source="deterministic",
        summary=(
            f"Reference timing offset averaged {ctx.average_absolute_offset_seconds:.2f}s."
            if ctx.has_reference
            else f"Movement pulse consistency measured {ctx.pulse_consistency:.0%} without a reference."
        )
        + (
            f" Beat alignment: {ctx.beat_consistency:.0%} at {ctx.tempo_bpm:.0f} BPM."
            if ctx.has_audio
            else ""
        ),
        strengths=strengths,
        issues=issues,
        suggestions=suggestions,
        evidence=(
            [
                CoachEvidence(
                    metric="average_reference_offset",
                    value=ctx.average_absolute_offset_seconds,
                    unit="seconds",
                ),
                CoachEvidence(
                    metric="timing_offset_spread",
                    value=ctx.offset_spread_seconds,
                    unit="seconds",
                ),
            ]
            if ctx.has_reference
            else [
                CoachEvidence(
                    metric="movement_pulse_consistency",
                    value=ctx.pulse_consistency,
                    unit="ratio",
                )
            ]
        )
        + (
            [
                CoachEvidence(
                    metric="group_sync_score",
                    value=ctx.group_sync_score,
                    unit="ratio",
                )
            ]
            if ctx.group_sync_score is not None
            else []
        )
        + (
            [
                CoachEvidence(
                    metric="detected_tempo_bpm",
                    value=ctx.tempo_bpm,
                    unit="bpm",
                ),
                CoachEvidence(
                    metric="beat_alignment_consistency",
                    value=ctx.beat_consistency,
                    unit="ratio",
                ),
                CoachEvidence(
                    metric="mean_beat_lag",
                    value=ctx.mean_beat_lag,
                    unit="seconds",
                ),
            ]
            if ctx.has_audio
            else []
        ),
        confidence=round(confidence, 2),
    )


def _formation_agent(ctx: FormationContext) -> CoachPhase:
    if not ctx.enabled:
        return CoachPhase(
            phase=3,
            name=_AGENT_NAMES[3],
            available=False,
            source="deterministic",
            summary="Formation coaching is only used for group choreography.",
            confidence=0.0,
        )
    if not ctx.available:
        return CoachPhase(
            phase=3,
            name=_AGENT_NAMES[3],
            available=False,
            source="deterministic",
            summary="Fewer than two dancers had usable floor positions at the same time.",
            issues=[CoachIssue(description="The group formation could not be measured.")],
            suggestions=["Keep at least two dancers visible and confirm the floor calibration."],
            confidence=0.0,
        )

    strengths: list[str] = []
    issues: list[CoachIssue] = []
    suggestions: list[str] = []

    if ctx.spacing_variation <= 0.2:
        strengths.append("Relative spacing stayed stable as the group moved.")
    elif ctx.spacing_variation >= 0.45:
        issues.append(
            CoachIssue(
                description=f"Spacing changed substantially across the take ({ctx.spacing_variation:.0%} variation).",
                severity="high",
                category="spacing",
            )
        )
        suggestions.append("Assign each dancer a floor landmark and check spacing at every transition.")
    else:
        issues.append(
            CoachIssue(
                description=f"Group spacing drifted during transitions ({ctx.spacing_variation:.0%} variation).",
                severity="medium",
                category="spacing",
            )
        )
        suggestions.append("Freeze at formation checkpoints and correct spacing before continuing.")

    if ctx.close_spacing_rate > 0.2:
        issues.append(
            CoachIssue(
                description=f"Dancers came very close together in {ctx.close_spacing_rate:.0%} of measured pair positions.",
                severity="medium",
                category="crowding",
            )
        )
        suggestions.append("Widen the tightest pathway or stagger crossing times.")
    else:
        strengths.append("The group generally maintained enough separation.")

    if ctx.reference_match_score is not None:
        if ctx.reference_match_score >= 0.8:
            strengths.append("The group's paths closely matched the reference formation.")
        elif ctx.reference_match_score < 0.5:
            issues.append(
                CoachIssue(
                    description="The group's spatial paths differ substantially from the reference.",
                    severity="high",
                    category="formation_match",
                )
            )
            suggestions.append("Compare one formation checkpoint at a time before joining the full sequence.")

    confidence = min(1.0, 0.5 + ctx.observed_group_frames / 40)
    return CoachPhase(
        phase=3,
        name=_AGENT_NAMES[3],
        available=True,
        source="deterministic",
        summary=(
            f"Tracked {ctx.tracked_dancers} dancers together across {ctx.observed_group_frames} moments; "
            f"spacing variation was {ctx.spacing_variation:.0%}."
        ),
        strengths=strengths,
        issues=issues,
        suggestions=suggestions,
        evidence=[
            CoachEvidence(
                metric="spacing_variation",
                value=ctx.spacing_variation,
                unit="ratio",
            ),
            CoachEvidence(
                metric="close_spacing_rate",
                value=ctx.close_spacing_rate,
                unit="ratio",
            ),
            CoachEvidence(
                metric="tracked_dancers",
                value=ctx.tracked_dancers,
                unit="dancers",
            ),
        ],
        confidence=round(confidence, 2),
    )


def _detection_phase(ctx: DetectionContext) -> CoachPhase:
    if ctx.total_frames == 0:
        return CoachPhase(
            phase=2,
            name=_PHASE_NAMES[2],
            available=False,
            source="deterministic",
            summary="No video frames were sampled. Visibility analysis is unavailable.",
            issues=[CoachIssue(description="No sampled moments to check visibility.")],
            confidence=0.0,
        )

    coverage = ctx.frames_with_detections / max(1, ctx.total_frames)
    pose_coverage = ctx.frames_with_poses / max(1, ctx.total_frames)

    strengths: list[str] = []
    issues: list[CoachIssue] = []
    suggestions: list[str] = []

    if coverage >= 0.8:
        strengths.append(
            f"Great camera visibility — you showed up clearly in {ctx.frames_with_detections}/{ctx.total_frames} moments "
            f"({coverage:.0%})"
        )
    elif coverage >= 0.5:
        suggestions.append(
            f"Camera visibility is at {coverage:.0%}. Try adjusting the camera angle or "
            "lighting so you're easier to see."
        )
    else:
        issues.append(
            CoachIssue(
                description=f"Low camera visibility — you were only caught in {coverage:.0%} of the moments.",
                severity="high",
                category="visibility",
            )
        )
        suggestions.append(
            "Try brighter lighting, smoother movements, or repositioning the camera so it catches you clearly."
        )

    if pose_coverage >= 0.8:
        strengths.append(
            f"Body recognition worked well — your movement was captured in {ctx.frames_with_poses}/{ctx.total_frames} moments "
            f"({pose_coverage:.0%})"
        )
    elif pose_coverage < 0.3 and ctx.frames_with_detections > 0:
        issues.append(
            CoachIssue(
                description=f"Movement data is limited — body recognition worked in only {pose_coverage:.0%} of moments.",
                severity="medium",
                category="pose",
            )
        )
        suggestions.append(
            "Make sure you're filling enough of the frame and not blocked by anything for better movement capture."
        )

    strengths.append(
        f"Up to {ctx.max_persons_per_frame} dancer(s) spotted at once."
    )

    summary = (
        f"You were clearly visible in {ctx.frames_with_detections} out of {ctx.total_frames} sampled moments "
        f"({coverage:.0%}), with up to {ctx.max_persons_per_frame} dancer(s) at a time. "
        f"Movement data captured in {ctx.frames_with_poses}/{ctx.total_frames} moments "
        f"({pose_coverage:.0%})."
    )

    return CoachPhase(
        phase=2,
        name=_PHASE_NAMES[2],
        available=True,
        source="deterministic",
        summary=summary,
        strengths=strengths,
        issues=issues,
        suggestions=suggestions,
        confidence=round(max(coverage, pose_coverage), 2),
    )


def _tracking_phase(ctx: TrackingContext) -> CoachPhase:
    if ctx.total_frames == 0:
        return CoachPhase(
            phase=3,
            name=_PHASE_NAMES[3],
            available=False,
            source="deterministic",
            summary="No movement following data available because no frames were sampled.",
            issues=[CoachIssue(description="No sampled moments to analyse.")],
            confidence=0.0,
        )

    strengths: list[str] = []
    issues: list[CoachIssue] = []
    suggestions: list[str] = []

    total_events = ctx.occlusion_events + ctx.lost_events
    total_track_observations = ctx.total_frames * max(1, ctx.max_concurrent_tracks)
    occlusion_rate = ctx.occlusion_events / max(1, total_track_observations)
    loss_rate = ctx.lost_events / max(1, total_track_observations)

    if ctx.total_tracks <= 1:
        strengths.append("No who-is-who confusion — just one dancer throughout.")
    else:
        strengths.append(f"Followed {ctx.total_tracks} unique dancer(s) across the routine.")

    if ctx.max_concurrent_tracks >= 1:
        strengths.append(
            f"Up to {ctx.max_concurrent_tracks} dancers followed at the same time."
        )

    if occlusion_rate > 0.3:
        issues.append(
            CoachIssue(
                description=f"Quite a bit of occlusion — dancers overlapped in {occlusion_rate:.0%} of the observed moments.",
                severity="medium",
                category="flow",
            )
        )
        suggestions.append(
            "Try a wider camera angle or a higher viewpoint so dancers overlap less."
        )

    if loss_rate > 0.1:
        issues.append(
            CoachIssue(
                description=f"Lost track of you in {ctx.lost_events} moment(s).",
                severity="high" if loss_rate > 0.2 else "medium",
                category="flow",
            )
        )
        suggestions.append(
            "Keep lighting even and avoid long overlaps — losing track can confuse who is who."
        )

    if not issues:
        suggestions.append(
            "Movement following stayed smooth. No major overlaps or lost moments detected."
        )

    summary = (
        f"Followed {ctx.total_tracks} dancer(s) with up to {ctx.max_concurrent_tracks} at once. "
        f"Overlap rate: {occlusion_rate:.0%}, lost-track rate: {loss_rate:.0%}."
    )

    return CoachPhase(
        phase=3,
        name=_PHASE_NAMES[3],
        available=True,
        source="deterministic",
        summary=summary,
        strengths=strengths,
        issues=issues,
        suggestions=suggestions,
        confidence=round(1.0 - min(occlusion_rate + loss_rate, 1.0), 2),
    )


def _calibration_phase(ctx: CalibrationContext) -> CoachPhase:
    if not ctx.has_calibration:
        return CoachPhase(
            phase=4,
            name=_PHASE_NAMES[4],
            available=True,
            source="deterministic",
            summary="No practice space markers were set up for this session. Space analysis is not available.",
            strengths=[],
            issues=[
                CoachIssue(
                    description="Floor calibration and practice space markers haven't been set up yet.",
                    severity="high",
                    category="space",
                )
            ],
            suggestions=[
                "Set space markers via the setup tool using four points on the floor to map out your practice area."
            ],
            confidence=0.0,
        )

    strengths: list[str] = []
    issues: list[CoachIssue] = []
    suggestions: list[str] = []
    projection_coverage = ctx.frames_with_projection / max(1, ctx.total_frames)

    strengths.append(
        f"Practice space is set up with a {ctx.grid_columns}x{ctx.grid_rows} practice grid."
    )

    if ctx.tracked_dancers > 0:
        strengths.append(
            f"Following {ctx.tracked_dancers} dancer(s) in the mapped practice space."
        )
        if projection_coverage >= 0.7:
            strengths.append(
                f"Good floor mapping coverage — your position was mapped in {projection_coverage:.0%} of moments."
            )
        elif projection_coverage < 0.3:
            issues.append(
                CoachIssue(
                    description=f"Low floor mapping coverage — only {projection_coverage:.0%} of moments were mapped to the floor.",
                    severity="medium",
                    category="space",
                )
            )
            suggestions.append(
                "Try to stay within the marked practice area so your movement path can be fully mapped."
            )

        strengths.append(
            f"Average movement path length: {ctx.avg_trajectory_length:.1f} moments."
        )
    else:
        issues.append(
            CoachIssue(
                description="No dancers were followed in the practice space.",
                severity="medium",
                category="space",
            )
        )
        suggestions.append(
            "Step into the marked practice area so we can analyse your space usage."
        )

    summary = (
        f"Practice space is {'set up' if ctx.has_calibration else 'not set up'}. "
        f"{ctx.tracked_dancers} dancer(s) followed in the {ctx.grid_columns}x{ctx.grid_rows} practice grid "
        f"across {ctx.frames_with_projection}/{ctx.total_frames} moments."
    )

    return CoachPhase(
        phase=4,
        name=_PHASE_NAMES[4],
        available=True,
        source="deterministic",
        summary=summary,
        strengths=strengths,
        issues=issues,
        suggestions=suggestions,
        confidence=round(min(projection_coverage if ctx.tracked_dancers > 0 else 0.0, 1.0), 2)
        if ctx.has_calibration
        else 0.0,
    )


def _comparison_phase(ctx: ComparisonContext) -> CoachPhase:
    if not ctx.available:
        return CoachPhase(
            phase=5,
            name=_PHASE_NAMES[5],
            available=False,
            source="deterministic",
            summary="Not applicable (single-video mode). Performance match data is only available "
            "with both a reference and an attempt video to compare.",
            confidence=0.0,
        )

    strengths: list[str] = []
    issues: list[CoachIssue] = []
    suggestions: list[str] = []

    score = ctx.overall_score
    if score >= 0.8:
        strengths.append(
            f"Excellent match score: {score:.2f}. Your performance closely matches the reference. Great work!"
        )
    elif score < 0.5:
        issues.append(
            CoachIssue(
                description=f"Overall match score is a bit low: {score:.2f}.",
                severity="high",
                category="match",
            )
        )
        suggestions.append(
            "Check the comparison details to spot which moments or dancers had the biggest differences."
        )
    else:
        strengths.append(
            f"Decent match score: {score:.2f}. Some differences from the reference, but you're on the right track."
        )
        suggestions.append(
            "Focus on the dancers and parts with the biggest differences for targeted practice."
        )

    if ctx.matched_pairs > 0:
        strengths.append(
            f"Matched {ctx.matched_pairs} dancer pair(s) between reference and your performance."
        )
        strengths.append(
            f"Movement similarity score: {ctx.avg_dtw_cost:.4f}, average difference: "
            f"{ctx.avg_deviation:.4f}."
        )
    else:
        issues.append(
            CoachIssue(
                description="No dancer pairs were matched between the reference and your performance.",
                severity="high",
                category="match",
            )
        )
        suggestions.append(
            "Make sure both videos contain the same dancers and a similar routine."
        )

    if ctx.unmatched_reference > 0 or ctx.unmatched_attempt > 0:
        if ctx.unmatched_reference > 0:
            issues.append(
                CoachIssue(
                    description=f"{ctx.unmatched_reference} dancer(s) in the reference "
                    "couldn't be matched with your performance.",
                    severity="medium",
                    category="match",
                )
            )
        if ctx.unmatched_attempt > 0:
            issues.append(
                CoachIssue(
                    description=f"{ctx.unmatched_attempt} dancer(s) in your performance "
                    "couldn't be matched with the reference.",
                    severity="medium",
                    category="match",
                )
            )
        suggestions.append(
            "Make sure the same number of dancers perform in both videos."
        )

    summary = (
        f"Performance match with {ctx.matched_pairs} paired dancer(s). "
        f"Overall match score: {score:.4f}. "
        f"Unmatched: {ctx.unmatched_reference} in reference, {ctx.unmatched_attempt} in your performance."
    )

    return CoachPhase(
        phase=5,
        name=_PHASE_NAMES[5],
        available=True,
        source="deterministic",
        summary=summary,
        strengths=strengths,
        issues=issues,
        suggestions=suggestions,
        confidence=round(score, 2),
    )


def generate_deterministic_report(
    session_id: UUID,
    mode: str,
    ctx: CoachingContext,
    *,
    is_group: bool = False,
) -> CoachingReport:
    """Generate specialist-agent insights deterministically. No LLM needed."""
    observation = _observation_agent(ctx.observation)
    agents = [observation]
    coordination_notes: list[str] = []
    if observation_allows_specialists(observation):
        agents.append(_timing_agent(ctx.timing))
        if is_group:
            agents.append(_formation_agent(ctx.formation))
    else:
        reason = "Paused because the Observation Agent could not verify the video reliably."
        coordination_notes.append(reason)
        agents.append(_gated_agent(2, reason))
        if is_group:
            agents.append(_gated_agent(3, reason))

    available_summaries = [agent.summary for agent in agents if agent.available]
    practice_label = "Group" if is_group else "Solo"
    overall = (
        f"{practice_label} coaching team report. "
        + " ".join(available_summaries)
    )

    return CoachingReport(
        session_id=session_id,
        report_version=3,
        mode=mode,
        practice_type="group" if is_group else "solo",
        overall_summary=overall,
        agents=agents,
        coordination_notes=coordination_notes,
        generated_at=datetime.now(timezone.utc),
        llm_model_used=None,
    )
