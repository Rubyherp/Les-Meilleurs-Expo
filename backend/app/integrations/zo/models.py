from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

from app.integrations.models import EvidenceCategory, IntegrationRun, IntegrationStatus, _MIN_TS

ZoVisibility = Literal["private", "unlisted"]
ZoExportStatus = Literal["pending", "completed", "failed", "not_configured"]


class ZoEvidenceEntry(BaseModel):
    timestamp_seconds: float = Field(default=0.0, ge=0.0)
    category: EvidenceCategory
    summary: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="before")
    @classmethod
    def migrate_timestamp(cls, value):
        if isinstance(value, dict) and "timestamp_seconds" not in value and "timestamp" in value:
            if isinstance(value["timestamp"], datetime) and value["timestamp"] < _MIN_TS:
                raise ValueError("legacy timestamp is before the supported minimum")
            value = {**value, "timestamp_seconds": 0.0}
        if isinstance(value, dict) and value.get("category") == "spacing":
            value = {**value, "category": "formation"}
        return value

    @property
    def timestamp(self):
        return self.timestamp_seconds


class ZoExportArtifact(BaseModel):
    artifact_version: int = Field(default=1, ge=1)
    session_id: UUID
    session_summary: str = ""
    next_actions: list[str] = Field(default_factory=list)
    evidence: list[ZoEvidenceEntry] = Field(default_factory=list)
    provider_statuses: dict[str, str] = Field(default_factory=dict)
    visibility: ZoVisibility = "private"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), ge=_MIN_TS)
    idempotency_key: str = ""

    @field_validator("provider_statuses")
    @classmethod
    def validate_statuses(cls, value):
        allowed = {"configured", "not_configured", "pending", "running", "completed", "fallback", "failed"}
        if any(status not in allowed for status in value.values()):
            raise ValueError("invalid provider status")
        return value


class ZoExportRequest(BaseModel):
    visibility: ZoVisibility | None = None
    schedule_reminder: bool = False
    reminder_at: datetime | None = None
    timezone: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_reminder(self) -> "ZoExportRequest":
        if self.schedule_reminder and (self.reminder_at is None or not self.timezone):
            raise ValueError("reminder_at and timezone are required when scheduling")
        return self


class ZoExportResponse(BaseModel):
    session_id: UUID
    status: ZoExportStatus
    export_id: str | None = None
    url: str | None = None
    idempotency_key: str = ""
    created_at: datetime | None = None
    message: str = ""
    reminder_id: str | None = None
    integration: IntegrationRun | None = None

    def model_post_init(self, _ctx) -> None:
        if self.status == "not_configured" and not self.message:
            self.message = "Zo export is not configured."
