"""End-to-end test for the upload -> durable job -> sample slice.

Proves the acceptance path from the role brief: a new file is uploaded
privately, validated, processed exactly once despite retries, stored with full
versions and evidence, and returned through the API without fabricated fields.

The inline worker is disabled so the durable-job path is exercised
deterministically via ``worker.process_job_by_id`` / ``process_frame``.
"""

import os
import time
import uuid
import cv2
import numpy as np

# Keep the durable-job test deterministic: no background thread racing the test
# for the same job. Must be set before the app lifespan runs.
os.environ.setdefault("GHOST_RIDER_INLINE_WORKER", "false")

import pytest
from fastapi.testclient import TestClient

from backend import database, worker
from backend.api.server import app
from backend.ingestion.queue import QueueItem
from backend.queues import ensure_v1_tables


def _jpeg_bytes(size_pad: int = 64) -> bytes:
    """A decodable road-like image, rather than a JPEG header alone."""
    image = np.random.default_rng(42).integers(60, 180, (256, 256, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return encoded.tobytes()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _allocate_upload(client, name: str = "slice_road.jpg") -> dict:
    response = client.post(
        "/v1/uploads",
        json={"filename": name, "content_type": "image/jpeg", "expected_size": len(_jpeg_bytes())},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _put_local(client, upload_id: str, body: bytes, content_type: str = "image/jpeg"):
    return client.put(
        f"/v1/uploads/{upload_id}/local",
        content=body,
        headers={"Content-Type": content_type},
    )


def _finalize(client, upload_id: str) -> dict:
    response = client.post(
        f"/v1/uploads/{upload_id}/finalize",
        json={
            "metadata": {
                "gps": {"lat": 12.9716, "lon": 77.5946, "accuracy_m": 4.0, "simulated": False},
                "captured_at": "2026-10-16T09:15:00+00:00",
                "source_mode": "upload",
            },
            "source_mode": "upload",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _wait_terminal(client, job_id: str, timeout: float = 10.0) -> dict:
    """Return the terminal job state, nudging an explicit worker if needed."""
    deadline = time.time() + timeout
    job = client.get(f"/v1/jobs/{job_id}").json()
    while job["status"] not in ("succeeded", "partial", "failed") and time.time() < deadline:
        worker.process_job_by_id(job_id)
        time.sleep(0.1)
        job = client.get(f"/v1/jobs/{job_id}").json()
    return job


def test_upload_job_sample_slice(client):
    slot = _allocate_upload(client)
    upload_id = slot["upload_id"]
    assert slot["status"] == "ready"
    assert slot["object_key"].startswith("uploads/")
    assert slot["upload_url"].endswith(f"/v1/uploads/{upload_id}/local")

    # Upload the bytes through the bounded local path.
    image = _jpeg_bytes()
    put = _put_local(client, upload_id, image)
    assert put.status_code == 200, put.text
    stored = put.json()
    assert stored["status"] == "uploaded"
    assert stored["size_bytes"] == len(image)
    assert len(stored["sha256"]) == 64

    # Finalize: validates the object and creates a durable queued job.
    fin = _finalize(client, upload_id)
    assert fin["status"] == "queued"
    job_id = fin["job_id"]
    assert job_id

    queued = client.get(f"/v1/jobs/{job_id}").json()
    assert queued["status"] in ("received", "validated", "queued")
    assert queued["result_sample_id"] is None

    # Process (as the deployed worker would).
    job = _wait_terminal(client, job_id)
    assert job["status"] == "partial", job
    sample_id = job["result_sample_id"]
    assert sample_id
    assert job["attempt_count"] == 1
    assert job["versions"]["model"]

    # Sample is returned through the API with real provenance and honest nulls.
    response = client.get(f"/v1/samples/{sample_id}")
    assert response.status_code == 200, response.text
    sample = response.json()
    assert sample["sample_id"] == sample_id
    assert sample["model_version"]
    # No fabricated physics: uncalibrated geometry stays unknown.
    assert sample["geometry_valid"] is False
    assert sample["observed_area"] is None or sample["observed_area"]["observed_area_m2"] is None
    assert sample["metrics"] is None or sample["metrics"]["chip_density_per_m2"] is None
    assert sample["score"] is None
    assert sample["quality"] is not None
    assert sample["distress_detection"]["status"] == "unavailable"
    assert sample["distress_detection"]["reason"] == "weights_not_found"
    # Capture time and GPS are preserved from the finalize telemetry.
    assert sample["captured_at"] == "2026-10-16T09:15:00+00:00"
    assert sample["gps"]["lat"] == 12.9716
    assert sample["gps"]["accuracy_m"] == 4.0


def test_job_processing_is_idempotent(client):
    slot = _allocate_upload(client, name="idempotent.jpg")
    upload_id = slot["upload_id"]
    assert _put_local(client, upload_id, _jpeg_bytes()).status_code == 200
    job_id = _finalize(client, upload_id)["job_id"]

    terminal = _wait_terminal(client, job_id)
    assert terminal["status"] == "partial"
    sample_id = terminal["result_sample_id"]

    # A second explicit attempt must not create another sample.
    assert worker.process_job_by_id(job_id) is None
    with database.read_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM samples WHERE route_id = ?", (job_id,)
        ).fetchone()["c"]
    assert count == 1
    assert client.get(f"/v1/jobs/{job_id}").json()["result_sample_id"] == sample_id


def test_process_frame_stores_single_sample():
    """Live/replay frames persist once, keyed on (session, frame, model)."""
    database.init_db()
    ensure_v1_tables()
    session_id = f"idem-{uuid.uuid4()}"
    item = QueueItem(
        session_id=session_id,
        frame_index=1,
        source_mode="live",
        filename="frame_000001.jpg",
        received_at="2026-10-16T09:15:00+00:00",
        monotonic_received_ns=1,
    )
    first = worker.process_frame(item)
    second = worker.process_frame(item)
    assert first is not None
    assert second is None
    with database.read_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM samples WHERE route_id = ?", (session_id,)
        ).fetchone()["c"]
    assert count == 1


def test_finalize_without_object_is_rejected(client):
    slot = _allocate_upload(client, name="missing.jpg")
    response = client.post(
        f"/v1/uploads/{slot['upload_id']}/finalize",
        json={"metadata": {"source_mode": "upload"}},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "object_not_found"


def test_upload_rejects_non_image_bytes(client):
    slot = _allocate_upload(client, name="not_an_image.jpg")
    response = _put_local(client, slot["upload_id"], b"this is not an image")
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "invalid_image"
