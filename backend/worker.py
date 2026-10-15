"""Ghost-Rider inference worker.

The worker turns received frames into stored assessment samples. It:

* consumes the shared bounded ingestion queue in
  :mod:`backend.ingestion.queue`, so live/replay frames are *dropped* under
  backpressure instead of stalling the API, and a stale result can never appear
  current;
* invokes the ML-owned analysis callable (:func:`run_inference`). Until the ML
  AI delivers a packaged artifact, this is a typed stub that returns *unknown*
  measurements - it never fabricates physical units, counts or scores;
* persists results idempotently on ``(session_id, frame_index, model_version)``
  so a retry or a duplicate submission can never double-count a frame;
* updates the session processed counter and last-processed timestamp.

The worker can run standalone for the deployed EC2 path::

    python -m backend.worker --poll 1.0

or as an in-process daemon thread during local development
(:func:`start_background_worker`).

Ownership: Backend & AWS AI
Reference: docs/final_plan.md (Sections 11.1, 11.3, 11.4)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from . import database, s3_service
from .ingestion.adapter import generate_idempotency_key
from .ingestion.queue import QueueItem, get_ingestion_queue
from .queues import ensure_v1_tables
from .schemas import (
    FrameMetadata,
    SegmentResult,
)

logger = logging.getLogger("ghost_rider.worker")

# Version tags recorded with every stored result. These change together with the
# ML artifact; the idempotency key pins the result to ``MODEL_VERSION``.
MODEL_VERSION = os.getenv("GHOST_RIDER_MODEL_VERSION", "stub-0.0.0")
FEATURE_VERSION = os.getenv("GHOST_RIDER_FEATURE_VERSION", "stub")
SCORING_VERSION = os.getenv("GHOST_RIDER_SCORING_VERSION", "stub")

# A durable upload job may be attempted this many times before it is failed with
# an explicit reason code. A processing job whose lease has expired (worker crash)
# becomes claimable again.
MAX_JOB_ATTEMPTS = int(os.getenv("GHOST_RIDER_JOB_MAX_ATTEMPTS", "3") or 3)
JOB_LEASE_SECONDS = int(os.getenv("GHOST_RIDER_JOB_LEASE_SECONDS", "300") or 300)

_worker_thread: Optional[threading.Thread] = None
_worker_lock = threading.Lock()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# Analysis adapter (ML-owned interface; stubbed for early integration)
# --------------------------------------------------------------------------- #

def run_inference(frame: QueueItem) -> Optional[SegmentResult]:
    """Invoke the road-assessment analysis for one frame.

    This is the single integration point between the backend and the ML AI. The
    real implementation will call the packaged ``quality -> geometry ->
    aggregate/distress -> reference -> score`` pipeline and return a populated
    :class:`SegmentResult`.

    The current stub returns a *typed* result whose physical measurements are all
    ``None`` (unknown). It deliberately does not invent counts, areas, scales or
    scores, so the API contract can be exercised end-to-end without fake data.
    """
    metadata: Optional[FrameMetadata] = None
    if frame.metadata_json:
        try:
            metadata = FrameMetadata.model_validate(json.loads(frame.metadata_json))
        except Exception as exc:  # pragma: no cover - malformed telemetry is non-fatal
            logger.debug("Ignoring malformed telemetry for %s:%d (%s)", frame.session_id, frame.frame_index, exc)

    image_url = s3_service.to_local_url(frame.image_path) if frame.image_path else None

    return SegmentResult(
        segment_id=frame.frame_index,
        route_id=frame.session_id,
        sample_id=None,
        image_path=frame.image_path,
        image_url=image_url,
        raw_url=image_url,
        mask_url=None,
        captured_at=metadata.captured_at if metadata else None,
        gps=metadata.gps if metadata else None,
        grade=metadata.grade if metadata else None,
        geometry_valid=False,
        observed_area=None,
        quality=None,
        metrics=None,
        evidence=None,
        score=None,
        reference=None,
        model_version=MODEL_VERSION,
        feature_version=FEATURE_VERSION,
        scoring_version=SCORING_VERSION,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        error=None,
    )


# --------------------------------------------------------------------------- #
# Idempotent persistence
# --------------------------------------------------------------------------- #

_SAMPLE_INSERT = (
    "INSERT INTO samples (sample_id, segment_id, route_id, image_path, image_url, mask_url, raw_url, "
    "captured_at, gps_json, geometry_valid, area_json, quality_json, "
    "metrics_json, evidence_json, score_json, reference_json, "
    "model_version, feature_version, scoring_version, created_at, error) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def _json_or_none(model: Any) -> Optional[str]:
    return json.dumps(model.model_dump()) if model is not None else None


def _sample_row_values(sample_id: str, result: SegmentResult) -> Tuple[Any, ...]:
    """Column values for ``_SAMPLE_INSERT`` in schema order."""
    return (
        sample_id,
        result.segment_id,
        result.route_id,
        result.image_path,
        result.image_url,
        result.mask_url,
        result.raw_url,
        result.captured_at,
        _json_or_none(result.gps),
        int(result.geometry_valid),
        _json_or_none(result.observed_area),
        _json_or_none(result.quality),
        _json_or_none(result.metrics),
        _json_or_none(result.evidence),
        _json_or_none(result.score),
        _json_or_none(result.reference),
        result.model_version,
        result.feature_version,
        result.scoring_version,
        result.created_at,
        result.error,
    )


def process_frame(frame: QueueItem) -> Optional[str]:
    """Process one queued frame exactly once.

    Returns the stored ``sample_id`` when this call performed the work, or
    ``None`` when the frame was already processed (duplicate) or inference could
    not produce a result. The processed-frame marker and the sample row are
    written in one transaction, so a crash cannot leave a half-written result.
    """
    key = generate_idempotency_key(frame.session_id, frame.frame_index, MODEL_VERSION)

    # Fast path: already processed by an earlier attempt.
    try:
        with database.read_connection() as conn:
            existing = conn.execute(
                "SELECT sample_id FROM processed_frames WHERE idempotency_key = ?", (key,)
            ).fetchone()
        if existing is not None:
            logger.debug("Frame %s:%d already processed (sample %s)", frame.session_id, frame.frame_index, existing["sample_id"])
            return None
    except Exception as exc:  # pragma: no cover - read path is best-effort
        logger.debug("Could not check processed_frames for %s: %s", key, exc)

    result = run_inference(frame)
    if result is None:
        logger.warning("Inference returned no result for %s:%d", frame.session_id, frame.frame_index)
        return None

    sample_id = str(uuid.uuid4())
    processed_at = database._now()

    with database.get_connection() as conn:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO processed_frames "
            "(idempotency_key, session_id, frame_index, model_version, sample_id, processed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (key, frame.session_id, frame.frame_index, MODEL_VERSION, sample_id, processed_at),
        )
        if cursor.rowcount == 0:
            # Another writer claimed this frame first; do not double-store.
            logger.debug("Lost idempotency race for %s", key)
            return None

        conn.execute(_SAMPLE_INSERT, _sample_row_values(sample_id, result))
        conn.execute(
            "UPDATE sessions SET processed_count = processed_count + 1, "
            "last_processed_at = ?, updated_at = ? WHERE session_id = ?",
            (processed_at, processed_at, frame.session_id),
        )

    logger.info("Persisted sample %s for session %s frame %d", sample_id, frame.session_id, frame.frame_index)
    return sample_id


# --------------------------------------------------------------------------- #
# Durable upload-job processing
# --------------------------------------------------------------------------- #

def _sha256_file(path: Any) -> Optional[str]:
    try:
        digest = hashlib.sha256()
        with Path(path).open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except Exception as exc:  # pragma: no cover - best-effort provenance
        logger.debug("Could not hash %s: %s", path, exc)
        return None


def _claim_job(job_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Atomically claim a queued (or stale-leased) durable job.

    Returns the claimed job row, or ``None`` when there is nothing claimable.
    A job that has already exhausted ``MAX_JOB_ATTEMPTS`` is failed with an
    explicit reason code instead of being retried forever.
    """
    now = _iso_now()
    lease_until = (
        datetime.now(timezone.utc) + timedelta(seconds=JOB_LEASE_SECONDS)
    ).isoformat(timespec="seconds")
    claimable = (
        "status IN ('queued','received','validated') "
        "OR (status = 'processing' AND (lease_expires_at IS NULL OR lease_expires_at < ?))"
    )
    columns = "job_id, parent_type, parent_id, status, attempt_count, metadata_json"

    with database.get_connection() as conn:
        if job_id is not None:
            row = conn.execute(
                f"SELECT {columns} FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        else:
            row = conn.execute(
                f"SELECT {columns} FROM jobs WHERE {claimable} "
                "ORDER BY received_at ASC LIMIT 1",
                (now,),
            ).fetchone()
        if row is None:
            return None

        attempts = int(row["attempt_count"] or 0)
        if attempts >= MAX_JOB_ATTEMPTS:
            conn.execute(
                "UPDATE jobs SET status='failed', error_reason=?, completed_at=?, "
                "updated_at=?, lease_expires_at=NULL WHERE job_id=?",
                ("attempt_limit_exceeded", now, now, row["job_id"]),
            )
            conn.execute(
                "INSERT INTO job_events (job_id, status, detail, at) VALUES (?, 'failed', ?, ?)",
                (row["job_id"], "attempt_limit_exceeded", now),
            )
            return None

        if job_id is not None:
            cursor = conn.execute(
                "UPDATE jobs SET status='processing', attempt_count=attempt_count+1, "
                "started_at=COALESCE(started_at, ?), updated_at=?, lease_expires_at=? "
                "WHERE job_id=? AND (" + claimable + ")",
                (now, now, lease_until, row["job_id"], now),
            )
        else:
            cursor = conn.execute(
                "UPDATE jobs SET status='processing', attempt_count=attempt_count+1, "
                "started_at=COALESCE(started_at, ?), updated_at=?, lease_expires_at=? "
                f"WHERE job_id=? AND ({claimable})",
                (now, now, lease_until, row["job_id"], now),
            )
        if cursor.rowcount == 0:
            return None
        conn.execute(
            "INSERT INTO job_events (job_id, status, detail, at) VALUES (?, 'processing', ?, ?)",
            (row["job_id"], f"attempt={attempts + 1}", now),
        )

    claimed = dict(row)
    claimed["attempt_count"] = attempts + 1
    return claimed


def _complete_job(job_id: str, sample_id: str, note: Optional[str] = None) -> None:
    now = _iso_now()
    versions = json.dumps(
        {"model": MODEL_VERSION, "feature": FEATURE_VERSION, "scoring": SCORING_VERSION}
    )
    detail = f"sample={sample_id}" + (f" {note}" if note else "")
    try:
        with database.get_connection() as conn:
            conn.execute(
                "UPDATE jobs SET status='succeeded', error_reason=NULL, completed_at=?, "
                "updated_at=?, lease_expires_at=NULL, versions_json=? WHERE job_id=?",
                (now, now, versions, job_id),
            )
            conn.execute(
                "INSERT INTO job_events (job_id, status, detail, at) VALUES (?, 'succeeded', ?, ?)",
                (job_id, detail, now),
            )
    except Exception as exc:  # pragma: no cover
        logger.exception("Could not complete job %s: %s", job_id, exc)


def _fail_job(job_id: str, reason: str) -> None:
    now = _iso_now()
    try:
        with database.get_connection() as conn:
            conn.execute(
                "UPDATE jobs SET status='failed', error_reason=?, completed_at=?, "
                "updated_at=?, lease_expires_at=NULL WHERE job_id=?",
                (reason, now, now, job_id),
            )
            conn.execute(
                "INSERT INTO job_events (job_id, status, detail, at) VALUES (?, 'failed', ?, ?)",
                (job_id, reason, now),
            )
    except Exception as exc:  # pragma: no cover
        logger.exception("Could not fail job %s: %s", job_id, exc)


def run_upload_inference(job: Dict[str, Any]) -> Optional[SegmentResult]:
    """Analyse one finalized upload.

    This is the ML integration seam for the upload path (mirrors
    :func:`run_inference` for live frames). The stub returns a typed result whose
    physical measurements are all unknown and never fabricated; provenance (the
    resolved media path/URL and capture time) is real.
    """
    metadata: Optional[FrameMetadata] = None
    if job.get("metadata_json"):
        try:
            metadata = FrameMetadata.model_validate_json(job["metadata_json"])
        except Exception as exc:
            logger.debug("Ignoring malformed metadata for job %s: %s", job.get("job_id"), exc)

    object_key = None
    try:
        with database.read_connection() as conn:
            row = conn.execute(
                "SELECT object_key FROM upload_slots WHERE upload_id = ?",
                (job.get("parent_id"),),
            ).fetchone()
        if row is not None:
            object_key = row["object_key"]
    except Exception as exc:
        logger.debug("Could not resolve object key for job %s: %s", job.get("job_id"), exc)

    image_path = None
    image_url = None
    raw_url = None
    if object_key:
        local_path = s3_service.to_local_path(object_key)
        try:
            if local_path.exists() and local_path.is_file() and local_path.stat().st_size > 0:
                image_path = str(local_path)
                image_url = s3_service.to_local_url(local_path)
                raw_url = image_url
        except Exception as exc:
            logger.debug("Could not inspect object for job %s: %s", job.get("job_id"), exc)

    return SegmentResult(
        segment_id=1,
        route_id=job.get("job_id"),
        sample_id=None,
        image_path=image_path,
        image_url=image_url,
        raw_url=raw_url,
        mask_url=None,
        captured_at=metadata.captured_at if metadata else None,
        gps=metadata.gps if metadata else None,
        grade=metadata.grade if metadata else None,
        geometry_valid=False,
        observed_area=None,
        quality=None,
        metrics=None,
        evidence=None,
        score=None,
        reference=None,
        model_version=MODEL_VERSION,
        feature_version=FEATURE_VERSION,
        scoring_version=SCORING_VERSION,
        created_at=_iso_now(),
        error=None,
    )


def process_upload_job(job: Dict[str, Any]) -> Optional[str]:
    """Process a claimed upload job exactly once; returns the stored sample id."""
    job_id = str(job["job_id"])
    key = generate_idempotency_key(job_id, 1, MODEL_VERSION)

    # Idempotent replay: a previous attempt already stored a result.
    try:
        with database.read_connection() as conn:
            existing = conn.execute(
                "SELECT sample_id FROM processed_frames WHERE idempotency_key = ?", (key,)
            ).fetchone()
        if existing is not None and existing["sample_id"]:
            _complete_job(job_id, existing["sample_id"], note="idempotent_replay")
            return existing["sample_id"]
    except Exception as exc:  # pragma: no cover
        logger.debug("Could not check processed_frames for job %s: %s", job_id, exc)

    try:
        result = run_upload_inference(job)
    except Exception as exc:
        _fail_job(job_id, f"inference_error:{type(exc).__name__}")
        logger.exception("Inference failed for job %s: %s", job_id, exc)
        return None

    if result is None:
        _fail_job(job_id, "inference_returned_no_result")
        return None

    sample_id = str(uuid.uuid4())
    now = _iso_now()
    file_sha = _sha256_file(result.image_path) if result.image_path else None

    with database.get_connection() as conn:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO processed_frames "
            "(idempotency_key, session_id, frame_index, model_version, sample_id, processed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (key, job_id, 1, MODEL_VERSION, sample_id, now),
        )
        if cursor.rowcount == 0:
            logger.debug("Lost idempotency race for job %s", job_id)
            return None
        conn.execute(_SAMPLE_INSERT, _sample_row_values(sample_id, result))

    _complete_job(job_id, sample_id, note=f"sha256={file_sha}" if file_sha else None)
    logger.info("Persisted sample %s for upload job %s", sample_id, job_id)
    return sample_id


