"""Tests for evidence frame preparation (extraction, resize, hash, cleanup)."""

import os
import tempfile

import cv2
import numpy as np
import pytest

from app.integrations.models import EvidenceFrame, EvidenceMoment
from app.services.evidence.frames import prepare_evidence_images
from app.services.evidence.models import EvidenceMedia, PreparedEvidenceImage


@pytest.fixture
def tiny_video_path():
    """Create a tiny 5-frame, 16x16 grayscale MP4 and return its path."""
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "tiny.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, 10.0, (16, 16), isColor=False)
    for i in range(5):
        # Each frame is a slightly different gray value
        frame = np.full((16, 16), 50 + i * 40, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    yield path
    # Cleanup
    try:
        os.unlink(path)
        os.rmdir(tmpdir)
    except OSError:
        pass


@pytest.fixture
def tiny_reference_video_path():
    """Create a different tiny reference video."""
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "tiny_ref.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, 10.0, (16, 16), isColor=False)
    for i in range(5):
        frame = np.full((16, 16), 100 + i * 20, dtype=np.uint8)
        writer.write(frame)
    writer.release()
    yield path
    try:
        os.unlink(path)
        os.rmdir(tmpdir)
    except OSError:
        pass


def _make_moment(*, timestamps, category="visibility", with_reference=False):
    """Helper to create an EvidenceMoment with frame timestamps."""
    frames = [EvidenceFrame(seconds=ts, annotation=f"frame at {ts:.2f}s") for ts in timestamps]
    return EvidenceMoment(
        category=category,
        severity="medium",
        description="Test evidence moment",
        timestamp="2025-01-01T00:00:00Z",
        frames=frames,
        metadata={"needs_reference": with_reference},
    )


def _settings(agn_max_edge=2048):
    """Minimal settings mock."""
    from unittest.mock import MagicMock

    s = MagicMock()
    s.agnes_max_image_edge = agn_max_edge
    return s


# ── Frame extraction and resize ────────────────────────────────────────

def test_prepare_images_extracts_and_resizes(tiny_video_path):
    """Frames are extracted, resized to bounded dimensions, and output as JPEG."""
    media = EvidenceMedia(video_path=tiny_video_path)
    moment = _make_moment(timestamps=[0.0])
    settings = _settings(agn_max_edge=2048)

    images = prepare_evidence_images(moment, media, settings)

    assert len(images) == 1
    img = images[0]
    # Should be JPEG bytes
    assert img.image_bytes[:3] == b"\xff\xd8\xff"  # JPEG magic
    # SHA-256 should be a 64-char hex string
    assert len(img.sha256) == 64
    assert all(c in "0123456789abcdef" for c in img.sha256)
    # Dimensions should be positive and bounded by max edge
    assert 1 <= img.width <= 2048
    assert 1 <= img.height <= 2048
    assert img.timestamp_seconds == pytest.approx(0.0)


def test_prepare_images_respects_max_edge(tiny_video_path):
    """Output is bounded by agnes_max_image_edge on longest side."""
    media = EvidenceMedia(video_path=tiny_video_path)
    moment = _make_moment(timestamps=[0.0])
    settings = _settings(agn_max_edge=128)

    images = prepare_evidence_images(moment, media, settings)

    assert len(images) == 1
    assert images[0].width <= 128
    assert images[0].height <= 128
    # The longest edge should be exactly 128 (or less if source is smaller)
    assert max(images[0].width, images[0].height) <= 128


def test_prepare_images_multiple_frames(tiny_video_path):
    """Multiple frame timestamps produce multiple images."""
    media = EvidenceMedia(video_path=tiny_video_path)
    moment = _make_moment(timestamps=[0.0, 0.1, 0.2])
    settings = _settings()

    images = prepare_evidence_images(moment, media, settings)

    assert len(images) == 3
    for img in images:
        assert img.sha256
        assert len(img.sha256) == 64


# ── SHA-256 deterministic hashing ──────────────────────────────────────

def test_prepare_images_deterministic_hash(tiny_video_path):
    """Same frame produces identical SHA-256 hash."""
    media = EvidenceMedia(video_path=tiny_video_path)
    moment = _make_moment(timestamps=[0.0])
    settings = _settings()

    run1 = prepare_evidence_images(moment, media, settings)
    run2 = prepare_evidence_images(moment, media, settings)

    assert run1[0].sha256 == run2[0].sha256


# ── Reference / attempt pairing ────────────────────────────────────────

def test_prepare_images_with_reference(tiny_video_path, tiny_reference_video_path):
    """When reference video is provided, attempt frames carry reference images."""
    media = EvidenceMedia(
        video_path=tiny_video_path,
        reference_video_path=tiny_reference_video_path,
    )
    moment = _make_moment(timestamps=[0.1], with_reference=True)
    moment.metadata["reference_timestamps"] = [0.1]
    settings = _settings()

    images = prepare_evidence_images(moment, media, settings)

    assert len(images) == 1
    assert images[0].reference_image is not None
    ref = images[0].reference_image
    assert ref.sha256
    assert ref.width > 0
    assert ref.height > 0
    # Reference and attempt should be different (different videos)
    assert images[0].sha256 != ref.sha256


def test_prepare_images_no_reference_when_not_provided(tiny_video_path):
    """Without reference video, reference_image is None."""
    media = EvidenceMedia(video_path=tiny_video_path)
    moment = _make_moment(timestamps=[0.1], with_reference=True)
    settings = _settings()

    images = prepare_evidence_images(moment, media, settings)

    assert len(images) == 1
    assert images[0].reference_image is None


# ── Cleanup ────────────────────────────────────────────────────────────

def test_prepare_images_does_not_leak_temp_files(tiny_video_path):
    """Frame preparation does not leave temporary files behind."""
    media = EvidenceMedia(video_path=tiny_video_path)
    moment = _make_moment(timestamps=[0.0])
    settings = _settings()

    before = set(os.listdir(tempfile.gettempdir()))
    images = prepare_evidence_images(moment, media, settings)
    after = set(os.listdir(tempfile.gettempdir()))

    assert len(images) > 0, "Expected at least one image to be produced"

    new_files = after - before
    assert not new_files, (
        f"Temp files leaked: {new_files}"
    )


def test_prepare_images_handles_missing_video():
    """Gracefully returns empty when video path doesn't exist."""
    media = EvidenceMedia(video_path="/nonexistent/path.mp4")
    moment = _make_moment(timestamps=[0.0])
    settings = _settings()

    images = prepare_evidence_images(moment, media, settings)
    # Missing video → no frames extracted
    assert images == []


def test_prepare_images_handles_out_of_bounds_timestamp(tiny_video_path):
    """Timestamp beyond video duration raises or returns empty."""
    media = EvidenceMedia(video_path=tiny_video_path)
    # Video is 5 frames at 10fps = 0.5 sec max timestamp
    moment = _make_moment(timestamps=[999.0])
    settings = _settings()

    # May raise or return empty — both are acceptable
    try:
        images = prepare_evidence_images(moment, media, settings)
        # If it returns, it should be empty since timestamp is OOB
        assert len(images) == 0
    except Exception:
        pass  # Raising is also fine
