import asyncio
import io
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.base import Base
from app.models import (
    AnalysisAttempt,
    AnalysisCache,
    AnalysisJob,
    AnalysisResult,
    AnalysisSession,
    StoredMedia,
)
from app.services.comparison import (
    ComparisonError,
    compare_result_metadata,
    deterministic_dtw,
    match_dancers,
)
from app.services.pipeline import ProgressEvent
from app.services.storage import StoredObject
from app.tasks import analysis


def point(x, y, source="observed", status="active"):
    return {"x": x, "y": y, "source": source, "status": status}


def phase4_result(trajectories, *, calibrated=True):
    frame_count = max((len(sequence) for sequence in trajectories.values()), default=0)
    frames = []
    for index in range(frame_count):
        tracks = []
        for track_id in sorted(trajectories):
            sequence = trajectories[track_id]
            value = sequence[index] if index < len(sequence) else None
            tracks.append(
                {
                    "track_id": track_id,
                    "status": value.get("status", "active") if value else "lost",
                    "bbox_source": value.get("source", "observed") if value else "none",
                    "bbox": {"x1": 0, "y1": 0, "x2": 1, "y2": 1} if value else None,
                    "top_down": value,
                }
            )
        frames.append({"frame_index": index, "timestamp_seconds": index / 10, "tracks": tracks})
    return {
        "phase": 4,
        "projection": {
            "calibration_available": calibrated,
            "calibration_required": not calibrated,
            "coordinate_space": "stage_normalized" if calibrated else None,
            "grid_columns": 10,
            "grid_rows": 10,
        },
        "sampled_frames": frames,
    }


def test_dtw_identical_and_different_lengths_are_deterministic():
    identical = deterministic_dtw([(0, 0), (0.5, 0.5), (1, 1)], [(0, 0), (0.5, 0.5), (1, 1)])
    different_lengths = deterministic_dtw([(0, 0), (0.5, 0.5), (1, 1)], [(0, 0), (1, 1)])
    assert identical.normalized_cost == pytest.approx(0)
    assert identical.alignment_path == [(0, 0), (1, 1), (2, 2)]
    assert different_lengths.valid_pair_count >= 2
    assert different_lengths.coverage == pytest.approx(1)


def test_dtw_rejects_invalid_predicted_and_low_coverage_samples():
    with pytest.raises(ComparisonError, match="No valid overlap"):
        deterministic_dtw(
            [point(0, 0, source="predicted", status="occluded")],
            [point(0, 0)],
        )
    with pytest.raises(ComparisonError, match="coverage"):
        deterministic_dtw(
            [point(0, 0), None, None, None],
            [point(0, 0), point(0, 0), point(0, 0), point(0, 0)],
            min_coverage=0.5,
        )


def test_matching_is_sorted_deterministic_and_reports_unmatched():
    matches, unmatched_reference, unmatched_attempt = match_dancers(
        {
            2: [point(0.8, 0.8), point(0.8, 0.8)],
            1: [point(0.1, 0.1), point(0.1, 0.1)],
        },
        {
            20: [point(0.1, 0.1), point(0.1, 0.1)],
            10: [point(0.8, 0.8), point(0.8, 0.8)],
            30: [point(0.5, 0.5), point(0.5, 0.5)],
        },
    )
    assert [(match.reference_id, match.attempt_id) for match in matches] == [(1, 20), (2, 10)]
    assert unmatched_reference == []
    assert unmatched_attempt == [30]


def test_comparison_rejects_coordinate_mismatch_and_missing_calibration():
    calibrated = phase4_result({1: [point(0.1, 0.1)]})
    mismatch = phase4_result({1: [point(0.1, 0.1)]})
    mismatch["projection"]["coordinate_space"] = "image_normalized"
    with pytest.raises(ComparisonError, match="stage_normalized"):
        compare_result_metadata(calibrated, mismatch)
    with pytest.raises(ComparisonError, match="no calibration"):
        compare_result_metadata(calibrated, phase4_result({1: [point(0.1, 0.1)]}, calibrated=False))


def test_comparison_result_contains_phase5_alignment_and_deviation():
    result = compare_result_metadata(
        phase4_result({1: [point(0.1, 0.1), point(0.2, 0.2)]}),
        phase4_result({8: [point(0.1, 0.1), point(0.2, 0.2)]}),
    )
    assert result["phase"] == 5
    assert result["mode"] == "comparison"
    assert result["coordinate_space"] == "stage_normalized"
    assert result["matches"][0]["reference_id"] == 1
    assert result["reference"] == result["reference_result"]
    assert result["attempt"] == result["attempt_result"]
    assert result["matches"][0]["reference_track_id"] == 1
    assert result["matches"][0]["attempt_track_id"] == 8
    assert result["matches"][0]["dtw_cost"] == pytest.approx(0)
    assert result["deviations"][0]["normalized_dtw_cost"] == pytest.approx(0)
    assert result["deviations"][0]["mean_distance"] == pytest.approx(0)
    assert result["deviations"][0]["reference_track_id"] == 1
    assert result["deviations"][0]["attempt_track_id"] == 8
    assert result["deviations"][0]["per_frame"][0] == {
        "reference_frame_index": 0,
        "attempt_frame_index": 0,
        "reference": {"x": 0.1, "y": 0.1},
        "attempt": {"x": 0.1, "y": 0.1},
        "reference_point": {"x": 0.1, "y": 0.1},
        "attempt_point": {"x": 0.1, "y": 0.1},
        "distance": 0.0,
    }


