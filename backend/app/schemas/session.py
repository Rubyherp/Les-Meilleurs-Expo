from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.services.projection import CalibrationError, validate_calibration_points


class SessionCreateResponse(BaseModel):
    session_id: UUID
    status: str
    created_at: datetime


class UploadResponse(BaseModel):
    session_id: UUID
    media_id: UUID
    task_id: UUID
    status: str


class TaskStatusResponse(BaseModel):
    task_id: UUID
    session_id: UUID
    status: str
    progress: int
    control: dict | None = None
    error: str | None = None
    result: dict | None = None


class CalibrationRequest(BaseModel):
    points: list[tuple[float, float]] = Field(min_length=4, max_length=4)
    source: Literal["human", "approximate", "agent"] = "human"

    @field_validator("points")
    @classmethod
    def validate_points(cls, value: list[tuple[float, float]]) -> list[tuple[float, float]]:
        try:
            validate_calibration_points(value)
        except CalibrationError as exc:
            raise ValueError(str(exc)) from exc
        return value


class CalibrationResponse(BaseModel):
    session_id: UUID
    points: list[tuple[float, float]]
    source: str = "human"
    status: str = "verified"


class SessionResultResponse(BaseModel):
    session_id: UUID
    task_id: UUID
    created_at: datetime
    metadata: dict


class RoleMediaResponse(BaseModel):
    session_id: UUID
    media_id: UUID
    role: str


class ComparisonRequest(BaseModel):
    reference_media_id: UUID | None = None
    attempt_media_id: UUID | None = None
    expected_dancer_count: int = Field(default=1, ge=1, le=24)


class ComparisonResponse(BaseModel):
    session_id: UUID
    task_id: UUID
    status: str
    mode: str
    reference_media_id: UUID
    attempt_media_id: UUID
