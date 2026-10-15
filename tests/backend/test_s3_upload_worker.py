"""A finalized S3 upload must be analysed from its object, not a local mirror."""

import io
import uuid
from pathlib import Path

import cv2
import numpy as np

from backend import database, s3_service, worker
from backend.queues import ensure_v1_tables


def test_s3_only_upload_is_read_before_a_job_can_complete(monkeypatch):
    database.init_db()
    ensure_v1_tables()
    upload_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    key = f"uploads/{upload_id}/road.jpg"
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO upload_slots (upload_id, object_key, filename, status, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (upload_id, key, "road.jpg", "validated", "2026-10-16", "2026-10-16"),
        )
        conn.execute(
            "INSERT INTO jobs (job_id, parent_type, parent_id, status, received_at, updated_at) "
            "VALUES (?, 'upload', ?, 'processing', ?, ?)",
            (job_id, upload_id, "2026-10-16", "2026-10-16"),
        )

    ok, encoded = cv2.imencode(".jpg", np.full((256, 256, 3), 110, np.uint8))
    assert ok

    class FakeS3:
        def get_object(self, *, Bucket, Key):
            assert (Bucket, Key) == ("test-bucket", key)
            return {"ContentLength": len(encoded), "Body": io.BytesIO(encoded.tobytes())}

    monkeypatch.setattr(s3_service, "is_s3_enabled", lambda: True)
    monkeypatch.setattr(s3_service, "get_s3_client", lambda: FakeS3())
    monkeypatch.setattr(s3_service, "get_s3_settings", lambda: {"bucket": "test-bucket"})
    monkeypatch.setattr(s3_service, "get_presigned_url", lambda object_key: "https://example.test/road.jpg")
    monkeypatch.setattr(s3_service, "to_local_path", lambda object_key: Path("nonexistent-s3-object"))

    result = worker.run_upload_inference({"job_id": job_id, "parent_id": upload_id})
    assert result is not None
    assert result.image_url == "https://example.test/road.jpg"
    assert result.quality is not None
    sample_id = worker.process_upload_job({"job_id": job_id, "parent_id": upload_id})
    assert sample_id
    with database.read_connection() as conn:
        job = conn.execute("SELECT status FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        sample = conn.execute("SELECT image_url, quality_json FROM samples WHERE sample_id = ?", (sample_id,)).fetchone()
    assert job["status"] == "partial"  # Image analysed; scoring is not implemented.
    assert sample["image_url"] == "https://example.test/road.jpg"
    assert sample["quality_json"] is not None


def test_missing_upload_object_cannot_produce_success(monkeypatch):
    monkeypatch.setattr(s3_service, "to_local_path", lambda object_key: Path("nonexistent-object"))
    upload_id = str(uuid.uuid4())
    with database.get_connection() as conn:
        conn.execute(
            "INSERT INTO upload_slots (upload_id, object_key, filename, status, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (upload_id, f"uploads/{upload_id}/road.jpg", "road.jpg", "validated", "2026-10-16", "2026-10-16"),
        )
    result = worker.run_upload_inference({"job_id": "missing-job", "parent_id": upload_id})
    assert result is None
