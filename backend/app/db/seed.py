"""Idempotent seed script that inserts two demo sessions.

Skip insertion when sessions already exist so it is safe to run on every
container start alongside ``python -m app.db.init``.

Session 1 – Mode A (single-video formation):
    * One dancer with a sinusoidal trajectory over 9 sampled frames.
    * result_metadata in the ``FramePosePipeline.run()`` Phase 4 format.

Session 2 – Mode B (reference-vs-attempt comparison with DTW):
    * Two slightly different dancer trajectories (9 frames each).
    * result_metadata in the ``compare_result_metadata()`` Phase 5 format.
    * overall_score ~0.97; realistic per-frame deviations.
"""

import asyncio
import math
import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models import AnalysisJob, AnalysisResult, AnalysisSession

# ---------------------------------------------------------------------------
# Fixed UUIDs so seed data is stable across restarts
# ---------------------------------------------------------------------------
SESSION_1_ID = uuid.UUID("ddd418e0-8893-4862-984a-5304b766805d")
SESSION_2_ID = uuid.UUID("bae46a8b-eda1-4fa1-8245-256acb7e6640")

_SESSION_IDS = [SESSION_1_ID, SESSION_2_ID]


# ---------------------------------------------------------------------------
# Helpers – Phase 4 payload construction
# ---------------------------------------------------------------------------

def _make_track(
    track_id: int,
    x: float,
    y: float,
) -> dict:
    return {
        "track_id": track_id,
        "status": "active",
        "bbox_source": "observed",
        "bbox": {
            "x1": round(max(0.0, x - 0.08), 4),
            "y1": round(max(0.0, y - 0.08), 4),
            "x2": round(min(1.0, x + 0.08), 4),
            "y2": round(min(1.0, y + 0.08), 4),
        },
        "top_down": {
            "x": round(x, 6),
            "y": round(y, 6),
            "source": "observed",
            "status": "active",
        },
        "pose": None,
    }


def _build_frames(
    track_id: int,
    *,
    frame_count: int = 9,
    fps: float = 2.0,
    x_center: float = 0.5,
    y_center: float = 0.5,
    x_amplitude: float = 0.15,
    y_amplitude: float = 0.12,
    phase_offset: float = 0.0,
) -> list[dict]:
    """Build *frame_count* sampled frames with a single sinusoidal dancer."""
    frames: list[dict] = []
    for i in range(frame_count):
        angle = 2.0 * math.pi * i / frame_count + phase_offset
        x = x_center + x_amplitude * math.sin(angle)
        y = y_center + y_amplitude * math.cos(angle)
        track = _make_track(track_id, x, y)
        frames.append(
            {
                "frame_index": i,
                "timestamp_seconds": round(i / fps, 3),
                "detections": [track],
                "tracks": [track],
            }
        )
    return frames


