"""Evidence-specific data models for selection and frame preparation.

These models live alongside the shared Pydantic contracts in
``app.integrations.models`` (EvidenceMoment, EvidenceFrame, VisualReview, etc.)
and represent the lower-level pipeline types used during evidence processing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PreparedEvidenceImage:
    """A single frame extracted, resized, and hashed for provider submission.

    ``reference_image`` is populated only in comparison mode when a reference
    video is available and the moment's metadata specifies a corresponding
    reference timestamp.
    """

    image_bytes: bytes
    sha256: str
    width: int
    height: int
    timestamp_seconds: float
    reference_image: PreparedEvidenceImage | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "sha256": self.sha256,
            "width": self.width,
            "height": self.height,
            "timestamp_seconds": self.timestamp_seconds,
        }
        if self.reference_image:
            d["reference_image"] = self.reference_image.to_dict()
        return d


@dataclass(frozen=True)
class EvidenceMedia:
    """Path-based descriptor for the video source(s) used to extract frames.

    The ``video_path`` is the primary (attempt) video.
    ``reference_video_path``, when present, enables paired reference/attempt
    frame extraction in comparison mode.
    """

    video_path: str
    reference_video_path: str | None = None


@dataclass
class _Candidate:
    """Internal ranked candidate during evidence selection.

    ``metric_value`` is the primary sorting value (higher = more interesting).
    ``reason`` records why the candidate was selected.
    """

    category: str
    timestamp_seconds: float
    metric_value: float
    reason: str
    source_data: dict[str, Any] = field(default_factory=dict)
    reference_timestamp_seconds: float | None = None
