"""Extract structured coaching context from AnalysisResult metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "DetectionContext",
    "TrackingContext",
    "CalibrationContext",
    "ComparisonContext",
    "CoachingContext",
    "extract_coaching_context",
]


@dataclass
class DetectionContext:
    total_frames: int = 0
    frames_with_detections: int = 0
    frames_with_poses: int = 0
    max_persons_per_frame: int = 0


@dataclass
class TrackingContext:
    total_tracks: int = 0
    max_concurrent_tracks: int = 0
    occlusion_events: int = 0  # count of occluded statuses
    lost_events: int = 0  # count of lost statuses
    total_frames: int = 0


@dataclass
class CalibrationContext:
    has_calibration: bool = False
    grid_columns: int = 0
    grid_rows: int = 0
    frames_with_projection: int = 0
    total_frames: int = 0
    tracked_dancers: int = 0
    avg_trajectory_length: float = 0.0


@dataclass
class ComparisonContext:
    available: bool = False  # False for single mode
    overall_score: float = 0.0
    matched_pairs: int = 0
    unmatched_reference: int = 0
    unmatched_attempt: int = 0
    avg_dtw_cost: float = 0.0
    avg_deviation: float = 0.0


@dataclass
class CoachingContext:
    detection: DetectionContext = field(default_factory=DetectionContext)
    tracking: TrackingContext = field(default_factory=TrackingContext)
    calibration: CalibrationContext = field(default_factory=CalibrationContext)
    comparison: ComparisonContext = field(default_factory=ComparisonContext)


def _safe_int(value: Any, default: int = 0) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _extract_detection(frames: list[dict[str, Any]]) -> DetectionContext:
    total = len(frames)
    with_detections = 0
    with_poses = 0
    max_persons = 0
    for frame in frames:
        tracks = frame.get("tracks", [])
        observed = [t for t in tracks if t.get("bbox_source") == "observed"]
        if observed:
            with_detections += 1
            count = len(observed)
            if count > max_persons:
                max_persons = count
        has_pose = sum(1 for t in tracks if t.get("pose") is not None)
        if has_pose > 0:
            with_poses += 1
    return DetectionContext(
        total_frames=total,
        frames_with_detections=with_detections,
        frames_with_poses=with_poses,
        max_persons_per_frame=max_persons,
    )


def _extract_tracking(frames: list[dict[str, Any]]) -> TrackingContext:
    total = len(frames)
    all_track_ids: set[int] = set()
    occlusion_count = 0
    lost_count = 0
    max_concurrent = 0
    for frame in frames:
        tracks = frame.get("tracks", [])
        current_ids: set[int] = set()
        for t in tracks:
            tid = t.get("track_id")
            if tid is not None:
                tid_int = int(tid)
                all_track_ids.add(tid_int)
                current_ids.add(tid_int)
            status = t.get("status", "active")
            if status == "occluded":
                occlusion_count += 1
            elif status == "lost":
                lost_count += 1
        if len(current_ids) > max_concurrent:
            max_concurrent = len(current_ids)
    return TrackingContext(
        total_tracks=len(all_track_ids),
        max_concurrent_tracks=max_concurrent,
        occlusion_events=occlusion_count,
        lost_events=lost_count,
        total_frames=total,
    )


def _extract_calibration(
    frames: list[dict[str, Any]],
    projection: dict[str, Any] | None,
) -> CalibrationContext:
    if projection is None:
        projection = {}
    has_cal = bool(projection.get("calibration_available", False))
    grid_cols = _safe_int(projection.get("grid_columns", 0))
    grid_rows = _safe_int(projection.get("grid_rows", 0))
    total = len(frames)
    frames_with_proj = 0
    dancer_track_ids: set[int] = set()
    trajectory_lengths: list[int] = []
    track_appearances: dict[int, int] = {}

    for frame in frames:
        tracks = frame.get("tracks", [])
        has_proj_in_frame = False
        for t in tracks:
            td = t.get("top_down")
            if isinstance(td, dict) and td.get("x") is not None and td.get("y") is not None:
                has_proj_in_frame = True
                tid = t.get("track_id")
                if tid is not None:
                    tid_int = int(tid)
                    dancer_track_ids.add(tid_int)
                    track_appearances[tid_int] = track_appearances.get(tid_int, 0) + 1
        if has_proj_in_frame:
            frames_with_proj += 1

    if track_appearances:
        trajectory_lengths = list(track_appearances.values())

    avg_len = sum(trajectory_lengths) / max(1, len(trajectory_lengths)) if trajectory_lengths else 0.0

    return CalibrationContext(
        has_calibration=has_cal,
        grid_columns=grid_cols,
        grid_rows=grid_rows,
        frames_with_projection=frames_with_proj,
        total_frames=total,
        tracked_dancers=len(dancer_track_ids),
        avg_trajectory_length=round(avg_len, 2),
    )


def _extract_comparison(result: dict[str, Any], mode: str) -> ComparisonContext:
    if mode != "comparison":
        return ComparisonContext(available=False)

    overall_score = _safe_float(result.get("overall_score", 0.0))
    matches = result.get("matches") or []
    unmatched_ref = result.get("unmatched_reference_ids") or []
    unmatched_att = result.get("unmatched_attempt_ids") or []
    matched_pairs = len(matches)

    dtw_costs = [float(m.get("dtw_cost", m.get("cost", 0))) for m in matches if m.get("dtw_cost") is not None or m.get("cost") is not None]
    avg_cost = sum(dtw_costs) / max(1, len(dtw_costs)) if dtw_costs else 0.0

    deviations = result.get("deviations") or []
    dev_values = [
        float(d.get("mean_euclidean_deviation", d.get("mean_distance", 0)))
        for d in deviations
        if d.get("mean_euclidean_deviation") is not None or d.get("mean_distance") is not None
    ]
    avg_dev = sum(dev_values) / max(1, len(dev_values)) if dev_values else 0.0

    return ComparisonContext(
        available=True,
        overall_score=round(overall_score, 4),
        matched_pairs=matched_pairs,
        unmatched_reference=len(unmatched_ref),
        unmatched_attempt=len(unmatched_att),
        avg_dtw_cost=round(avg_cost, 4),
        avg_deviation=round(avg_dev, 4),
    )


def extract_coaching_context(result: dict, mode: str) -> CoachingContext:
    """Single extraction function. Both LLM and deterministic paths use this."""
    frames = result.get("sampled_frames") or []
    projection = result.get("projection")

    detection = _extract_detection(frames)
    tracking = _extract_tracking(frames)
    calibration = _extract_calibration(frames, projection)
    comparison = _extract_comparison(result, mode)

    return CoachingContext(
        detection=detection,
        tracking=tracking,
        calibration=calibration,
        comparison=comparison,
    )
