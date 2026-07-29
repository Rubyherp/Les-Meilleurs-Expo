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
│   ├── components/   Reusable UI (TopDownGrid, TimelineScrubber, etc.)
│   ├── models/       TypeScript model types
│   ├── services/     API client, analysis pipeline
│   ├── store/        Zustand state management
│   └── theme/        Shared colors and tokens
├── backend/          Python/FastAPI video analysis server
│   ├── app/          API, services, models, tasks
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

Video inference samples at 10 FPS by default. Override `SAMPLE_FPS` in
`backend/.env` only when a different speed/temporal-resolution tradeoff is
required.

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

## Tech stack

**Mobile:** React Native, Expo SDK 54, Expo Router, NativeWind/Tailwind,
Reanimated, Zustand

**Backend:** FastAPI, Celery/Redis, PostgreSQL, SQLAlchemy async, MinIO/S3,
OpenCV, YOLOv11, MediaPipe, ByteTrack, SciPy DTW

**Infra:** Docker Compose (API, worker, Postgres, Redis, MinIO)

## Collaborative AI coaching

The group-choreography switch routes each practice to the applicable coaching
specialists:

| Agent | Solo | Group | What it analyzes |
|-------|------|-------|------------------|
| Observation | Yes | Yes | Visibility, pose readability, occlusion, and track reliability |
| Timing | Yes | Yes | Reference timing offset or movement-pulse consistency |
| Formation | No | Yes | Relative spacing, crowding, and spatial match |

Group means two or more dancers. Formation feedback is intentionally omitted
from solo reports. The existing AI coach coordinates the specialist outputs and
presents one combined report.

The coaching works **deterministically without any API key** — it inspects the
analysis result metadata directly and produces data-grounded insights. Optionally
set `LLM_API_KEY` in `backend/.env` to enhance reports with an LLM:

```
LLM_API_KEY=sk-your-key
LLM_MODEL=gpt-4o-mini
LLM_TEMPERATURE=0.3
```

Coaching is triggered from the analysis results screen via a "Run coaching agents"
button, or programmatically:

```sh
curl -s -X POST "http://localhost:8000/api/v1/sessions/$SESSION_ID/coach" \
  -H "Content-Type: application/json" \
  -d '{"is_group":true,"expected_dancer_count":4}' | jq .
curl -s "http://localhost:8000/api/v1/sessions/$SESSION_ID/coach" | jq .report.agents
```

## License

MIT
