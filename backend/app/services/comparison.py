"""Deterministic reference-vs-attempt trajectory comparison."""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Sequence, cast


class ComparisonError(ValueError):
    """Raised when trajectories cannot be compared safely."""


@dataclass(frozen=True)
class DTWResult:
    normalized_cost: float
    valid_pair_count: int
    coverage: float
    alignment_path: list[tuple[int, int]]
    local_costs: list[float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "normalized_cost": self.normalized_cost,
            "valid_pair_count": self.valid_pair_count,
            "coverage": self.coverage,
            "alignment_path": [list(pair) for pair in self.alignment_path],
            "local_costs": self.local_costs,
        }


@dataclass(frozen=True)
class DancerMatch:
    reference_id: int
    attempt_id: int
    dtw: DTWResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_id": self.reference_id,
            "attempt_id": self.attempt_id,
            "reference_track_id": self.reference_id,
            "attempt_track_id": self.attempt_id,
            "cost": self.dtw.normalized_cost,
            "dtw_cost": self.dtw.normalized_cost,
            "coverage": self.dtw.coverage,
            "valid_pair_count": self.dtw.valid_pair_count,
            "alignment_path": [list(pair) for pair in self.dtw.alignment_path],
        }


def deterministic_dtw(
    reference: Sequence[Any],
    attempt: Sequence[Any],
    *,
    min_coverage: float = 0.5,
    include_predicted: bool = False,
    predicted_weight: float = 0.1,
) -> DTWResult:
    """Align two normalized stage trajectories without treating missing as zero."""
    if not 0 <= min_coverage <= 1:
        raise ValueError("min_coverage must be between 0 and 1")
    if not 0 < predicted_weight <= 1:
        raise ValueError("predicted_weight must be in (0, 1]")
    reference_values = _valid_samples(reference, include_predicted, predicted_weight)
    attempt_values = _valid_samples(attempt, include_predicted, predicted_weight)
    if not reference_values or not attempt_values:
        raise ComparisonError("No valid overlap exists between the trajectories.")

    reference_coverage = len(reference_values) / max(1, len(reference))
    attempt_coverage = len(attempt_values) / max(1, len(attempt))
    coverage = min(reference_coverage, attempt_coverage)
    if coverage < min_coverage:
        raise ComparisonError(
            f"Trajectory coverage {coverage:.3f} is below the required {min_coverage:.3f}."
        )

    reference_count = len(reference_values)
    attempt_count = len(attempt_values)
    costs = [[0.0] * attempt_count for _ in range(reference_count)]
    for row, (_, left, left_weight) in enumerate(reference_values):
        for column, (_, right, right_weight) in enumerate(attempt_values):
            costs[row][column] = math.hypot(left[0] - right[0], left[1] - right[1]) * min(
                left_weight, right_weight
            )

    table = [[math.inf] * (attempt_count + 1) for _ in range(reference_count + 1)]
    previous: list[list[tuple[int, int] | None]] = [
        [None] * (attempt_count + 1) for _ in range(reference_count + 1)
    ]
    table[0][0] = 0.0
    for row in range(1, reference_count + 1):
        for column in range(1, attempt_count + 1):
            options = (
                (table[row - 1][column - 1], (row - 1, column - 1)),
                (table[row - 1][column], (row - 1, column)),
                (table[row][column - 1], (row, column - 1)),
            )
            best = min(options, key=lambda item: (item[0], item[1]))
            table[row][column] = costs[row - 1][column - 1] + best[0]
            previous[row][column] = best[1]

    path: list[tuple[int, int]] = []
    row, column = reference_count, attempt_count
    while row or column:
        parent = previous[row][column]
        if parent is None:
            raise ComparisonError("Unable to construct a DTW alignment path.")
        path.append((reference_values[row - 1][0], attempt_values[column - 1][0]))
        parent_row, parent_column = parent
        row, column = parent_row, parent_column
    path.reverse()
    local_costs = [
        math.hypot(
            _point_at(reference, reference_index)[0] - _point_at(attempt, attempt_index)[0],
            _point_at(reference, reference_index)[1] - _point_at(attempt, attempt_index)[1],
        )
        for reference_index, attempt_index in path
    ]
    return DTWResult(
        normalized_cost=table[reference_count][attempt_count] / max(1, len(path)),
        valid_pair_count=len(path),
        coverage=coverage,
        alignment_path=path,
        local_costs=local_costs,
    )


