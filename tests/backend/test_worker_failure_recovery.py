"""Worker failure, retry-recovery and lease tests.

Covers the role brief's durability requirements: "the deployed application
survives tested worker/network failures" —

- a worker crash mid-job (lease expiry) lets another worker reclaim the job;
- a job that exhausts ``MAX_JOB_ATTEMPTS`` fails with an explicit reason code
  instead of retrying forever;
- an unexpected error inside the analysis stack is recorded as a job failure
  (never silently dropped, never a fabricated result);
- S3 unavailability degrades to local URLs and never raises.
"""

import os

# Deterministic worker behaviour: no background thread racing these tests.
os.environ.setdefault("GHOST_RIDER_INLINE_WORKER", "false")

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend import database, s3_service, worker
from backend.api.server import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _job_bytes() -> bytes:
    return b"\xff\xd8\xff\xe0" + b"\x00" * 64


def _create_job(client, name: str) -> str:
    """Allocate, upload and finalize an upload; return the durable job id."""
    slot = client.post(
        "/v1/uploads",
        json={"filename": name, "content_type": "image/jpeg", "expected_size": 68},
    ).json()
    upload_id = slot["upload_id"]
    put = client.put(f"/v1/uploads/{upload_id}/local", content=_job_bytes(),
                     headers={"Content-Type": "image/jpeg"})
    assert put.status_code == 200, put.text
    fin = client.post(
        f"/v1/uploads/{upload_id}/finalize",
        json={"metadata": {"source_mode": "upload"}, "source_mode": "upload"},
    )
    assert fin.status_code == 200, fin.text
    return fin.json()["job_id"]


def _job_row(job_id: str) -> dict:
    with database.read_connection() as conn:
        row = conn.execute(
            "SELECT job_id, status, attempt_count, error_reason FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    return dict(row) if row else {}


# --------------------------------------------------------------------------- #
# Crash / lease recovery
# --------------------------------------------------------------------------- #

def test_expired_lease_is_reclaimed_after_worker_crash(client):
    """A job stuck in 'processing' after a worker crash becomes claimable."""
    job_id = _create_job(client, f"crash-{uuid.uuid4()}.jpg")

    # Simulate a worker that claimed the job and died: processing + stale lease.
    past = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat(timespec="seconds")
    with database.get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET status='processing', lease_expires_at=? WHERE job_id=?",
            (past, job_id),
        )

    # Claim the crashed job specifically by id (the test DB holds other jobs
    # from earlier modules; the lease/claim logic is identical either way).
    reclaimed = worker._claim_job(job_id)
    assert reclaimed is not None
    assert reclaimed["job_id"] == job_id
    assert _job_row(job_id)["status"] == "processing"  # claimed again by the new worker
    assert reclaimed["attempt_count"] == 1


def test_active_lease_is_not_stolen(client):
    """A job leased by a live worker is NOT claimable by another worker."""
    job_id = _create_job(client, f"live-{uuid.uuid4()}.jpg")

    future = (datetime.now(timezone.utc) + timedelta(seconds=worker.JOB_LEASE_SECONDS)).isoformat(timespec="seconds")
    with database.get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET status='processing', lease_expires_at=? WHERE job_id=?",
            (future, job_id),
        )

    # Nothing else is queued in this hermetic DB beyond unrelated fixture jobs,
    # so assert directly that this specific job is not claimable.
    claimed = worker._claim_job(job_id)
    assert claimed is None
    assert _job_row(job_id)["attempt_count"] == 0


def test_attempt_limit_fails_job_with_reason_code(client):
    """A job that exhausted MAX_JOB_ATTEMPTS fails explicitly, not forever."""
    job_id = _create_job(client, f"limit-{uuid.uuid4()}.jpg")

    with database.get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET attempt_count=? WHERE job_id=?",
            (worker.MAX_JOB_ATTEMPTS, job_id),
        )

    assert worker._claim_job(job_id) is None
    row = _job_row(job_id)
    assert row["status"] == "failed"
    assert row["error_reason"] == "attempt_limit_exceeded"


# --------------------------------------------------------------------------- #
# Analysis-stack failure handling
# --------------------------------------------------------------------------- #

def test_analysis_crash_fails_job_without_fabricating(client, monkeypatch):
    """An unexpected error in the analysis stack is recorded, never faked."""
    job_id = _create_job(client, f"boom-{uuid.uuid4()}.jpg")

    def _explode(*args, **kwargs):
        raise RuntimeError("simulated cv2/network failure")

    monkeypatch.setattr(worker.analysis, "decode_image", _explode)

    assert worker.process_job_by_id(job_id) is None
    row = _job_row(job_id)
    assert row["status"] == "failed"
    assert row["error_reason"] == "inference_error:RuntimeError"

    with database.read_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM samples WHERE route_id = ?", (job_id,)
        ).fetchone()["c"]
    assert count == 0  # no fabricated sample for the failed job


# --------------------------------------------------------------------------- #
# S3 degradation
# --------------------------------------------------------------------------- #

def test_s3_unavailable_falls_back_to_local_url_without_raising():
    """Upload helpers never raise; they degrade to /uploads URLs."""
    url = s3_service.upload_file_to_s3("/nonexistent/ghost.jpg", "uploads/x/ghost.jpg")
    assert url.startswith("/uploads/")

    # Presign also degrades rather than raising when nothing is configured.
    local = s3_service.get_presigned_url("uploads/x/ghost.jpg")
    assert local.startswith("/uploads/") or local.startswith("http")
