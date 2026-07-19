from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


class VideoDecodeError(RuntimeError):
    """Raised when OpenCV cannot open or decode a video."""


@dataclass(frozen=True)
class VideoProperties:
    fps: float
    frame_count: int
    width: int
    height: int
    duration_seconds: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "fps": self.fps,
            "frame_count": self.frame_count,
            "width": self.width,
            "height": self.height,
            "duration_seconds": self.duration_seconds,
        }


@dataclass(frozen=True)
class SampledFrame:
    frame_index: int
    timestamp_seconds: float
    frame: Any


def _import_cv2() -> Any:
    try:
        import cv2
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise VideoDecodeError("OpenCV is required to decode videos.") from exc
    return cv2


class OpenCVVideoDecoder:
    """Frame metadata and streaming sampler backed by OpenCV VideoCapture."""

    def inspect(self, video_path: str | Path) -> VideoProperties:
        cv2 = _import_cv2()
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            capture.release()
            raise VideoDecodeError(f"Unable to open video for reading: {video_path}")
        try:
            return self._properties(capture, video_path)
        finally:
            capture.release()

    def iter_sampled_frames(
        self,
        video_path: str | Path,
        *,
        frame_stride: int = 1,
        target_fps: float | None = None,
    ) -> Iterator[SampledFrame]:
        if frame_stride < 1:
            raise ValueError("frame_stride must be at least 1")
        if target_fps is not None and target_fps <= 0:
            raise ValueError("target_fps must be greater than zero")

        cv2 = _import_cv2()
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            capture.release()
            raise VideoDecodeError(f"Unable to open video for reading: {video_path}")

        try:
            properties = self._properties(capture, video_path)
            stride = frame_stride
            if target_fps is not None:
                stride = max(1, round(properties.fps / target_fps))

            frame_index = 0
            decoded_frames = 0
            while True:
                ok, frame = capture.read()
                if not ok:
                    if decoded_frames == 0:
                        raise VideoDecodeError(f"Unable to decode any frames from video: {video_path}")
                    break
                decoded_frames += 1
                if frame_index % stride == 0:
                    yield SampledFrame(
                        frame_index=frame_index,
                        timestamp_seconds=frame_index / properties.fps,
                        frame=frame,
                    )
                frame_index += 1
        finally:
            capture.release()

    @staticmethod
    def _properties(capture: Any, video_path: str | Path) -> VideoProperties:
        cv2 = _import_cv2()
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_count = max(0, int(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
        if fps <= 0 or width <= 0 or height <= 0:
            raise VideoDecodeError(f"Video has invalid metadata and cannot be decoded: {video_path}")
        return VideoProperties(
            fps=fps,
            frame_count=frame_count,
            width=width,
            height=height,
            duration_seconds=frame_count / fps if frame_count else 0.0,
        )