def match_dancers(
    reference: Mapping[int, Sequence[Any]],
    attempt: Mapping[int, Sequence[Any]],
    *,
    max_dancers: int = 24,
    min_coverage: float = 0.5,
    max_cost: float = 1.0,
    unmatched_penalty: float = 1.25,
    include_predicted: bool = False,
    predicted_weight: float = 0.1,
) -> tuple[list[DancerMatch], list[int], list[int]]:
    """Match dancer trajectories with deterministic Hungarian assignment."""
    reference_ids = sorted(reference)
    attempt_ids = sorted(attempt)
    if len(reference_ids) > max_dancers or len(attempt_ids) > max_dancers:
        raise ComparisonError(f"Comparison supports at most {max_dancers} dancers per video.")
    if max_cost < 0 or unmatched_penalty < 0:
        raise ValueError("max_cost and unmatched_penalty must not be negative")

    pair_results: dict[tuple[int, int], DTWResult] = {}
    for reference_id in reference_ids:
        for attempt_id in attempt_ids:
            try:
                result = deterministic_dtw(
                    reference[reference_id],
                    attempt[attempt_id],
                    min_coverage=min_coverage,
                    include_predicted=include_predicted,
                    predicted_weight=predicted_weight,
                )
            except ComparisonError:
                continue
            if result.normalized_cost <= max_cost:
                pair_results[(reference_id, attempt_id)] = result

    reference_count = len(reference_ids)
    attempt_count = len(attempt_ids)
    size = reference_count + attempt_count
    if size == 0:
        return [], [], []
    matrix = [[unmatched_penalty] * size for _ in range(size)]
    for row, reference_id in enumerate(reference_ids):
        for column, attempt_id in enumerate(attempt_ids):
            result = pair_results.get((reference_id, attempt_id))
            matrix[row][column] = result.normalized_cost if result else unmatched_penalty
    for row in range(attempt_count, size):
        for column in range(reference_count, size):
            matrix[row][column] = 0.0

    try:
        from scipy.optimize import linear_sum_assignment
    except ImportError as exc:  # pragma: no cover - dependency availability
        raise ComparisonError("SciPy is required for dancer matching.") from exc
    assigned_rows, assigned_columns = linear_sum_assignment(matrix)
    matches: list[DancerMatch] = []
    matched_reference: set[int] = set()
    matched_attempt: set[int] = set()
    for row, column in zip(assigned_rows, assigned_columns):
        if row >= reference_count or column >= attempt_count:
            continue
        reference_id = reference_ids[row]
        attempt_id = attempt_ids[column]
        result = pair_results.get((reference_id, attempt_id))
        if result is not None:
            matches.append(DancerMatch(reference_id, attempt_id, result))
            matched_reference.add(reference_id)
            matched_attempt.add(attempt_id)
    matches.sort(key=lambda item: (item.reference_id, item.attempt_id))
    return (
        matches,
        [identifier for identifier in reference_ids if identifier not in matched_reference],
        [identifier for identifier in attempt_ids if identifier not in matched_attempt],
    )


def compare_result_metadata(
    reference_result: dict[str, Any],
    attempt_result: dict[str, Any],
    *,
    max_dancers: int = 24,
    min_coverage: float = 0.5,
    max_cost: float = 1.0,
    unmatched_penalty: float = 1.25,
    include_predicted: bool = False,
    predicted_weight: float = 0.1,
) -> dict[str, Any]:
    """Compare two persisted Phase 4 outputs without rerunning tracking."""
    _require_stage_results(reference_result, "reference")
    _require_stage_results(attempt_result, "attempt")
    reference_tracks = extract_track_trajectories(
        reference_result, include_predicted=include_predicted
    )
    attempt_tracks = extract_track_trajectories(
        attempt_result, include_predicted=include_predicted
    )
    matches, unmatched_reference, unmatched_attempt = match_dancers(
        reference_tracks,
        attempt_tracks,
        max_dancers=max_dancers,
        min_coverage=min_coverage,
        max_cost=max_cost,
        unmatched_penalty=unmatched_penalty,
        include_predicted=include_predicted,
        predicted_weight=predicted_weight,
    )
    serialized_matches = [match.to_dict() for match in matches]
    deviations = [
        _deviation_for_match(match, reference_tracks, attempt_tracks) for match in matches
    ]
    mean_cost = sum(match.dtw.normalized_cost for match in matches) / max(1, len(matches))
    overall_score = max(0.0, 1.0 - mean_cost / math.sqrt(2)) if matches else 0.0
    return {
        "phase": 5,
        "mode": "comparison",
        "coordinate_space": "stage_normalized",
        "reference": reference_result,
        "attempt": attempt_result,
        "reference_result": reference_result,
        "attempt_result": attempt_result,
        "alignment": {
            "method": "dtw",
            "assignment": "scipy.optimize.linear_sum_assignment",
            "matches": serialized_matches,
        },
        "matches": serialized_matches,
        "unmatched_reference_ids": unmatched_reference,
        "unmatched_attempt_ids": unmatched_attempt,
        "deviations": deviations,
        "overall_score": overall_score,
        "algorithm": {
            "dtw_local_cost": "euclidean",
            "dtw_cost_normalization": "path_length",
            "min_coverage": min_coverage,
            "max_cost": max_cost,
            "unmatched_penalty": unmatched_penalty,
            "include_predicted": include_predicted,
            "predicted_weight": predicted_weight,
            "max_dancers": max_dancers,
        },
    }


