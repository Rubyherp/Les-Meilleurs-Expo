from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.integrations.models import EvidenceMoment, IntegrationRun
from app.schemas.coaching import CoachAgent, CoachIssue
from app.services.coaching.context import CoachingContext


class SpecialistOutput(BaseModel):
    summary: str = Field(min_length=1, max_length=700)
    strengths: list[str] = Field(default_factory=list, max_length=6)
    issues: list[CoachIssue] = Field(default_factory=list, max_length=6)
    suggestions: list[str] = Field(default_factory=list, max_length=6)
    cited_evidence_ids: list[str] = Field(default_factory=list, max_length=6)
    confidence: float = Field(ge=0.0, le=1.0)


class SynthesisOutput(BaseModel):
    overall_summary: str = Field(min_length=1, max_length=1000)
    next_actions: list[str] = Field(default_factory=list, min_length=1, max_length=3)


@dataclass(frozen=True)
class AgentRunContext:
    session_id: str
    coaching: CoachingContext
    evidence: tuple[EvidenceMoment, ...]


class AgenticCoachingResult(BaseModel):
    agents: list[CoachAgent]
    overall_summary: str
    coordination_notes: list[str] = Field(default_factory=list)
    integrations: list[IntegrationRun] = Field(default_factory=list)
    trace_id: str | None = None