def _phase4_result(frames: list[dict]) -> dict:
    """Wrap a frame list in the Phase 4 pipeline output contract."""
    return {
        "video": {
            "width": 1920,
            "height": 1080,
            "fps": 30.0,
            "frame_count": len(frames),
        },
        "sampling": {"frame_stride": 1, "target_fps": None},
        "projection": {
            "calibration_available": True,
            "calibration_required": False,
            "coordinate_space": "stage_normalized",
            "grid_columns": 8,
            "grid_rows": 6,
        },
        "tracking": {
            "tracker": "bytetrack",
            "buffer_frames": 0,
            "buffer_measured_in": "processed_frames",
        },
        "sampled_frame_timestamps": [f["timestamp_seconds"] for f in frames],
        "sampled_frames": frames,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def seed() -> None:
    """Insert demo sessions if they do not already exist."""
    async with AsyncSessionLocal() as db:
        # -- Idempotency check -----------------------------------------------
        existing = await db.execute(
            select(AnalysisSession.id).where(AnalysisSession.id.in_(_SESSION_IDS))
        )
        existing_ids = {row[0] for row in existing}

        if existing_ids == set(_SESSION_IDS):
            print("Demo sessions already seeded.")
            return

        # -- Session 1: Mode A (single-video formation) ---------------------
        if SESSION_1_ID not in existing_ids:
            frames_a = _build_frames(
                track_id=1,
                x_amplitude=0.15,
                y_amplitude=0.12,
            )
            result_a = _phase4_result(frames_a)

            sess1 = AnalysisSession(
                id=SESSION_1_ID,
                status="completed",
                created_at=datetime(2025, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
            )
            db.add(sess1)

            job1 = AnalysisJob(
                id=uuid.uuid4(),
                session_id=SESSION_1_ID,
                mode="single",
                status="completed",
                progress=100,
                created_at=datetime(2025, 6, 15, 10, 0, 1, tzinfo=timezone.utc),
            )
            db.add(job1)

            await db.flush()  # materialise job1.id

            db.add(
                AnalysisResult(
                    job_id=job1.id,
                    result_metadata=result_a,
                    created_at=datetime(2025, 6, 15, 10, 0, 2, tzinfo=timezone.utc),
                )
            )

            print(f"Seeded session 1 ({SESSION_1_ID}) — Mode A")

        # -- Session 2: Mode B (comparison with DTW) ------------------------
        if SESSION_2_ID not in existing_ids:
            # Reference  – narrower range
            ref_frames = _build_frames(
                track_id=1,
                x_amplitude=0.10,
                y_amplitude=0.08,
                phase_offset=0.0,
            )
            # Attempt – wider range, slightly phase-shifted
            att_frames = _build_frames(
                track_id=1,
                x_amplitude=0.12,
                y_amplitude=0.10,
                phase_offset=0.2,
            )

            ref_result = _phase4_result(ref_frames)
            att_result = _phase4_result(att_frames)

            # Compute per-frame deviations programmatically
            per_frame: list[dict] = []
            distances: list[float] = []
            for i in range(9):
                ref_pt = ref_frames[i]["tracks"][0]["top_down"]
                att_pt = att_frames[i]["tracks"][0]["top_down"]
                d = math.hypot(
                    ref_pt["x"] - att_pt["x"],
                    ref_pt["y"] - att_pt["y"],
                )
                distances.append(d)
                entry = {
                    "reference_frame_index": i,
                    "attempt_frame_index": i,
                    "reference": ref_pt,
                    "attempt": att_pt,
                    "reference_point": ref_pt,
                    "attempt_point": att_pt,
                    "distance": round(d, 4),
                }
                per_frame.append(entry)

            mean_dist = sum(distances) / len(distances)
            max_dist = max(distances)

            alignment_path = [[i, i] for i in range(9)]

            comparison_result = {
                "phase": 5,
                "mode": "comparison",
                "coordinate_space": "stage_normalized",
                "reference": ref_result,
                "attempt": att_result,
                "reference_result": ref_result,
                "attempt_result": att_result,
                "overall_score": 0.97,
                "deviations": [
                    {
                        "reference_track_id": 1,
                        "attempt_track_id": 1,
                        "mean_distance": round(mean_dist, 6),
                        "max_distance": round(max_dist, 6),
                        "per_frame": per_frame,
                    }
                ],
                "matches": [
                    {
                        "reference_track_id": 1,
                        "attempt_track_id": 1,
                        "reference_id": 1,
                        "attempt_id": 1,
                        "alignment_path": alignment_path,
                    }
                ],
                "alignment": {
                    "method": "dtw",
                    "matches": [
                        {
                            "reference_track_id": 1,
                            "attempt_track_id": 1,
                            "reference_id": 1,
                            "attempt_id": 1,
                            "alignment_path": alignment_path,
                        }
                    ],
                },
                "unmatched_reference_ids": [],
                "unmatched_attempt_ids": [],
            }

            sess2 = AnalysisSession(
                id=SESSION_2_ID,
                status="completed",
                created_at=datetime(2025, 6, 15, 11, 0, 0, tzinfo=timezone.utc),
            )
            db.add(sess2)

            job2 = AnalysisJob(
                id=uuid.uuid4(),
                session_id=SESSION_2_ID,
                mode="comparison",
                status="completed",
                progress=100,
                created_at=datetime(2025, 6, 15, 11, 0, 1, tzinfo=timezone.utc),
            )
            db.add(job2)

            await db.flush()

            db.add(
                AnalysisResult(
                    job_id=job2.id,
                    result_metadata=comparison_result,
                    created_at=datetime(2025, 6, 15, 11, 0, 2, tzinfo=timezone.utc),
                )
            )

            print(f"Seeded session 2 ({SESSION_2_ID}) — Mode B (comparison)")

        await db.commit()
        print("Demo sessions seeded successfully.")


if __name__ == "__main__":
    asyncio.run(seed())
