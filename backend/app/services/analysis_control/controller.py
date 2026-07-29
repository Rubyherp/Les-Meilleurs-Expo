from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from app.core.config import Settings
from app.services.analysis_control.calibration import CalibrationSpecialist
from app.services.analysis_control.merge import merge_segment_results
from app.services.analysis_control.models import (
    AttemptOutcome,
    ControlState,
    ControlledAnalysisResult,
    ReasonCode,
    ScoutReport,
)
from app.services.analysis_control.planner import ReanalysisPlanner
from app.services.analysis_control.profiles import ProfileRegistry
from app.services.analysis_control.quality import QualityAuditor
from app.services.analysis_control.scout import VideoScout
from app.services.analysis_control.verifier import IndependentVerifier
from app.services.pipeline import ProgressEvent


AnalysisExecutor = Callable[
    [
        Any,
        tuple[Any, ...],
        Callable[[ProgressEvent], None] | None,
        dict[str, Any] | None,
    ],
    dict[str, Any],
]
ProgressCallback = Callable[[ProgressEvent], None]


class AdaptiveAnalysisController:
    """Bounded perception supervisor with deterministic plans and acceptance."""

    def __init__(self, settings: Settings, *, expected_dancer_count: int) -> None:
        self.settings = settings
        self.expected_dancer_count = max(1, expected_dancer_count)
        self.calibration_specialist = CalibrationSpecialist()
        registry = ProfileRegistry(settings, self.expected_dancer_count)
        self.scout = VideoScout(
            target_fps=settings.analysis_scout_fps,
            max_frames=settings.analysis_scout_max_frames,
            calibration_specialist=self.calibration_specialist,
        )
        self.auditor = QualityAuditor(
            minimum_score=settings.analysis_min_quality_score
        )
        self.planner = ReanalysisPlanner(
            registry,
            segment_padding_seconds=settings.analysis_segment_padding_seconds,
            maximum_retry_seconds=settings.analysis_max_retry_seconds,
        )
        self.verifier = IndependentVerifier(
            minimum_improvement=settings.analysis_min_improvement
        )

    def run(
        self,
        video_path: str | Path,
        *,
        calibration: dict[str, Any] | None,
        executor: AnalysisExecutor,
        progress_callback: ProgressCallback | None = None,
    ) -> ControlledAnalysisResult:
        self._emit(progress_callback, ControlState.SCOUT, 6)
        try:
            scout = self.scout.inspect(
                video_path,
                allow_calibration_proposal=calibration is None,
            )
        except Exception as exc:
            # The executor still gets a chance to produce a useful diagnostic.
            # This also keeps injected/test executors independent of OpenCV.
            scout = ScoutReport(
                video={"duration_seconds": 0.0},
                sampled_frames=0,
                brightness_mean=0.0,
                dark_frame_rate=0.0,
                blur_score=0.0,
                camera_motion_score=0.0,
                reason_codes=(ReasonCode.INSUFFICIENT_EVIDENCE,),
                calibration_proposal={
                    "status": "unavailable",
                    "explanation": str(exc),
                },
            )
        effective_calibration = calibration
        if (
            effective_calibration is None
            and self.settings.analysis_auto_calibration_enabled
            and scout.calibration_proposal is not None
            and scout.calibration_proposal.get("confidence", 0) >= 0.9
        ):
            effective_calibration = {
                **scout.calibration_proposal,
                "status": "agent_verified",
            }

        initial_plan = self.planner.initial(scout)
        self._emit(progress_callback, ControlState.PLAN, 10)
        started = time.monotonic()
        result = executor(
            initial_plan.profile,
            (),
            self._attempt_progress(progress_callback, 12, 62),
            effective_calibration,
        )
        initial_runtime = time.monotonic() - started
        self._emit(progress_callback, ControlState.DIAGNOSE, 64)
        calibration_report = self.calibration_specialist.evaluate(
            effective_calibration, result
        )
        quality = self.auditor.audit(
            result,
            expected_dancer_count=self.expected_dancer_count,
            calibration_report=calibration_report,
        )
        attempts = [
            AttemptOutcome(
                plan=initial_plan,
                quality=quality,
                runtime_seconds=initial_runtime,
                accepted=True,
            )
        ]
        accepted_result = result
        accepted_quality = quality
        consumed_retry_seconds = 0.0
        state = self._terminal_state(quality)

        control_mode = self.settings.analysis_control_mode
        if control_mode == "active":
            for attempt_number in range(2, self.settings.analysis_max_attempts + 1):
                if accepted_quality.disposition != "retry":
                    break
                plan = self.planner.retry(
                    accepted_quality,
                    attempt_number=attempt_number,
                    video_duration_seconds=float(
                        scout.video.get("duration_seconds", 0.0)
                    ),
                    consumed_retry_seconds=consumed_retry_seconds,
                )
                if plan is None:
                    state = ControlState.HUMAN_REVIEW
                    break
                consumed_retry_seconds += sum(
                    segment.duration_seconds for segment in plan.segments
                )
                self._emit(progress_callback, ControlState.TARGETED_RETRY, 68)
                retry_started = time.monotonic()
                retry_result = executor(
                    plan.profile,
                    plan.segments,
                    self._attempt_progress(progress_callback, 70, 88),
                    effective_calibration,
                )
                runtime = time.monotonic() - retry_started
                candidate = merge_segment_results(
                    accepted_result, retry_result, plan.segments
                )
                candidate_calibration = self.calibration_specialist.evaluate(
                    effective_calibration, candidate
                )
                candidate_quality = self.auditor.audit(
                    candidate,
                    expected_dancer_count=self.expected_dancer_count,
                    calibration_report=candidate_calibration,
                )
                self._emit(progress_callback, ControlState.VERIFY, 90)
                verification = self.verifier.verify(
                    accepted_quality, candidate_quality
                )
                attempts.append(
                    AttemptOutcome(
                        plan=plan,
                        quality=candidate_quality,
                        runtime_seconds=runtime,
                        accepted=verification.accepted,
                        verification=verification,
                    )
                )
                if verification.accepted:
                    attempts[-2].accepted = False
                    accepted_result = candidate
                    accepted_quality = candidate_quality
                    calibration_report = candidate_calibration
                    state = self._terminal_state(candidate_quality)
                    continue
                state = ControlState.HUMAN_REVIEW
                break
        elif control_mode == "shadow" and accepted_quality.disposition == "retry":
            shadow_plan = self.planner.retry(
                accepted_quality,
                attempt_number=2,
                video_duration_seconds=float(
                    scout.video.get("duration_seconds", 0.0)
                ),
                consumed_retry_seconds=0.0,
            )
            if shadow_plan is not None:
                accepted_result.setdefault("analysis_control_shadow_plan", shadow_plan.to_dict())
            state = ControlState.HUMAN_REVIEW
        elif control_mode == "disabled" and accepted_quality.disposition != "pass":
            state = ControlState.HUMAN_REVIEW

        if state == ControlState.TARGETED_RETRY:
            accepted_quality = replace(
                accepted_quality,
                reason_codes=tuple(
                    sorted(
                        set(accepted_quality.reason_codes)
                        | {str(ReasonCode.COMPUTE_BUDGET_EXHAUSTED)}
                    )
                ),
                disposition="review",
            )
            state = ControlState.HUMAN_REVIEW

        self._emit(
            progress_callback,
            ControlState.ACCEPT if state == ControlState.ACCEPT else state,
            94,
        )
        controlled = ControlledAnalysisResult(
            result=accepted_result,
            scout=scout,
            final_quality=accepted_quality,
            attempts=attempts,
            state=state,
            control_mode=control_mode,
            calibration=calibration_report,
        )
        controlled.result["analysis_control"] = controlled.control_metadata()
        return controlled

    @staticmethod
    def _terminal_state(quality: Any) -> str:
        return (
            ControlState.ACCEPT
            if quality.disposition == "pass"
            else ControlState.HUMAN_REVIEW
            if quality.disposition == "review"
            else ControlState.TARGETED_RETRY
        )

    @staticmethod
    def _attempt_progress(
        callback: ProgressCallback | None, start: int, end: int
    ) -> ProgressCallback | None:
        if callback is None:
            return None

        def mapped(event: ProgressEvent) -> None:
            progress = start + int((end - start) * event.progress / 100)
            callback(
                ProgressEvent(
                    stage=event.stage,
                    progress=min(end, progress),
                    sampled_frames=event.sampled_frames,
                )
            )

        return mapped

    @staticmethod
    def _emit(
        callback: ProgressCallback | None, state: str, progress: int
    ) -> None:
        if callback is not None:
            callback(ProgressEvent(str(state), progress, 0))
