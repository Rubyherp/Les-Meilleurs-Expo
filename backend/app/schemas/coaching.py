"""Versioned Pydantic schemas for the coaching subsystem."""

from datetime import datetime
from uuid import UUID

from pydantic import AliasChoices, BaseModel, Field, field_validator

from app.integrations.models import EvidenceMoment, IntegrationRun


class CoachingRequest(BaseModel):
    is_group: bool = False
    expected_dancer_count: int = Field(default=1, ge=1, le=8)


class CoachIssue(BaseModel):
    description: str
    severity: str = "medium"  # low | medium | high
    category: str | None = None


class CoachEvidence(BaseModel):
    metric: str
    value: float | int | str
    unit: str | None = None
    start_seconds: float | None = Field(default=None, ge=0.0)
    end_seconds: float | None = Field(default=None, ge=0.0)
    dancer_ids: list[int] = []


class CoachAgent(BaseModel):
    agent_id: int = Field(
        validation_alias=AliasChoices("agent_id", "phase")
    )  # 1 Observation, 2 Timing, 3 Formation
    name: str
    available: bool
    source: str  # "llm" | "deterministic" | "error"
    summary: str
    strengths: list[str] = []
    issues: list[CoachIssue] = []
    suggestions: list[str] = []
    evidence: list[CoachEvidence] = []
    confidence: float = Field(ge=0.0, le=1.0)

    @property
    def phase(self) -> int:
        """Compatibility accessor for version-1 callers."""
        return self.agent_id


# Compatibility import for older internal callers while the report contract
# now uses agent terminology.
CoachPhase = CoachAgent


class CoachingReport(BaseModel):
    session_id: UUID
    report_version: int = 4
    mode: str  # "single" | "comparison"
    practice_type: str = "solo"  # "solo" | "group"
    overall_summary: str
    agents: list[CoachAgent] = Field(
        validation_alias=AliasChoices("agents", "phases")
    )  # 2 for solo; 3 for group
    coordination_notes: list[str] = []
    generated_at: datetime
    llm_model_used: str | None = None

    # ── Sponsor integration extensions (v4) ────────────────────────────
    evidence_moments: list[EvidenceMoment] = Field(default_factory=list)
    integrations: list[IntegrationRun] = Field(default_factory=list)
    trace_id: str | None = None

    @field_validator("trace_id", mode="before")
    @classmethod
    def stringify_trace_id(cls, value):
        return str(value) if value is not None else None

    @property
    def phases(self) -> list[CoachAgent]:
        """Compatibility accessor for version-1 callers."""
        return self.agents


class CoachingResponse(BaseModel):
    session_id: UUID
    report: CoachingReport | None = None
    status: str  # "completed" | "pending" | "not_configured" | "no_data"
    message: str = ""
