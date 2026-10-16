"""Ghost-Rider inference worker.

The worker turns received frames into stored assessment samples. It:

* consumes the shared bounded ingestion queue in
  :mod:`backend.ingestion.queue`, so live/replay frames are *dropped* under
  backpressure instead of stalling the API, and a stale result can never appear
  current;
* invokes the real ML analysis pipeline (quality gate → scale → aggregate
  measurement) through :mod:`backend.analysis`, which translates the ML-owned
  modules into the API contract. Frames are measured **unscaled** (no
  calibration store exists yet), so physical units stay ``null`` rather than
  being fabricated; counts and ratios are real;
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
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from . import analysis, database, s3_service
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
# ``measure-v1`` / ``quality-v1`` are the ML modules' own config versions
# (``MeasurementConfig.config_version`` / ``QualityPolicy.policy_version``);
# results stored by the earlier ``stub-*`` tags are intentionally not
# recomputed — version-pinned idempotency keeps old rows auditable.
MODEL_VERSION = os.getenv("GHOST_RIDER_MODEL_VERSION", "measure-v1")
FEATURE_VERSION = os.getenv("GHOST_RIDER_FEATURE_VERSION", "quality-v1")
SCORING_VERSION = os.getenv("GHOST_RIDER_SCORING_VERSION", "not-implemented")

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

def _measure_frame_from_path(image_path: Optional[str],
                             metadata: Optional[FrameMetadata]) -> Optional[Dict[str, Any]]:
    """Decode and analyse the image at ``image_path``.

    Returns the :func:`backend.analysis.measure_frame` outcome, or ``None``
    when there is no readable image (the caller then stores an honest
    all-unknown result).
    """
    if not image_path:
        return None
    image = analysis.decode_image(image_path)
    if image is None:
        logger.debug("No decodable image at %s; recording unknown measurements.", image_path)
        return None
    return analysis.measure_frame(image, metadata)


def run_inference(frame: QueueItem, *, sample_id: Optional[str] = None,
                  received_at: Optional[str] = None) -> Optional[SegmentResult]:
    """Invoke the road-assessment analysis for one live/replay frame.

    This is the single integration point between the backend and the ML AI's
    modules: the image is decoded and run through the real quality gate,
    tiled aggregate measurement and distress path (:mod:`backend.analysis`).
    Physical measurements stay ``None`` while the frame is uncalibrated;
    counts, ratios and quality verdicts are real. When ``sample_id`` is
    supplied the canonical record (final plan §11.5) is attached too.
    """
    metadata: Optional[FrameMetadata] = None
    if frame.metadata_json:
        try:
            metadata = FrameMetadata.model_validate(json.loads(frame.metadata_json))
        except Exception as exc:  # pragma: no cover - malformed telemetry is non-fatal
            logger.debug("Ignoring malformed telemetry for %s:%d (%s)", frame.session_id, frame.frame_index, exc)

    image_path = frame.image_path or None
    image_url = s3_service.to_local_url(frame.image_path) if frame.image_path else None
    measured = _measure_frame_from_path(image_path, metadata)

    result = analysis.build_segment_result(
        segment_id=frame.frame_index,
        route_id=frame.session_id,
        metadata=metadata,
        image_path=image_path,
        image_url=image_url,
        raw_url=image_url,
        model_version=MODEL_VERSION,
        feature_version=FEATURE_VERSION,
        scoring_version=SCORING_VERSION,
        sample_id=sample_id,
        measured=measured,
    )

    if sample_id and image_path:
        result.canonical = analysis.build_canonical_record(
            sample_id=sample_id,
            route_id=frame.session_id,
            sequence_id=frame.frame_index,
            metadata=metadata,
            measured=measured,
            image_path=image_path,
            file_sha256=_sha256_file(image_path),
            received_at=received_at or frame.received_at,
            model_version=MODEL_VERSION,
            feature_version=FEATURE_VERSION,
            scoring_version=SCORING_VERSION,
        )
    return result


# --------------------------------------------------------------------------- #
# Idempotent persistence
# --------------------------------------------------------------------------- #

_SAMPLE_INSERT = (
    "INSERT INTO samples (sample_id, segment_id, route_id, image_path, image_url, mask_url, raw_url, "
    "captured_at, gps_json, geometry_valid, area_json, quality_json, "
    "metrics_json, evidence_json, score_json, reference_json, "
    "model_version, feature_version, scoring_version, created_at, error, canonical_json) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
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
        _json_or_none(result.canonical),
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

    # The sample id is allocated BEFORE inference so the canonical record can
    # carry the same identity the row is stored under.
    sample_id = str(uuid.uuid4())
    result = run_inference(frame, sample_id=sample_id, received_at=frame.received_at)
    if result is None:
        logger.warning("Inference returned no result for %s:%d", frame.session_id, frame.frame_index)
        return None

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
    columns = "job_id, parent_type, parent_id, status, attempt_count, received_at, metadata_json"

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


def _complete_job(job_id: str, sample_id: str, note: Optional[str] = None,
                  status: str = "succeeded") -> None:
    now = _iso_now()
    versions = json.dumps(
        {"model": MODEL_VERSION, "feature": FEATURE_VERSION, "scoring": SCORING_VERSION}
    )
    detail = f"sample={sample_id}" + (f" {note}" if note else "")
    try:
        with database.get_connection() as conn:
            conn.execute(
                "UPDATE jobs SET status=?, error_reason=NULL, completed_at=?, "
                "updated_at=?, lease_expires_at=NULL, versions_json=? WHERE job_id=?",
                (status, now, now, versions, job_id),
            )
            conn.execute(
                "INSERT INTO job_events (job_id, status, detail, at) VALUES (?, ?, ?, ?)",
                (job_id, status, detail, now),
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


def run_upload_inference(job: Dict[str, Any], *, sample_id: Optional[str] = None,
                         received_at: Optional[str] = None,
                         file_sha256: Optional[str] = None) -> Optional[SegmentResult]:
    """Analyse one finalized upload.

    This is the ML integration seam for the upload path (mirrors
    :func:`run_inference` for live frames): the resolved local object is run
    through the real quality gate, tiled measurement and distress path.
    Provenance (the resolved media path/URL and capture time) is real; physical
    units stay ``None`` while the frame is uncalibrated. When ``sample_id`` is
    supplied the canonical record (final plan §11.5) is attached too.
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
    measured = None
    if object_key:
        if s3_service.is_s3_enabled():
            client = s3_service.get_s3_client()
            if client is None:
                raise RuntimeError("s3_client_unavailable")
            response = client.get_object(
                Bucket=s3_service.get_s3_settings()["bucket"], Key=object_key
            )
            max_bytes = max(1, int(os.getenv("MAX_UPLOAD_MB", "25") or 25)) * 1024 * 1024
            body = response["Body"]
            try:
                if int(response.get("ContentLength") or 0) > max_bytes:
                    raise ValueError("upload_too_large")
                with tempfile.TemporaryDirectory() as private_dir:
                    temporary = Path(private_dir) / "upload.jpg"
                    total = 0
                    with temporary.open("wb") as target:
                        while chunk := body.read(1024 * 1024):
                            total += len(chunk)
                            if total > max_bytes:
                                raise ValueError("upload_too_large")
                            target.write(chunk)
                    # Hash while the private copy still exists, then measure.
                    file_sha256 = file_sha256 or _sha256_file(str(temporary))
                    measured = _measure_frame_from_path(str(temporary), metadata)
            finally:
                body.close()
            # The canonical record's original URI is the S3 object key; the
            # private temp copy is deleted with the context manager above.
            image_path = object_key
            signed_url = s3_service.get_presigned_url(object_key)
            image_url = signed_url if signed_url and not signed_url.startswith("/uploads/") else None
            raw_url = image_url
        else:
            local_path = s3_service.to_local_path(object_key)
            if local_path.exists() and local_path.is_file() and local_path.stat().st_size > 0:
                image_path = str(local_path)
                image_url = s3_service.to_local_url(local_path)
                raw_url = image_url
                measured = _measure_frame_from_path(image_path, metadata)

    if measured is None:
        return None

    result = analysis.build_segment_result(
        segment_id=1,
        route_id=job.get("job_id"),
        metadata=metadata,
        image_path=image_path,
        image_url=image_url,
        raw_url=raw_url,
        model_version=MODEL_VERSION,
        feature_version=FEATURE_VERSION,
        scoring_version=SCORING_VERSION,
        sample_id=sample_id,
        measured=measured,
    )

    if sample_id and image_path:
        result.canonical = analysis.build_canonical_record(
            sample_id=sample_id,
            route_id=job.get("job_id"),
            sequence_id=1,
            metadata=metadata,
            measured=measured,
            image_path=image_path,
            file_sha256=file_sha256 or _sha256_file(image_path),
            received_at=received_at or job.get("received_at"),
            model_version=MODEL_VERSION,
            feature_version=FEATURE_VERSION,
            scoring_version=SCORING_VERSION,
        )
    return result


