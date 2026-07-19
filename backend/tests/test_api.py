def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_session_creation(client):
    response = client.post("/api/v1/sessions")
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "created"
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


def test_missing_task_returns_404(client):
    response = client.get("/api/v1/tasks/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
