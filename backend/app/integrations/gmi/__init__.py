"""GMI Cloud inference plus optional GPU runtime diagnostics.

Reports actual CUDA availability through ``torch.cuda.is_available()`` at
runtime.  Configuration alone (``ml_device="cuda"``, ``gmi_enabled=True``)
never implies GPU success.
"""

from app.integrations.gmi.health import GmiRuntimeInfo, inspect_gmi_runtime
from app.integrations.gmi.client import GmiInferenceClient

__all__ = ["GmiInferenceClient", "GmiRuntimeInfo", "inspect_gmi_runtime"]