def _deviation_for_match(
    match: DancerMatch,
    reference_tracks: Mapping[int, Sequence[Any]],
    attempt_tracks: Mapping[int, Sequence[Any]],
) -> dict[str, Any]:
    per_frame: list[dict[str, Any]] = []
    distances: list[float] = []
    reference_trajectory = reference_tracks.get(match.reference_id, [])
    attempt_trajectory = attempt_tracks.get(match.attempt_id, [])
    for path_index, (reference_frame_index, attempt_frame_index) in enumerate(
        match.dtw.alignment_path
    ):
        reference_point = _canonical_position(
            reference_trajectory[reference_frame_index]
            if reference_frame_index < len(reference_trajectory)
            else None
        )
        attempt_point = _canonical_position(
            attempt_trajectory[attempt_frame_index]
            if attempt_frame_index < len(attempt_trajectory)
            else None
        )
        distance: float | None = None
        if reference_point is not None and attempt_point is not None:
            distance = math.hypot(
                reference_point["x"] - attempt_point["x"],
                reference_point["y"] - attempt_point["y"],
            )
            distances.append(distance)
        per_frame.append(
            {
                "reference_frame_index": reference_frame_index,
                "attempt_frame_index": attempt_frame_index,
                "reference": reference_point,
                "attempt": attempt_point,
                "reference_point": reference_point,
                "attempt_point": attempt_point,
                "distance": distance,
            }
        )
    mean_distance = sum(distances) / max(1, len(distances))
    max_distance = max(distances, default=0.0)
    return {
        "reference_id": match.reference_id,
        "attempt_id": match.attempt_id,
        "reference_track_id": match.reference_id,
        "attempt_track_id": match.attempt_id,
        "mean_euclidean_deviation": mean_distance,
        "max_euclidean_deviation": max_distance,
        "normalized_dtw_cost": match.dtw.normalized_cost,
        "mean_distance": mean_distance,
        "max_distance": max_distance,
        "per_frame": per_frame,
        "per_frame_aligned_points": per_frame,
    }


def _canonical_position(sample: Any) -> dict[str, float] | None:
    point = _point_or_none(sample, include_predicted=True)
    if point is None:
        return None
    return {"x": point[0], "y": point[1]}


def extract_track_trajectories(result: dict[str, Any], *, include_predicted: bool = False) -> dict[int, list[Any]]:
    frames = result.get("sampled_frames") or []
    identifiers = sorted(
        {
            int(track["track_id"])
            for frame in frames
            for track in frame.get("tracks", [])
            if track.get("track_id") is not None
        }
    )
    trajectories = {identifier: [] for identifier in identifiers}
    for frame in frames:
        by_id = {int(track["track_id"]): track for track in frame.get("tracks", [])}
        for identifier in identifiers:
            track = by_id.get(identifier)
            trajectories[identifier].append(
                _sample_from_track(track, include_predicted) if track is not None else None
            )
    return trajectories


def _require_stage_results(result: dict[str, Any], label: str) -> None:
    projection = result.get("projection") or {}
    if not projection.get("calibration_available") or projection.get("calibration_required"):
        raise ComparisonError(f"{label} result has no calibration and cannot be compared.")
    if projection.get("coordinate_space") != "stage_normalized":
        raise ComparisonError(f"{label} result does not use stage_normalized coordinates.")


def _sample_from_track(track: dict[str, Any] | None, include_predicted: bool) -> Any:
    if track is None:
        return None
    top_down = track.get("top_down")
    if not isinstance(top_down, dict):
        return None
    source = top_down.get("source", track.get("bbox_source"))
    status = top_down.get("status", track.get("status"))
    if source != "observed" and not include_predicted:
        return None
    if status == "lost" or source == "none":
        return None
    x, y = top_down.get("x"), top_down.get("y")
    if not _valid_point(x, y):
        return None
    return {
        "x": float(cast(float, x)),
        "y": float(cast(float, y)),
        "source": source,
        "status": status,
    }


def _valid_samples(samples: Sequence[Any], include_predicted: bool, predicted_weight: float):
    valid = []
    for index, sample in enumerate(samples):
        point = _point_or_none(sample, include_predicted)
        if point is None:
            continue
        source = sample.get("source") if isinstance(sample, dict) else "observed"
        weight = predicted_weight if source == "predicted" else 1.0
        valid.append((index, point, weight))
    return valid


def _point_or_none(sample: Any, include_predicted: bool) -> tuple[float, float] | None:
    if sample is None:
        return None
    if isinstance(sample, Mapping):
        if sample.get("source") != "observed" and not include_predicted:
            return None
        x, y = sample.get("x"), sample.get("y")
    else:
        x, y = sample[0], sample[1]
    if not _valid_point(x, y):
        return None
    return float(cast(float, x)), float(cast(float, y))


def _point_at(samples: Sequence[Any], index: int) -> tuple[float, float]:
    point = _point_or_none(samples[index], include_predicted=True)
    if point is None:
        raise ComparisonError("DTW path referenced an invalid sample.")
    return point


def _valid_point(x: Any, y: Any) -> bool:
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return False
    return math.isfinite(float(cast(float, x))) and math.isfinite(float(cast(float, y)))
