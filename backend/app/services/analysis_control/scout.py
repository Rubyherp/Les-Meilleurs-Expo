from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from app.services.analysis_control.calibration import CalibrationSpecialist
from app.services.analysis_control.models import ReasonCode, ScoutReport
from app.services.video import OpenCVVideoDecoder


class VideoScout:
    """Low-cost visual diagnostics that do not load YOLO or MediaPipe."""

    def __init__(
        self,
        *,
        target_fps: float = 2.0,
        max_frames: int = 24,
        calibration_specialist: CalibrationSpecialist | None = None,
    ) -> None:
        self.target_fps = target_fps
        self.max_frames = max_frames
        self.calibration_specialist = calibration_specialist or CalibrationSpecialist()

    def inspect(
        self,
        video_path: str | Path,
        *,
        allow_calibration_proposal: bool = False,
    ) -> ScoutReport:
        import cv2
        import numpy as np

        decoder = OpenCVVideoDecoder()
        properties = decoder.inspect(video_path)
        brightness: list[float] = []
        blur: list[float] = []
        motion: list[float] = []
        candidate_frames: list[Any] = []
        previous_gray: Any | None = None

        iterator = decoder.iter_sampled_frames(
            video_path, target_fps=self.target_fps
        )
        try:
            for sampled in iterator:
                frame = sampled.frame
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                brightness.append(float(np.mean(gray)) / 255.0)
                blur.append(float(cv2.Laplacian(gray, cv2.CV_64F).var()))
                if previous_gray is not None:
                    motion.append(self._camera_motion(previous_gray, gray))
                previous_gray = gray
                if allow_calibration_proposal:
                    candidate_frames.append(frame.copy())
                if len(brightness) >= self.max_frames:
                    break
        finally:
            close = getattr(iterator, "close", None)
            if close is not None:
                close()

        mean_brightness = self._mean(brightness)
        dark_frame_rate = (
            sum(value < 0.18 for value in brightness) / len(brightness)
            if brightness
            else 1.0
        )
        blur_score = self._median(blur)
        camera_motion_score = self._median(motion)
        reasons: list[str] = []
        if dark_frame_rate > 0.35 or mean_brightness < 0.18:
            reasons.append(ReasonCode.LOW_LIGHT)
        if blur and blur_score < 35:
            reasons.append(ReasonCode.BLURRY_VIDEO)
        if motion and camera_motion_score > 0.012:
            reasons.append(ReasonCode.CAMERA_MOTION)
        if not brightness:
            reasons.append(ReasonCode.INSUFFICIENT_EVIDENCE)

        proposal = None
        if allow_calibration_proposal and candidate_frames:
            proposal = self.calibration_specialist.propose(candidate_frames)

        return ScoutReport(
            video=properties.to_dict(),
            sampled_frames=len(brightness),
            brightness_mean=round(mean_brightness, 6),
            dark_frame_rate=round(dark_frame_rate, 6),
            blur_score=round(blur_score, 6),
            camera_motion_score=round(camera_motion_score, 6),
            reason_codes=tuple(dict.fromkeys(str(reason) for reason in reasons)),
            calibration_proposal=proposal,
        )

    @staticmethod
    def _camera_motion(previous: Any, current: Any) -> float:
        import cv2
        import numpy as np

        points = cv2.goodFeaturesToTrack(
            previous,
            maxCorners=120,
            qualityLevel=0.01,
            minDistance=8,
            blockSize=7,
        )
        if points is None or len(points) < 8:
            return 0.0
        next_points, status, _ = cv2.calcOpticalFlowPyrLK(
            previous, current, points, None
        )
        if next_points is None or status is None:
            return 0.0
        valid = status.reshape(-1) == 1
        if int(valid.sum()) < 8:
            return 0.0
        displacement = next_points[valid] - points[valid]
        magnitudes = np.linalg.norm(displacement.reshape(-1, 2), axis=1)
        diagonal = math.hypot(current.shape[1], current.shape[0])
        return float(np.median(magnitudes)) / max(1.0, diagonal)

    @staticmethod
    def _mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _median(values: list[float]) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[middle]
        return (ordered[middle - 1] + ordered[middle]) / 2
