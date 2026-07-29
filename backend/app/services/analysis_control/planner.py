from __future__ import annotations

from app.services.analysis_control.models import (
    AnalysisPlan,
    AnalysisSegment,
    ControlState,
    QualityReport,
    ReasonCode,
    ScoutReport,
)
from app.services.analysis_control.profiles import ProfileRegistry
from app.services.analysis_control.quality import RETRYABLE_REASONS


class ReanalysisPlanner:
    def __init__(
        self,
        registry: ProfileRegistry,
        *,
        segment_padding_seconds: float = 0.75,
        maximum_retry_seconds: float = 30.0,
    ) -> None:
        self.registry = registry
        self.segment_padding_seconds = segment_padding_seconds
        self.maximum_retry_seconds = maximum_retry_seconds

    def initial(self, scout: ScoutReport) -> AnalysisPlan:
        return AnalysisPlan(
            attempt_number=1,
            state=ControlState.EXECUTE,
            action="full_analysis",
            profile=self.registry.initial(scout),
            reason_codes=tuple(scout.reason_codes),
        )

    def retry(
        self,
        quality: QualityReport,
        *,
        attempt_number: int,
        video_duration_seconds: float,
        consumed_retry_seconds: float,
    ) -> AnalysisPlan | None:
        retryable = tuple(
            sorted(
                reason
                for reason in quality.reason_codes
                if reason in RETRYABLE_REASONS
            )
        )
        if not retryable:
            return None
        remaining = max(0.0, self.maximum_retry_seconds - consumed_retry_seconds)
        if remaining <= 0:
            return None
        segments = self._prepare_segments(
            quality.segments,
            duration=video_duration_seconds,
            budget=remaining,
        )
        if not segments:
            return None
        return AnalysisPlan(
            attempt_number=attempt_number,
            state=ControlState.TARGETED_RETRY,
            action="targeted_reanalysis",
            profile=self.registry.recovery(retryable),
            reason_codes=retryable,
            segments=segments,
        )

    def _prepare_segments(
        self,
        segments: tuple[AnalysisSegment, ...],
        *,
        duration: float,
        budget: float,
    ) -> tuple[AnalysisSegment, ...]:
        padded = [
            AnalysisSegment(
                max(0.0, item.start_seconds - self.segment_padding_seconds),
                min(
                    duration,
                    max(item.end_seconds, item.start_seconds + 0.25)
                    + self.segment_padding_seconds,
                ),
                item.reason_codes,
            )
            for item in segments
        ]
        merged: list[AnalysisSegment] = []
        for item in sorted(padded, key=lambda value: value.start_seconds):
            if not merged or item.start_seconds > merged[-1].end_seconds + 0.1:
                merged.append(item)
                continue
            previous = merged[-1]
            merged[-1] = AnalysisSegment(
                previous.start_seconds,
                max(previous.end_seconds, item.end_seconds),
                tuple(sorted(set(previous.reason_codes) | set(item.reason_codes))),
            )

        selected: list[AnalysisSegment] = []
        consumed = 0.0
        for item in merged:
            available = budget - consumed
            if available <= 0:
                break
            if item.duration_seconds <= available:
                selected.append(item)
                consumed += item.duration_seconds
            else:
                selected.append(
                    AnalysisSegment(
                        item.start_seconds,
                        min(item.end_seconds, item.start_seconds + available),
                        item.reason_codes,
                    )
                )
                break
        return tuple(item for item in selected if item.duration_seconds > 0)
