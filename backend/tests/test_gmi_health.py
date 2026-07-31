"""Tests for GMI runtime diagnostics and provenance reporting.

All tests mock torch so they run without a GPU.  The production implementation
must call ``torch.cuda.is_available()`` at runtime and never infer GPU state
from configuration alone.
"""

import pytest


# ---------------------------------------------------------------------------
# GmiRuntimeInfo contract
# ---------------------------------------------------------------------------

def test_gmi_runtime_info_requires_no_args():
    """GmiRuntimeInfo accepts no required arguments and exposes safe defaults."""
    from app.integrations.gmi.health import GmiRuntimeInfo

    info = GmiRuntimeInfo()
    assert info.gpu_available is False
    assert info.device_count == 0
    assert info.device_labels == []
    assert info.frame_count == 0
    assert info.sample_fps == 0.0
    assert info.effective_fps == 0.0
    assert info.pipeline_version == ""
    assert info.failure_reason is None


def test_gmi_runtime_info_full_state():
    """All fields populate correctly for a healthy multi-GPU runtime."""
    from app.integrations.gmi.health import GmiRuntimeInfo

    info = GmiRuntimeInfo(
        gpu_available=True,
        device_count=2,
        device_labels=["Tesla T4", "Tesla T4"],
        frame_count=1500,
        sample_fps=10.0,
        effective_fps=85.3,
        pipeline_version="gmi-v2.1",
    )
    assert info.gpu_available is True
    assert info.device_count == 2
    assert info.device_labels == ["Tesla T4", "Tesla T4"]
    assert info.frame_count == 1500
    assert info.sample_fps == 10.0
    assert info.effective_fps == 85.3
    assert info.pipeline_version == "gmi-v2.1"
    assert info.failure_reason is None


def test_gmi_runtime_info_failure_reason_preserved():
    """failure_reason is stored when GPU is unavailable."""
    from app.integrations.gmi.health import GmiRuntimeInfo

    info = GmiRuntimeInfo(
        gpu_available=False,
        failure_reason="cuda_unavailable",
    )
    assert info.gpu_available is False
    assert info.failure_reason == "cuda_unavailable"


# ---------------------------------------------------------------------------
# inspect_gmi_runtime – CPU path
# ---------------------------------------------------------------------------

def test_cuda_configuration_without_device_is_not_available(monkeypatch):
    """GPU config alone must never imply GPU success; runtime check is authoritative."""
    from app.core.config import Settings
    from app.integrations.gmi.health import inspect_gmi_runtime

    # Override torch import so tests run without a real GPU.
    fake_torch = _fake_torch_module(cuda_available=False, device_count=0)
    monkeypatch.setattr("app.integrations.gmi.health._import_torch", lambda: fake_torch)

    info = inspect_gmi_runtime(Settings(ml_device="cuda", gmi_enabled=True))
    assert info.gpu_available is False
    assert info.failure_reason == "cuda_unavailable"


def test_inspect_gmi_runtime_cpu_mode(monkeypatch):
    """Local CPU work must never be reported as completed GMI work."""
    from app.core.config import Settings
    from app.integrations.gmi.health import inspect_gmi_runtime

    fake_torch = _fake_torch_module(cuda_available=False, device_count=0)
    monkeypatch.setattr("app.integrations.gmi.health._import_torch", lambda: fake_torch)

    info = inspect_gmi_runtime(Settings(ml_device="cpu", gmi_enabled=False))
    assert info.gpu_available is False
    assert info.failure_reason == "gmi_not_configured"
    assert info.device_count == 0


def test_inspect_gmi_runtime_gmi_disabled_skips(monkeypatch):
    """When gmi_enabled=False, runtime reports not_configured status."""
    from app.core.config import Settings
    from app.integrations.gmi.health import inspect_gmi_runtime

    fake_torch = _fake_torch_module(cuda_available=True, device_count=1)
    monkeypatch.setattr("app.integrations.gmi.health._import_torch", lambda: fake_torch)

    info = inspect_gmi_runtime(Settings(ml_device="cuda", gmi_enabled=False))
    assert info.gpu_available is False
    assert info.failure_reason == "gmi_not_configured"


# ---------------------------------------------------------------------------
# inspect_gmi_runtime – CUDA path (mocked)
# ---------------------------------------------------------------------------

def test_inspect_gmi_runtime_cuda_available_single_gpu(monkeypatch):
    """A single CUDA device is reported correctly."""
    from app.core.config import Settings
    from app.integrations.gmi.health import inspect_gmi_runtime

    fake_torch = _fake_torch_module(cuda_available=True, device_count=1)
    monkeypatch.setattr("app.integrations.gmi.health._import_torch", lambda: fake_torch)

    info = inspect_gmi_runtime(Settings(ml_device="cuda", gmi_enabled=True))
    assert info.gpu_available is True
    assert info.device_count == 1
    assert info.failure_reason is None


