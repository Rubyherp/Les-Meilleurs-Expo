"""Internal Agnes request/response contracts."""

from pydantic import BaseModel, Field


class AgnesStructuredReview(BaseModel):
    summary: str = Field(min_length=1, max_length=600)
    visible_differences: list[str] = Field(default_factory=list, max_length=8)
    limitations: list[str] = Field(default_factory=list, max_length=8)
    confidence: float = Field(ge=0.0, le=1.0)
