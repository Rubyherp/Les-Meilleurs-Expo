from __future__ import annotations

from app.services.analysis_control.models import QualityReport, VerificationResult


class IndependentVerifier:
    """Accept a retry only when it improves quality without critical regression."""

    METRIC_REGRESSION_TOLERANCE = {
        "person_count_recall": 0.04,
        "pose_coverage": 0.04,
        "calibration_confidence": 0.03,
        "calibration_in_bounds_rate": 0.04,
    }

    def __init__(self, *, minimum_improvement: float = 0.025) -> None:
        self.minimum_improvement = minimum_improvement

    def verify(
        self, baseline: QualityReport, candidate: QualityReport
    ) -> VerificationResult:
        delta = candidate.score - baseline.score
        regressions: list[str] = []
        for metric, tolerance in self.METRIC_REGRESSION_TOLERANCE.items():
            before = baseline.metrics.get(metric, 0.0)
            after = candidate.metrics.get(metric, 0.0)
            if after + tolerance < before:
                regressions.append(metric)

        resolved = set(baseline.reason_codes) - set(candidate.reason_codes)
        introduced = set(candidate.reason_codes) - set(baseline.reason_codes)
        critical_introduced = sorted(
            reason for reason in introduced if reason.startswith("calibration_")
        )
        regressions.extend(critical_introduced)
        accepted = (
            not regressions
            and (
                delta >= self.minimum_improvement
                or (
                    bool(resolved)
                    and delta >= 0
                    and len(candidate.reason_codes) < len(baseline.reason_codes)
                )
            )
        )
        should_retry = (
            not accepted
            and candidate.disposition == "retry"
            and not critical_introduced
        )
        if accepted:
            explanation = (
                f"Accepted: score improved by {delta:.3f}; "
                f"resolved {', '.join(sorted(resolved)) or 'quality debt'}."
            )
        elif regressions:
            explanation = "Rejected because these metrics regressed: " + ", ".join(
                regressions
            )
        else:
            explanation = (
                f"Rejected because score improvement {delta:.3f} was below "
                f"{self.minimum_improvement:.3f}."
            )
        return VerificationResult(
            accepted=accepted,
            should_retry=should_retry,
            score_delta=delta,
            regressions=tuple(regressions),
            explanation=explanation,
        )
