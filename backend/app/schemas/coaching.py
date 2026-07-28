"""Versioned Pydantic schemas for the coaching subsystem."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CoachIssue(BaseModel):
    description: str
    severity: str = "medium"  # low | medium | high
    category: str | None = None


class CoachPhase(BaseModel):
    phase: int  # 2, 3, 4, or 5
    name: str  # "Detection & Pose" | "Tracking & Continuity" | "Calibration & Space" | "Reference Comparison"
    available: bool  # False if phase data missing from result
    source: str  # "llm" | "deterministic" | "error"
    summary: str
    strengths: list[str] = []
    issues: list[CoachIssue] = []
    suggestions: list[str] = []
    confidence: float = Field(ge=0.0, le=1.0)


class CoachingReport(BaseModel):
    session_id: UUID
    report_version: int = 1
    mode: str  # "single" | "comparison"
    overall_summary: str
    phases: list[CoachPhase]  # always exactly 4 entries
    generated_at: datetime
    llm_model_used: str | None = None


class CoachingResponse(BaseModel):
    session_id: UUID
    report: CoachingReport | None = None
    status: str  # "completed" | "pending" | "not_configured" | "no_data"
    message: str = ""
