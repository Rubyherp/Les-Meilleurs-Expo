def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_session_creation(client):
    response = client.post("/api/v1/sessions")
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "queued"
    assert body["session_id"]
    assert body["created_at"]


def test_upload_validation_rejects_unsupported_type(client):
    session_id = client.post("/api/v1/sessions").json()["session_id"]
    response = client.post(
        f"/api/v1/sessions/{session_id}/upload",
        files={"video": ("clip.txt", b"not a video", "text/plain")},
    )
    assert response.status_code == 415
    assert "Unsupported" in response.json()["detail"]


def test_upload_returns_task_and_status_endpoint(client):
    session_id = client.post("/api/v1/sessions").json()["session_id"]
    upload = client.post(
        f"/api/v1/sessions/{session_id}/upload",
        files={"video": ("clip.mp4", b"small test payload", "video/mp4")},
    )
    assert upload.status_code == 201
    body = upload.json()
    assert body["status"] == "queued"

    status_response = client.get(f"/api/v1/tasks/{body['task_id']}")
    assert status_response.status_code == 200
    assert status_response.json() == {
        "task_id": body["task_id"],
        "session_id": session_id,
        "status": "queued",
        "progress": 0,
        "error": None,
        "result": None,
    }


def test_upload_persists_expected_dancer_count_for_routing(client):
    import asyncio
    from uuid import UUID

    from app.models import AnalysisJob

    session_id = client.post("/api/v1/sessions").json()["session_id"]
    upload = client.post(
        f"/api/v1/sessions/{session_id}/upload",
        data={"expected_dancer_count": "7"},
        files={"video": ("group.mp4", b"group payload", "video/mp4")},
    )
    assert upload.status_code == 201

    async def load_job():
        async with client.app.state.test_session_factory() as db:
            return await db.get(AnalysisJob, UUID(upload.json()["task_id"]))

    job = asyncio.run(load_job())
    assert job is not None
    assert job.expected_dancer_count == 7


def test_missing_task_returns_404(client):
    response = client.get("/api/v1/tasks/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_upload_dispatcher_failure_returns_500(client):
    """When dispatcher.enqueue fails, /upload returns 500 and persists a failed job."""
    from uuid import UUID as UUIDType

    session_id_str = client.post("/api/v1/sessions").json()["session_id"]
    session_id = UUIDType(session_id_str)
    from app.api.dependencies import get_task_dispatcher
    from tests.conftest import FailingDispatcher

    original = client.app.dependency_overrides.get(get_task_dispatcher)
    client.app.dependency_overrides[get_task_dispatcher] = lambda: FailingDispatcher()
    try:
        response = client.post(
            f"/api/v1/sessions/{session_id_str}/upload",
            files={"video": ("clip.mp4", b"test payload", "video/mp4")},
        )
    finally:
        if original is not None:
            client.app.dependency_overrides[get_task_dispatcher] = original
        else:
            del client.app.dependency_overrides[get_task_dispatcher]

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "Task queue unavailable" in detail

    async def _verify():
        from sqlalchemy import select
        from app.models import AnalysisJob, AnalysisSession

        async with client.app.state.test_session_factory() as db:
            jobs = (
                (await db.execute(select(AnalysisJob).where(AnalysisJob.session_id == session_id)))
                .scalars()
                .all()
            )
            assert len(jobs) == 1
            assert jobs[0].status == "failed"
            assert jobs[0].error_message is not None
            assert "Task queue unavailable" in jobs[0].error_message

            session = await db.get(AnalysisSession, session_id)
            assert session is not None
            assert session.status == "failed"

    import asyncio
    asyncio.run(_verify())


def test_compare_dispatcher_failure_returns_500(client):
    """When dispatcher.enqueue fails, /compare returns 500 and persists a failed job."""
    from uuid import UUID as UUIDType

    session_id_str = client.post("/api/v1/sessions").json()["session_id"]
    session_id = UUIDType(session_id_str)
    client.post(
        f"/api/v1/sessions/{session_id_str}/calibration",
        json={"points": [[0, 0], [1, 0], [1, 1], [0, 1]]},
    )
    ref = client.post(
        f"/api/v1/sessions/{session_id_str}/reference",
        files={"video": ("ref.mp4", b"reference", "video/mp4")},
    )
    att = client.post(
        f"/api/v1/sessions/{session_id_str}/attempt",
        files={"video": ("att.mp4", b"attempt", "video/mp4")},
    )
    assert ref.status_code == 201
    assert att.status_code == 201

    from app.api.dependencies import get_task_dispatcher
    from tests.conftest import FailingDispatcher

    original = client.app.dependency_overrides.get(get_task_dispatcher)
    client.app.dependency_overrides[get_task_dispatcher] = lambda: FailingDispatcher()
    try:
        response = client.post(f"/api/v1/sessions/{session_id_str}/compare", json={})
    finally:
        if original is not None:
            client.app.dependency_overrides[get_task_dispatcher] = original
        else:
            del client.app.dependency_overrides[get_task_dispatcher]

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "Task queue unavailable" in detail

    async def _verify():
        from sqlalchemy import select
        from app.models import AnalysisJob, AnalysisSession

        async with client.app.state.test_session_factory() as db:
            jobs = (
                (await db.execute(select(AnalysisJob).where(AnalysisJob.session_id == session_id)))
                .scalars()
                .all()
            )
            assert len(jobs) == 1
            assert jobs[0].status == "failed"
            assert jobs[0].error_message is not None
            assert "Task queue unavailable" in jobs[0].error_message

            session = await db.get(AnalysisSession, session_id)
            assert session is not None
            assert session.status == "failed"

    import asyncio
    asyncio.run(_verify())
