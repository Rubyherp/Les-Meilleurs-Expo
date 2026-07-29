from __future__ import annotations

from app.core.config import Settings
from app.services.analysis_control.controller import AdaptiveAnalysisController
from app.services.analysis_control.calibration import CalibrationSpecialist
from app.services.analysis_control.merge import merge_segment_results
from app.services.analysis_control.models import (
    AnalysisSegment,
    QualityReport,
    ReasonCode,
    ScoutReport,
)
from app.services.analysis_control.planner import ReanalysisPlanner
from app.services.analysis_control.profiles import ProfileRegistry
from app.services.analysis_control.quality import QualityAuditor
from app.services.analysis_control.verifier import IndependentVerifier


CALIBRATION = {
    "points": [[0, 0], [1, 0], [1, 1], [0, 1]],
    "source": "human",
    "status": "verified",
}
CALIBRATION_REPORT = {
    "verified": True,
    "confidence": 0.98,
    "in_bounds_rate": 1.0,
    "trajectory_jump_rate": 0.0,
    "reason_codes": [],
}


def track(track_id: int, *, with_pose: bool = True) -> dict:
    pose = None
    if with_pose:
        pose = {
            "landmarks": [
                {"index": 23, "x": 0.45, "y": 0.6, "visibility": 0.95},
                {"index": 24, "x": 0.55, "y": 0.6, "visibility": 0.95},
            ]
        }
    return {
        "track_id": track_id,
        "status": "active",
        "bbox_source": "observed",
        "confidence": 0.9,
        "bbox": {"x1": 10, "y1": 10, "x2": 40, "y2": 80},
        "pose": pose,
        "top_down": {
            "x": 0.5,
            "y": 0.5,
            "raw_x": 0.5,
            "raw_y": 0.5,
            "source": "observed",
            "status": "active",
        },
    }


def result_with_counts(counts: list[int], *, retry_track_id: int = 1) -> dict:
    frames = []
    for index, count in enumerate(counts):
        tracks = [track(retry_track_id + offset) for offset in range(count)]
        frames.append(
            {
                "frame_index": index * 10,
                "timestamp_seconds": float(index),
                "tracks": tracks,
                "detections": tracks,
            }
        )
    return {
        "video": {
            "fps": 10.0,
            "frame_count": len(counts) * 10,
            "width": 100,
            "height": 100,
            "duration_seconds": float(len(counts)),
        },
        "projection": {
            "calibration_available": True,
            "calibration_required": False,
            "coordinate_space": "stage_normalized",
        },
        "sampled_frames": frames,
        "sampled_frame_timestamps": [
            frame["timestamp_seconds"] for frame in frames
        ],
    }


def test_quality_auditor_reports_localized_detection_failure():
    report = QualityAuditor().audit(
        result_with_counts([1, 0, 1, 1]),
        expected_dancer_count=1,
        calibration_report=CALIBRATION_REPORT,
    )

    assert ReasonCode.LOW_DETECTION_RECALL in report.reason_codes
    assert report.disposition == "retry"
    assert report.segments == (
        AnalysisSegment(1.0, 1.0, (ReasonCode.LOW_DETECTION_RECALL,)),
    )


def test_router_uses_moving_camera_profile_and_bounded_segments():
    settings = Settings(
        _env_file=None,
        analysis_max_retry_seconds=1.5,
        analysis_segment_padding_seconds=0.25,
    )
    registry = ProfileRegistry(settings, expected_dancer_count=8)
    scout = ScoutReport(
        video={"duration_seconds": 10},
        sampled_frames=10,
        brightness_mean=0.5,
        dark_frame_rate=0,
        blur_score=100,
        camera_motion_score=0.02,
        reason_codes=(ReasonCode.CAMERA_MOTION,),
    )
    assert registry.initial(scout).tracker_name == "botsort.yaml"
    assert registry.initial(scout).max_persons == 8

    planner = ReanalysisPlanner(
        registry,
        segment_padding_seconds=0.25,
        maximum_retry_seconds=1.5,
    )
    quality = QualityReport(
        score=0.4,
        metrics={},
        reason_codes=(ReasonCode.POSE_DROPOUT,),
        segments=(
            AnalysisSegment(1.0, 2.0, (ReasonCode.POSE_DROPOUT,)),
            AnalysisSegment(5.0, 7.0, (ReasonCode.POSE_DROPOUT,)),
        ),
        disposition="retry",
    )
    plan = planner.retry(
        quality,
        attempt_number=2,
        video_duration_seconds=10,
        consumed_retry_seconds=0,
    )
    assert plan is not None
    assert sum(segment.duration_seconds for segment in plan.segments) <= 1.5
    assert "pose" in plan.profile.profile_id


