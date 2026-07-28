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
    2: "Detection & Pose",
    3: "Tracking & Continuity",
    4: "Calibration & Space",
    5: "Reference Comparison",
}


def _detection_phase(ctx: DetectionContext) -> CoachPhase:
    if ctx.total_frames == 0:
        return CoachPhase(
            phase=2,
            name=_PHASE_NAMES[2],
            available=False,
            source="deterministic",
            summary="No video frames were sampled. Detection analysis is unavailable.",
            issues=[CoachIssue(description="No sampled frames found in the analysis result.")],
            confidence=0.0,
        )

    coverage = ctx.frames_with_detections / max(1, ctx.total_frames)
    pose_coverage = ctx.frames_with_poses / max(1, ctx.total_frames)

    strengths: list[str] = []
    issues: list[CoachIssue] = []
    suggestions: list[str] = []

    if coverage >= 0.8:
        strengths.append(
            f"High detection coverage: {ctx.frames_with_detections}/{ctx.total_frames} frames "
            f"({coverage:.0%})"
        )
    elif coverage >= 0.5:
        suggestions.append(
            f"Detection coverage is {coverage:.0%}. Consider adjusting the camera angle or "
            "lighting to improve person visibility."
        )
    else:
        issues.append(
            CoachIssue(
                description=f"Low detection coverage: only {coverage:.0%} of frames have detections.",
                severity="high",
                category="detection",
            )
        )
        suggestions.append(
            "Improve lighting, reduce motion blur, or reposition the camera so dancers are "
            "clearly visible."
        )

    if pose_coverage >= 0.8:
        strengths.append(
            f"Pose estimation was successful on {ctx.frames_with_poses}/{ctx.total_frames} frames "
            f"({pose_coverage:.0%})"
        )
    elif pose_coverage < 0.3 and ctx.frames_with_detections > 0:
        issues.append(
            CoachIssue(
                description=f"Low pose coverage: only {pose_coverage:.0%} of frames have pose data.",
                severity="medium",
                category="pose",
            )
        )
        suggestions.append(
            "Ensure dancers are large enough in the frame and not heavily occluded for "
            "better pose estimation."
        )

    strengths.append(
        f"Up to {ctx.max_persons_per_frame} person(s) detected in a single frame."
    )

    summary = (
        f"Detected persons in {ctx.frames_with_detections}/{ctx.total_frames} sampled frames "
        f"({coverage:.0%} coverage) with up to {ctx.max_persons_per_frame} concurrent person(s). "
        f"Pose data available in {ctx.frames_with_poses}/{ctx.total_frames} frames "
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
            summary="No tracking data available because no frames were sampled.",
            issues=[CoachIssue(description="No sampled frames found.")],
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
        strengths.append("No identity switches detected — single-track scenario.")
    else:
        strengths.append(f"Tracked {ctx.total_tracks} unique dancer identities across the video.")

    if ctx.max_concurrent_tracks >= 1:
        strengths.append(
            f"Up to {ctx.max_concurrent_tracks} dancers tracked simultaneously."
        )

    if occlusion_rate > 0.3:
        issues.append(
            CoachIssue(
                description=f"High occlusion rate ({occlusion_rate:.0%} of track observations).",
                severity="medium",
                category="tracking",
            )
        )
        suggestions.append(
            "Consider a wider camera angle or elevated position to reduce dancer overlap "
            "and occlusions."
        )

    if loss_rate > 0.1:
        issues.append(
            CoachIssue(
                description=f"Track loss detected in {ctx.lost_events} event(s).",
                severity="high" if loss_rate > 0.2 else "medium",
                category="tracking",
            )
        )
        suggestions.append(
            "Ensure consistent lighting and avoid long occlusions. Track loss may cause "
            "identity fragmentation."
        )

    if not issues:
        suggestions.append(
            "Tracking continuity is good. No major occlusions or losses detected."
        )

    summary = (
        f"{ctx.total_tracks} unique track(s) with up to {ctx.max_concurrent_tracks} concurrent "
        f"dancer(s). Occlusion rate: {occlusion_rate:.0%}, loss rate: {loss_rate:.0%}."
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
            summary="No calibration data was configured for this session. Spatial analysis "
            "is not available.",
            strengths=[],
            issues=[
                CoachIssue(
                    description="Calibration points have not been set.",
                    severity="high",
                    category="calibration",
                )
            ],
            suggestions=[
                "Set calibration points via the /calibration endpoint with four normalized "
                "image coordinates to enable top-down spatial analysis."
            ],
            confidence=0.0,
        )

    strengths: list[str] = []
    issues: list[CoachIssue] = []
    suggestions: list[str] = []
    projection_coverage = ctx.frames_with_projection / max(1, ctx.total_frames)

    strengths.append(
        f"Calibration is configured with a {ctx.grid_columns}x{ctx.grid_rows} grid."
    )

    if ctx.tracked_dancers > 0:
        strengths.append(
            f"Tracking {ctx.tracked_dancers} dancer(s) in the calibrated space."
        )
        if projection_coverage >= 0.7:
            strengths.append(
                f"Good top-down projection coverage: {projection_coverage:.0%} of frames."
            )
        elif projection_coverage < 0.3:
            issues.append(
                CoachIssue(
                    description=f"Low projection coverage ({projection_coverage:.0%}).",
                    severity="medium",
                    category="calibration",
                )
            )
            suggestions.append(
                "Ensure dancers remain within the calibrated area to maintain projection."
            )

        strengths.append(
            f"Average trajectory length: {ctx.avg_trajectory_length:.1f} frames."
        )
    else:
        issues.append(
            CoachIssue(
                description="No dancers were tracked in the calibrated space.",
                severity="medium",
                category="calibration",
            )
        )
        suggestions.append(
            "Position dancers within the calibrated area for spatial analysis."
        )

    summary = (
        f"Calibration is {'active' if ctx.has_calibration else 'inactive'}. "
        f"{ctx.tracked_dancers} dancer(s) tracked in the {ctx.grid_columns}x{ctx.grid_rows} grid "
        f"space across {ctx.frames_with_projection}/{ctx.total_frames} frames."
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
            summary="Not applicable (single-video mode). Comparison data is only available "
            "when running in comparison mode with both a reference and an attempt video.",
            confidence=0.0,
        )

    strengths: list[str] = []
    issues: list[CoachIssue] = []
    suggestions: list[str] = []

    score = ctx.overall_score
    if score >= 0.8:
        strengths.append(
            f"Excellent overall similarity score: {score:.2f}. The attempt closely matches "
            "the reference."
        )
    elif score < 0.5:
        issues.append(
            CoachIssue(
                description=f"Low overall similarity score: {score:.2f}.",
                severity="high",
                category="comparison",
            )
        )
        suggestions.append(
            "Review the alignment details to identify specific frames or dancers with "
            "large deviations."
        )
    else:
        strengths.append(
            f"Moderate similarity score: {score:.2f}. Some deviations exist."
        )
        suggestions.append(
            "Focus on the dancers and segments with the highest deviation for targeted "
            "improvement."
        )

    if ctx.matched_pairs > 0:
        strengths.append(
            f"Matched {ctx.matched_pairs} dancer pair(s) between reference and attempt."
        )
        strengths.append(
            f"Average DTW cost: {ctx.avg_dtw_cost:.4f}, average deviation: "
            f"{ctx.avg_deviation:.4f}."
        )
    else:
        issues.append(
            CoachIssue(
                description="No dancer pairs were matched between reference and attempt.",
                severity="high",
                category="comparison",
            )
        )
        suggestions.append(
            "Ensure both videos contain the same dancers and similar choreography."
        )

    if ctx.unmatched_reference > 0 or ctx.unmatched_attempt > 0:
        if ctx.unmatched_reference > 0:
            issues.append(
                CoachIssue(
                    description=f"{ctx.unmatched_reference} dancer(s) in the reference were "
                    "not matched in the attempt.",
                    severity="medium",
                    category="comparison",
                )
            )
        if ctx.unmatched_attempt > 0:
            issues.append(
                CoachIssue(
                    description=f"{ctx.unmatched_attempt} dancer(s) in the attempt were "
                    "not matched in the reference.",
                    severity="medium",
                    category="comparison",
                )
            )
        suggestions.append(
            "Verify that the same number of dancers perform in both videos."
        )

    summary = (
        f"Comparison {'available' if ctx.available else 'not available'} with "
        f"{ctx.matched_pairs} matched pair(s). "
        f"Overall score: {score:.4f}. "
        f"Unmatched: {ctx.unmatched_reference} reference, {ctx.unmatched_attempt} attempt."
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
    overall = (
        f"Deterministic analysis of {mode} session. "
        + " ".join(summaries)
    )

    return CoachingReport(
        session_id=session_id,
        report_version=1,
        mode=mode,
        overall_summary=overall,
        phases=phase_funcs,
        generated_at=datetime.now(timezone.utc),
        llm_model_used=None,
    )
