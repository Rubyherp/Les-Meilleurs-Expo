from datetime import datetime
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
    error: str | None = None
    result: dict | None = None


class CalibrationRequest(BaseModel):
    points: list[tuple[float, float]] = Field(min_length=4, max_length=4)

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


class ComparisonResponse(BaseModel):
    session_id: UUID
    task_id: UUID
    status: str
    mode: str
    reference_media_id: UUID
    attempt_media_id: UUID


# ── Coaching ─────────────────────────────────────────────────────────────

class CoachIssue(BaseModel):
    description: str
    severity: str = "medium"  # low, medium, high


class AgentInsight(BaseModel):
    agent_name: str
    summary: str
    strengths: list[str]
    issues: list[CoachIssue]
    suggestions: list[str]
    confidence: float


class CoachingReport(BaseModel):
    session_id: UUID
    mode: str  # "single" | "comparison"
    overall_summary: str
    agents: list[AgentInsight]
    generated_at: datetime


class CoachingResponse(BaseModel):
    session_id: UUID
    report: CoachingReport | None = None
    status: str  # "completed" | "not_configured" | "no_data" | "processing"
    message: str = ""
