from __future__ import annotations

import copy
import math
from typing import Any

from app.services.analysis_control.models import AnalysisSegment


def merge_segment_results(
    baseline: dict[str, Any],
    retry: dict[str, Any],
    segments: tuple[AnalysisSegment, ...],
) -> dict[str, Any]:
    """Replace only retried windows and reconcile retry-local track identifiers."""
    output = copy.deepcopy(baseline)
    base_frames = copy.deepcopy(baseline.get("sampled_frames", []))
    retry_frames = copy.deepcopy(retry.get("sampled_frames", []))
    track_mapping = _track_mapping(base_frames, retry_frames)
    next_track_id = (
        max(
            (
                track.get("track_id", 0)
                for frame in base_frames
                for track in frame.get("tracks", [])
                if isinstance(track.get("track_id"), int)
            ),
            default=0,
        )
        + 1
    )
    seen_tracks: set[int] = set()
    for frame in retry_frames:
        for key in ("tracks", "detections"):
            for track in frame.get(key, []):
                object_id = id(track)
                if object_id in seen_tracks:
                    continue
                seen_tracks.add(object_id)
                track_id = track.get("track_id")
                if not isinstance(track_id, int):
                    continue
                if track_id not in track_mapping:
                    track_mapping[track_id] = next_track_id
                    next_track_id += 1
                track["track_id"] = track_mapping[track_id]

    retained = [
        frame
        for frame in base_frames
        if not _inside_segments(
            float(frame.get("timestamp_seconds", 0.0)), segments
        )
    ]
    merged = sorted(
        [*retained, *retry_frames],
        key=lambda frame: (
            float(frame.get("timestamp_seconds", 0.0)),
            int(frame.get("frame_index", 0)),
        ),
    )
    output["sampled_frames"] = merged
    output["sampled_frame_timestamps"] = [
        frame.get("timestamp_seconds", 0.0) for frame in merged
    ]
    output["adaptive_sampling"] = {
        "targeted_segments": [segment.to_dict() for segment in segments],
        "identity_mapping": {
            str(source): target for source, target in sorted(track_mapping.items())
        },
    }
    return output


def _inside_segments(
    timestamp: float, segments: tuple[AnalysisSegment, ...]
) -> bool:
    return any(
        segment.start_seconds <= timestamp <= segment.end_seconds
        for segment in segments
    )


def _track_mapping(
    base_frames: list[dict[str, Any]], retry_frames: list[dict[str, Any]]
) -> dict[int, int]:
    scores: dict[tuple[int, int], list[float]] = {}
    for retry_frame in retry_frames:
        timestamp = float(retry_frame.get("timestamp_seconds", 0.0))
        observed_base_frames = [
            frame
            for frame in base_frames
            if any(
                isinstance(track.get("bbox"), dict)
                for track in frame.get("tracks", [])
            )
        ]
        base_frame = min(
            observed_base_frames,
            key=lambda frame: abs(
                float(frame.get("timestamp_seconds", 0.0)) - timestamp
            ),
            default=None,
        )
        if base_frame is None:
            continue
        if (
            abs(float(base_frame.get("timestamp_seconds", 0.0)) - timestamp)
            > 2.0
        ):
            continue
        for retry_track in retry_frame.get("tracks", []):
            retry_id = retry_track.get("track_id")
            retry_box = retry_track.get("bbox")
            if not isinstance(retry_id, int) or not isinstance(retry_box, dict):
                continue
            for base_track in base_frame.get("tracks", []):
                base_id = base_track.get("track_id")
                base_box = base_track.get("bbox")
                if not isinstance(base_id, int) or not isinstance(base_box, dict):
                    continue
                similarity = _box_similarity(retry_box, base_box)
                if similarity >= 0.2:
                    scores.setdefault((retry_id, base_id), []).append(similarity)

    mapping: dict[int, int] = {}
    used_base: set[int] = set()
    ranked = sorted(
        (
            (sum(values) / len(values), retry_id, base_id)
            for (retry_id, base_id), values in scores.items()
        ),
        reverse=True,
    )
    for _, retry_id, base_id in ranked:
        if retry_id in mapping or base_id in used_base:
            continue
        mapping[retry_id] = base_id
        used_base.add(base_id)
    return mapping


def _box_similarity(first: dict[str, Any], second: dict[str, Any]) -> float:
    try:
        ax1, ay1, ax2, ay2 = (
            float(first["x1"]),
            float(first["y1"]),
            float(first["x2"]),
            float(first["y2"]),
        )
        bx1, by1, bx2, by2 = (
            float(second["x1"]),
            float(second["y1"]),
            float(second["x2"]),
            float(second["y2"]),
        )
    except (KeyError, TypeError, ValueError):
        return 0.0
    intersection = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(
        0.0, min(ay2, by2) - max(ay1, by1)
    )
    first_area = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    second_area = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = first_area + second_area - intersection
    iou = intersection / union if union > 0 else 0.0
    first_center = ((ax1 + ax2) / 2, (ay1 + ay2) / 2)
    second_center = ((bx1 + bx2) / 2, (by1 + by2) / 2)
    diagonal = max(1.0, math.hypot(ax2 - ax1, ay2 - ay1))
    proximity = max(0.0, 1 - math.dist(first_center, second_center) / diagonal)
    return iou * 0.75 + proximity * 0.25
