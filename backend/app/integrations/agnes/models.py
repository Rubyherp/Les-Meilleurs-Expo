"""Internal Agnes request/response contracts."""

from typing import Any

from pydantic import BaseModel, Field, model_validator


class AgnesStructuredReview(BaseModel):
    summary: str = Field(min_length=1, max_length=600)
    visible_differences: list[str] = Field(default_factory=list, max_length=8)
    limitations: list[str] = Field(default_factory=list, max_length=8)
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="before")
    @classmethod
    def normalize_compatible_output(cls, value: Any) -> Any:
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
            return normalized[:8]

        differences = short_list(first(
            "visible_differences", "differences", "observations", "findings"
        ))
        summary = first("summary", "visual_summary", "description", "analysis")
        if summary is None and differences:
            summary = differences[0]

        confidence = first("confidence", "confidence_score", "score")
        was_percent = isinstance(confidence, str) and "%" in confidence
        if isinstance(confidence, str):
            try:
                confidence = float(confidence.strip().rstrip("%"))
            except ValueError:
                confidence = None
        if isinstance(confidence, (int, float)) and (was_percent or confidence > 1):
            confidence = confidence / 100

        return {
            **value,
            "summary": str(summary).strip()[:600] if summary is not None else summary,
            "visible_differences": differences,
            "limitations": short_list(first(
                "limitations", "caveats", "uncertainties", "constraints"
            )),
            "confidence": confidence,
        }
