# Optional GMI GPU Compute Deployment Lane

The default sponsor integration uses GMI **Serverless Inference** through
`GMI_API_KEY` and does not require this deployment. Use this lane only when a
GMI GPU Compute instance has actually been provisioned and the goal is to run
the local YOLO/MediaPipe pipeline on CUDA.

Deploy the CUDA-enabled analysis worker on GMI Cloud GPU compute.

## Prerequisites

1. **GMI account** — request GPU quota from your GMI account manager.
   You must retrieve the **current GPU product / template** and the matching
   **CUDA + PyTorch pairing** from the GMI console or API.
   **Do not hard-code product IDs** — they may change between quota cycles.

2. **NVIDIA Container Toolkit** installed on the host (required for GPU passthrough).

## Quickstart

```bash
# 1. Build the CUDA image
docker build -f Dockerfile.gmi -t les-meilleurs-backend:gmi .

# 2. Start GPU services
docker compose -f deploy/gmi/docker-compose.gpu.yml up -d

# 3. Run smoke checks
bash deploy/gmi/smoke-test.sh
```

## Environment Variables

| Variable | Purpose | Required |
|---|---|---|
| `GMI_ENABLED` | Must be `true` for GPU path | Yes |
| `ML_DEVICE` | Set to `cuda` | Yes |
| `GMI_REGION` | Region label copied from the GMI console | Recommended |
| `GMI_INSTANCE_LABEL` | Instance identifier for logging | Recommended |
| `GMI_GPU_LABEL` | GPU product label from GMI console | Recommended |

## Verifying the CUDA / PyTorch Pairing

After building, inspect the image to confirm the installed versions match the
GMI-provided template:

```bash
docker run --rm --gpus all les-meilleurs-backend:gmi \
    python -c "import torch; print(f'CUDA: {torch.version.cuda}'); print(f'PyTorch: {torch.__version__}')"
```

## Smoke Checks

`deploy/gmi/smoke-test.sh` performs runtime validation:

- Confirms CUDA is available (`torch.cuda.is_available()`)
- Validates device count > 0
- Reports sanitised device labels (no topology leaks)
- **Exits non-zero** when CUDA is configured but unavailable

No smoke check shall pass by configuration alone — every claim is backed by
an actual CUDA runtime probe.

## Troubleshooting

| Symptom | Likely Cause |
|---|---|
| `cuda_unavailable` | Docker runtime missing `--gpus all`; NVIDIA toolkit not installed |
| `torch_unavailable` | PyTorch not installed or CUDA wheel mismatch |
| `gmi_not_configured` | `GMI_ENABLED=false` or `ML_DEVICE=cpu` |
