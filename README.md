# Les Meilleurs

Dance practice analysis tool that transforms phone-recorded videos into
interactive top-down formation views. Record your dance practice, and the AI
pipeline detects each dancer, tracks them through frames, projects their
positions onto a calibrated stage grid, and shows you where formations drift.

## How it works

```
Record/Upload Video → YOLO Person Detection → ByteTrack Multi-Dancer Tracking
    → MediaPipe Pose Estimation → Floor Calibration → Top-Down Grid Projection
    → Interactive Formation View
```

Two modes:

- **Mode A (Single video)** — record one take, see the top-down formation.
- **Mode B (Reference vs attempt)** — compare your dance against a reference
  with DTW temporal alignment and per-dancer deviation scoring.

The app ships with **seeded demo sessions** that show real analysis results
without requiring a video upload: tap "Preview your first trend" for Mode A
formation data, or "Compare two takes" for Mode B DTW comparison.

## Project structure

```
├── app/              Expo Router screen files
├── src/
│   ├── components/   Reusable UI (TopDownGrid, CoachFeedbackView, etc.)
│   ├── models/       TypeScript types (CoachReport, AnalysisResult, etc.)
│   ├── services/     API clients (analysis, coaching, remote)
│   ├── store/        Zustand state management
│   └── theme/        Shared colors and tokens
├── backend/          Python/FastAPI video analysis server
│   ├── app/
│   │   ├── api/      Route handlers
│   │   ├── services/
│   │   │   └── coaching/  Multi-agent coaching agents
│   │   ├── tasks/    Celery async workers
│   │   └── models.py DB models
│   └── tests/        pytest test suite (38 tests)
├── app.json          Expo configuration
└── package.json      Mobile dependencies
```

## Quick start (mobile)

```sh
npm install
npx expo start
```

Scan the QR code with Expo Go on your device.

For local development, create a `.env` file in the project root:

```
EXPO_PUBLIC_API_URL=http://localhost:8000
```

Use your Mac's local IP (e.g. `http://<YOUR_MAC_IP>:8000`) instead of
`localhost` when running on a physical iPhone.

## Quick start (backend)

Requirements: Python 3.12, Docker, Apple Silicon Mac (ARM64).

```sh
cd backend
cp .env.example .env
docker compose up --build
```

The API is available at `http://localhost:8000`. Interactive docs at `/docs`.

Services: API (`:8000`), Celery worker, Postgres (`:5432`), Redis (`:6379`),
MinIO/S3 (`:9000`, console `:9001`).

### Model assets

Place these two files in `backend/models/` (automatically mounted into the
Docker container):

| File | SHA-256 |
|------|---------|
| `yolo11n.pt` | `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1` |
| `pose_landmarker_lite.task` | `59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a` |

### ARM64 compatibility

The backend is tuned for Apple Silicon Docker. Key dependency pins:

| Package | Version | Reason |
|---------|---------|--------|
| `mediapipe` | `0.10.18` | Latest with Linux ARM64 wheel |
| `opencv-python` | `4.11.0.86` | Required by ultralytics (not headless) |
| `lap` | `0.5.13` | Prebuilt ARM64 CPython 3.12 wheel |

## Connecting mobile to backend

Set `EXPO_PUBLIC_API_URL` in the `.env` file at the project root:

```sh
# iOS simulator (shares host network):
EXPO_PUBLIC_API_URL=http://localhost:8000

# Physical iPhone (must be on same WiFi):
EXPO_PUBLIC_API_URL=http://<YOUR_MAC_IP>:8000
```

When unset, the app uses local mock analysis.

## Seeding the demo data

The app fetches real analysis results from the backend for two pre-processed
demo sessions:

| Demo | Mode | Backend session | Video |
|------|------|-----------------|-------|
| Preview your first trend | A — Formation | `ddd418e0-…` | `reference.mov` (18.6s, 1 dancer) |
| Compare two takes | B — Comparison | `bae46a8b-…` | `reference.mov` vs `user-upload.mov` (0.97 score) |

To re-run the analysis against new video files:

```sh
# Mode A — single video
curl -s -X POST http://localhost:8000/api/v1/sessions | jq .session_id
# → SESSION_ID
curl -s -X POST "http://localhost:8000/api/v1/sessions/$SESSION_ID/upload" \
  -F "video=@assets/videos/your-video.mp4;type=video/mp4"

# Mode B — comparison (requires calibration)
curl -s -X POST "http://localhost:8000/api/v1/sessions/$SESSION_ID/calibration" \
  -H "Content-Type: application/json" \
  -d '{"points":[[0.08,0.1],[0.92,0.1],[0.92,0.9],[0.08,0.9]]}'
curl -s -X POST "http://localhost:8000/api/v1/sessions/$SESSION_ID/reference" \
  -F "video=@reference.mov;type=video/quicktime"
curl -s -X POST "http://localhost:8000/api/v1/sessions/$SESSION_ID/attempt" \
  -F "video=@attempt.mov;type=video/quicktime"
curl -s -X POST "http://localhost:8000/api/v1/sessions/$SESSION_ID/compare" \
  -H "Content-Type: application/json" \
  -d '{"reference_media_id":"<REF_ID>","attempt_media_id":"<ATT_ID>"}'
```

## Backend commands

```sh
pip install -e '.[test]'
pytest                    # 38 tests
uvicorn app.main:app --reload
```

## AI Coaching

After analysis completes, a multi-agent system reviews the CV results and
produces actionable practice notes:

| Agent | Analyzes |
|-------|----------|
| **Formation** | Dancer spacing, group shapes, symmetry, drift over time |
| **Timing** | Synchronization, tempo, entry/exit timing |
| **Spatial** | Individual trajectories, stage coverage, movement patterns |
| **Comparison** | Reference vs attempt gaps, deviation trends (Mode B only) |

### Default — no config needed

Without an API key, agents generate **deterministic data-driven insights**
directly from the pose/tracking/grid data. Coaching works out of the box.

### With an LLM (optional)

Add to `backend/.env`:

```sh
LLM_API_KEY=sk-your-key-here
LLM_MODEL=deepseek-chat          # or gpt-4o-mini
LLM_BASE_URL=https://api.deepseek.com   # omit for OpenAI
```

| Provider | `LLM_MODEL` | `LLM_BASE_URL` |
|----------|-------------|----------------|
| OpenAI | `gpt-4o-mini` | *(omit)* |
| DeepSeek | `deepseek-chat` | `https://api.deepseek.com` |

### API

```sh
# Trigger coaching for a session
curl -s -X POST http://localhost:8000/api/v1/sessions/$SESSION_ID/coach

# Retrieve cached report
curl -s http://localhost:8000/api/v1/sessions/$SESSION_ID/coach
```

## Tech stack

**Mobile:** React Native, Expo SDK 54, Expo Router, NativeWind/Tailwind,
Reanimated, Zustand

**Backend:** FastAPI, Celery/Redis, PostgreSQL, SQLAlchemy async, MinIO/S3,
OpenCV, YOLOv11, MediaPipe, ByteTrack, SciPy DTW

**AI Coaching:** OpenAI SDK (provider-agnostic), 4 specialized agents,
deterministic fallback mode

**Infra:** Docker Compose (API, worker, Postgres, Redis, MinIO)

## License

MIT