def _assessment_job_status(score: Optional[Dict[str, Any]], quality: Optional[Dict[str, Any]]) -> str:
    return "succeeded" if (
        score and score.get("value") is not None
        and score.get("status") in {"Good", "Bad"}
        and quality and quality.get("status") == "accepted"
    ) else "partial"


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
            with database.read_connection() as conn:
                row = conn.execute(
                "SELECT score_json, quality_json FROM samples WHERE sample_id = ?", (existing["sample_id"],)
                ).fetchone()
            prior_score = json.loads(row["score_json"]) if row and row["score_json"] else None
            prior_quality = json.loads(row["quality_json"]) if row and row["quality_json"] else None
            prior_status = _assessment_job_status(prior_score, prior_quality)
            _complete_job(job_id, existing["sample_id"], note="idempotent_replay", status=prior_status)
            return existing["sample_id"]
    except Exception as exc:  # pragma: no cover
        logger.debug("Could not check processed_frames for job %s: %s", job_id, exc)

    # The sample id is allocated BEFORE inference so the canonical record can
    # carry the same identity the row is stored under.
    sample_id = str(uuid.uuid4())

    try:
        result = run_upload_inference(
            job,
            sample_id=sample_id,
            received_at=job.get("received_at"),
        )
    except Exception as exc:
        _fail_job(job_id, f"inference_error:{type(exc).__name__}")
        logger.exception("Inference failed for job %s: %s", job_id, exc)
        return None

    if result is None:
        _fail_job(job_id, "inference_returned_no_result")
        return None

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

    status = _assessment_job_status(
        result.score.model_dump() if result.score else None,
        result.quality.model_dump() if result.quality else None,
    )
    _complete_job(job_id, sample_id, note=f"sha256={file_sha}" if file_sha else None, status=status)
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

        stored = None
        try:
            stored = process_frame(frame)
            if stored is None:
                queue.mark_rejected()
            else:
                queue.mark_processed()
        except Exception as exc:
            queue.mark_rejected()
            logger.exception("Worker error for %s:%d: %s", frame.session_id, frame.frame_index, exc)
        if stored is None:
            try:
                with database.get_connection() as conn:
                    conn.execute("UPDATE sessions SET rejected_count=rejected_count+1 WHERE session_id=?",
                                 (frame.session_id,))
            except Exception:
                logger.exception("Could not update rejection count for session %s", frame.session_id)

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