def test_comparison_media_roles_and_missing_media(client):
    session_id = client.post("/api/v1/sessions").json()["session_id"]
    assert client.post(
        f"/api/v1/sessions/{session_id}/compare", json={}
    ).status_code == 400
    client.post(
        f"/api/v1/sessions/{session_id}/calibration",
        json={"points": [[0, 0], [1, 0], [1, 1], [0, 1]]},
    )
    assert client.post(f"/api/v1/sessions/{session_id}/compare", json={}).status_code == 404

    reference = client.post(
        f"/api/v1/sessions/{session_id}/reference",
        files={"video": ("reference.mp4", b"reference", "video/mp4")},
    )
    attempt = client.post(
        f"/api/v1/sessions/{session_id}/attempt",
        files={"video": ("attempt.mp4", b"attempt", "video/mp4")},
    )
    assert reference.status_code == 201
    assert attempt.status_code == 201
    comparison = client.post(f"/api/v1/sessions/{session_id}/compare", json={})
    assert comparison.status_code == 201
    assert comparison.json()["mode"] == "comparison"
    assert comparison.json()["reference_media_id"] == reference.json()["media_id"]


class FakeComparisonStorage:
    async def upload(self, file_obj, object_key: str, content_type: str):
        return StoredObject(object_key=object_key)

    async def download(self, object_key):
        return io.BytesIO(b"not decoded by fake pipeline")


class FakeComparisonPipeline:
    def run(self, video_path, progress_callback):
        progress_callback(ProgressEvent("completed", 100, 1))
        return phase4_result({1: [point(0.2, 0.2), point(0.3, 0.3)]})


def test_comparison_task_persists_result_with_injected_pipeline(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'comparison.db'}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session_id, reference_id, attempt_id, job_id = uuid4(), uuid4(), uuid4(), uuid4()

    async def run():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as db:
            db.add(
                AnalysisSession(
                    id=session_id,
                    status="queued",
                    calibration={"points": [[0, 0], [1, 0], [1, 1], [0, 1]]},
                )
            )
            db.add_all(
                [
                    StoredMedia(
                        id=reference_id,
                        session_id=session_id,
                        role="reference",
                        object_key="reference.mp4",
                        original_filename="reference.mp4",
                        content_type="video/mp4",
                        size_bytes=1,
                        checksum_sha256="0" * 64,
                    ),
                    StoredMedia(
                        id=attempt_id,
                        session_id=session_id,
                        role="attempt",
                        object_key="attempt.mp4",
                        original_filename="attempt.mp4",
                        content_type="video/mp4",
                        size_bytes=1,
                        checksum_sha256="0" * 64,
                    ),
                ]
            )
            db.add(
                AnalysisJob(
                    id=job_id,
                    session_id=session_id,
                    mode="comparison",
                    reference_media_id=reference_id,
                    attempt_media_id=attempt_id,
                    status="pending",
                )
            )
            await db.commit()

        monkeypatch.setattr(analysis, "AsyncSessionLocal", session_factory)
        monkeypatch.setattr(analysis, "get_settings", lambda: Settings(storage_backend="local"))
        await analysis._process_job(
            job_id,
            storage=FakeComparisonStorage(),
            pipeline_factory=cast(Any, lambda settings, calibration: FakeComparisonPipeline()),
        )

        async with session_factory() as db:
            job = await db.get(AnalysisJob, job_id)
            result = (await db.execute(select(AnalysisResult).where(AnalysisResult.job_id == job_id))).scalar_one()
            attempts = (
                await db.execute(
                    select(AnalysisAttempt).where(AnalysisAttempt.job_id == job_id)
                )
            ).scalars().all()
            cache_entries = (await db.execute(select(AnalysisCache))).scalars().all()
            assert job is not None
            assert job.status == "completed"
            assert result.result_metadata["phase"] == 5
            assert result.result_metadata["mode"] == "comparison"
            assert result.result_metadata["analysis_control"]["version"] == 1
            assert len(attempts) == 2
            assert len(cache_entries) == 1
        await engine.dispose()

    asyncio.run(run())
