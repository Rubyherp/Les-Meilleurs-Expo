"""Typed contracts for the GMI Inference coaching audit."""

from typing import Any

from pydantic import BaseModel, Field, model_validator


class GmiAuditOutput(BaseModel):
    summary: str = Field(min_length=1, max_length=600)
    strengths: list[str] = Field(default_factory=list, max_length=3)
    cautions: list[str] = Field(default_factory=list, max_length=3)
    suggestions: list[str] = Field(default_factory=list, max_length=3)
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="before")
    @classmethod
    def normalize_compatible_output(cls, value: Any) -> Any:
        """Map common equivalent model keys into the app's strict contract."""
        if not isinstance(value, dict):
            return value

        def first(*keys: str) -> Any:
            return next((value[key] for key in keys if value.get(key) is not None), None)

        def short_list(raw: Any) -> list[str]:
            if raw is None:
                return []
            items = raw if isinstance(raw, list) else [raw]
            normalized: list[str] = []
            for item in items:
                if isinstance(item, dict):
                    item = next(
                        (item[key] for key in ("text", "description", "summary") if item.get(key)),
                        None,
                    )
                if item is not None and str(item).strip():
                    normalized.append(str(item).strip()[:300])
            return normalized[:3]

        confidence = first("confidence", "confidence_score", "score")
        was_percent = isinstance(confidence, str) and "%" in confidence
        if isinstance(confidence, str):
            try:
                confidence = float(confidence.strip().rstrip("%"))
            except ValueError:
                confidence = None
        if isinstance(confidence, (int, float)) and (was_percent or confidence > 1):
            confidence = confidence / 100

        summary = first("summary", "audit_summary", "overall_assessment", "assessment")
        return {
            **value,
            "summary": str(summary).strip()[:600] if summary is not None else summary,
            "strengths": short_list(first("strengths", "key_strengths", "validated_points")),
            "cautions": short_list(first("cautions", "concerns", "limitations", "issues")),
            "suggestions": short_list(first("suggestions", "recommendations", "next_actions")),
            "confidence": confidence,
        }
