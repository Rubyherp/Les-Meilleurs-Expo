from __future__ import annotations

import math
from typing import Any, Sequence

from app.services.projection import CalibrationError, validate_calibration_points


class CalibrationSpecialist:
    """Propose and verify calibration without silently fabricating a homography."""

    def propose(self, frames: Sequence[Any]) -> dict[str, Any] | None:
        import cv2
        import numpy as np

        candidates: list[list[tuple[float, float]]] = []
        for frame in frames:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(gray, 60, 160)
            contours, _ = cv2.findContours(
                edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
            )
            height, width = gray.shape[:2]
            frame_area = float(width * height)
            best: tuple[float, list[tuple[float, float]]] | None = None
            for contour in contours:
                perimeter = cv2.arcLength(contour, True)
                approximation = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
                if len(approximation) != 4 or not cv2.isContourConvex(approximation):
                    continue
                area_ratio = abs(cv2.contourArea(approximation)) / max(1.0, frame_area)
                if not 0.18 <= area_ratio <= 0.92:
                    continue
                points = [
                    (float(point[0][0]) / width, float(point[0][1]) / height)
                    for point in approximation
                ]
                ordered = self._order_points(points)
                try:
                    validate_calibration_points(ordered)
                except CalibrationError:
                    continue
                if best is None or area_ratio > best[0]:
                    best = (area_ratio, ordered)
            if best is not None:
                candidates.append(best[1])

        if len(candidates) < 3:
            return None
        stack = np.asarray(candidates, dtype=float)
        median = np.median(stack, axis=0)
        deviations = np.linalg.norm(stack - median[None, :, :], axis=2)
        median_deviation = float(np.median(deviations))
        max_deviation = float(np.max(np.median(deviations, axis=1)))
        if median_deviation > 0.025 or max_deviation > 0.06:
            return None
        points = [(float(point[0]), float(point[1])) for point in median]
        try:
            validated = validate_calibration_points(points)
        except CalibrationError:
            return None
        confidence = min(
            0.99,
            0.65
            + min(0.2, len(candidates) * 0.025)
            + max(0.0, 0.14 - median_deviation * 3),
        )
        return {
            "points": [list(point) for point in validated],
            "source": "agent",
            "status": "proposed",
            "confidence": round(confidence, 6),
            "supporting_frames": len(candidates),
            "median_corner_deviation": round(median_deviation, 6),
            "requires_confirmation": True,
        }

    def evaluate(
        self, calibration: dict[str, Any] | None, result: dict[str, Any]
    ) -> dict[str, Any]:
        if calibration is None:
            return {
                "source": "none",
                "status": "unavailable",
                "verified": False,
                "confidence": 0.0,
                "reason_codes": ["calibration_unverified"],
            }
        points = calibration.get("points")
        try:
            validated = validate_calibration_points(points or [])
        except CalibrationError as exc:
            return {
                "source": calibration.get("source", "unknown"),
                "status": "rejected",
                "verified": False,
                "confidence": 0.0,
                "reason_codes": ["calibration_unverified"],
                "explanation": str(exc),
            }

        raw_points: list[tuple[float, float]] = []
        trajectories: dict[int, list[tuple[float, float]]] = {}
        for frame in result.get("sampled_frames", []):
            for track in frame.get("tracks", []):
                top_down = track.get("top_down")
                if not isinstance(top_down, dict):
                    continue
                raw_x, raw_y = top_down.get("raw_x"), top_down.get("raw_y")
                if self._finite(raw_x) and self._finite(raw_y):
                    value = (float(raw_x), float(raw_y))
                    raw_points.append(value)
                    track_id = track.get("track_id")
                    if isinstance(track_id, int):
                        trajectories.setdefault(track_id, []).append(value)

        in_bounds_rate = (
            sum(0 <= x <= 1 and 0 <= y <= 1 for x, y in raw_points)
            / len(raw_points)
            if raw_points
            else 0.0
        )
        jumps = 0
        transitions = 0
        for points_for_track in trajectories.values():
            for first, second in zip(points_for_track, points_for_track[1:]):
                transitions += 1
                if math.dist(first, second) > 0.22:
                    jumps += 1
        jump_rate = jumps / transitions if transitions else 0.0
        area = self._polygon_area(validated)
        geometry_score = min(1.0, area / 0.25)
        evidence_score = min(1.0, len(raw_points) / 12)
        confidence = (
            geometry_score * 0.25
            + in_bounds_rate * 0.5
            + (1 - min(1.0, jump_rate * 4)) * 0.15
            + evidence_score * 0.1
        )
        reasons: list[str] = []
        if raw_points and in_bounds_rate < 0.85:
            reasons.append("calibration_out_of_bounds")
        if jump_rate > 0.12:
            reasons.append("calibration_trajectory_jump")
        source = calibration.get("source", "human")
        verified = (
            source == "human"
            or (
                confidence >= 0.9
                and calibration.get("status") in {"verified", "agent_verified"}
            )
        )
        if not verified:
            reasons.append("calibration_unverified")
        return {
            "source": source,
            "status": "verified" if verified and not reasons else "needs_review",
            "verified": verified and not reasons,
            "confidence": round(confidence, 6),
            "in_bounds_rate": round(in_bounds_rate, 6),
            "trajectory_jump_rate": round(jump_rate, 6),
            "quadrilateral_area": round(area, 6),
            "reason_codes": reasons,
        }

    @staticmethod
    def _order_points(
        points: Sequence[tuple[float, float]],
    ) -> list[tuple[float, float]]:
        center_x = sum(point[0] for point in points) / 4
        center_y = sum(point[1] for point in points) / 4
        clockwise = sorted(
            points,
            key=lambda point: math.atan2(point[1] - center_y, point[0] - center_x),
        )
        start = min(
            range(4), key=lambda index: clockwise[index][0] + clockwise[index][1]
        )
        ordered = clockwise[start:] + clockwise[:start]
        if ordered[1][0] < ordered[-1][0]:
            ordered = [ordered[0], *reversed(ordered[1:])]
        return ordered

    @staticmethod
    def _polygon_area(points: Sequence[tuple[float, float]]) -> float:
        return abs(
            sum(
                points[index][0] * points[(index + 1) % 4][1]
                - points[(index + 1) % 4][0] * points[index][1]
                for index in range(4)
            )
            / 2
        )

    @staticmethod
    def _finite(value: Any) -> bool:
        try:
            return math.isfinite(float(value))
        except (TypeError, ValueError):
            return False
