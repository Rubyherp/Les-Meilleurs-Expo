"""Bounded-frame extraction and preparation for evidence images.

Extracts frames from video at evidence timestamps, resizes to a
configurable maximum edge length, encodes as JPEG, and computes a
deterministic SHA-256 hash.  Comparison mode can optionally pair each
attempt frame with a corresponding reference frame.

**Important**: Original video pixels are never persisted to disk.
"""

from __future__ import annotations

import hashlib
import math
from typing import TYPE_CHECKING

import cv2
import numpy as np

from app.integrations.models import EvidenceMoment
from app.services.evidence.models import EvidenceMedia, PreparedEvidenceImage

if TYPE_CHECKING:
    from app.core.config import Settings


def _read_frame(video_path: str, timestamp_seconds: float) -> np.ndarray | None:
    """Open *video_path*, seek to *timestamp_seconds*, and return the frame.

    Returns ``None`` if the video cannot be opened, the timestamp is out of
    range, or reading fails.  The returned array is a BGR ``uint8`` image.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        cap.release()
        return None

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        cap.release()
        return None

    # Seek to nearest keyframe then advance
    frame_index = int(round(timestamp_seconds * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)

    success, frame = cap.read()
    cap.release()

    if not success or frame is None or frame.size == 0:
        return None

    return frame


def _resize_frame(frame: np.ndarray, max_edge: int) -> np.ndarray:
    """Resize *frame* so the longest edge does not exceed *max_edge*.

    Aspect ratio is preserved.  If the frame is already within bounds it is
    returned unchanged.
    """
    h, w = frame.shape[:2]
    if max(h, w) <= max_edge:
        return frame

    scale = max_edge / max(h, w)
    new_w = int(w * scale)
    new_h = int(h * scale)
    return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)


def _encode_jpeg(frame: np.ndarray, quality: int = 92) -> bytes:
    """Encode *frame* as JPEG bytes."""
    success, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not success:
        raise RuntimeError("JPEG encoding failed")
    return buf.tobytes()


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _prepare_single_frame(
    video_path: str,
    timestamp_seconds: float,
    max_edge: int,
) -> PreparedEvidenceImage | None:
    """Extract, resize, encode, and hash a single frame from *video_path*."""
    frame = _read_frame(video_path, timestamp_seconds)
    if frame is None:
        return None

    resized = _resize_frame(frame, max_edge)
    jpeg_bytes = _encode_jpeg(resized)
    sha = _sha256_hex(jpeg_bytes)
    h, w = resized.shape[:2]

    return PreparedEvidenceImage(
        image_bytes=jpeg_bytes,
        sha256=sha,
        width=w,
        height=h,
        timestamp_seconds=timestamp_seconds,
    )


# ── Public API ────────────────────────────────────────────────────────

def prepare_evidence_images(
    moment: EvidenceMoment,
    media: EvidenceMedia,
    settings: Settings,
) -> list[PreparedEvidenceImage]:
    """Extract and prepare bounded JPEG images for every frame in *moment*.

    Parameters
    ----------
    moment:
        Evidence moment whose ``frames`` list specifies the timestamps to
        extract from the primary video.
    media:
        Path descriptor for the attempt video and, optionally, a reference
        video for comparison mode.
    settings:
        Application settings.  ``agnes_max_image_edge`` controls the resize
        ceiling.

    Returns
    -------
    list[PreparedEvidenceImage]
        One ``PreparedEvidenceImage`` per timestamp in ``moment.frames``
        for which a frame could be successfully extracted.  Frames that
        fail extraction (out of bounds, corrupted) are silently skipped.
    """
    max_edge = getattr(settings, "agnes_max_image_edge", 2048)
    images: list[PreparedEvidenceImage] = []

    reference_video = media.reference_video_path
    reference_timestamp = moment.deterministic_metrics.get("reference_timestamp_seconds")
    if reference_timestamp is None:
        legacy_timestamps = moment.deterministic_metrics.get("reference_timestamps")
        if isinstance(legacy_timestamps, list) and legacy_timestamps:
            reference_timestamp = legacy_timestamps[0]
    may_need_reference = bool(reference_video and isinstance(reference_timestamp, (int, float)))

    timestamps = [frame.timestamp_seconds for frame in moment.frame_assets]
    if not timestamps:
        timestamps = [moment.primary_timestamp_seconds]
    for ts in timestamps:

        # Extract attempt frame
        img = _prepare_single_frame(media.video_path, ts, max_edge)
        if img is None:
            continue

        # Extract reference frame if applicable
        ref_img: PreparedEvidenceImage | None = None
        if may_need_reference:
            ref_ts = float(reference_timestamp)
            ref_img = _prepare_single_frame(reference_video, ref_ts, max_edge)  # type: ignore[arg-type]

        images.append(
            PreparedEvidenceImage(
                image_bytes=img.image_bytes,
                sha256=img.sha256,
                width=img.width,
                height=img.height,
                timestamp_seconds=ts,
                reference_image=ref_img,
            )
        )

    return images