def process_next_job() -> Optional[str]:
    """Claim and process the next durable job, if any."""
    job = _claim_job()
    if job is None:
        return None
    if job.get("parent_type") != "upload":
        _fail_job(str(job["job_id"]), f"unsupported_parent_type:{job.get('parent_type')}")
        return None
    return process_upload_job(job)


def process_job_by_id(job_id: str) -> Optional[str]:
    """Claim and process a specific job (used by tests and manual recovery)."""
    job = _claim_job(job_id)
    if job is None:
        return None
    if job.get("parent_type") != "upload":
        _fail_job(job_id, f"unsupported_parent_type:{job.get('parent_type')}")
        return None
    return process_upload_job(job)


# --------------------------------------------------------------------------- #
# Worker loop
# --------------------------------------------------------------------------- #

def worker_loop(stop_event: Optional[threading.Event] = None,
                poll_interval_sec: float = 1.0,
                idle_sleep_sec: float = 0.5) -> None:
    """Consume frames from the shared ingestion queue until stopped.

    Frames whose inference fails or returns nothing are counted as rejected;
    frames dropped because the queue was full were already counted at enqueue
    time (see :class:`~backend.ingestion.queue.BoundedIngestionQueue`).
    """
    queue = get_ingestion_queue()
    logger.info("Worker started (model=%s, poll=%.2fs)", MODEL_VERSION, poll_interval_sec)

    while stop_event is None or not stop_event.is_set():
        # Durable upload jobs are processed before best-effort live frames so a
        # finalized upload cannot starve behind a high-rate camera stream.
        try:
            if process_next_job() is not None:
                continue
        except Exception as exc:  # pragma: no cover - loop must survive job errors
            logger.exception("Worker job error: %s", exc)

        frame = queue.dequeue(timeout_sec=poll_interval_sec)
        if frame is None:
            if stop_event is not None and stop_event.is_set():
                break
            time.sleep(idle_sleep_sec)
            continue

        try:
            stored = process_frame(frame)
            if stored is None:
                queue.mark_rejected()
            else:
                queue.mark_processed()
        except Exception as exc:
            queue.mark_rejected()
            logger.exception("Worker error for %s:%d: %s", frame.session_id, frame.frame_index, exc)

    logger.info("Worker stopped")