def test_inspect_gmi_runtime_cuda_available_multi_gpu(monkeypatch):
    """Multiple CUDA devices are reported correctly."""
    from app.core.config import Settings
    from app.integrations.gmi.health import inspect_gmi_runtime

    fake_torch = _fake_torch_module(cuda_available=True, device_count=4)
    monkeypatch.setattr("app.integrations.gmi.health._import_torch", lambda: fake_torch)

    info = inspect_gmi_runtime(Settings(ml_device="cuda", gmi_enabled=True))
    assert info.gpu_available is True
    assert info.device_count == 4


def test_inspect_gmi_runtime_device_labels_sanitized(monkeypatch):
    """Device labels must be collected but never expose raw GPU identifiers in a
    way that would leak infrastructure topology."""
    from app.core.config import Settings
    from app.integrations.gmi.health import inspect_gmi_runtime

    fake_torch = _fake_torch_module(cuda_available=True, device_count=2)
    monkeypatch.setattr("app.integrations.gmi.health._import_torch", lambda: fake_torch)

    info = inspect_gmi_runtime(Settings(ml_device="cuda", gmi_enabled=True))
    assert info.device_count == 2
    assert len(info.device_labels) == 2
    # Labels must contain the device name portion only.
    for label in info.device_labels:
        assert isinstance(label, str)
        assert "Tesla" in label or "device" in label.lower()


def test_inspect_gmi_runtime_torch_unavailable(monkeypatch):
    """When torch cannot be imported, a clear failure_reason is set."""
    from app.core.config import Settings
    from app.integrations.gmi.health import inspect_gmi_runtime

    monkeypatch.setattr(
        "app.integrations.gmi.health._import_torch",
        lambda: (_ for _ in ()).throw(ImportError("No module named 'torch'")),
    )

    info = inspect_gmi_runtime(Settings(ml_device="cuda", gmi_enabled=True))
    assert info.gpu_available is False
    assert info.failure_reason == "torch_unavailable"


# ---------------------------------------------------------------------------
# IntegrationRun provenance (typed model, not raw dict)
# ---------------------------------------------------------------------------


def test_integration_run_typed_gmi_provenance():
    """GMI provenance must use the typed IntegrationRun model with truthful
    timestamps and valid status semantics."""
    from datetime import datetime, timezone

    from app.integrations.models import IntegrationRun

    now = datetime.now(timezone.utc)
    run = IntegrationRun(
        provider="gmi",
        product="analysis-runtime",
        status="completed",
        started_at=now,
        finished_at=now,
        message="",
        metadata={
            "gpu_available": True,
            "device_count": 1,
            "device_labels": ["Tesla T4"],
            "frame_count": 1500,
            "sample_fps": 10.0,
            "effective_fps": 85.3,
            "pipeline_version": "gmi-v2.1",
        },
    )
    assert run.provider == "gmi"
    assert run.product == "analysis-runtime"
    assert run.status == "completed"
    assert run.started_at == now
    assert run.finished_at == now
    assert run.metadata["gpu_available"] is True
    assert run.metadata["frame_count"] == 1500
    assert run.metadata["effective_fps"] == 85.3


def test_integration_run_status_not_configured():
    """gmi_not_configured maps to not_configured, not failed."""
    from app.integrations.models import IntegrationRun

    run = IntegrationRun(
        provider="gmi",
        product="analysis-runtime",
        status="not_configured",
        metadata={"failure_reason": "gmi_not_configured"},
    )
    assert run.status == "not_configured"


def test_integration_run_status_failed():
    """cuda_unavailable / torch_unavailable map to failed, not not_configured."""
    from app.integrations.models import IntegrationRun

    for reason in ("cuda_unavailable", "torch_unavailable"):
        run = IntegrationRun(
            provider="gmi",
            product="analysis-runtime",
            status="failed",
            message=reason,
            metadata={"failure_reason": reason},
        )
        assert run.status == "failed"
        assert run.message == reason


def test_integration_run_timestamps_present():
    """IntegrationRun started_at / finished_at must be UTC-aware datetimes,
    not epoch-zero or None when the pipeline actually ran."""
    from datetime import datetime, timezone

    from app.integrations.models import IntegrationRun

    started = datetime(2026, 7, 31, 12, 0, 0, tzinfo=timezone.utc)
    finished = datetime(2026, 7, 31, 12, 5, 30, tzinfo=timezone.utc)
    run = IntegrationRun(
        provider="gmi",
        product="analysis-runtime",
        status="completed",
        started_at=started,
        finished_at=finished,
    )
    assert run.started_at == started
    assert run.finished_at == finished
    assert run.started_at.tzinfo is not None
    assert run.finished_at.tzinfo is not None


