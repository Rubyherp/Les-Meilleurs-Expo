"""Evidence selection, frame preparation, and caching.

Deterministic pipeline for extracting and preparing visual evidence
moments from analysis results for submission to provider integrations.
"""

from app.services.evidence.cache import evidence_cache_key
from app.services.evidence.frames import prepare_evidence_images
from app.services.evidence.models import EvidenceMedia, PreparedEvidenceImage
from app.services.evidence.selector import select_evidence

__all__ = [
    "EvidenceMedia",
    "PreparedEvidenceImage",
    "evidence_cache_key",
    "prepare_evidence_images",
    "select_evidence",
]
