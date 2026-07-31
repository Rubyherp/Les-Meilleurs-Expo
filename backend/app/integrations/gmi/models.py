"""Typed contracts for the GMI Inference coaching audit."""

from pydantic import BaseModel, Field


class GmiAuditOutput(BaseModel):
    summary: str = Field(min_length=1, max_length=600)
    strengths: list[str] = Field(default_factory=list, max_length=3)
    cautions: list[str] = Field(default_factory=list, max_length=3)
    suggestions: list[str] = Field(default_factory=list, max_length=3)
    confidence: float = Field(ge=0.0, le=1.0)
