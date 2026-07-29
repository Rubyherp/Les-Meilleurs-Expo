"""Pure-function deterministic report generation for all four analysis phases."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.schemas.coaching import CoachIssue, CoachPhase, CoachingReport
from app.services.coaching.context import (
    CalibrationContext,
    CoachingContext,
    ComparisonContext,
    DetectionContext,
    TrackingContext,
)

__all__ = ["generate_deterministic_report"]


_PHASE_NAMES: dict[int, str] = {
    2: "Camera & Visibility",
    3: "Movement Flow",
    4: "Space Usage",
    5: "Performance Match",
}


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
                description=f"Quite a bit of overlapping — dancers overlapped in {occlusion_rate:.0%} of the observed moments.",
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
                    description="Practice space markers haven't been set up yet.",
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
    session_id: UUID, mode: str, ctx: CoachingContext
) -> CoachingReport:
    """Generate all phase insights deterministically. No LLM needed."""
    phase_funcs = [
        _detection_phase(ctx.detection),
        _tracking_phase(ctx.tracking),
        _calibration_phase(ctx.calibration),
        _comparison_phase(ctx.comparison),
    ]

    summaries = [p.summary for p in phase_funcs]
    overall = f"Here's your coaching breakdown. " + " ".join(summaries)

    return CoachingReport(
        session_id=session_id,
        report_version=1,
        mode=mode,
        overall_summary=overall,
        phases=phase_funcs,
        generated_at=datetime.now(timezone.utc),
        llm_model_used=None,
    )
