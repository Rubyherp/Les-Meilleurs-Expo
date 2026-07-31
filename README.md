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

After analyzing, hit "Run coaching agents" to receive a full report produced by
a team of specialist agents. Each agent owns a narrow domain and delivers
data-grounded feedback with strengths, issues, suggestions, evidence, and a
confidence score.

Three specialists are available:

| Agent | Solo | Group | Domain |
|-------|------|-------|--------|
| **Observation** | ✓ | ✓ | Camera visibility, pose readability, occlusion, tracking reliability. |
| **Timing** | ✓ | ✓ | Reference timing offset (Mode B), movement-pulse consistency, beat alignment to audio, group synchronization. |
| **Formation** | — | ✓ | Relative dancer spacing, crowding rate, spatial drift, reference formation match. |

#### How the coaching team works

The **orchestrator** (`run_coaching`) coordinates the agents as a gated pipeline:

1. **Context extraction** — structured metrics are pulled from the analysis
   result: detection coverage, pose rates, occlusion events, movement peaks,
   pair distances, DTW offsets, beat alignment, and more.
2. **Observation gates the team** — the Observation Agent runs first. If it
   can't verify video quality (confidence < 0.55, or a high-severity visibility
   / tracking / group-visibility issue exists), Timing and Formation are
   paused with a clear reason. This prevents unreliable data from producing
   misleading feedback.
3. **Remaining agents run in parallel** — if Observation passes, Timing (and
   Formation for groups) execute concurrently.

#### Deterministic-first, LLM-enhanced

Coaching works **without any API key**. The deterministic path uses pure
functions that inspect the analysis metrics directly — no model calls, no
hallucinations, always reproducible.

Optionally set an LLM API key in `backend/.env` to enhance reports. When
configured, each specialist becomes an independent LLM call:

1. The orchestrator sends each agent a compact system prompt + structured
   context string (the same metrics the deterministic path uses).
2. Each agent responds with a JSON object: summary, strengths, issues,
   suggestions, and confidence.
3. If an LLM call fails, times out, or returns invalid JSON, the agent
   **falls back to its deterministic counterpart** transparently. Users never
   see a broken report.
4. The orchestrator merges all agent outputs into a single `CoachingReport`
   with per-agent scores, evidence, coordination notes, and an overall
   summary.

This architecture means the coaching team degrades gracefully: LLMs improve
language quality and depth, but the system is fully functional without them.

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

### Coaching via API

```sh
curl -s -X POST "http://localhost:8000/api/v1/sessions/$SESSION/coach" \
  -H "Content-Type: application/json" \
  -d '{"is_group":true,"expected_dancer_count":4}' | jq .
curl -s "http://localhost:8000/api/v1/sessions/$SESSION/coach" | jq .report.agents
```

Set sponsor credentials only in the ignored `backend/.env` file:

```
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.4-nano
AGNES_API_KEY=
AGNES_BASE_URL=https://apihub.agnes-ai.com/v1
AGNES_MODEL=agnes-2.5-flash
ZO_API_KEY=
ZO_API_URL=https://api.zo.computer
GMI_API_KEY=
GMI_BASE_URL=https://api.gmi-serving.com/v1
GMI_MODEL=openai/gpt-5.4-nano
```

OpenAI uses typed specialist agents after a deterministic observation gate.
Agnes receives at most three derived JPEG evidence moments, never a raw video.
Zo export is an explicit private/unlisted action; reminder creation is separate
and opt-in. Missing or failed providers leave deterministic coaching usable and
appear as `not_configured`, `fallback`, or `failed` in report provenance.

GMI Cloud serverless inference independently audits draft coaching against only
aggregate measurements and deterministic evidence text. Its model, latency,
request ID, token counts, and fallback status appear in provenance. The separate
`backend/Dockerfile.gmi` remains an optional GPU Compute deployment lane; CUDA
success is recorded only after a real runtime probe. See
`backend/deploy/gmi/README.md` for that optional path.

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