def start_background_worker(poll_interval_sec: float = 1.0) -> threading.Thread:
    """Start the worker as a daemon thread (idempotent).

    Intended for the single-host prototype where API and worker share a process.
    Production keeps the worker as its own systemd service (see
    ``backend/scripts/ghost-rider.service``).
    """
    global _worker_thread
    with _worker_lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            return _worker_thread

        ensure_v1_tables()
        stop_event = threading.Event()
        thread = threading.Thread(
            target=worker_loop,
            kwargs={"stop_event": stop_event, "poll_interval_sec": poll_interval_sec},
            name="ghost-rider-worker",
            daemon=True,
        )
        thread.start()
        _worker_thread = thread
        logger.info("Background worker thread started")
        return thread


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    parser = argparse.ArgumentParser(description="Ghost-Rider inference worker")
    parser.add_argument("--poll", type=float, default=1.0, help="Queue poll interval in seconds")
    parser.add_argument("--idle", type=float, default=0.5, help="Idle sleep in seconds")
    args = parser.parse_args()

    ensure_v1_tables()
    stop_event = threading.Event()
    try:
        worker_loop(stop_event=stop_event, poll_interval_sec=args.poll, idle_sleep_sec=args.idle)
    except KeyboardInterrupt:  # pragma: no cover - manual shutdown
        stop_event.set()
        logger.info("Worker interrupted; exiting")


if __name__ == "__main__":  # pragma: no cover - manual start
    main()
