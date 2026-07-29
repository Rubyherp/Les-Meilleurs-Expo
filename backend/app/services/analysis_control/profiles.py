from __future__ import annotations

import hashlib
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from app.core.config import Settings
from app.services.analysis_control.models import AnalysisProfile, ReasonCode, ScoutReport


class ProfileRegistry:
    """Approved configurations available to the deterministic router."""

    def __init__(self, settings: Settings, expected_dancer_count: int) -> None:
        self.settings = settings
        self.max_persons = max(settings.max_persons, expected_dancer_count)

    def balanced(self) -> AnalysisProfile:
        settings = self.settings
        return AnalysisProfile(
            profile_id="balanced-v1",
            yolo_model_path=settings.yolo_model_path,
            pose_model_path=settings.pose_model_path,
            tracker_name=settings.tracker_name,
            target_fps=settings.sample_fps,
            frame_stride=settings.frame_stride,
            image_size=settings.analysis_image_size,
            low_confidence=settings.tracker_low_confidence,
            high_confidence=settings.tracker_high_confidence,
            max_persons=self.max_persons,
            crop_padding=settings.crop_padding,
            tracker_buffer_seconds=settings.tracker_buffer_seconds,
            tracker_buffer_frames=settings.tracker_buffer_frames,
            tracker_iou_threshold=settings.tracker_iou_threshold,
            pose_min_detection_confidence=settings.pose_min_detection_confidence,
            pose_min_presence_confidence=settings.pose_min_presence_confidence,
            pose_min_tracking_confidence=settings.pose_min_tracking_confidence,
            yolo_model_sha256=_asset_sha256(settings.yolo_model_path),
            pose_model_sha256=_asset_sha256(settings.pose_model_path),
        )

    def initial(self, scout: ScoutReport) -> AnalysisProfile:
        profile = self.balanced()
        visual_risks = {
            ReasonCode.CAMERA_MOTION,
            ReasonCode.LOW_LIGHT,
            ReasonCode.BLURRY_VIDEO,
        }
        if not set(scout.reason_codes) & visual_risks:
            profile = replace(
                profile,
                profile_id="fast-static-v1",
                target_fps=self.settings.analysis_fast_sample_fps,
            )
        if ReasonCode.CAMERA_MOTION in scout.reason_codes:
            profile = replace(
                profile,
                profile_id="balanced-moving-camera-v1",
                tracker_name="botsort.yaml",
            )
        return profile

    def recovery(self, reason_codes: tuple[str, ...]) -> AnalysisProfile:
        settings = self.settings
        reasons = set(reason_codes)
        base = self.balanced()
        detector_failure = bool(
            reasons
            & {
                ReasonCode.LOW_DETECTION_RECALL,
                ReasonCode.LOW_DETECTION_CONFIDENCE,
                ReasonCode.EXTRA_PERSON_DETECTIONS,
            }
        )
        pose_failure = bool(
            reasons
            & {
                ReasonCode.POSE_DROPOUT,
                ReasonCode.LOW_POSE_VISIBILITY,
                ReasonCode.POSE_TEMPORAL_JITTER,
            }
        )
        tracking_failure = bool(
            reasons
            & {
                ReasonCode.TRACKING_DROPOUT,
                ReasonCode.TRACK_FRAGMENTATION,
                ReasonCode.CAMERA_MOTION,
            }
        )

        yolo_path = self._available_or_default(
            settings.analysis_recovery_yolo_model_path, base.yolo_model_path
        )
        pose_path = self._available_or_default(
            settings.analysis_recovery_pose_model_path, base.pose_model_path
        )
        labels = ["recovery"]
        if detector_failure:
            labels.append("detector")
        if pose_failure:
            labels.append("pose")
        if tracking_failure:
            labels.append("tracking")

        return replace(
            base,
            profile_id="-".join(labels) + "-v1",
            yolo_model_path=yolo_path if detector_failure else base.yolo_model_path,
            pose_model_path=pose_path if pose_failure else base.pose_model_path,
            yolo_model_sha256=(
                _asset_sha256(yolo_path)
                if detector_failure
                else base.yolo_model_sha256
            ),
            pose_model_sha256=(
                _asset_sha256(pose_path)
                if pose_failure
                else base.pose_model_sha256
            ),
            tracker_name="botsort.yaml" if tracking_failure else base.tracker_name,
            target_fps=settings.analysis_recovery_sample_fps,
            image_size=(
                settings.analysis_recovery_image_size
                if detector_failure
                else settings.analysis_image_size
            ),
            low_confidence=max(0.01, base.low_confidence * 0.75),
            crop_padding=min(0.5, base.crop_padding + (0.1 if pose_failure else 0.05)),
            tracker_buffer_seconds=(
                max(3.0, base.tracker_buffer_seconds)
                if tracking_failure
                else base.tracker_buffer_seconds
            ),
        )

    @staticmethod
    def _available_or_default(candidate: str | None, default: str) -> str:
        if candidate and Path(candidate).is_file():
            return candidate
        return default


def _asset_sha256(path_value: str) -> str:
    path = Path(path_value)
    try:
        stat = path.stat()
    except OSError:
        return "missing"
    return _cached_asset_sha256(
        str(path.resolve()), stat.st_mtime_ns, stat.st_size
    )


@lru_cache(maxsize=16)
def _cached_asset_sha256(path: str, modified_ns: int, size: int) -> str:
    del modified_ns, size
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
