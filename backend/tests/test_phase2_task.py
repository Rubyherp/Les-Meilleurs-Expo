import asyncio
import io
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.base import Base
from app.models import AnalysisJob, AnalysisResult, AnalysisSession, StoredMedia
from app.services.storage import StoredObject
from app.services.pipeline import ProgressEvent
from app.tasks import analysis


class FakeStorage:
    async def upload(self, file_obj, object_key: str, content_type: str):
        return StoredObject(object_key=object_key)

    async def download(self, object_key: str):
        return io.BytesIO(b"fake video bytes")


class FakePipeline:
    def run(self, video_path, progress_callback):
        progress_callback(ProgressEvent(stage="detecting", progress=40, sampled_frames=1))
        return {
            "video": {"fps": 10.0, "frame_count": 1, "width": 2, "height": 2, "duration_seconds": 0.1},
            "sampling": {"frame_stride": 1, "target_fps": None},
            "sampled_frames": [],
        }


def test_task_persists_pipeline_result_and_final_status(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'task.db'}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session_id = uuid4()
    media_id = uuid4()
    job_id = uuid4()

    async def setup_and_run():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as db:
            db.add(AnalysisSession(id=session_id, status="queued"))
            db.add(
                StoredMedia(
                    id=media_id,
                    session_id=session_id,
                    object_key="sessions/example/video.mp4",
                    original_filename="video.mp4",
                    content_type="video/mp4",
                    size_bytes=10,
                    checksum_sha256="0" * 64,
                )
            )
            db.add(AnalysisJob(id=job_id, session_id=session_id, media_id=media_id, status="pending"))
            await db.commit()

        monkeypatch.setattr(analysis, "AsyncSessionLocal", session_factory)
        monkeypatch.setattr(analysis, "get_settings", lambda: Settings(storage_backend="local"))
        monkeypatch.setattr(analysis, "build_pipeline", lambda settings: FakePipeline())
        await analysis._process_job(job_id, storage=FakeStorage())

        async with session_factory() as db:
            job = await db.get(AnalysisJob, job_id)
            session = await db.get(AnalysisSession, session_id)
            result = (await db.execute(select(AnalysisResult).where(AnalysisResult.job_id == job_id))).scalar_one()
            assert job is not None
            assert session is not None
            assert job.status == "completed"
            assert job.progress == 100
            assert session.status == "completed"
            assert result.result_metadata["video"]["frame_count"] == 1

        await engine.dispose()

    asyncio.run(setup_and_run())