def test_segment_merge_reconciles_retry_local_track_ids():
    baseline = result_with_counts([1, 1, 1])
    retry = result_with_counts([1], retry_track_id=99)
    retry["sampled_frames"][0]["timestamp_seconds"] = 1.0
    retry["sampled_frames"][0]["frame_index"] = 10

    merged = merge_segment_results(
        baseline,
        retry,
        (AnalysisSegment(0.75, 1.25, (ReasonCode.POSE_DROPOUT,)),),
    )

    middle = next(
        frame for frame in merged["sampled_frames"] if frame["timestamp_seconds"] == 1
    )
    assert middle["tracks"][0]["track_id"] == 1
    assert merged["adaptive_sampling"]["identity_mapping"] == {"99": 1}


def test_controller_accepts_only_verified_targeted_improvement():
    settings = Settings(
        _env_file=None,
        analysis_control_mode="active",
        analysis_max_attempts=3,
        analysis_min_improvement=0.01,
        analysis_segment_padding_seconds=0.1,
    )
    controller = AdaptiveAnalysisController(settings, expected_dancer_count=1)
    controller.scout = type(
        "FakeScout",
        (),
        {
            "inspect": lambda self, path, allow_calibration_proposal: ScoutReport(
                video={"duration_seconds": 4.0},
                sampled_frames=4,
                brightness_mean=0.5,
                dark_frame_rate=0,
                blur_score=100,
                camera_motion_score=0,
            )
        },
    )()
    calls: list[tuple] = []

    def execute(profile, segments, callback, calibration):
        calls.append(segments)
        if segments:
            recovered = result_with_counts([1], retry_track_id=99)
            recovered["sampled_frames"][0]["timestamp_seconds"] = 1.0
            recovered["sampled_frames"][0]["frame_index"] = 10
            return recovered
        return result_with_counts([1, 0, 1, 1])

    controlled = controller.run(
        "unused.mp4",
        calibration=CALIBRATION,
        executor=execute,
    )

    assert len(calls) == 2
    assert len(controlled.attempts) == 2
    assert controlled.attempts[-1].accepted is True
    assert controlled.final_quality.passed is True
    assert controlled.result["analysis_control"]["state"] == "accept"


def test_verifier_rejects_improvement_with_calibration_regression():
    baseline = QualityReport(
        score=0.6,
        metrics={
            "person_count_recall": 0.7,
            "pose_coverage": 0.7,
            "calibration_confidence": 0.95,
            "calibration_in_bounds_rate": 0.95,
        },
        reason_codes=(ReasonCode.POSE_DROPOUT,),
        segments=(),
        disposition="retry",
    )
    candidate = QualityReport(
        score=0.8,
        metrics={
            "person_count_recall": 1.0,
            "pose_coverage": 1.0,
            "calibration_confidence": 0.5,
            "calibration_in_bounds_rate": 0.5,
        },
        reason_codes=(),
        segments=(),
        disposition="pass",
    )

    verification = IndependentVerifier().verify(baseline, candidate)
    assert verification.accepted is False
    assert "calibration_confidence" in verification.regressions


def test_calibration_specialist_requires_stable_multi_frame_evidence():
    import cv2
    import numpy as np

    frames = []
    polygon = np.asarray([[20, 20], [180, 25], [170, 170], [25, 175]], np.int32)
    for _ in range(4):
        frame = np.zeros((200, 200, 3), dtype=np.uint8)
        cv2.polylines(frame, [polygon], True, (255, 255, 255), 4)
        frames.append(frame)

    specialist = CalibrationSpecialist()
    proposal = specialist.propose(frames)
    assert proposal is not None
    assert proposal["source"] == "agent"
    assert proposal["requires_confirmation"] is True
    assert proposal["supporting_frames"] >= 3
    assert specialist.propose(frames[:1]) is None
