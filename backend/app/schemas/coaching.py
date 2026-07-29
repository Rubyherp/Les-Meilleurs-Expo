"""Versioned Pydantic schemas for the coaching subsystem."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CoachingRequest(BaseModel):
    is_group: bool = False
    expected_dancer_count: int = Field(default=1, ge=1, le=8)


class CoachIssue(BaseModel):
    description: str
    severity: str = "medium"  # low | medium | high
    category: str | None = None


class CoachPhase(BaseModel):
    phase: int  # Specialist order: 1 Observation, 2 Timing, 3 Formation
    name: str
    available: bool
    source: str  # "llm" | "deterministic" | "error"
    summary: str
    strengths: list[str] = []
    issues: list[CoachIssue] = []
    suggestions: list[str] = []
    confidence: float = Field(ge=0.0, le=1.0)


class CoachingReport(BaseModel):
    session_id: UUID
    report_version: int = 2
    mode: str  # "single" | "comparison"
    practice_type: str = "solo"  # "solo" | "group"
    overall_summary: str
    phases: list[CoachPhase]  # 2 for solo; 3 for group
    generated_at: datetime
    llm_model_used: str | None = None


class CoachingResponse(BaseModel):
    session_id: UUID
    report: CoachingReport | None = None
    status: str  # "completed" | "pending" | "not_configured" | "no_data"
    message: str = ""
