"""GMI runtime diagnostics — actual CUDA detection and provenance reporting.

:func:`inspect_gmi_runtime` must call ``torch.cuda.is_available()`` at runtime.
Configuration alone (``ml_device="cuda"``, ``gmi_enabled=True``) never implies
GPU success.  No secrets, URLs, or infrastructure topologies are exposed.
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import Settings

# ---------------------------------------------------------------------------
# Pipeline version identifier — bump when the processing graph changes
# ---------------------------------------------------------------------------
_PIPELINE_VERSION = "gmi-v2.1"


# ---------------------------------------------------------------------------
# GmiRuntimeInfo
# ---------------------------------------------------------------------------

class GmiRuntimeInfo(BaseModel):
    """Sanitised snapshot of the GMI processing environment.

    All device labels are cleaned to exclude raw topology data.  Effective FPS
    must be derived from actual frame throughput measurements, never estimated
    from configuration.
    """

    gpu_available: bool = False
    device_count: int = Field(default=0, ge=0)
    device_labels: list[str] = Field(default_factory=list)
    frame_count: int = Field(default=0, ge=0)
    sample_fps: float = Field(default=0.0, ge=0.0)
    effective_fps: float = Field(default=0.0, ge=0.0)
    pipeline_version: str = ""
    failure_reason: str | None = None


# ---------------------------------------------------------------------------
# Torch import guard (patchable in tests)
# ---------------------------------------------------------------------------

def _import_torch() -> Any:
    """Import torch dynamically and return the module, or raise ImportError."""
    import torch
    return torch


# ---------------------------------------------------------------------------
# Runtime inspection
# ---------------------------------------------------------------------------

def inspect_gmi_runtime(
    settings: Settings,
    *,
    frame_count: int = 0,
    elapsed_seconds: float | None = None,
    sample_fps: float = 0.0,
) -> GmiRuntimeInfo:
    """Probe the current GMI environment with actual runtime state.

    Parameters
    ----------
    settings : Settings
        Application configuration (``ml_device``, ``gmi_enabled``, etc.).
    frame_count : int
        Total frames processed during the latest pipeline run (if available).
    elapsed_seconds : float | None
        Wall-clock seconds spent in the latest pipeline run (used to compute
        ``effective_fps``).
    sample_fps : float
        The configured sample FPS for the current pipeline profile.

    Returns
    -------
    GmiRuntimeInfo
        A sanitised snapshot that never exposes secrets or topology.
    """
    # ── Fast path: GMI not enabled ──────────────────────────────────────
    if not settings.gmi_enabled:
        return GmiRuntimeInfo(
            gpu_available=False,
            failure_reason="gmi_not_configured",
            pipeline_version=_PIPELINE_VERSION,
        )

    # ── Import torch (graceful degradation) ────────────────────────────
    try:
        torch = _import_torch()
    except ImportError:
        return GmiRuntimeInfo(
            gpu_available=False,
            failure_reason="torch_unavailable",
            pipeline_version=_PIPELINE_VERSION,
        )

    # ── Actual CUDA check — configuration alone is NOT sufficient ──────
    cuda_available = bool(torch.cuda.is_available())

    if not cuda_available:
        return GmiRuntimeInfo(
            gpu_available=False,
            failure_reason="cuda_unavailable",
            pipeline_version=_PIPELINE_VERSION,
        )

    # ── CUDA is available — collect sanitised device information ───────
    count = torch.cuda.device_count()
    labels: list[str] = []
    for i in range(count):
        name = torch.cuda.get_device_name(i)
        # Keep only the device model name — strip bus IDs / topology.
        labels.append(_sanitize_device_label(name))

    # ── Compute effective FPS if we have timing data ───────────────────
    effective_fps = 0.0
    if elapsed_seconds is not None and elapsed_seconds > 0 and frame_count > 0:
        effective_fps = frame_count / elapsed_seconds

    return GmiRuntimeInfo(
        gpu_available=True,
        device_count=count,
        device_labels=labels,
        frame_count=frame_count,
        sample_fps=sample_fps,
        effective_fps=round(effective_fps, 1),
        pipeline_version=_PIPELINE_VERSION,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize_device_label(raw_name: str) -> str:
    """Extract only the human-readable device model portion.

    Device names from ``torch.cuda.get_device_name()`` can include bus IDs,
    UUID suffixes, or other topology-specific information.  We return only the
    model name prefix (e.g. ``"Tesla T4"``).
    """
    # Strip anything after the first opening parenthesis or comma that
    # typically separates topology data.
    for sep in (" (", ",", ":0000"):
        idx = raw_name.find(sep)
        if idx != -1:
            raw_name = raw_name[:idx]
    return raw_name.strip()


# ---------------------------------------------------------------------------
# Convenience: measure pipeline runtime with frame counts
# ---------------------------------------------------------------------------

class _GmiPipelineTimer:
    """Context manager to measure effective FPS for a pipeline run."""

    def __init__(self) -> None:
        self.start: float = 0.0
        self.elapsed: float = 0.0

    def __enter__(self) -> "_GmiPipelineTimer":
        self.start = time.monotonic()
        return self

    def __exit__(self, *args: object) -> None:
        self.elapsed = time.monotonic() - self.start


def finalize_gmi_runtime(
    settings: Settings,
    *,
    frame_count: int,
    elapsed_seconds: float,
    sample_fps: float = 0.0,
) -> GmiRuntimeInfo:
    """Post-pipeline runtime probe with actual timing data.

    Use after a pipeline run when frame counts and wall-clock timing are known.
    """
    return inspect_gmi_runtime(
        settings,
        frame_count=frame_count,
        elapsed_seconds=elapsed_seconds,
        sample_fps=sample_fps,
    )
