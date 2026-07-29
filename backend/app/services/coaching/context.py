"""Extract structured coaching context from AnalysisResult metadata."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "DetectionContext",
    "TrackingContext",
    "CalibrationContext",
    "ComparisonContext",
    "ObservationContext",
    "TimingContext",
    "FormationContext",
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
class ObservationContext:
    total_frames: int = 0
    frames_with_detections: int = 0
    frames_with_poses: int = 0
    max_persons_per_frame: int = 0
    total_tracks: int = 0
    max_concurrent_tracks: int = 0
    occlusion_events: int = 0
    lost_events: int = 0
    is_group: bool = False


@dataclass
class TimingContext:
    available: bool = False
    has_reference: bool = False
    sample_count: int = 0
    average_offset_seconds: float = 0.0
    average_absolute_offset_seconds: float = 0.0
    offset_spread_seconds: float = 0.0
    pulse_consistency: float = 0.0
    group_sync_score: float | None = None


@dataclass
class FormationContext:
    enabled: bool = False
    available: bool = False
    tracked_dancers: int = 0
    observed_group_frames: int = 0
    average_pair_distance: float = 0.0
    spacing_variation: float = 0.0
    close_spacing_rate: float = 0.0
    reference_match_score: float | None = None


@dataclass
class CoachingContext:
    detection: DetectionContext = field(default_factory=DetectionContext)
    tracking: TrackingContext = field(default_factory=TrackingContext)
    calibration: CalibrationContext = field(default_factory=CalibrationContext)
    comparison: ComparisonContext = field(default_factory=ComparisonContext)
    observation: ObservationContext = field(default_factory=ObservationContext)
    timing: TimingContext = field(default_factory=TimingContext)
    formation: FormationContext = field(default_factory=FormationContext)


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


def _analysis_result(result: dict[str, Any], mode: str) -> dict[str, Any]:
    """Return the take that should be coached.

    Comparison metadata wraps the analysed videos under ``reference`` and
    ``attempt``. The attempt is the dancer's take, so observation and formation
    feedback must inspect it instead of the empty comparison envelope.
    """
    if mode == "comparison":
        attempt = result.get("attempt") or result.get("attempt_result")
        if isinstance(attempt, dict):
            return attempt
    return result


def _observed_point(track: dict[str, Any]) -> tuple[float, float] | None:
    top_down = track.get("top_down")
    if not isinstance(top_down, dict):
        return None
    if top_down.get("source", track.get("bbox_source")) != "observed":
        return None
    x = top_down.get("x")
    y = top_down.get("y")
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return None
    if not math.isfinite(float(x)) or not math.isfinite(float(y)):
        return None
    return float(x), float(y)


def _frame_timestamp(frame: dict[str, Any], fallback: float) -> float:
    value = frame.get("timestamp_seconds")
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return fallback


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


def _extract_observation(
    detection: DetectionContext,
    tracking: TrackingContext,
    *,
    is_group: bool,
) -> ObservationContext:
    return ObservationContext(
        total_frames=detection.total_frames,
        frames_with_detections=detection.frames_with_detections,
        frames_with_poses=detection.frames_with_poses,
        max_persons_per_frame=detection.max_persons_per_frame,
        total_tracks=tracking.total_tracks,
        max_concurrent_tracks=tracking.max_concurrent_tracks,
        occlusion_events=tracking.occlusion_events,
        lost_events=tracking.lost_events,
        is_group=is_group,
    )


def _movement_timing(frames: list[dict[str, Any]], *, is_group: bool) -> TimingContext:
    previous: dict[int, tuple[float, float, float]] = {}
    energy_samples: list[tuple[float, float]] = []
    sync_scores: list[float] = []

    for index, frame in enumerate(frames):
        timestamp = _frame_timestamp(frame, float(index))
        speeds: list[float] = []
        for track in frame.get("tracks", []):
            track_id = track.get("track_id")
            point = _observed_point(track)
            if track_id is None or point is None:
                continue
            identifier = int(track_id)
            prior = previous.get(identifier)
            if prior is not None:
                elapsed = timestamp - prior[2]
                if elapsed > 0:
                    speeds.append(math.hypot(point[0] - prior[0], point[1] - prior[1]) / elapsed)
            previous[identifier] = (point[0], point[1], timestamp)

        if speeds:
            energy_samples.append((timestamp, statistics.fmean(speeds)))
            if is_group and len(speeds) >= 2:
                mean_speed = statistics.fmean(speeds)
                if mean_speed > 1e-6:
                    coefficient = statistics.pstdev(speeds) / mean_speed
                    sync_scores.append(max(0.0, 1.0 - min(1.0, coefficient)))

    if len(energy_samples) < 3:
        return TimingContext(
            available=False,
            has_reference=False,
            sample_count=len(energy_samples),
            group_sync_score=round(statistics.fmean(sync_scores), 3) if sync_scores else None,
        )

    energies = [sample[1] for sample in energy_samples]
    mean_energy = statistics.fmean(energies)
    peaks = [
        energy_samples[index][0]
        for index in range(1, len(energy_samples) - 1)
        if energies[index] >= energies[index - 1]
        and energies[index] > energies[index + 1]
        and energies[index] >= mean_energy
    ]
    intervals = [
        peaks[index] - peaks[index - 1]
        for index in range(1, len(peaks))
        if peaks[index] > peaks[index - 1]
    ]
    if len(intervals) >= 2 and statistics.fmean(intervals) > 0:
        pulse_variation = statistics.pstdev(intervals) / statistics.fmean(intervals)
    elif mean_energy > 1e-6:
        pulse_variation = statistics.pstdev(energies) / mean_energy
    else:
        pulse_variation = 0.0

    return TimingContext(
        available=True,
        has_reference=False,
        sample_count=len(energy_samples),
        pulse_consistency=round(max(0.0, 1.0 - min(1.0, pulse_variation)), 3),
        group_sync_score=round(statistics.fmean(sync_scores), 3) if sync_scores else None,
    )


def _extract_timing(
    result: dict[str, Any],
    analysis_result: dict[str, Any],
    mode: str,
    *,
    is_group: bool,
) -> TimingContext:
    frames = analysis_result.get("sampled_frames") or []
    baseline = _movement_timing(frames, is_group=is_group)
    if mode != "comparison":
        return baseline

    reference_result = result.get("reference") or result.get("reference_result") or {}
    reference_frames = reference_result.get("sampled_frames") or []
    attempt_frames = frames
    matches = result.get("matches") or []
    offsets: list[float] = []
    per_dancer_offsets: list[float] = []

    for match in matches:
        match_offsets: list[float] = []
        for pair in match.get("alignment_path") or []:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                continue
            reference_index = _safe_int(pair[0], -1)
            attempt_index = _safe_int(pair[1], -1)
            if not (0 <= reference_index < len(reference_frames)):
                continue
            if not (0 <= attempt_index < len(attempt_frames)):
                continue
            reference_time = _frame_timestamp(reference_frames[reference_index], float(reference_index))
            attempt_time = _frame_timestamp(attempt_frames[attempt_index], float(attempt_index))
            match_offsets.append(attempt_time - reference_time)
        if match_offsets:
            offsets.extend(match_offsets)
            per_dancer_offsets.append(statistics.fmean(match_offsets))

    if not offsets:
        return baseline

    spread = statistics.pstdev(offsets) if len(offsets) > 1 else 0.0
    group_sync_score: float | None = baseline.group_sync_score
    if is_group and len(per_dancer_offsets) >= 2:
        dancer_spread = statistics.pstdev(per_dancer_offsets)
        group_sync_score = max(0.0, 1.0 - min(1.0, dancer_spread / 0.35))

    return TimingContext(
        available=True,
        has_reference=True,
        sample_count=len(offsets),
        average_offset_seconds=round(statistics.fmean(offsets), 3),
        average_absolute_offset_seconds=round(statistics.fmean(abs(value) for value in offsets), 3),
        offset_spread_seconds=round(spread, 3),
        pulse_consistency=round(max(0.0, 1.0 - min(1.0, spread / 0.5)), 3),
        group_sync_score=round(group_sync_score, 3) if group_sync_score is not None else None,
    )


def _extract_formation(
    frames: list[dict[str, Any]],
    result: dict[str, Any],
    mode: str,
    *,
    is_group: bool,
) -> FormationContext:
    if not is_group:
        return FormationContext(enabled=False, available=False)

    distances_by_pair: dict[tuple[int, int], list[float]] = {}
    all_distances: list[float] = []
    close_distances = 0
    observed_group_frames = 0
    dancer_ids: set[int] = set()

    for frame in frames:
        points: dict[int, tuple[float, float]] = {}
        for track in frame.get("tracks", []):
            track_id = track.get("track_id")
            point = _observed_point(track)
            if track_id is not None and point is not None:
                identifier = int(track_id)
                dancer_ids.add(identifier)
                points[identifier] = point
        identifiers = sorted(points)
        if len(identifiers) < 2:
            continue
        observed_group_frames += 1
        for left_index, left_id in enumerate(identifiers):
            for right_id in identifiers[left_index + 1 :]:
                left = points[left_id]
                right = points[right_id]
                distance = math.hypot(left[0] - right[0], left[1] - right[1])
                distances_by_pair.setdefault((left_id, right_id), []).append(distance)
                all_distances.append(distance)
                if distance < 0.08:
                    close_distances += 1

    variations: list[float] = []
    for values in distances_by_pair.values():
        if len(values) < 2:
            continue
        mean_distance = statistics.fmean(values)
        if mean_distance > 1e-6:
            variations.append(statistics.pstdev(values) / mean_distance)

    reference_match_score = None
    if mode == "comparison" and isinstance(result.get("overall_score"), (int, float)):
        reference_match_score = max(0.0, min(1.0, float(result["overall_score"])))

    return FormationContext(
        enabled=True,
        available=observed_group_frames > 0,
        tracked_dancers=len(dancer_ids),
        observed_group_frames=observed_group_frames,
        average_pair_distance=round(statistics.fmean(all_distances), 3) if all_distances else 0.0,
        spacing_variation=round(statistics.fmean(variations), 3) if variations else 0.0,
        close_spacing_rate=round(close_distances / max(1, len(all_distances)), 3),
        reference_match_score=round(reference_match_score, 3) if reference_match_score is not None else None,
    )


def extract_coaching_context(
    result: dict,
    mode: str,
    is_group: bool = False,
) -> CoachingContext:
    """Single extraction function. Both LLM and deterministic paths use this."""
    coached_result = _analysis_result(result, mode)
    frames = coached_result.get("sampled_frames") or []
    projection = coached_result.get("projection")

    detection = _extract_detection(frames)
    tracking = _extract_tracking(frames)
    calibration = _extract_calibration(frames, projection)
    comparison = _extract_comparison(result, mode)
    observation = _extract_observation(detection, tracking, is_group=is_group)
    timing = _extract_timing(
        result,
        coached_result,
        mode,
        is_group=is_group,
    )
    formation = _extract_formation(
        frames,
        result,
        mode,
        is_group=is_group,
    )

    return CoachingContext(
        detection=detection,
        tracking=tracking,
        calibration=calibration,
        comparison=comparison,
        observation=observation,
        timing=timing,
        formation=formation,
    )
