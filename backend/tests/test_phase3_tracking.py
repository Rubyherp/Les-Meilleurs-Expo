from dataclasses import dataclass

import numpy as np
import pytest

from app.services.detector import BoundingBox
from app.services.pipeline import FramePosePipeline
from app.services.pose import PoseEstimate, PoseEstimator
from app.services.tracking import (
    ApplicationTracker,
    TrackObservation,
    TrackedDetection,
    UltralyticsByteTrackAdapter,
    effective_buffer_frames,
)
from app.services.video import SampledFrame, VideoProperties


def observation(x: float, external_id: int | None = None, confidence: float = 0.9):
    return TrackObservation(BoundingBox(x, 0, x + 10, 10), confidence, external_id)


def test_one_person_keeps_stable_application_id():
    tracker = ApplicationTracker(buffer_frames=2)
    first = tracker.update([observation(0, 4)], 0)[0]
    second = tracker.update([observation(1, 4)], 1)[0]
    assert first.track_id == second.track_id == 1
    assert second.status == "active"
    assert second.bbox_source == "observed"


def test_two_people_get_distinct_ids():
    tracks = ApplicationTracker(buffer_frames=2).update(
        [observation(0, 1), observation(30, 2)], 0
    )
    assert [track.track_id for track in tracks] == [1, 2]


def test_empty_frame_predicts_occlusion_and_advances_missed_frames():
    tracker = ApplicationTracker(buffer_frames=2)
    tracker.update([observation(5, 1)], 0)
    occluded = tracker.update([], 1)[0]
    still_occluded = tracker.update([], 2)[0]
    lost = tracker.update([], 3)[0]

    assert occluded.status == "occluded"
    assert occluded.bbox_source == "predicted"
    assert occluded.bbox == BoundingBox(5, 0, 15, 10)
    assert occluded.missed_frames == 1
    assert still_occluded.missed_frames == 2
    assert lost.status == "lost"
    assert lost.bbox_source == "none"
    assert lost.bbox is None


def test_reappearance_within_buffer_reactivates_same_id():
    tracker = ApplicationTracker(buffer_frames=2)
    original = tracker.update([observation(0, 11)], 0)[0]
    tracker.update([], 1)
    reappeared = tracker.update([observation(1, 99)], 2)[0]
    assert reappeared.track_id == original.track_id
    assert reappeared.reactivated is True
    assert reappeared.status == "active"


def test_reappearance_after_buffer_gets_new_id():
    tracker = ApplicationTracker(buffer_frames=1)
    original = tracker.update([observation(0, 11)], 0)[0]
    tracker.update([], 1)
    tracker.update([], 2)  # removal happens after the configured buffer
    reappeared = tracker.update([observation(0, 11)], 3)[0]
    assert reappeared.track_id != original.track_id
    assert reappeared.reactivated is False


def test_reset_prevents_state_leaking_between_videos():
    tracker = ApplicationTracker(buffer_frames=2)
    tracker.update([observation(0, 5)], 0)
    tracker.reset()
    next_video = tracker.update([observation(0, 5)], 0)[0]
    assert next_video.track_id == 1
    assert next_video.reactivated is False


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"source_fps": 30, "frame_stride": 3, "target_fps": None, "buffer_seconds": 2}, 20),
        ({"source_fps": 30, "frame_stride": 1, "target_fps": 10, "buffer_seconds": 2}, 20),
    ],
)
def test_buffer_scales_to_processed_frames(kwargs, expected):
    assert effective_buffer_frames(explicit_processed_frames=None, **kwargs) == expected
    assert effective_buffer_frames(
        source_fps=30,
        frame_stride=1,
        target_fps=None,
        buffer_seconds=2,
        explicit_processed_frames=7,
    ) == 7


class FakeTensor:
    def __init__(self, value):
        self.value = value

    def tolist(self):
        return self.value


@dataclass
class FakeBoxes:
    xyxy: FakeTensor
    conf: FakeTensor
    cls: FakeTensor
    id: FakeTensor | None


@dataclass
class FakeResult:
    boxes: FakeBoxes


class FakeUltralyticsModel:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def track(self, **kwargs):
        self.calls.append(kwargs)
        return [self.result]


def test_ultralytics_adapter_uses_public_track_contract_and_defensive_ids(monkeypatch):
    result = FakeResult(
        FakeBoxes(
            xyxy=FakeTensor([[1, 2, 10, 12]]),
            conf=FakeTensor([0.8]),
            cls=FakeTensor([0]),
            id=FakeTensor([42]),
        )
    )
    model = FakeUltralyticsModel(result)
    adapter = UltralyticsByteTrackAdapter("not-used.pt", device="cpu")
    monkeypatch.setattr(adapter, "_load_model", lambda: model)

    observed = adapter.track(np.zeros((20, 20, 3), dtype=np.uint8))
    assert observed[0].external_track_id == 42
    assert model.calls[0]["tracker"] == "bytetrack.yaml"
    assert model.calls[0]["persist"] is True
    assert model.calls[0]["classes"] == [0]
    assert model.calls[0]["verbose"] is False

    empty_model = FakeUltralyticsModel(
        FakeResult(FakeBoxes(FakeTensor([]), FakeTensor([]), FakeTensor([]), None))
    )
    monkeypatch.setattr(adapter, "_load_model", lambda: empty_model)
    assert adapter.track(np.zeros((20, 20, 3), dtype=np.uint8)) == []


class FakeDecoder:
    def inspect(self, path):
        return VideoProperties(10, 2, 4, 4, 0.2)

    def iter_sampled_frames(self, path, *, frame_stride, target_fps):
        for index in range(2):
            yield SampledFrame(index, index / 10, np.zeros((4, 4, 3), dtype=np.uint8))


class FakeFrameTracker:
    def __init__(self):
        self.frames = 0
        self.reset_count = 0

    def reset(self):
        self.reset_count += 1
        self.frames = 0

    def set_buffer_frames(self, buffer_frames):
        self.buffer_frames = buffer_frames

    def track(self, frame, frame_index):
        self.frames += 1
        if self.frames == 1:
            return [
                TrackedDetection(
                    1, "active", "observed", BoundingBox(0, 0, 2, 2), 0.9, 0, 0, 0, False
                )
            ]
        return [
            TrackedDetection(
                1, "occluded", "predicted", BoundingBox(0, 0, 2, 2), 0.9, 0, 0, 1, False
            )
        ]


class CountingPose(PoseEstimator):
    def __init__(self):
        self.calls = 0

    def estimate(self, frame, box):
        self.calls += 1
        return PoseEstimate([], [])


def test_pose_runs_only_for_observed_tracks():
    pose = CountingPose()
    tracker = FakeFrameTracker()
    result = FramePosePipeline(
        FakeDecoder(), None, pose, tracker=tracker, tracker_buffer_frames=1
    ).run("fake.mp4")
    assert pose.calls == 1
    assert result["sampled_frames"][0]["tracks"][0]["pose"] == {
        "landmarks": [],
        "world_landmarks": [],
    }
    assert result["sampled_frames"][1]["tracks"][0]["pose"] is None
