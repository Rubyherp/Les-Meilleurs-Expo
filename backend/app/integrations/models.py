"""Shared, privacy-safe contracts for sponsor integrations."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

_MIN_TS = datetime(2020, 1, 1, tzinfo=timezone.utc)

ProviderName = Literal["gmi", "agnes", "openai", "zo"]
IntegrationStatus = Literal[
    "not_configured", "pending", "running", "completed", "fallback", "failed"
]


class IntegrationRun(BaseModel):
    """One provider attempt. ``completed`` always means a real provider success."""

    provider: ProviderName
    product: str
    model: str | None = None
    status: IntegrationStatus
    started_at: datetime | None = Field(default=None, ge=_MIN_TS)
    completed_at: datetime | None = Field(
        default=None, ge=_MIN_TS,
        validation_alias=AliasChoices("completed_at", "finished_at"),
    )
    latency_ms: int | None = Field(default=None, ge=0)
    request_id: str | None = None
    trace_id: str | None = None
    fallback_reason: str | None = None
    message: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_timing(self) -> "IntegrationRun":
        if self.started_at and self.completed_at and self.completed_at < self.started_at:
            raise ValueError("completed_at cannot precede started_at")
        return self

    @property
    def finished_at(self) -> datetime | None:
        """Compatibility accessor for reports produced before v4 stabilized."""
        return self.completed_at


EvidenceCategory = Literal["observation", "timing", "formation", "comparison", "tracking"]
EvidenceSeverity = Literal["low", "medium", "high"]


class EvidenceFrame(BaseModel):
    role: Literal["attempt", "reference"] = "attempt"
    timestamp_seconds: float = Field(
        ge=0.0, validation_alias=AliasChoices("timestamp_seconds", "seconds")
    )
    object_key: str | None = None
    width: int = Field(default=0, ge=0)
    height: int = Field(default=0, ge=0)
    sha256: str = ""
    legacy_annotation: str = Field(default="", validation_alias="annotation", exclude=True)

    @field_validator("timestamp_seconds")
    @classmethod
    def finite_timestamp(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("timestamp_seconds must be finite")
        return value

    @property
    def seconds(self) -> float:
        return self.timestamp_seconds

    @property
    def annotation(self) -> str:
        return self.legacy_annotation


class VisualReview(BaseModel):
    provider: Literal["agnes"] = "agnes"
    summary: str = Field(min_length=1, max_length=600)
    visible_differences: list[str] = Field(default_factory=list, max_length=8)
    limitations: list[str] = Field(default_factory=list, max_length=8)
    confidence: float = Field(ge=0.0, le=1.0)
    model: str | None = None

    @model_validator(mode="before")
    @classmethod
    def legacy_caption(cls, value: Any) -> Any:
        if isinstance(value, dict) and "summary" not in value and value.get("caption"):
            value = {**value, "summary": value["caption"]}
        return value

    @property
    def caption(self) -> str:
        return self.summary


class EvidenceMoment(BaseModel):
    id: str = Field(min_length=1, max_length=96)
    start_seconds: float = Field(ge=0.0)
    end_seconds: float = Field(ge=0.0)
    primary_timestamp_seconds: float = Field(ge=0.0)
    category: EvidenceCategory
    severity: EvidenceSeverity
    deterministic_reason: str = Field(min_length=1, max_length=600)
    deterministic_metrics: dict[str, float | int | str | bool | None] = Field(
        default_factory=dict
    )
    frame_assets: list[EvidenceFrame] = Field(default_factory=list)
    visual_review: VisualReview | None = None
    legacy_confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, validation_alias="confidence", exclude=True
    )

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_shape(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "primary_timestamp_seconds" in value:
            return value
        frames = value.get("frames") or []
        timestamp = value.get("timestamp")
        if isinstance(timestamp, datetime) and timestamp < _MIN_TS:
            raise ValueError("legacy timestamp is before the supported minimum")
        seconds = 0.0
        if frames and isinstance(frames[0], dict):
            seconds = float(frames[0].get("timestamp_seconds", frames[0].get("seconds", 0.0)))
        category_map = {
            "visibility": "observation", "pose_quality": "observation",
            "calibration": "observation", "general": "observation", "spacing": "formation",
        }
        category = category_map.get(value.get("category"), value.get("category"))
        reason = value.get("deterministic_reason") or value.get("description") or "Legacy evidence"
        return {
            **value,
            "id": value.get("id") or f"legacy_{seconds:.4f}",
            "start_seconds": max(0.0, seconds - 0.5),
            "end_seconds": seconds + 0.5,
            "primary_timestamp_seconds": seconds,
            "category": category,
            "deterministic_reason": reason,
            "deterministic_metrics": value.get("metadata") or {},
            "frame_assets": frames,
        }

    @field_validator("start_seconds", "end_seconds", "primary_timestamp_seconds")
    @classmethod
    def finite_seconds(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("evidence timestamps must be finite")
        return value

    @model_validator(mode="after")
    def validate_range(self) -> "EvidenceMoment":
        if self.end_seconds < self.start_seconds:
            raise ValueError("end_seconds cannot precede start_seconds")
        if not self.start_seconds <= self.primary_timestamp_seconds <= self.end_seconds:
            raise ValueError("primary timestamp must be inside the evidence range")
        return self

    @property
    def frames(self) -> list[EvidenceFrame]:
        return self.frame_assets

    @property
    def metadata(self) -> dict[str, float | int | str | bool | None]:
        return self.deterministic_metrics

    @property
    def description(self) -> str:
        return self.deterministic_reason

    @property
    def confidence(self) -> float | None:
        return self.visual_review.confidence if self.visual_review else self.legacy_confidence


HealthOverall = Literal["healthy", "partial", "degraded", "not_configured"]


class IntegrationHealth(BaseModel):
    overall: HealthOverall = "not_configured"
    providers: dict[str, str] = Field(default_factory=dict)
    message: str = "No providers configured"
