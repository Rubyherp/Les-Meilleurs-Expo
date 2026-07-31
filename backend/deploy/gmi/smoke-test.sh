#!/usr/bin/env bash
# GMI GPU smoke test — validates CUDA availability at runtime.
# Exits non-zero if CUDA is requested but unavailable.
# Prints only sanitised device information (no raw topology / secrets).
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

CONTAINER="${GMI_CONTAINER:-les-meilleurs-backend-gpu-worker-1}"
DOCKER_COMPOSE_FILE="${DOCKER_COMPOSE_FILE:-deploy/gmi/docker-compose.gpu.yml}"

fail() {
    printf "%bFAIL%b %s\n" "$RED" "$NC" "$1" >&2
    exit 1
}

ok() {
    printf "%bOK%b   %s\n" "$GREEN" "$NC" "$1"
}

warn() {
    printf "%bWARN%b %s\n" "$YELLOW" "$NC" "$1" >&2
}

# ── Phase 1: Docker container must be running ────────────────────────────
printf "\n=== GMI GPU Smoke Test ===\n\n"

if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "$CONTAINER"; then
    fail "Container '$CONTAINER' is not running. Start with: docker compose -f $DOCKER_COMPOSE_FILE up -d"
fi
ok "Container '$CONTAINER' is running"

# ── Phase 2: GMI must be enabled ─────────────────────────────────────────
gmi_enabled=$(docker exec "$CONTAINER" python -c "from app.core.config import get_settings; print(get_settings().gmi_enabled)" 2>/dev/null || echo "")
if [ "$gmi_enabled" != "True" ]; then
    fail "GMI_ENABLED is not True (got: '$gmi_enabled'). Set GMI_ENABLED=true in .env"
fi
ok "GMI_ENABLED=true"

# ── Phase 3: ML_DEVICE must be set to cuda ───────────────────────────────
ml_device=$(docker exec "$CONTAINER" python -c "from app.core.config import get_settings; print(get_settings().ml_device)" 2>/dev/null || echo "")
if [ "$ml_device" != "cuda" ]; then
    fail "ML_DEVICE is not 'cuda' (got: '$ml_device'). Set ML_DEVICE=cuda in .env"
fi
ok "ML_DEVICE=cuda"

# ── Phase 4: PyTorch import must succeed ─────────────────────────────────
if ! docker exec "$CONTAINER" python -c "import torch" 2>/dev/null; then
    fail "PyTorch is not importable. Check the Dockerfile.gmi build."
fi
ok "PyTorch importable"

# ── Phase 5: Actual CUDA probe ── configuration alone is NOT enough ──────
cuda_ok=$(docker exec "$CONTAINER" python -c "import torch; print(torch.cuda.is_available())" 2>/dev/null || echo "False")

if [ "$cuda_ok" != "True" ]; then
    printf "\n"
    fail "CUDA is **not available** at runtime despite ML_DEVICE=cuda and GMI_ENABLED=true.\n  Check: NVIDIA Container Toolkit, --gpus flag, driver version.\n  NEVER claim GPU success from configuration alone.\n"
fi
ok "CUDA is available (runtime check: torch.cuda.is_available())"

# ── Phase 6: Sanitised device report ─────────────────────────────────────
printf "\n--- Sanitised Device Information ---\n"
docker exec "$CONTAINER" python -c "
import torch
count = torch.cuda.device_count()
print(f'  CUDA devices: {count}')
for i in range(count):
    raw = torch.cuda.get_device_name(i)
    # Sanitise: strip bus IDs and topology data
    sanitised = raw.split(' (')[0].split(',')[0].strip()
    print(f'  Device {i}: {sanitised}')
print(f'  CUDA version: {torch.version.cuda}')
print(f'  PyTorch version: {torch.__version__}')
" 2>/dev/null || fail "Failed to query device information"

# ── Phase 7: Pipeline version probe ──────────────────────────────────────
printf "\n--- Pipeline Provenance ---\n"
docker exec "$CONTAINER" python -c "
from app.integrations.gmi.health import inspect_gmi_runtime
from app.core.config import get_settings
info = inspect_gmi_runtime(get_settings())
print(f'  Pipeline version: {info.pipeline_version}')
print(f'  GPU available:    {info.gpu_available}')
print(f'  Device count:     {info.device_count}')
if info.failure_reason:
    print(f'  Failure reason:   {info.failure_reason}')
" 2>/dev/null || warn "Unable to query GMI runtime info (non-fatal for smoke test)"

printf "\n=== GMI GPU Smoke Test PASSED ===\n\n"
