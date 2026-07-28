# Video Analysis Backend — Phase 5

This directory contains a production-shaped, locally runnable FastAPI backend
and frame-level video analysis pipeline. It owns no files in the existing Expo
app.

Phase 2 implements OpenCV frame sampling, lazy Ultralytics person detection,
and lazy MediaPipe Tasks PoseLandmarker inference per detected crop. Phase 3
adds Ultralytics' built-in ByteTrack adapter, application-level track records,
and conservative frame-level occlusion bookkeeping. Higher-level ML
interpretation remains future work. Phase 4 adds validated four-point
calibration, OpenCV homography projection, and normalized top-down grid
metadata. 
Phase 5 adds reference-vs-attempt comparison over those persisted Phase 4
stage trajectories; it does not rerun tracking outside the existing pipeline.

## Local setup

Requirements: Python 3.12, Docker, and Docker Compose.

```sh
cd backend
cp .env.example .env
docker compose up --build
```

The API is available at <http://localhost:8000>, and interactive docs are at
<http://localhost:8000/docs>. MinIO's console is at <http://localhost:9001>.
The API creates the configured bucket on first upload.

For a Python-only development run, use PostgreSQL/Redis/MinIO separately or
set `STORAGE_BACKEND=local` and `LOCAL_STORAGE_PATH=.storage`. Install the
package and test dependencies with:

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e '.[test]'
pytest
uvicorn app.main:app --reload
```

## Endpoints

All application routes are under `/api/v1`:

- `GET /health` — liveness response.
- `POST /sessions` — creates an analysis session.
- `POST /sessions/{session_id}/upload` — multipart upload using the `video`
  field. Accepted types are MP4, QuickTime/MOV, WebM, and Matroska/MKV. The
  response includes the `task_id`.
- `POST /sessions/{session_id}/calibration` — stores four normalized image
  points in `top-left, top-right, bottom-right, bottom-left` order.
- `POST /sessions/{session_id}/reference` and
  `POST /sessions/{session_id}/attempt` — store role-specific media without
  immediately enqueueing a single-video job.
- `POST /sessions/{session_id}/compare` — enqueues a comparison job using the
  latest media for each role, or explicit `reference_media_id` and
  `attempt_media_id` values.
- `GET /sessions/{session_id}/results` — returns the latest persisted result
  metadata, or `404` when no result exists.
- `GET /tasks/{task_id}` — returns `pending`, `queued`, `processing`,
  `completed`, or `failed`, plus progress and frame-level result metadata.

Uploads are size-limited by `MAX_UPLOAD_SIZE_BYTES` (500 MiB by default),
buffered before storage, and persisted as metadata in PostgreSQL. Actual media
is stored through the S3-compatible abstraction: MinIO in Compose or the
filesystem adapter in local mode.

## Configuration

Copy `.env.example` to `.env` and adjust:

- `DATABASE_URL` — async SQLAlchemy PostgreSQL URL.
- `REDIS_URL` — Celery broker/result backend.
- `STORAGE_BACKEND`, `LOCAL_STORAGE_PATH` — storage selection.
- `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`, and
  `S3_REGION` — MinIO or another S3-compatible service.
- `MAX_UPLOAD_SIZE_BYTES` and `ALLOWED_VIDEO_CONTENT_TYPES` — upload policy.
- `SAMPLE_FPS` or `FRAME_STRIDE` — frame sampling policy; target FPS takes
  precedence when set.
- `DETECTOR_CONFIDENCE`, `MAX_PERSONS`, and `CROP_PADDING` — detection and
  per-person pose settings.
- `YOLO_MODEL_PATH`, `POSE_MODEL_PATH`, and `ML_DEVICE` — explicit model asset
  paths and inference device.
- `TRACKER_NAME`, `TRACKER_BUFFER_SECONDS` or `TRACKER_BUFFER_FRAMES`,
  `TRACKER_IOU_THRESHOLD`, `TRACKER_HIGH_CONFIDENCE`, and
  `TRACKER_LOW_CONFIDENCE` — ByteTrack and application occlusion settings.
- `GRID_COLUMNS` and `GRID_ROWS` — top-down grid dimensions, defaulting to
  `10x10`.
- `COMPARISON_MAX_DANCERS`, `COMPARISON_MIN_COVERAGE`,
  `COMPARISON_MAX_COST`, and `COMPARISON_UNMATCHED_PENALTY` — deterministic
  matching policy. More than 24 dancers is rejected explicitly.
- `COMPARISON_INCLUDE_PREDICTED` and `COMPARISON_PREDICTED_WEIGHT` — optional
  low-weight use of occluded/predicted samples; excluded by default.

## Coaching

Coaching analysis can be triggered via `POST /sessions/{session_id}/coach` and
retrieved via `GET /sessions/{session_id}/coach`. It produces a four-phase
analysis report (detection, tracking, calibration, comparison) with strengths,
issues, and suggestions per phase.

By default, coaching uses deterministic analysis (no API calls). To enable
LLM-powered coaching with richer insights, set the following environment
variables:

- `LLM_API_KEY` — your OpenAI-compatible API key. When empty (default),
  deterministic reports are generated instead.
- `LLM_MODEL` — the model to use (default: `gpt-4o-mini`).
- `LLM_TEMPERATURE` — response creativity (default: `0.3`).

The LLM integration is optional—every phase can fall back to deterministic
analysis independently, so a missing key or a failed API call never prevents
report generation.

## Reference-vs-attempt comparison

The comparison job runs the existing Phase 4 pipeline once for the stored
reference and once for the stored attempt, sharing the session calibration,
then consumes the two JSON metadata objects. It uses Euclidean local cost DTW
with path-length normalization, coverage checks, and SciPy's Hungarian
assignment (`linear_sum_assignment`) with explicit unmatched penalties. The
persisted result has `phase: 5`, `mode: comparison`, both source results,
alignment paths, matches, unmatched IDs, deviations, and an overall score.

Only `coordinate_space: stage_normalized` results with session calibration are
comparable. Missing, lost, or `none` positions are never treated as `(0, 0)`;
predicted/occluded positions are excluded by default. This is a deterministic
trajectory baseline, not a claim of semantic identity through permanent
occlusion or mirror filtering.

## Calibration and top-down projection

Calibration is submitted as JSON such as:

```json
{"points": [[0.12, 0.10], [0.88, 0.11], [0.92, 0.90], [0.08, 0.89]]}
```

Points must be finite, normalized to `[0, 1]`, convex, non-degenerate, and in
the stated order. For each observed or conservatively predicted track, the
bottom-center of its bounding box is projected through the homography. The
continuous normalized `x`/`y` coordinates are the source of truth; `row`,
`column` (1-based), and labels such as `R5C6` are derived grid metadata.
Projection records also retain their bbox source and track status. Lost tracks
have `top_down: null`.

If a session has no calibration, frame-level detections, tracking, and poses
are still persisted, but every track has `top_down: null` and result metadata
marks calibration as required. The backend never invents a homography.

The buffer is measured in **processed frames**, not source frames. When only
`TRACKER_BUFFER_SECONDS` is set, it is converted using the effective sampled
FPS after `FRAME_STRIDE` or `SAMPLE_FPS`. Sampling means short occlusions between
processed frames are unobserved, and long gaps can exhaust the buffer sooner
than a full-frame tracker would. The app tracks people frame-by-frame only; it
does not claim robust identity through permanent occlusion or mirror filtering.

Each result frame includes `tracks` with an application `track_id`, status
(`active`, `occluded`, or `lost`), bbox source (`observed`, `predicted`, or
`none`), missed-frame count, and optional pose. Pose runs only on observed
active tracks. Predicted boxes use a conservative last-observed-box fallback;
once a track is removed after the buffer, a reappearing person receives a new
application ID.

## Model provisioning

Model assets are intentionally not included in git and are never silently
downloaded by the application. Provision them before processing videos and set
the corresponding explicit paths:

- YOLO weights, for example `models/yolo11n.pt`, at `YOLO_MODEL_PATH`.
- MediaPipe Tasks asset `pose_landmarker_lite.task` at `POSE_MODEL_PATH`.

Record the source URL, version, and SHA-256 checksum for each provisioned asset
in your deployment inventory. The application checks that both configured
files exist before the first inference; it does not verify or fetch them.

The database currently uses metadata creation at container startup. A future
phase should add versioned migrations before production deployment.
