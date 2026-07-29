from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from app.services.detector import BoundingBox, ModelAssetError


@dataclass(frozen=True)
class PoseEstimate:
    landmarks: list[dict[str, Any]]
    world_landmarks: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {"landmarks": self.landmarks, "world_landmarks": self.world_landmarks}


class PoseEstimator:
    def estimate(self, frame: Any, box: BoundingBox) -> PoseEstimate | None:
        raise NotImplementedError


def _value(landmark: Any, name: str) -> Any:
    if isinstance(landmark, dict):
        return landmark.get(name)
    return getattr(landmark, name, None)


def _landmark_dict(landmark: Any, index: int) -> dict[str, Any]:
    result: dict[str, Any] = {
        "index": index,
        "x": float(_value(landmark, "x") or 0.0),
        "y": float(_value(landmark, "y") or 0.0),
        "z": float(_value(landmark, "z") or 0.0),
    }
    for key in ("visibility", "presence"):
        value = _value(landmark, key)
        if value is not None:
            result[key] = float(value)
    return result


def map_landmarks_to_frame(
    landmarks: Iterable[Any], crop_box: BoundingBox, frame_width: int, frame_height: int
) -> list[dict[str, Any]]:
    crop_width = crop_box.x2 - crop_box.x1
    crop_height = crop_box.y2 - crop_box.y1
    mapped: list[dict[str, Any]] = []
    for index, landmark in enumerate(landmarks):
        local = _landmark_dict(landmark, index)
        local["crop_x"] = local["x"]
        local["crop_y"] = local["y"]
        x_px = crop_box.x1 + local["crop_x"] * crop_width
        y_px = crop_box.y1 + local["crop_y"] * crop_height
        local["x_px"] = x_px
        local["y_px"] = y_px
        local["x"] = x_px / frame_width
        local["y"] = y_px / frame_height
        local["x_full"] = local["x"]
        local["y_full"] = local["y"]
        mapped.append(local)
    return mapped


def padded_box(box: BoundingBox, frame_width: int, frame_height: int, padding: float) -> BoundingBox | None:
    if padding < 0:
        raise ValueError("padding must not be negative")
    width = box.x2 - box.x1
    height = box.y2 - box.y1
    if width <= 0 or height <= 0:
        return None
    return BoundingBox(
        max(0.0, box.x1 - width * padding),
        max(0.0, box.y1 - height * padding),
        min(float(frame_width), box.x2 + width * padding),
        min(float(frame_height), box.y2 + height * padding),
    )


@lru_cache(maxsize=12)
def _load_pose_landmarker(
    asset_path: str,
    min_detection_confidence: float,
    min_presence_confidence: float,
    min_tracking_confidence: float,
):
    path = Path(asset_path)
    if not path.is_file():
        raise ModelAssetError(
            f"MediaPipe pose asset was not found at {path}. Provision the file and set POSE_MODEL_PATH."
        )
    try:
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
    except ImportError as exc:  # pragma: no cover - dependency availability
        raise ModelAssetError("MediaPipe is required for pose estimation.") from exc

    options = vision.PoseLandmarkerOptions(
        base_options=python.BaseOptions(model_asset_path=str(path)),
        running_mode=vision.RunningMode.IMAGE,
        num_poses=1,
        min_pose_detection_confidence=min_detection_confidence,
        min_pose_presence_confidence=min_presence_confidence,
        min_tracking_confidence=min_tracking_confidence,
    )
    return mp, vision.PoseLandmarker.create_from_options(options)


class MediaPipePoseEstimator(PoseEstimator):
    """MediaPipe Tasks PoseLandmarker in IMAGE mode, loaded once per process."""

    def __init__(
        self,
        asset_path: str,
        padding: float = 0.15,
        *,
        min_detection_confidence: float = 0.5,
        min_presence_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ):
        if padding < 0:
            raise ValueError("padding must not be negative")
        self.asset_path = asset_path
        self.padding = padding
        self.min_detection_confidence = min_detection_confidence
        self.min_presence_confidence = min_presence_confidence
        self.min_tracking_confidence = min_tracking_confidence

    def estimate(self, frame: Any, box: BoundingBox) -> PoseEstimate | None:
        height, width = frame.shape[:2]
        crop_box = padded_box(box, width, height, self.padding)
        if crop_box is None:
            return None
        x1, y1 = int(crop_box.x1), int(crop_box.y1)
        x2, y2 = int(crop_box.x2), int(crop_box.y2)
        if x2 <= x1 or y2 <= y1:
            return None
        effective_crop_box = BoundingBox(float(x1), float(y1), float(x2), float(y2))

        import cv2

        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None
        mp, landmarker = _load_pose_landmarker(
            self.asset_path,
            self.min_detection_confidence,
            self.min_presence_confidence,
            self.min_tracking_confidence,
        )
        rgb_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_crop)
        result = landmarker.detect(image)
        poses = getattr(result, "pose_landmarks", None) or []
        if not poses:
            return None
        world_poses = getattr(result, "pose_world_landmarks", None) or []
        world = world_poses[0] if world_poses else []
        return PoseEstimate(
            landmarks=map_landmarks_to_frame(poses[0], effective_crop_box, width, height),
            world_landmarks=[_landmark_dict(item, index) for index, item in enumerate(world)],
        )
