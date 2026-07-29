"""Application tracking contracts and an Ultralytics ByteTrack adapter.

The application intentionally owns only the lifecycle/occlusion bookkeeping.
Ultralytics owns the actual ByteTrack association. Model weights stay cached
within each worker process while tracker state is reset between videos.
"""

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Protocol

from app.services.detector import BoundingBox, ModelAssetError, clamp_box

TrackStatus = Literal["active", "occluded", "lost"]
BboxSource = Literal["observed", "predicted", "none"]


@dataclass(frozen=True)
class TrackObservation:
    """One observation emitted by an underlying tracker for a sampled frame."""

    bbox: BoundingBox
    confidence: float
    external_track_id: int | None = None
    class_id: int = 0
    class_name: str = "person"


@dataclass
class TrackRecord:
    """Mutable application-owned history for one stable track ID."""

    track_id: int
    status: TrackStatus
    bbox: BoundingBox | None
    confidence: float | None
    first_observed_frame: int
    last_observed_frame: int
    bbox_source: BboxSource = "observed"
    missed_frames: int = 0
    reactivated: bool = False
    external_track_id: int | None = None
    last_observed_bbox: BoundingBox | None = None
    class_id: int = 0
    class_name: str = "person"

    def as_detection(self, bbox_source: BboxSource) -> "TrackedDetection":
        return TrackedDetection(
            track_id=self.track_id,
            status=self.status,
            bbox_source=bbox_source,
            bbox=self.bbox,
            confidence=self.confidence,
            first_observed_frame=self.first_observed_frame,
            last_observed_frame=self.last_observed_frame,
            missed_frames=self.missed_frames,
            reactivated=self.reactivated,
            external_track_id=self.external_track_id,
            class_id=self.class_id,
            class_name=self.class_name,
        )


@dataclass(frozen=True)
class TrackedDetection:
    """Serializable application-level track state for one sampled frame."""

    track_id: int
    status: TrackStatus
    bbox_source: BboxSource
    bbox: BoundingBox | None
    confidence: float | None
    first_observed_frame: int
    last_observed_frame: int
    missed_frames: int
    reactivated: bool
    external_track_id: int | None = None
    class_id: int = 0
    class_name: str = "person"

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "status": self.status,
            "bbox_source": self.bbox_source,
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "confidence": self.confidence,
            "first_observed_frame": self.first_observed_frame,
            "last_observed_frame": self.last_observed_frame,
            "missed_frames": self.missed_frames,
            "reactivated": self.reactivated,
            "external_track_id": self.external_track_id,
            "class_id": self.class_id,
            "class_name": self.class_name,
        }


class FrameTracker(Protocol):
    def track(self, frame: Any, frame_index: int) -> list[TrackedDetection]: ...

    def reset(self) -> None: ...

    def set_buffer_frames(self, buffer_frames: int) -> None: ...


