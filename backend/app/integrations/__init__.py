"""Shared integration contracts, models, and health aggregation.

No provider calls are made here — this layer holds only configuration‑safe
data types and sanitized health reporting.
"""

from app.integrations.models import (
    EvidenceFrame,
    EvidenceMoment,
    IntegrationHealth,
    IntegrationRun,
    VisualReview,
)
from app.integrations.health import get_integration_health

__all__ = [
    "EvidenceFrame",
    "EvidenceMoment",
    "IntegrationHealth",
    "IntegrationRun",
    "VisualReview",
    "get_integration_health",
]
