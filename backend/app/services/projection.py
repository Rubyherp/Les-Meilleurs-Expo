"""Calibration validation and normalized top-down homography projection."""

import math
from dataclasses import dataclass, field
from typing import Any, Sequence

from app.services.detector import BoundingBox


class CalibrationError(ValueError):
    """Raised when the ordered calibration quadrilateral is unusable."""


CalibrationPoints = tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]


def validate_calibration_points(points: Sequence[Sequence[float]]) -> CalibrationPoints:
    if len(points) != 4:
        raise CalibrationError("Calibration requires exactly four points.")
    normalized: list[tuple[float, float]] = []
    for point in points:
        if len(point) != 2:
            raise CalibrationError("Each calibration point must contain x and y.")
        x, y = float(point[0]), float(point[1])
        if not math.isfinite(x) or not math.isfinite(y):
            raise CalibrationError("Calibration points must contain finite values.")
        if not 0 <= x <= 1 or not 0 <= y <= 1:
            raise CalibrationError("Calibration points must be normalized to [0, 1].")
        normalized.append((x, y))

    crosses = []
    for index in range(4):
        first = normalized[index]
        second = normalized[(index + 1) % 4]
        third = normalized[(index + 2) % 4]
        crosses.append(_cross(first, second, third))
    if any(abs(value) <= 1e-9 for value in crosses):
        raise CalibrationError("Calibration points must form a non-degenerate quadrilateral.")
    if not all(value > 0 for value in crosses):
        raise CalibrationError(
            "Calibration points must be convex and ordered top-left, top-right, bottom-right, bottom-left."
        )
    return tuple(normalized)  # type: ignore[return-value]


@dataclass(frozen=True)
class HomographyProjector:
    """Maps normalized image coordinates into normalized stage coordinates."""

    points: CalibrationPoints
    grid_columns: int = 10
    grid_rows: int = 10
    _matrix: Any = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        validate_calibration_points(self.points)
        if self.grid_columns < 1 or self.grid_rows < 1:
            raise CalibrationError("Grid rows and columns must be positive.")
        try:
            import cv2
            import numpy as np
        except ImportError as exc:  # pragma: no cover - dependency availability
            raise CalibrationError("OpenCV and NumPy are required for projection.") from exc
        source = np.asarray(self.points, dtype=np.float32)
        destination = np.asarray(
            ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)), dtype=np.float32
        )
        matrix = cv2.getPerspectiveTransform(source, destination)
        if matrix is None or not np.isfinite(matrix).all():
            raise CalibrationError("Unable to construct a valid calibration homography.")
        object.__setattr__(self, "_matrix", matrix)

    def project_point(self, x: float, y: float, *, source: str, status: str) -> dict[str, Any]:
        if not math.isfinite(x) or not math.isfinite(y):
            raise CalibrationError("Projection input must contain finite values.")
        import cv2
        import numpy as np

        point = np.asarray([[[x, y]]], dtype=np.float32)
        projected = cv2.perspectiveTransform(point, self._matrix)[0][0]
        raw_x, raw_y = float(projected[0]), float(projected[1])
        if not math.isfinite(raw_x) or not math.isfinite(raw_y):
            raise CalibrationError("Homography produced an invalid projection.")
        # Keep the public stage coordinate bounded while retaining the raw
        # continuous result for diagnostics when a box falls outside the stage.
        projected_x = min(1.0, max(0.0, raw_x))
        projected_y = min(1.0, max(0.0, raw_y))
        row = min(self.grid_rows, max(1, math.ceil(projected_y * self.grid_rows)))
        column = min(self.grid_columns, max(1, math.ceil(projected_x * self.grid_columns)))
        return {
            "x": projected_x,
            "y": projected_y,
            "raw_x": raw_x,
            "raw_y": raw_y,
            "row": row,
            "column": column,
            "label": f"R{row}C{column}",
            "source": source,
            "status": status,
        }

    def project_bbox(
        self, bbox: BoundingBox, frame_width: int, frame_height: int, *, source: str, status: str
    ) -> dict[str, Any]:
        if frame_width <= 0 or frame_height <= 0:
            raise CalibrationError("Frame dimensions must be positive for projection.")
        bottom_center_x = ((bbox.x1 + bbox.x2) / 2) / frame_width
        bottom_center_y = bbox.y2 / frame_height
        return self.project_point(bottom_center_x, bottom_center_y, source=source, status=status)


def _cross(first: tuple[float, float], second: tuple[float, float], third: tuple[float, float]) -> float:
    first_vector = (second[0] - first[0], second[1] - first[1])
    second_vector = (third[0] - second[0], third[1] - second[1])
    return first_vector[0] * second_vector[1] - first_vector[1] * second_vector[0]
