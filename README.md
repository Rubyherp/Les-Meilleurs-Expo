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

## Quick start (backend)

Requirements: Python 3.12, Docker.

```sh
cd backend
cp .env.example .env
docker compose up --build
```

The API is available at `http://localhost:8000`. Interactive docs at `/docs`.

### Model assets

Place these two files in `backend/models/` (automatically excluded from git):

| File | SHA-256 |
|------|---------|
| `yolo11n.pt` | `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1` |
| `pose_landmarker_lite.task` | `59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a` |

## Connecting mobile to backend

Set the environment variable in your Expo environment:

```sh
EXPO_PUBLIC_API_URL=http://YOUR_COMPUTER_IP:8000
```

The phone and computer must be on the same network. When this variable is unset,
the app uses local mock analysis.

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

## License

MIT
