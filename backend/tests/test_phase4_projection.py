import asyncio
from uuid import UUID, uuid4

import pytest

from app.models import AnalysisJob, AnalysisResult
from app.services.detector import BoundingBox
from app.services.projection import CalibrationError, HomographyProjector, validate_calibration_points


RECTANGLE = ((0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9))


def test_rectangle_homography_maps_corners_and_center():
    projector = HomographyProjector(RECTANGLE)
    top_left = projector.project_point(0.1, 0.1, source="observed", status="active")
    center = projector.project_point(0.5, 0.5, source="observed", status="active")
    bottom_right = projector.project_point(0.9, 0.9, source="observed", status="active")

    assert (top_left["x"], top_left["y"]) == pytest.approx((0, 0))
    assert (center["x"], center["y"]) == pytest.approx((0.5, 0.5))
    assert (bottom_right["x"], bottom_right["y"]) == pytest.approx((1, 1))
    assert top_left["label"] == "R1C1"
    assert bottom_right["label"] == "R10C10"


@pytest.mark.parametrize(
    "points",
    [
        ((0, 0), (1, 0), (1, 1)),
        ((0, 0), (1, 0), (1, 1), (0, 0)),
        ((-0.1, 0), (1, 0), (1, 1), (0, 1)),
        ((0, 0), (float("nan"), 0), (1, 1), (0, 1)),
        ((0, 0), (0.5, 0), (1, 0), (0, 1)),
        ((0, 0), (1, 1), (1, 0), (0, 1)),
        ((0, 0), (0, 1), (1, 1), (1, 0)),
    ],
)
def test_invalid_calibration_is_rejected(points):
    with pytest.raises(CalibrationError):
        validate_calibration_points(points)


def test_bbox_bottom_center_projects_with_source_and_status():
    projector = HomographyProjector(((0, 0), (1, 0), (1, 1), (0, 1)), grid_columns=4, grid_rows=4)
    observed = projector.project_bbox(
        BoundingBox(20, 10, 40, 50), 100, 100, source="observed", status="active"
    )
    predicted = projector.project_bbox(
        BoundingBox(20, 10, 40, 50), 100, 100, source="predicted", status="occluded"
    )
    assert (observed["x"], observed["y"]) == pytest.approx((0.3, 0.5))
    assert observed["source"] == "observed"
    assert observed["status"] == "active"
    assert predicted["source"] == "predicted"
    assert predicted["status"] == "occluded"


def test_calibration_endpoint_and_results_404(client):
    session_id = client.post("/api/v1/sessions").json()["session_id"]
    invalid = client.post(
        f"/api/v1/sessions/{session_id}/calibration",
        json={"points": [[-0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]},
    )
    assert invalid.status_code == 422
    calibration = client.post(
        f"/api/v1/sessions/{session_id}/calibration",
        json={"points": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]},
    )
    assert calibration.status_code == 200
    assert calibration.json()["points"][0] == [0.1, 0.1]
    provisional = client.post(
        f"/api/v1/sessions/{session_id}/calibration",
        json={
            "points": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]],
            "source": "approximate",
        },
    )
    assert provisional.status_code == 200
    assert provisional.json()["source"] == "approximate"
    assert provisional.json()["status"] == "provisional"
    assert client.get(f"/api/v1/sessions/{session_id}/results").status_code == 404


def test_results_endpoint_returns_latest_persisted_metadata(client):
    session_id = UUID(client.post("/api/v1/sessions").json()["session_id"])
    session_factory = client.app.state.test_session_factory

    async def seed_result():
        async with session_factory() as db:
            job = AnalysisJob(id=uuid4(), session_id=session_id, status="completed", progress=100)
            db.add(job)
            await db.flush()
            db.add(AnalysisResult(job_id=job.id, result_metadata={"projection": {"grid": "10x10"}}))
            await db.commit()
            return job.id

    task_id = asyncio.run(seed_result())
    response = client.get(f"/api/v1/sessions/{session_id}/results")
    assert response.status_code == 200
    assert response.json()["task_id"] == str(task_id)
    assert response.json()["metadata"]["projection"]["grid"] == "10x10"
