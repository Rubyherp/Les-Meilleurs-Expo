import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol


class ModelAssetError(RuntimeError):
    """Raised when a configured inference asset is not provisioned."""


@dataclass(frozen=True)
class BoundingBox:
    x1: float
    y1: float
    x2: float
    y2: float

    def to_dict(self) -> dict[str, float]:
        return {"x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2}


@dataclass(frozen=True)
class Detection:
    box: BoundingBox
    confidence: float
    class_id: int = 0
    class_name: str = "person"

    def to_dict(self) -> dict[str, Any]:
        return {
            "box": self.box.to_dict(),
            "confidence": self.confidence,
            "class_id": self.class_id,
            "class_name": self.class_name,
        }


class PersonDetector(Protocol):
    def detect(self, frame: Any) -> list[Detection]: ...


def clamp_box(box: BoundingBox, width: int, height: int) -> BoundingBox | None:
    if not all(math.isfinite(value) for value in (box.x1, box.y1, box.x2, box.y2)):
        return None
    clamped = BoundingBox(
        x1=max(0.0, min(float(width), box.x1)),
        y1=max(0.0, min(float(height), box.y1)),
        x2=max(0.0, min(float(width), box.x2)),
        y2=max(0.0, min(float(height), box.y2)),
    )
    if clamped.x2 <= clamped.x1 or clamped.y2 <= clamped.y1:
        return None
    return clamped


@lru_cache(maxsize=8)
def _load_yolo_model(weights_path: str):
    path = Path(weights_path)
    if not path.is_file():
        raise ModelAssetError(
            f"YOLO weights were not found at {path}. Provision the file and set YOLO_MODEL_PATH."
        )
    try:
        from ultralytics import YOLO
    except ImportError as exc:  # pragma: no cover - dependency availability
        raise ModelAssetError("Ultralytics is required for YOLO person detection.") from exc
    return YOLO(str(path))


class YOLOPersonDetector:
    """Lazy, process-cached Ultralytics detector restricted to class 0 (person)."""

    def __init__(self, weights_path: str, confidence: float = 0.25, max_persons: int = 5, device: str = "cpu"):
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if max_persons < 1:
            raise ValueError("max_persons must be at least 1")
        self.weights_path = weights_path
        self.confidence = confidence
        self.max_persons = max_persons
        self.device = device

    def detect(self, frame: Any) -> list[Detection]:
        model = _load_yolo_model(self.weights_path)
        height, width = frame.shape[:2]
        results = model.predict(
            source=frame,
            classes=[0],
            conf=self.confidence,
            device=self.device,
            verbose=False,
        )
        if not results:
            return []

        boxes = results[0].boxes
        xyxy = self._to_list(boxes.xyxy)
        confidences = self._to_list(boxes.conf)
        class_ids = self._to_list(boxes.cls)
        detections: list[Detection] = []
        for coordinates, confidence, class_id in zip(xyxy, confidences, class_ids):
            class_number = int(class_id)
            if class_number != 0 or len(coordinates) != 4:
                continue
            if not math.isfinite(float(confidence)):
                continue
            box = clamp_box(BoundingBox(*map(float, coordinates)), width, height)
            if box is not None:
                detections.append(Detection(box=box, confidence=float(confidence)))
        detections.sort(key=lambda item: item.confidence, reverse=True)
        return detections[: self.max_persons]

    @staticmethod
    def _to_list(value: Any) -> list[Any]:
        if hasattr(value, "detach"):
            value = value.detach().cpu()
        if hasattr(value, "tolist"):
            value = value.tolist()
        return value
