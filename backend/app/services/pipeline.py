import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.services.detector import PersonDetector
from app.services.pose import PoseEstimator
from app.services.projection import HomographyProjector
from app.services.tracking import (
    DetectorTrackingAdapter,
    FrameTracker,
    effective_buffer_frames,
)


@dataclass(frozen=True)
class ProgressEvent:
    stage: str
    progress: int
    sampled_frames: int = 0


ProgressCallback = Callable[[ProgressEvent], None]


class FramePosePipeline:
    """Sampled-frame tracking followed by per-person pose association."""

    def __init__(
        self,
        decoder: Any,
        detector: PersonDetector | None,
        pose_estimator: PoseEstimator,
        *,
        tracker: FrameTracker | None = None,
        frame_stride: int = 1,
        target_fps: float | None = None,
        tracker_name: str = "application",
        tracker_buffer_seconds: float = 2.0,
        tracker_buffer_frames: int | None = None,
        projector: HomographyProjector | None = None,
        grid_columns: int = 10,
        grid_rows: int = 10,
    ) -> None:
        self.decoder = decoder
        self.detector = detector
        self.pose_estimator = pose_estimator
        self.tracker = tracker or DetectorTrackingAdapter(detector, buffer_frames=0)
        self.frame_stride = frame_stride
        self.target_fps = target_fps
        self.tracker_name = tracker_name
        self.tracker_buffer_seconds = tracker_buffer_seconds
        self.tracker_buffer_frames = tracker_buffer_frames
        self.projector = projector
        self.grid_columns = grid_columns
        self.grid_rows = grid_rows

    def run(self, video_path: str | Path, progress_callback: ProgressCallback | None = None) -> dict[str, Any]:
        properties = self.decoder.inspect(video_path)
        self._emit(progress_callback, "decoding", 5, 0)
        sampled_frames: list[dict[str, Any]] = []
        total = properties.frame_count or 1
        processed_buffer = effective_buffer_frames(
            source_fps=properties.fps,
            frame_stride=self.frame_stride,
            target_fps=self.target_fps,
            buffer_seconds=self.tracker_buffer_seconds,
            explicit_processed_frames=self.tracker_buffer_frames,
        )
        self.tracker.reset()
        self.tracker.set_buffer_frames(processed_buffer)
        frame_iterator = self.decoder.iter_sampled_frames(
            video_path, frame_stride=self.frame_stride, target_fps=self.target_fps
        )
        try:
            for sampled_count, sampled in enumerate(frame_iterator, start=1):
                self._emit(
                    progress_callback,
                    "detecting",
                    min(45, 10 + int(sampled.frame_index / total * 35)),
                    sampled_count,
                )
                self._emit(progress_callback, "tracking", min(45, 10 + int(sampled.frame_index / total * 35)), sampled_count)
                tracks = self.tracker.track(sampled.frame, sampled.frame_index)
                serialized_tracks: list[dict[str, Any]] = []
                for track in tracks:
                    self._emit(
                        progress_callback,
                        "posing",
                        min(90, 45 + int(sampled_count / max(1, total) * 45)),
                        sampled_count,
                    )
                    item = track.to_dict()
                    pose = None
                    if (
                        track.status == "active"
                        and track.bbox_source == "observed"
                        and track.bbox is not None
                    ):
                        pose = self.pose_estimator.estimate(sampled.frame, track.bbox)
                    item["pose"] = pose.to_dict() if pose is not None else None
                    if (
                        self.projector is not None
                        and track.bbox is not None
                        and track.status != "lost"
                    ):
                        item["top_down"] = self.projector.project_bbox(
                            track.bbox,
                            properties.width,
                            properties.height,
                            source=track.bbox_source,
                            status=track.status,
                        )
                    else:
                        item["top_down"] = None
                    serialized_tracks.append(item)
                sampled_frames.append(
                    {
                        "frame_index": sampled.frame_index,
                        "timestamp_seconds": sampled.timestamp_seconds,
                        "detections": [
                            item for item in serialized_tracks if item["bbox_source"] == "observed"
                        ],
                        "tracks": serialized_tracks,
                    }
                )
        finally:
            close = getattr(frame_iterator, "close", None)
            if close:
                close()
            self.tracker.reset()

        self._emit(progress_callback, "completed", 100, len(sampled_frames))
        result = {
            "video": properties.to_dict(),
            "sampling": {"frame_stride": self.frame_stride, "target_fps": self.target_fps},
            "tracking": {
                "tracker": self.tracker_name,
                "buffer_frames": processed_buffer,
                "buffer_measured_in": "processed_frames",
            },
            "projection": {
                "calibration_available": self.projector is not None,
                "calibration_required": self.projector is None,
                "coordinate_space": "stage_normalized",
                "grid_columns": self.grid_columns,
                "grid_rows": self.grid_rows,
            },
            "sampled_frame_timestamps": [
                frame["timestamp_seconds"] for frame in sampled_frames
            ],
            "sampled_frames": sampled_frames,
        }
        # Keep the pipeline contract explicit: task results must be JSON-safe.
        json.dumps(result)
        return result

    @staticmethod
    def _emit(callback: ProgressCallback | None, stage: str, progress: int, sampled_frames: int) -> None:
        if callback:
            callback(ProgressEvent(stage=stage, progress=progress, sampled_frames=sampled_frames))
