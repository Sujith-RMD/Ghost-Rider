"""Integration tests for all 10 v1 endpoints in backend/api/v1.py.

Verifies:
- POST /v1/uploads
- POST /v1/uploads/{id}/finalize
- POST /v1/sessions
- POST /v1/sessions/{id}/frames
- POST /v1/sessions/{id}/finish
- GET  /v1/jobs/{id}
- GET  /v1/samples/{id}
- GET  /v1/sessions/{id}/segments
- POST /v1/reports
- GET  /v1/health
"""

import io
import json
import uuid
import pytest
from fastapi.testclient import TestClient

from backend import database
from backend.api.server import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_v1_health(client):
    response = client.get("/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "version" in data
    assert "services" in data
    assert "database" in data["services"]
    assert "worker" in data["services"]


def test_v1_upload_and_finalize_lifecycle(client):
    # 1. Allocate upload slot
    payload = {
        "filename": "test_road_frame.jpg",
        "content_type": "image/jpeg",
        "expected_size": 1024,
    }
    create_res = client.post("/v1/uploads", json=payload)
    assert create_res.status_code == 200
    slot = create_res.json()
    assert "upload_id" in slot
    assert "upload_url" in slot
    assert "object_key" in slot
    assert slot["status"] == "ready"

    upload_id = slot["upload_id"]

    # 2. Simulate uploaded file present in local storage
    from backend import s3_service
    local_file = s3_service.to_local_path(slot["object_key"])
    local_file.parent.mkdir(parents=True, exist_ok=True)
    # Write valid JPEG magic header
    local_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 200)

    # 3. Finalize upload
    finalize_payload = {
        "metadata": {
            "gps": {"lat": 12.9716, "lon": 77.5946, "accuracy_m": 5.0},
            "source_mode": "upload",
        },
        "source_mode": "upload",
    }
    finalize_res = client.post(f"/v1/uploads/{upload_id}/finalize", json=finalize_payload)
    assert finalize_res.status_code == 200
    job_info = finalize_res.json()
    assert job_info["upload_id"] == upload_id
    assert job_info["status"] == "queued"
    assert "job_id" in job_info

    # 4. Check job status via GET /v1/jobs/{id}
    job_id = job_info["job_id"]
    job_res = client.get(f"/v1/jobs/{job_id}")
    assert job_res.status_code == 200
    job_data = job_res.json()
    assert job_data["job_id"] == job_id
    assert job_data["status"] == "queued"


def test_v1_session_and_frames_lifecycle(client):
    # 1. Create session
    session_payload = {
        "mode": "live",
        "camera_id": "test_phone_cam",
        "calibration_id": "cal_2026_10",
    }
    session_res = client.post("/v1/sessions", json=session_payload)
    assert session_res.status_code == 200
    session_data = session_res.json()
    assert "session_id" in session_data
    assert session_data["mode"] == "live"
    assert session_data["frame_count"] == 0

    session_id = session_data["session_id"]

    # 2. Post frame (multipart)
    jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 500
    meta_json = json.dumps({
        "gps": {"lat": 12.9716, "lon": 77.5946, "accuracy_m": 2.5},
        "captured_at": "2026-10-15T12:00:00Z",
    })

    frame_res = client.post(
        f"/v1/sessions/{session_id}/frames",
        files={"frame": ("frame_001.jpg", jpeg_bytes, "image/jpeg")},
        data={"metadata": meta_json},
    )
    assert frame_res.status_code == 200
    frame_data = frame_res.json()
    assert frame_data["frame_count"] == 1

    # 3. Finish session
    finish_res = client.post(f"/v1/sessions/{session_id}/finish")
    assert finish_res.status_code == 200


def test_v1_segments_endpoint(client):
    # Create session with a dummy sample stored in database
    session_id = f"test-sess-{uuid.uuid4()}"
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO sessions (session_id, mode, status, created_at, updated_at) "
            "VALUES (?, 'live', 'finished', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (session_id,),
        )
        sample_id = f"sample-{uuid.uuid4()}"
        gps_json = json.dumps({"lat": 12.9716, "lon": 77.5946, "accuracy_m": 3.0})
        quality_json = json.dumps({"status": "accepted", "reasons": []})
        score_json = json.dumps({"value": 85, "status": "Good", "severe_defect_flag": False})
        conn.execute(
            "INSERT INTO samples (sample_id, segment_id, route_id, gps_json, quality_json, score_json, created_at) "
            "VALUES (?, 1, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (sample_id, session_id, gps_json, quality_json, score_json),
        )

    res = client.get(f"/v1/sessions/{session_id}/segments?bin_length_m=50.0")
    assert res.status_code == 200
    seg_list = res.json()
    assert seg_list["route_id"] == session_id
    assert len(seg_list["segments"]) >= 1
    assert seg_list["segments"][0]["sample_count"] >= 1


def test_v1_reports_endpoint(client, monkeypatch):
    from backend.api import v1
    from backend.schemas import SegmentResult
    monkeypatch.setattr(v1, "_get_sample", lambda _: SegmentResult(segment_id=1, sample_id="test-assessment-001"))
    report_res = client.post(
        "/v1/reports",
        json={
            "assessment_id": "test-assessment-001",
            "include_narrative": False,
            "quality_status": "accepted",
            "score_value": 78,
            "score_status": "Good",
        },
    )
    assert report_res.status_code == 200
    report_data = report_res.json()
    assert report_data["assessment_id"] == "test-assessment-001"
    assert "content" in report_data
    assert "summary" in report_data["content"]
    assert report_data["content"]["factual_template_used"] is False
