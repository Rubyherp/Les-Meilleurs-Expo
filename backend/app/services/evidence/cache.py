"""Deterministic cache-key generation for evidence analysis requests.

Produces a compact, repeatable key from (moment, images, model, schema_version)
so that identical evidence requests map to the same cached provider response.
"""

from __future__ import annotations

import hashlib
import json

from app.integrations.models import EvidenceMoment
from app.services.evidence.models import PreparedEvidenceImage


def evidence_cache_key(
    moment: EvidenceMoment,
    images: list[PreparedEvidenceImage],
    model: str,
    schema_version: int,
) -> str:
    """Generate a deterministic cache key for a single evidence analysis call.

    The key aggregates:
      - ``moment`` category, severity, description, frame timestamps, and
        metadata (excluding mutable fields like ``visual_review``).
      - ``images`` SHA-256 digests (the image content is hashed, so we only
        need to include the digest).
      - ``model`` name.
      - ``schema_version`` integer.

    The result is a 64‑character hex SHA-256 string.
    """
    image_hashes = sorted([img.sha256 for img in images])

    payload = {
        "id": moment.id,
        "category": moment.category,
        "severity": moment.severity,
        "primary_timestamp_seconds": moment.primary_timestamp_seconds,
        "reason": moment.deterministic_reason,
        "metrics": dict(sorted(moment.deterministic_metrics.items())),
        "image_sha256s": image_hashes,
        "model": model,
        "schema_version": schema_version,
    }

    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
