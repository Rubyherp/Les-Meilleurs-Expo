# Les Meilleurs

Dance practice, made readable. Record your choreography on your phone, and Les
Meilleurs maps each dancer's position onto a top-down stage view so you can see
exactly where formations drift — and how to fix them.

## What you can do

### See your formations from above
Record a video of your group dancing (or pick one from your library), mark the
stage corners on screen, and the app produces an interactive top-down formation
view. You'll see every dancer's position across time — gaps, crowding, and
drift all become visible at a glance.

### Compare your take against a reference
Got a trend you're trying to nail? Pick a reference clip, then record your
attempt. The app aligns both performances in time and scores how closely you
match. See which sections you've got and which need more reps.

### Get AI coaching
After analyzing, hit "Run coaching agents" to receive data-grounded feedback:

| Agent      | Solo | Group | What it tells you |
|------------|------|-------|-------------------|
| Observation| ✓    | ✓     | Visibility, pose readability, and track quality |
| Timing     | ✓    | ✓     | Whether you're on beat with the reference |
| Formation  | —    | ✓     | Relative spacing, crowding, and spatial match |

Coaching works **without any API key** — it reads the analysis results
directly. Optionally plug in an LLM for richer reports.

### Try it now with demo data
No video needed. Two seeded demo sessions show real analysis results:
- **Preview your first trend** — a single-take formation view
- **Compare two takes** — side-by-side DTW alignment and scoring

## Screens

- **Practice** — your home tab. See session history, start a new session.
- **Analyze** — interactive formation view with scrub-able timeline, dancer
  overlays, and coaching reports.
- **Groups** — coming soon: share takes with your crew (analysis stays private
  until you choose to share).
- **Profile** — your stats and streak.

## Two analysis modes

**Mode A — Formation:** One video in, formation map out. Perfect for quick
check-ins after rehearsal.

**Mode B — Comparison:** Reference video + your attempt. The analyzer aligns
both performances with DTW, then scores per-dancer deviation. Great for trend
practice and before/after comparisons.

---

## Quick start (mobile)

```sh
npm install
npx expo start
```

Scan the QR code with Expo Go on your device.

## Connecting to the backend

Create a `.env` file in the project root:

```
EXPO_PUBLIC_API_URL=http://localhost:8000
```

For iOS simulator, use `localhost`. For a physical iPhone on the same WiFi, use
your Mac's local IP (e.g. `http://192.168.1.5:8000`).

When `EXPO_PUBLIC_API_URL` is unset, the app runs with local mock analysis.

## Quick start (backend)

Requirements: Python 3.12, Docker, Apple Silicon Mac.

```sh
cd backend
cp .env.example .env
docker compose up --build
```

The API is at `http://localhost:8000`. Interactive docs at `/docs`.

Services: API (`:8000`), Celery worker, Postgres (`:5432`), Redis (`:6379`),
MinIO/S3 (`:9000`, console `:9001`).

### Model assets

Place these in `backend/models/` (mounted into the Docker container):

| File | SHA-256 |
|------|---------|
| `yolo11n.pt` | `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1` |
| `pose_landmarker_lite.task` | `59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a` |

## Seeding demo data

The app fetches pre-processed analysis results for two demo sessions:

| Demo | Mode | Backend session | Video |
|------|------|-----------------|-------|
| Preview your first trend | A — Formation | `ddd418e0-…` | `reference.mov` (18.6s, 1 dancer) |
| Compare two takes | B — Comparison | `bae46a8b-…` | `reference.mov` vs `user-upload.mov` |

To re-run analysis against new videos:

```sh
# Mode A — single video
SESSION=$(curl -s -X POST http://localhost:8000/api/v1/sessions | jq -r .session_id)
curl -s -X POST "http://localhost:8000/api/v1/sessions/$SESSION/upload" \
  -F "video=@your-video.mp4;type=video/mp4"

# Mode B — comparison
curl -s -X POST "http://localhost:8000/api/v1/sessions/$SESSION/calibration" \
  -H "Content-Type: application/json" \
  -d '{"points":[[0.08,0.1],[0.92,0.1],[0.92,0.9],[0.08,0.9]]}'
curl -s -X POST "http://localhost:8000/api/v1/sessions/$SESSION/reference" \
  -F "video=@reference.mov;type=video/quicktime"
curl -s -X POST "http://localhost:8000/api/v1/sessions/$SESSION/attempt" \
  -F "video=@attempt.mov;type=video/quicktime"
curl -s -X POST "http://localhost:8000/api/v1/sessions/$SESSION/compare" \
  -H "Content-Type: application/json" \
  -d '{"reference_media_id":"<REF_ID>","attempt_media_id":"<ATT_ID>"}'
```

### Coaching via API

```sh
curl -s -X POST "http://localhost:8000/api/v1/sessions/$SESSION/coach" \
  -H "Content-Type: application/json" \
  -d '{"is_group":true,"expected_dancer_count":4}' | jq .
curl -s "http://localhost:8000/api/v1/sessions/$SESSION/coach" | jq .report.agents
```

Optionally set these in `backend/.env` for LLM-enhanced coaching reports:

```
LLM_API_KEY=sk-your-key
LLM_MODEL=gpt-4o-mini
LLM_TEMPERATURE=0.3
```

## Pipeline

```
Record/Upload → YOLO Person Detection → ByteTrack Multi-Dancer Tracking
    → Floor Calibration → Top-Down Grid Projection → Interactive Formation View
    → (Mode B) DTW Alignment + Deviation Scoring → Coaching Report
```

## Project structure

```
├── app/              Expo Router screens
├── src/
│   ├── components/   Reusable UI (TopDownGrid, TimelineScrubber, etc.)
│   ├── models/       TypeScript types
│   ├── services/     API client, analysis pipeline
│   ├── store/        Zustand state management
│   └── theme/        Shared colors and tokens
├── backend/          Python/FastAPI video analysis server
│   ├── app/          API, services, models, tasks
│   └── tests/        pytest test suite (38 tests)
├── app.json          Expo configuration
└── package.json      Mobile dependencies
```

## Tech stack

**Mobile:** React Native, Expo SDK 54, Expo Router, NativeWind/Tailwind,
Reanimated, Zustand

**Backend:** FastAPI, Celery/Redis, PostgreSQL, SQLAlchemy async, MinIO/S3,
OpenCV, YOLOv11, ByteTrack, SciPy DTW

**Infra:** Docker Compose (API, worker, Postgres, Redis, MinIO)

## Backend notes

Video inference samples at 10 FPS by default. Override `SAMPLE_FPS` in
`backend/.env` only when a different speed/resolution tradeoff is needed.

### ARM64 compatibility

| Package | Version | Reason |
|---------|---------|--------|
| `mediapipe` | `0.10.18` | Latest with Linux ARM64 wheel |
| `opencv-python` | `4.11.0.86` | Required by ultralytics (not headless) |
| `lap` | `0.5.13` | Prebuilt ARM64 CPython 3.12 wheel |

## License

MIT
