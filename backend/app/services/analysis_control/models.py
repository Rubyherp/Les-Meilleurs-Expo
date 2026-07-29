from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class ControlState(StrEnum):
    SCOUT = "scout"
    DIAGNOSE = "diagnose"
    PLAN = "plan"
    EXECUTE = "execute"
    VERIFY = "verify"
    ACCEPT = "accept"
    TARGETED_RETRY = "targeted_retry"
    HUMAN_REVIEW = "human_review"


class ReasonCode(StrEnum):
    LOW_DETECTION_RECALL = "low_detection_recall"
    EXTRA_PERSON_DETECTIONS = "extra_person_detections"
    LOW_DETECTION_CONFIDENCE = "low_detection_confidence"
    TRACKING_DROPOUT = "tracking_dropout"
    TRACK_FRAGMENTATION = "track_fragmentation"
    POSE_DROPOUT = "pose_dropout"
    LOW_POSE_VISIBILITY = "low_pose_visibility"
    POSE_TEMPORAL_JITTER = "pose_temporal_jitter"
    CAMERA_MOTION = "camera_motion"
    LOW_LIGHT = "low_light"
    BLURRY_VIDEO = "blurry_video"
    CALIBRATION_UNVERIFIED = "calibration_unverified"
    CALIBRATION_OUT_OF_BOUNDS = "calibration_out_of_bounds"
    CALIBRATION_TRAJECTORY_JUMP = "calibration_trajectory_jump"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    COMPUTE_BUDGET_EXHAUSTED = "compute_budget_exhausted"


@dataclass(frozen=True)
class AnalysisSegment:
    start_seconds: float
    end_seconds: float
    reason_codes: tuple[str, ...] = ()

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.end_seconds - self.start_seconds)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_seconds": round(self.start_seconds, 4),
            "end_seconds": round(self.end_seconds, 4),
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class AnalysisProfile:
    profile_id: str
    yolo_model_path: str
    pose_model_path: str
    tracker_name: str
    target_fps: float | None
    frame_stride: int
    image_size: int
    low_confidence: float
    high_confidence: float
    max_persons: int
    crop_padding: float
    tracker_buffer_seconds: float
    tracker_buffer_frames: int | None
    tracker_iou_threshold: float
    pose_min_detection_confidence: float
    pose_min_presence_confidence: float
    pose_min_tracking_confidence: float
    yolo_model_sha256: str
    pose_model_sha256: str

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["fingerprint"] = self.fingerprint
        return value


@dataclass(frozen=True)
class ScoutReport:
    video: dict[str, Any]
    sampled_frames: int
    brightness_mean: float
    dark_frame_rate: float
    blur_score: float
    camera_motion_score: float
    reason_codes: tuple[str, ...] = ()
    calibration_proposal: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class QualityReport:
    score: float
    metrics: dict[str, float]
    reason_codes: tuple[str, ...]
    segments: tuple[AnalysisSegment, ...]
    disposition: str

    @property
    def passed(self) -> bool:
        return self.disposition == "pass"

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 6),
            "metrics": self.metrics,
            "reason_codes": list(self.reason_codes),
            "segments": [segment.to_dict() for segment in self.segments],
            "disposition": self.disposition,
        }


@dataclass(frozen=True)
class AnalysisPlan:
    attempt_number: int
    state: str
    action: str
    profile: AnalysisProfile
    reason_codes: tuple[str, ...] = ()
    segments: tuple[AnalysisSegment, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_number": self.attempt_number,
            "state": self.state,
            "action": self.action,
            "profile": self.profile.to_dict(),
            "reason_codes": list(self.reason_codes),
            "segments": [segment.to_dict() for segment in self.segments],
        }


@dataclass(frozen=True)
class VerificationResult:
    accepted: bool
    should_retry: bool
    score_delta: float
    regressions: tuple[str, ...] = ()
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "should_retry": self.should_retry,
            "score_delta": round(self.score_delta, 6),
            "regressions": list(self.regressions),
            "explanation": self.explanation,
        }


@dataclass
class AttemptOutcome:
    plan: AnalysisPlan
    quality: QualityReport
    runtime_seconds: float
    accepted: bool
    verification: VerificationResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "quality": self.quality.to_dict(),
            "runtime_seconds": round(self.runtime_seconds, 6),
            "accepted": self.accepted,
            "verification": self.verification.to_dict() if self.verification else None,
        }


@dataclass
class ControlledAnalysisResult:
    result: dict[str, Any]
    scout: ScoutReport
    final_quality: QualityReport
    attempts: list[AttemptOutcome] = field(default_factory=list)
    state: str = ControlState.ACCEPT
    control_mode: str = "active"
    calibration: dict[str, Any] | None = None
    cache_hit: bool = False

    def control_metadata(self) -> dict[str, Any]:
        return {
            "version": 1,
            "mode": self.control_mode,
            "state": str(self.state),
            "cache_hit": self.cache_hit,
            "scout": self.scout.to_dict(),
            "final_quality": self.final_quality.to_dict(),
            "calibration": self.calibration,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
        }
