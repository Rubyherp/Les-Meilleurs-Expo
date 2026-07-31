"""Tests for integration settings in app.core.config."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


# ── Provider visibility enum ──────────────────────────────────────────────

def test_zo_visibility_defaults_to_private():
    """Default visibility should be 'private'."""
    s = Settings()
    assert s.zo_export_visibility == "private"


def test_zo_visibility_rejects_invalid():
    """Visibility must be one of private or unlisted."""
    for v in ("world", "public", "team"):
        with pytest.raises(ValidationError):
            Settings(zo_export_visibility=v)


def test_zo_visibility_accepts_valid():
    for v in ("private", "unlisted"):
        s = Settings(zo_export_visibility=v)
        assert s.zo_export_visibility == v


# ── Empty keys = not_configured ───────────────────────────────────────────

def test_empty_openai_key_means_not_configured():
    s = Settings(openai_api_key="")
    assert s.openai_api_key == ""


def test_empty_agnes_key_means_not_configured():
    s = Settings(agnes_api_key="")
    assert s.agnes_api_key == ""


def test_empty_zo_key_means_not_configured():
    s = Settings(zo_api_key="")
    assert s.zo_api_key == ""


# ── Positive timeout validation ───────────────────────────────────────────

def test_openai_timeout_positive():
    s = Settings(openai_timeout_seconds=30.0)
    assert s.openai_timeout_seconds == 30.0

    with pytest.raises(ValidationError):
        Settings(openai_timeout_seconds=0)


def test_agnes_timeout_positive():
    s = Settings(agnes_timeout_seconds=15.0)
    assert s.agnes_timeout_seconds == 15.0

    with pytest.raises(ValidationError):
        Settings(agnes_timeout_seconds=-1.0)


def test_zo_timeout_positive():
    s = Settings(zo_timeout_seconds=60.0)
    assert s.zo_timeout_seconds == 60.0

    with pytest.raises(ValidationError):
        Settings(zo_timeout_seconds=0)


# ── Evidence count bounds ─────────────────────────────────────────────────

def test_agnes_max_evidence_moments_bounds():
    s = Settings(agnes_max_evidence_moments=3)
    assert s.agnes_max_evidence_moments == 3

    with pytest.raises(ValidationError):
        Settings(agnes_max_evidence_moments=-1)

    with pytest.raises(ValidationError):
        Settings(agnes_max_evidence_moments=6)


# ── Image edge bounds ─────────────────────────────────────────────────────

def test_agnes_max_image_edge_bounds():
    s = Settings(agnes_max_image_edge=1024)
    assert s.agnes_max_image_edge == 1024

    with pytest.raises(ValidationError):
        Settings(agnes_max_image_edge=0)

    # Should allow a large but reasonable edge
    s2 = Settings(agnes_max_image_edge=4096)
    assert s2.agnes_max_image_edge == 4096


# ── Provider model defaults ───────────────────────────────────────────────

def test_openai_model_default():
    s = Settings()
    assert s.openai_model == "gpt-5.4-nano"
    assert s.llm_model == "gpt-5.4-nano"  # deprecated alias


def test_agnes_model_default():
    s = Settings()
    assert s.agnes_model == "agnes-2.5-flash"
    assert s.agnes_fallback_model == "agnes-2.0-flash"
    assert s.agnes_max_retries == 1
    assert s.agnes_max_evidence_moments == 1


def test_agnes_retry_and_output_bounds():
    with pytest.raises(ValidationError):
        Settings(agnes_max_retries=3)
    with pytest.raises(ValidationError):
        Settings(agnes_retry_base_seconds=-0.1)
    with pytest.raises(ValidationError):
        Settings(agnes_max_output_tokens=32)


# ── GMI settings ──────────────────────────────────────────────────────────

def test_gmi_defaults():
    s = Settings()
    assert s.gmi_enabled is False
    assert s.gmi_region == ""
    assert s.gmi_instance_label == ""
    assert s.gmi_gpu_label == ""


def test_gmi_enabled_with_labels():
    s = Settings(gmi_enabled=True, gmi_region="us-central1", gmi_instance_label="n1-standard", gmi_gpu_label="nvidia-t4")
    assert s.gmi_enabled is True
    assert s.gmi_region == "us-central1"
    assert s.gmi_instance_label == "n1-standard"
    assert s.gmi_gpu_label == "nvidia-t4"


# ── Default settings produce a valid object ──────────────────────────────

def test_default_settings_valid():
    """Default Settings() should construct without validation errors."""
    s = Settings()
    assert s.app_name == "Video Analysis API"
    # Provider keys may be set via environment — we only assert valid defaults.
    assert isinstance(s.openai_api_key, str)
    assert isinstance(s.agnes_api_key, str)
    assert isinstance(s.zo_api_key, str)
    assert s.openai_timeout_seconds > 0
    assert s.agnes_timeout_seconds > 0
    assert s.zo_timeout_seconds > 0
    assert s.agnes_max_evidence_moments in range(0, 6)
    assert s.agnes_max_image_edge >= 128
