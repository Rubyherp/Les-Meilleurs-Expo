from __future__ import annotations

import math
from collections import defaultdict
from statistics import median
from typing import Any

from app.services.analysis_control.models import (
    AnalysisSegment,
    QualityReport,
    ReasonCode,
)


RETRYABLE_REASONS = {
    ReasonCode.LOW_DETECTION_RECALL,
    ReasonCode.EXTRA_PERSON_DETECTIONS,
    ReasonCode.LOW_DETECTION_CONFIDENCE,
    ReasonCode.TRACKING_DROPOUT,
    ReasonCode.TRACK_FRAGMENTATION,
    ReasonCode.POSE_DROPOUT,
    ReasonCode.LOW_POSE_VISIBILITY,
    ReasonCode.POSE_TEMPORAL_JITTER,
}

REVIEW_REASONS = {
    ReasonCode.CALIBRATION_UNVERIFIED,
    ReasonCode.CALIBRATION_OUT_OF_BOUNDS,
    ReasonCode.CALIBRATION_TRAJECTORY_JUMP,
    ReasonCode.INSUFFICIENT_EVIDENCE,
}


class QualityAuditor:
    def __init__(self, *, minimum_score: float = 0.72) -> None:
        self.minimum_score = minimum_score

    def audit(
        self,
        result: dict[str, Any],
        *,
        expected_dancer_count: int,
        calibration_report: dict[str, Any] | None = None,
    ) -> QualityReport:
        frames = result.get("sampled_frames")
        if not isinstance(frames, list) or not frames:
            return QualityReport(
                score=0.0,
                metrics=self._empty_metrics(),
                reason_codes=(ReasonCode.INSUFFICIENT_EVIDENCE,),
                segments=(),
                disposition="review",
            )

        expected = max(1, expected_dancer_count)
        exact_counts = 0
        count_covered = 0
        extra_counts = 0
        observed_total = 0
        pose_total = 0
        confidence_values: list[float] = []
        visibility_values: list[float] = []
        predicted_or_lost = 0
        track_total = 0
        observed_track_ids: set[int] = set()
        frame_issues: list[tuple[float, set[str]]] = []
        pose_points: dict[tuple[int, int], tuple[float, float]] = {}
        pose_jumps = 0
        pose_transitions = 0

        for frame in frames:
            tracks = frame.get("tracks") or frame.get("detections") or []
            observed = [
                item
                for item in tracks
                if item.get("bbox_source") == "observed"
                and item.get("status", "active") == "active"
            ]
            timestamp = self._float(frame.get("timestamp_seconds"))
            issues: set[str] = set()
            observed_count = len(observed)
            exact_counts += int(observed_count == expected)
            count_covered += int(observed_count >= expected)
            extra_counts += int(observed_count > expected)
            if observed_count < expected:
                issues.add(ReasonCode.LOW_DETECTION_RECALL)
            if observed_count > expected:
                issues.add(ReasonCode.EXTRA_PERSON_DETECTIONS)

            for track in tracks:
                track_total += 1
                if (
                    track.get("status") != "active"
                    or track.get("bbox_source") != "observed"
                ):
                    predicted_or_lost += 1
                    issues.add(ReasonCode.TRACKING_DROPOUT)
                track_id = track.get("track_id")
                if (
                    isinstance(track_id, int)
                    and track.get("bbox_source") == "observed"
                ):
                    observed_track_ids.add(track_id)

            for item in observed:
                observed_total += 1
                confidence = item.get("confidence")
                if self._finite(confidence):
                    confidence_values.append(float(confidence))
                pose = item.get("pose")
                if not isinstance(pose, dict):
                    issues.add(ReasonCode.POSE_DROPOUT)
                    continue
                landmarks = pose.get("landmarks")
                if not isinstance(landmarks, list) or not landmarks:
                    issues.add(ReasonCode.POSE_DROPOUT)
                    continue
                pose_total += 1
                for landmark in landmarks:
                    visibility = landmark.get("visibility")
                    if self._finite(visibility):
                        visibility_values.append(float(visibility))
                track_id = item.get("track_id")
                anchor = self._pose_anchor(landmarks)
                if isinstance(track_id, int) and anchor is not None:
                    key = (track_id, len(frame_issues))
                    pose_points[key] = anchor
                    previous = pose_points.get((track_id, len(frame_issues) - 1))
                    if previous is not None:
                        pose_transitions += 1
                        if math.dist(previous, anchor) > 0.18:
                            pose_jumps += 1

            frame_issues.append((timestamp, issues))

        frame_count = len(frames)
        count_recall = count_covered / frame_count
        exact_count_rate = exact_counts / frame_count
        extra_person_rate = extra_counts / frame_count
        pose_coverage = pose_total / observed_total if observed_total else 0.0
        median_confidence = median(confidence_values) if confidence_values else 0.0
        median_visibility = median(visibility_values) if visibility_values else 0.0
        tracking_dropout_rate = (
            predicted_or_lost / track_total if track_total else 1.0
        )
        fragmentation_ratio = len(observed_track_ids) / expected
        pose_jitter_rate = pose_jumps / pose_transitions if pose_transitions else 0.0

        calibration = calibration_report or {}
        calibration_available = bool(
            result.get("projection", {}).get("calibration_available")
        )
        calibration_confidence = self._float(calibration.get("confidence"))
        calibration_in_bounds = self._float(calibration.get("in_bounds_rate"))
        calibration_jump_rate = self._float(
            calibration.get("trajectory_jump_rate")
        )

        reasons: set[str] = set()
        if count_recall < 0.8:
            reasons.add(ReasonCode.LOW_DETECTION_RECALL)
        if extra_person_rate > 0.15:
            reasons.add(ReasonCode.EXTRA_PERSON_DETECTIONS)
        if median_confidence and median_confidence < 0.4:
            reasons.add(ReasonCode.LOW_DETECTION_CONFIDENCE)
        if tracking_dropout_rate > 0.2:
            reasons.add(ReasonCode.TRACKING_DROPOUT)
        if fragmentation_ratio > 1.6:
            reasons.add(ReasonCode.TRACK_FRAGMENTATION)
        if pose_coverage < 0.75:
            reasons.add(ReasonCode.POSE_DROPOUT)
        if visibility_values and median_visibility < 0.55:
            reasons.add(ReasonCode.LOW_POSE_VISIBILITY)
        if pose_jitter_rate > 0.12:
            reasons.add(ReasonCode.POSE_TEMPORAL_JITTER)
        if not calibration_available or not calibration.get("verified", False):
            reasons.add(ReasonCode.CALIBRATION_UNVERIFIED)
        for reason in calibration.get("reason_codes", []):
            reasons.add(str(reason))

        detection_score = (
            count_recall * 0.65
            + exact_count_rate * 0.2
            + (1 - extra_person_rate) * 0.15
        )
        confidence_score = min(1.0, median_confidence / 0.65)
        tracking_score = (
            (1 - min(1.0, tracking_dropout_rate)) * 0.7
            + max(0.0, 1 - max(0.0, fragmentation_ratio - 1) / 2) * 0.3
        )
        pose_score = (
            pose_coverage * 0.7
            + min(1.0, median_visibility / 0.75) * 0.2
            + (1 - min(1.0, pose_jitter_rate * 4)) * 0.1
        )
        calibration_score = (
            calibration_confidence if calibration_available else 0.0
        )
        score = max(
            0.0,
            min(
                1.0,
                detection_score * 0.32
                + confidence_score * 0.08
                + tracking_score * 0.2
                + pose_score * 0.25
                + calibration_score * 0.15,
            ),
        )

        if any(reason in REVIEW_REASONS for reason in reasons):
            disposition = "review"
        elif reasons & RETRYABLE_REASONS:
            disposition = "retry"
        elif score >= self.minimum_score:
            disposition = "pass"
        else:
            disposition = "review"

        return QualityReport(
            score=round(score, 6),
            metrics={
                "frame_count": float(frame_count),
                "expected_dancer_count": float(expected),
                "person_count_recall": round(count_recall, 6),
                "exact_person_count_rate": round(exact_count_rate, 6),
                "extra_person_rate": round(extra_person_rate, 6),
                "median_detection_confidence": round(median_confidence, 6),
                "tracking_dropout_rate": round(tracking_dropout_rate, 6),
                "track_fragmentation_ratio": round(fragmentation_ratio, 6),
                "pose_coverage": round(pose_coverage, 6),
                "median_pose_visibility": round(median_visibility, 6),
                "pose_temporal_jitter_rate": round(pose_jitter_rate, 6),
                "calibration_confidence": round(calibration_confidence, 6),
                "calibration_in_bounds_rate": round(calibration_in_bounds, 6),
                "calibration_trajectory_jump_rate": round(
                    calibration_jump_rate, 6
                ),
            },
            reason_codes=tuple(sorted(str(reason) for reason in reasons)),
            segments=self._segments(frame_issues),
            disposition=disposition,
        )

    @staticmethod
    def _segments(
        frame_issues: list[tuple[float, set[str]]],
    ) -> tuple[AnalysisSegment, ...]:
        if not frame_issues:
            return ()
        timestamps = [value[0] for value in frame_issues]
        intervals = [
            second - first
            for first, second in zip(timestamps, timestamps[1:])
            if second > first
        ]
        gap_limit = max(0.75, (median(intervals) * 2.5 if intervals else 0.75))
        output: list[AnalysisSegment] = []
        start: float | None = None
        end = 0.0
        reasons: set[str] = set()
        previous = 0.0
        for timestamp, current_reasons in frame_issues:
            retryable = {
                str(reason)
                for reason in current_reasons
                if reason in RETRYABLE_REASONS
            }
            if not retryable:
                if start is not None:
                    output.append(
                        AnalysisSegment(start, end, tuple(sorted(reasons)))
                    )
                    start = None
                    reasons = set()
                previous = timestamp
                continue
            if start is None or timestamp - previous > gap_limit:
                if start is not None:
                    output.append(
                        AnalysisSegment(start, end, tuple(sorted(reasons)))
                    )
                start = timestamp
                reasons = set()
            end = timestamp
            reasons.update(retryable)
            previous = timestamp
        if start is not None:
            output.append(AnalysisSegment(start, end, tuple(sorted(reasons))))
        return tuple(output)

    @staticmethod
    def _pose_anchor(
        landmarks: list[dict[str, Any]],
    ) -> tuple[float, float] | None:
        by_index = {
            item.get("index"): item
            for item in landmarks
            if isinstance(item, dict)
        }
        anchors = [by_index.get(23), by_index.get(24), by_index.get(0)]
        points = [
            (float(item["x"]), float(item["y"]))
            for item in anchors
            if item is not None
            and QualityAuditor._finite(item.get("x"))
            and QualityAuditor._finite(item.get("y"))
        ]
        if not points:
            return None
        return (
            sum(point[0] for point in points) / len(points),
            sum(point[1] for point in points) / len(points),
        )

    @staticmethod
    def _empty_metrics() -> dict[str, float]:
        return {
            "frame_count": 0.0,
            "expected_dancer_count": 0.0,
            "person_count_recall": 0.0,
            "exact_person_count_rate": 0.0,
            "extra_person_rate": 0.0,
            "median_detection_confidence": 0.0,
            "tracking_dropout_rate": 1.0,
            "track_fragmentation_ratio": 0.0,
            "pose_coverage": 0.0,
            "median_pose_visibility": 0.0,
            "pose_temporal_jitter_rate": 0.0,
            "calibration_confidence": 0.0,
            "calibration_in_bounds_rate": 0.0,
            "calibration_trajectory_jump_rate": 0.0,
        }

    @staticmethod
    def _finite(value: Any) -> bool:
        try:
            return math.isfinite(float(value))
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _float(value: Any) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0.0
        return parsed if math.isfinite(parsed) else 0.0