class ApplicationTracker:
    """Adds stable application IDs and conservative occlusion bookkeeping.

    A missing observation keeps the last observed box as a conservative
    prediction. This avoids pretending to know motion during occlusion. A
    track is removed after ``buffer_frames`` processed frames, so a later
    detection receives a new application ID.
    """

    def __init__(self, buffer_frames: int = 30, iou_threshold: float = 0.1) -> None:
        if buffer_frames < 0:
            raise ValueError("buffer_frames must not be negative")
        if not 0 <= iou_threshold <= 1:
            raise ValueError("iou_threshold must be between 0 and 1")
        self.buffer_frames = buffer_frames
        self.iou_threshold = iou_threshold
        self._next_track_id = 1
        self._active: dict[int, TrackRecord] = {}
        self._external_to_application: dict[int, int] = {}
        self.records: dict[int, TrackRecord] = {}

    def set_buffer_frames(self, buffer_frames: int) -> None:
        if buffer_frames < 0:
            raise ValueError("buffer_frames must not be negative")
        self.buffer_frames = buffer_frames

    def reset(self) -> None:
        self._next_track_id = 1
        self._active.clear()
        self._external_to_application.clear()
        self.records.clear()

    def update(self, observations: list[TrackObservation], frame_index: int) -> list[TrackedDetection]:
        output: list[TrackedDetection] = []
        matched: set[int] = set()

        for observation in observations:
            application_id = self._match_observation(observation, matched)
            if application_id is None:
                application_id = self._next_track_id
                self._next_track_id += 1
                record = TrackRecord(
                    track_id=application_id,
                    status="active",
                    bbox=observation.bbox,
                    confidence=observation.confidence,
                    first_observed_frame=frame_index,
                    last_observed_frame=frame_index,
                    last_observed_bbox=observation.bbox,
                    bbox_source="observed",
                    external_track_id=observation.external_track_id,
                    class_id=observation.class_id,
                    class_name=observation.class_name,
                )
                self._active[application_id] = record
                self.records[application_id] = record
            else:
                record = self._active[application_id]
                record.reactivated = record.missed_frames > 0
                record.status = "active"
                record.bbox_source = "observed"
                record.bbox = observation.bbox
                record.last_observed_bbox = observation.bbox
                record.confidence = observation.confidence
                record.last_observed_frame = frame_index
                record.missed_frames = 0
                if (
                    record.external_track_id is not None
                    and record.external_track_id != observation.external_track_id
                ):
                    self._external_to_application.pop(record.external_track_id, None)
                record.external_track_id = observation.external_track_id
                record.class_id = observation.class_id
                record.class_name = observation.class_name

            matched.add(application_id)
            if observation.external_track_id is not None:
                self._external_to_application[observation.external_track_id] = application_id
            output.append(record.as_detection("observed"))

        for application_id, record in list(self._active.items()):
            if application_id in matched:
                continue
            record.reactivated = False
            record.missed_frames += 1
            if record.missed_frames <= self.buffer_frames:
                record.status = "occluded"
                record.bbox = record.last_observed_bbox
                record.bbox_source = "predicted"
                output.append(record.as_detection("predicted"))
            else:
                record.status = "lost"
                record.bbox = None
                record.bbox_source = "none"
                output.append(record.as_detection("none"))
                self._remove_active(application_id)

        return sorted(output, key=lambda item: item.track_id)

    def _match_observation(self, observation: TrackObservation, matched: set[int]) -> int | None:
        external_id = observation.external_track_id
        if external_id is not None:
            candidate = self._external_to_application.get(external_id)
            if candidate in self._active and candidate not in matched:
                return candidate

        best_id: int | None = None
        best_iou = self.iou_threshold
        for application_id, record in self._active.items():
            if application_id in matched or record.bbox is None:
                continue
            overlap = _iou(record.bbox, observation.bbox)
            if overlap >= best_iou:
                best_iou = overlap
                best_id = application_id
        return best_id

    def _remove_active(self, application_id: int) -> None:
        record = self._active.pop(application_id, None)
        if record and record.external_track_id is not None:
            self._external_to_application.pop(record.external_track_id, None)


class DetectorTrackingAdapter:
    """Compatibility adapter for Phase 2 callers without an Ultralytics tracker."""

    def __init__(self, detector: Any, buffer_frames: int = 0) -> None:
        self.detector = detector
        self.application_tracker = ApplicationTracker(buffer_frames=buffer_frames)

    def track(self, frame: Any, frame_index: int) -> list[TrackedDetection]:
        observations = [
            TrackObservation(bbox=item.box, confidence=item.confidence)
            for item in self.detector.detect(frame)
        ]
        return self.application_tracker.update(observations, frame_index)

    def reset(self) -> None:
        self.application_tracker.reset()

    def set_buffer_frames(self, buffer_frames: int) -> None:
        self.application_tracker.set_buffer_frames(buffer_frames)