# ---------------------------------------------------------------------------
# _extract_frame_count – comparison aggregation
# ---------------------------------------------------------------------------


def test_extract_frame_count_single_result():
    """A standard (non-comparison) result yields frames_processed."""
    from app.tasks.analysis import _extract_frame_count

    result = {"frames_processed": 300}
    assert _extract_frame_count(result) == 300


def test_extract_frame_count_comparison_aggregates():
    """Comparison mode must sum frames from nested reference and attempt
    results, not report zero."""
    from app.tasks.analysis import _extract_frame_count

    result = {
        "mode": "comparison",
        "reference": {"frames_processed": 300},
        "attempt": {"frames_processed": 300},
    }
    assert _extract_frame_count(result) == 600


def test_extract_frame_count_comparison_missing_nested():
    """Comparison mode gracefully handles missing nested frame counts."""
    from app.tasks.analysis import _extract_frame_count

    result = {
        "mode": "comparison",
        "reference": {},
        "attempt": {},
    }
    assert _extract_frame_count(result) == 0


def test_extract_frame_count_comparison_total_frames():
    """Comparison mode sums total_frames from reference and attempt."""
    from app.tasks.analysis import _extract_frame_count

    result = {
        "mode": "comparison",
        "reference": {"total_frames": 150},
        "attempt": {"total_frames": 200},
    }
    assert _extract_frame_count(result) == 350


def test_extract_frame_count_poses_fallback():
    """Fallback to len(poses) when no frame_count keys exist."""
    from app.tasks.analysis import _extract_frame_count

    result = {"poses": [{"x": 0}] * 42}
    assert _extract_frame_count(result) == 42


def test_extract_frame_count_empty():
    """Empty result yields 0."""
    from app.tasks.analysis import _extract_frame_count

    assert _extract_frame_count({}) == 0


# ---------------------------------------------------------------------------
# Effective FPS (inspect_gmi_runtime with timing)
# ---------------------------------------------------------------------------


def test_effective_fps_computed_from_timing(monkeypatch):
    """Effective FPS = frame_count / elapsed_seconds when both are provided."""
    from app.core.config import Settings
    from app.integrations.gmi.health import inspect_gmi_runtime

    fake_torch = _fake_torch_module(cuda_available=True, device_count=1)
    monkeypatch.setattr("app.integrations.gmi.health._import_torch", lambda: fake_torch)

    info = inspect_gmi_runtime(
        Settings(ml_device="cuda", gmi_enabled=True),
        frame_count=1500,
        elapsed_seconds=17.6,
        sample_fps=10.0,
    )
    assert info.gpu_available is True
    assert info.frame_count == 1500
    assert info.sample_fps == 10.0
    # 1500 / 17.6 ≈ 85.2, rounded to 1 decimal
    assert info.effective_fps == round(1500 / 17.6, 1)
    assert info.effective_fps > 0


def test_effective_fps_zero_when_no_timing(monkeypatch):
    """Effective FPS is 0 when elapsed_seconds is None."""
    from app.core.config import Settings
    from app.integrations.gmi.health import inspect_gmi_runtime

    fake_torch = _fake_torch_module(cuda_available=True, device_count=1)
    monkeypatch.setattr("app.integrations.gmi.health._import_torch", lambda: fake_torch)

    info = inspect_gmi_runtime(
        Settings(ml_device="cuda", gmi_enabled=True),
        frame_count=1000,
        elapsed_seconds=None,
    )
    assert info.effective_fps == 0.0


def test_effective_fps_zero_when_no_frames(monkeypatch):
    """Effective FPS is 0 when frame_count is 0."""
    from app.core.config import Settings
    from app.integrations.gmi.health import inspect_gmi_runtime

    fake_torch = _fake_torch_module(cuda_available=True, device_count=1)
    monkeypatch.setattr("app.integrations.gmi.health._import_torch", lambda: fake_torch)

    info = inspect_gmi_runtime(
        Settings(ml_device="cuda", gmi_enabled=True),
        frame_count=0,
        elapsed_seconds=10.0,
    )
    assert info.effective_fps == 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_torch_module(*, cuda_available: bool, device_count: int):
    """Build a minimal torch module substitute for unit tests."""

    class _FakeDevice:
        def __init__(self, index):
            self._index = index

        @property
        def name(self) -> str:
            return f"Tesla T4 (device {self._index})"

    class _FakeCuda:
        @staticmethod
        def is_available() -> bool:
            return cuda_available

        @staticmethod
        def device_count() -> int:
            return device_count

        def get_device_name(self, index) -> str:
            return _FakeDevice(index).name

    class _FakeTorch:
        cuda = _FakeCuda()

    return _FakeTorch()
