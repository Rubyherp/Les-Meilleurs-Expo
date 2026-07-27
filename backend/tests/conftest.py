import asyncio
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.dependencies import get_storage_service, get_task_dispatcher
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.services.storage import StoredObject


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return compiler.visit_JSON(type_, **kw)


class FakeStorage:
    async def upload(self, file_obj, object_key: str, content_type: str) -> StoredObject:
        return StoredObject(object_key=object_key)


class FakeDispatcher:
    def enqueue(self, job_id) -> str:
        return f"celery-{job_id}"


class FailingDispatcher:
    def enqueue(self, job_id):
        msg = "Task queue unavailable"
        raise RuntimeError(msg)


@pytest.fixture
def client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(setup())

    async def override_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_storage_service] = lambda: FakeStorage()
    app.dependency_overrides[get_task_dispatcher] = lambda: FakeDispatcher()
    app.state.test_session_factory = session_factory
    with TestClient(app) as test_client:
        yield test_client
    del app.state.test_session_factory
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())