class UltralyticsByteTrackAdapter:
    """Lazy adapter around the public Ultralytics ``model.track`` API."""

    def __init__(
        self,
        weights_path: str,
        *,
        tracker_name: str = "bytetrack.yaml",
        confidence: float = 0.1,
        high_confidence: float = 0.25,
        max_persons: int = 5,
        device: str = "cpu",
        image_size: int = 640,
    ) -> None:
        if not 0 <= confidence <= 1 or not 0 <= high_confidence <= 1:
            raise ValueError("tracker confidence thresholds must be between 0 and 1")
        if high_confidence < confidence:
            raise ValueError("high_confidence must be at least the low confidence threshold")
        self.weights_path = weights_path
        self.tracker_name = tracker_name
        self.confidence = confidence
        self.high_confidence = high_confidence
        self.max_persons = max_persons
        self.device = device
        self.image_size = image_size
        self._model: Any | None = None

    def _load_model(self) -> Any:
        if self._model is None:
            self._model = _load_tracking_model(self.weights_path)
        return self._model

    def track(self, frame: Any) -> list[TrackObservation]:
        model = self._load_model()
        results = model.track(
            source=frame,
            tracker=self.tracker_name,
            persist=True,
            classes=[0],
            conf=self.confidence,
            device=self.device,
            imgsz=self.image_size,
            verbose=False,
        )
        return self._parse_result(results, frame.shape[1], frame.shape[0])

    def reset(self) -> None:
        if self._model is None:
            return
        predictor = getattr(self._model, "predictor", None)
        for tracker in getattr(predictor, "trackers", ()):
            reset = getattr(tracker, "reset", None)
            if reset is not None:
                reset()
        if predictor is not None and hasattr(predictor, "vid_path"):
            predictor.vid_path = [None] * len(getattr(predictor, "trackers", ()))

    def _parse_result(self, results: Any, width: int, height: int) -> list[TrackObservation]:
        if not results:
            return []
        boxes = getattr(results[0], "boxes", None)
        if boxes is None:
            return []
        xyxy = self._to_list(getattr(boxes, "xyxy", []))
        confidences = self._to_list(getattr(boxes, "conf", []))
        class_ids = self._to_list(getattr(boxes, "cls", []))
        raw_ids = getattr(boxes, "id", None)
        ids = self._to_list(raw_ids) if raw_ids is not None else [None] * len(xyxy)
        observations: list[TrackObservation] = []
        for coordinates, confidence, class_id, external_id in zip(
            xyxy, confidences, class_ids, ids
        ):
            if len(coordinates) != 4 or int(class_id) != 0:
                continue
            if not math.isfinite(float(confidence)):
                continue
            # Keep low-confidence candidates available to ByteTrack via conf,
            # but only expose high-confidence observations to pose/application state.
            if float(confidence) < self.high_confidence:
                continue
            box = clamp_box(BoundingBox(*map(float, coordinates)), width, height)
            if box is None:
                continue
            parsed_id = int(external_id) if external_id is not None else None
            observations.append(
                TrackObservation(box, float(confidence), parsed_id, int(class_id), "person")
            )
        observations.sort(key=lambda item: item.confidence, reverse=True)
        return observations[: self.max_persons]

    @staticmethod
    def _to_list(value: Any) -> list[Any]:
        if hasattr(value, "detach"):
            value = value.detach().cpu()
        if hasattr(value, "tolist"):
            value = value.tolist()
        return value


@lru_cache(maxsize=4)
def _load_tracking_model(weights_path: str) -> Any:
    path = Path(weights_path)
    if not path.is_file():
        raise ModelAssetError(
            f"YOLO weights were not found at {path}. Provision the file and set YOLO_MODEL_PATH."
        )
    try:
        from ultralytics import YOLO
    except ImportError as exc:  # pragma: no cover - dependency availability
        raise ModelAssetError("Ultralytics is required for ByteTrack.") from exc
    return YOLO(str(path))


class UltralyticsByteTrack:
    """One-video facade combining Ultralytics observations and app bookkeeping."""

    def __init__(
        self,
        adapter: UltralyticsByteTrackAdapter,
        buffer_frames: int = 30,
        iou_threshold: float = 0.1,
    ) -> None:
        self.adapter = adapter
        self.application_tracker = ApplicationTracker(
            buffer_frames=buffer_frames, iou_threshold=iou_threshold
        )

    def track(self, frame: Any, frame_index: int) -> list[TrackedDetection]:
        return self.application_tracker.update(self.adapter.track(frame), frame_index)

    def reset(self) -> None:
        self.adapter.reset()
        self.application_tracker.reset()

    def set_buffer_frames(self, buffer_frames: int) -> None:
        self.application_tracker.set_buffer_frames(buffer_frames)


def _iou(left: BoundingBox, right: BoundingBox) -> float:
    intersection_left = max(left.x1, right.x1)
    intersection_top = max(left.y1, right.y1)
    intersection_right = min(left.x2, right.x2)
    intersection_bottom = min(left.y2, right.y2)
    intersection_width = max(0.0, intersection_right - intersection_left)
    intersection_height = max(0.0, intersection_bottom - intersection_top)
    intersection = intersection_width * intersection_height
    if intersection == 0:
        return 0.0
    left_area = (left.x2 - left.x1) * (left.y2 - left.y1)
    right_area = (right.x2 - right.x1) * (right.y2 - right.y1)
    return intersection / (left_area + right_area - intersection)


def effective_buffer_frames(
    *,
    source_fps: float,
    frame_stride: int,
    target_fps: float | None,
    buffer_seconds: float,
    explicit_processed_frames: int | None,
) -> int:
    """Convert a seconds buffer to processed-frame units after sampling."""
    if explicit_processed_frames is not None:
        return max(0, explicit_processed_frames)
    effective_stride = frame_stride
    if target_fps is not None:
        effective_stride = max(1, round(source_fps / target_fps))
    processed_fps = source_fps / max(1, effective_stride)
    return max(0, round(buffer_seconds * processed_fps))
