import json
from dataclasses import dataclass

import numpy as np
import pytest

from app.services.detector import BoundingBox, Detection
from app.services.pipeline import FramePosePipeline, ProgressEvent
from app.services.pose import PoseEstimate, PoseEstimator, map_landmarks_to_frame
from app.services.video import OpenCVVideoDecoder, VideoDecodeError


@dataclass
class FakeLandmark:
    x: float
    y: float
    z: float
    visibility: float = 0.9


class FakeDetector:
    def detect(self, frame):
        height, width = frame.shape[:2]
        return [Detection(BoundingBox(1, 1, width - 1, height - 1), 0.91)]


class FakePoseEstimator(PoseEstimator):
    def estimate(self, frame, box):
        height, width = frame.shape[:2]
        landmarks = map_landmarks_to_frame(
            [FakeLandmark(0.5, 0.5, -0.1)], box, width, height
        )
        return PoseEstimate(landmarks=landmarks, world_landmarks=[])


@pytest.fixture
def tiny_video(tmp_path):
    cv2 = pytest.importorskip("cv2")
    path = tmp_path / "tiny.mp4"
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (16, 12)
    )
    if not writer.isOpened():
        pytest.skip("OpenCV MP4 writer is unavailable")
    for index in range(6):
        writer.write(np.full((12, 16, 3), index * 20, dtype=np.uint8))
    writer.release()
    return path


def test_frame_sampling_reports_properties_and_stride(tiny_video):
    decoder = OpenCVVideoDecoder()
    properties = decoder.inspect(tiny_video)
    frames = list(decoder.iter_sampled_frames(tiny_video, frame_stride=2))

    assert properties.width == 16
    assert properties.height == 12
    assert properties.fps == pytest.approx(10, abs=1)
    assert [frame.frame_index for frame in frames] == [0, 2, 4]
    assert [frame.timestamp_seconds for frame in frames] == pytest.approx([0, 0.2, 0.4])


def test_pipeline_emits_progress_and_json_serializable_result(tiny_video):
    events: list[ProgressEvent] = []
    pipeline = FramePosePipeline(
        OpenCVVideoDecoder(),
        FakeDetector(),
        FakePoseEstimator(),
        frame_stride=2,
    )

    result = pipeline.run(tiny_video, events.append)
    json.dumps(result)

    assert {event.stage for event in events} >= {"decoding", "detecting", "posing", "completed"}
    assert result["video"]["frame_count"] >= 6
    assert len(result["sampled_frames"]) == 3
    assert result["sampled_frames"][0]["detections"][0]["pose"]["landmarks"][0]["x_full"] > 0
    assert result["projection"]["calibration_required"] is True
    assert result["sampled_frames"][0]["tracks"][0]["top_down"] is None


def test_crop_landmarks_map_to_full_frame_coordinates():
    mapped = map_landmarks_to_frame(
        [FakeLandmark(0.5, 0.25, 0.1)], BoundingBox(20, 10, 60, 50), 100, 100
    )
    assert mapped[0]["x_px"] == pytest.approx(40)
    assert mapped[0]["y_px"] == pytest.approx(20)
    assert mapped[0]["x_full"] == pytest.approx(0.4)
    assert mapped[0]["visibility"] == pytest.approx(0.9)


def test_invalid_video_raises_clear_error(tmp_path):
    pytest.importorskip("cv2")
    with pytest.raises(VideoDecodeError, match="Unable to open video"):
        OpenCVVideoDecoder().inspect(tmp_path / "missing.mp4")
