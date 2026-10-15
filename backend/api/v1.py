"""Ghost-Rider v1 API endpoints.

Implements the minimum HTTP interface required by Final Plan Section 11.4:
- POST /v1/uploads: Allocate private object key and short-lived upload URL
- POST /v1/uploads/{id}/finalize: Check uploaded object and enqueue analysis
- POST /v1/sessions: Create live/replay session with mode, camera and calibration
- POST /v1/sessions/{id}/frames: Accept sequence, original frame reference, capture times and telemetry
- POST /v1/sessions/{id}/finish: Close capture and request segment aggregation
- GET  /v1/jobs/{id}: Return durable lifecycle state and error reason
- GET  /v1/samples/{id}: Return evidence, metrics, quality, score and narrative status
- GET  /v1/sessions/{id}/segments: Return 50m bin summaries and coverage truth
- POST /v1/reports: Generate factual report and Bedrock wording
- GET  /v1/health: State model/worker/storage/integration readiness

Ownership: Backend & AWS AI
Reference: docs/contracts/endpoints.md, docs/final_plan.md (Section 11.4)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from pydantic import ValidationError

from .. import database, queues, s3_service, schemas
from ..ingestion import (
    IngestionAdapter,
    compute_file_sha256,
    generate_idempotency_key,
    get_ingestion_queue,
    validate_image_bytes,
)
from ..reports import (
    DEFAULT_BEDROCK_MODEL_ID,
    compute_factual_hash,
    extract_facts_from_sample,
    generate_report_for_assessment,
    is_bedrock_configured,
)
from ..routes import aggregate_route_segments
from ..schemas import (
    FinalizeRequest,
    FinalizeResponse,
    FrameMetadata,
    HealthStatus,
    JobState,
    JobStatus,
    ReportContent,
    ReportResult,
    SegmentList,
    SegmentResult,
    SessionState,
    SourceMode,
    UploadRequest,
    UploadResponse,
)

logger = logging.getLogger("ghost_rider.api.v1")

router = APIRouter(prefix="/v1", tags=["v1"])

# Maximum accepted size for the local (S3-less) streaming upload path.
MAX_LOCAL_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "25") or 25) * 1024 * 1024


# --------------------------------------------------------------------------- #
# Error helpers
# --------------------------------------------------------------------------- #

def _validation_error(status_code: int, exc: ValidationError) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error": "validation_error",
            "message": "Request payload failed validation",
            "issues": exc.errors(),
        },
    )


def _not_found(resource: str, identifier: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": "not_found", "message": f"{resource} {identifier} not found"},
    )


def _conflict(resource: str, identifier: str, reason: str) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "error": "conflict",
            "message": f"{resource} {identifier}: {reason}",
        },
    )


def _bad_request(message: str, error_code: str = "bad_request") -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"error": error_code, "message": message},
    )


def _safe_filename(filename: Optional[str]) -> str:
    raw = str(filename or "frame.jpg").replace("\\", "/").split("/")[-1]
    stem = "".join(ch if (ch.isalnum() or ch in "._- ") else "_" for ch in raw).strip(" ._")[:80]
    extension = ".jpg"
    if "." in raw:
        ext = raw.rsplit(".", 1)[-1].lower()
        if ext in {"jpg", "jpeg", "png", "webp", "bmp"}:
            extension = f".{ext}"
    if not stem:
        stem = "frame"
    if stem.lower().endswith(extension):
        stem = stem[:-len(extension)]
    return f"{stem}{extension}"


def _ensure_v1_tables() -> None:
    """Ensure the v1 tables exist.

    Delegates to :func:`backend.queues.ensure_v1_tables`, which is the single
    owner of the v1 DDL (upload slots, jobs + lifecycle events, sessions, frames,
    samples, reports and the worker's processed-frame idempotency table).
    """
    queues.ensure_v1_tables()


# --------------------------------------------------------------------------- #
# Upload Endpoints
# --------------------------------------------------------------------------- #

@router.post(
    "/uploads",
    response_model=UploadResponse,
    summary="Allocate an upload URL",
    description="Create a private upload slot and return a presigned S3 or bounded local upload URL.",
)
async def create_upload(
    payload: UploadRequest,
    request: Request,
) -> UploadResponse:
    """POST /v1/uploads — allocate private object key and short-lived upload URL."""
    _ensure_v1_tables()
    upload_id = str(uuid.uuid4())
    safe_name = _safe_filename(payload.filename)
    object_key = f"{s3_service.RAW_OBJECT_PREFIX}{upload_id}/{safe_name}"

    local_url = f"/v1/uploads/{upload_id}/local"
    upload_url = local_url
    expires_at = None
    if s3_service.is_s3_enabled():
        presigned_put = s3_service.get_presigned_put_url(
            object_key,
            content_type=payload.content_type,
            expires_in=s3_service.DEFAULT_PRESIGN_TTL,
        )
        if presigned_put:
            upload_url = presigned_put
            try:
                expires_at = (
                    datetime.now(timezone.utc)
                    + timedelta(seconds=s3_service.DEFAULT_PRESIGN_TTL)
                ).isoformat()
            except Exception:
                pass

    try:
        with database.get_connection() as conn:
            conn.execute(
                "INSERT INTO upload_slots (upload_id, object_key, filename, status, created_at, expires_at) "
                "VALUES (?, ?, ?, 'ready', ?, ?) "
                "ON CONFLICT(upload_id) DO UPDATE SET status='ready', updated_at=CURRENT_TIMESTAMP",
                (upload_id, object_key, safe_name, database._now(), expires_at),
            )
    except Exception as exc:
        logger.exception("Could not persist upload slot %s: %s", upload_id, exc)
        raise _bad_request("could not allocate upload slot") from exc

    return UploadResponse(
        upload_id=upload_id,
        upload_url=upload_url,
        object_key=object_key,
        expires_at=expires_at,
        status="ready",
    )


@router.put(
    "/uploads/{upload_id}/local",
    summary="Upload bytes to a private slot (S3-less / local fallback)",
    description=(
        "Bounded streaming upload used when no S3 bucket is configured, and by the "
        "local/replay demonstration path. The object is written under the media root "
        "at the slot's private object key and validated by magic header."
    ),
)
async def upload_local(upload_id: str, request: Request) -> Dict[str, Any]:
    """PUT /v1/uploads/{upload_id}/local — stream a bounded image into a private slot."""
    _ensure_v1_tables()
    with database.read_connection() as conn:
        row = conn.execute(
            "SELECT object_key, status FROM upload_slots WHERE upload_id = ?",
            (upload_id,),
        ).fetchone()
    if row is None:
        raise _not_found("upload", upload_id)
    if row["status"] not in {"ready", "uploaded"}:
        raise _conflict("upload", upload_id, f"already {row['status']}")

    object_key = row["object_key"]
    target = s3_service.to_local_path(object_key)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise _bad_request("could not prepare upload target") from exc

    hasher = hashlib.sha256()
    total = 0
    head = b""
    try:
        with target.open("wb") as fh:
            async for chunk in request.stream():
                if not chunk:
                    continue
                if len(head) < 16:
                    head += chunk[: 16 - len(head)]
                total += len(chunk)
                if total > MAX_LOCAL_UPLOAD_BYTES:
                    raise _bad_request(
                        f"upload exceeds the {MAX_LOCAL_UPLOAD_BYTES} byte limit",
                        error_code="upload_too_large",
                    )
                hasher.update(chunk)
                fh.write(chunk)
    except HTTPException:
        target.unlink(missing_ok=True)
        raise
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise _bad_request("could not store upload") from exc

    if total == 0:
        target.unlink(missing_ok=True)
        raise _bad_request("empty upload", error_code="empty_upload")

    is_valid, _detected_ext, error = validate_image_bytes(head)
    if not is_valid:
        target.unlink(missing_ok=True)
        raise _bad_request(error or "unsupported image format", error_code="invalid_image")

    uploaded_at = database._now()
    try:
        with database.get_connection() as conn:
            conn.execute(
                "UPDATE upload_slots SET status = 'uploaded', updated_at = ? WHERE upload_id = ?",
                (uploaded_at, upload_id),
            )
    except Exception as exc:
        logger.exception("Could not update upload slot %s after local upload: %s", upload_id, exc)

    return {
        "upload_id": upload_id,
        "status": "uploaded",
        "object_key": object_key,
        "size_bytes": total,
        "sha256": hasher.hexdigest(),
        "uploaded_at": uploaded_at,
    }


@router.post(
    "/uploads/{upload_id}/finalize",
    response_model=FinalizeResponse,
    summary="Finalize an upload and enqueue analysis",
    description="Verify uploaded object existence, size and format, record metadata, and enqueue processing.",
)
async def finalize_upload(
    upload_id: str,
    background_tasks: BackgroundTasks,
    payload: Optional[FinalizeRequest] = None,
) -> FinalizeResponse:
    """POST /v1/uploads/{upload_id}/finalize — check uploaded object and enqueue analysis."""
    _ensure_v1_tables()
    slot = None
    with database.get_connection() as conn:
        row = conn.execute(
            "SELECT upload_id, object_key, filename, status, created_at FROM upload_slots WHERE upload_id = ?",
            (upload_id,),
        ).fetchone()
        if row is not None:
            slot = dict(row)

    if slot is None:
        raise _not_found("upload", upload_id)
    if slot.get("status") not in {"ready", "uploaded", "validated"}:
        raise _conflict("upload", upload_id, f"already {slot.get('status')}")

    object_key = slot["object_key"]
    metadata: Optional[FrameMetadata] = None
    source_mode: SourceMode = SourceMode.UPLOAD

    if isinstance(payload, FinalizeRequest):
        metadata = payload.metadata
        source_mode = payload.source_mode

    # Verify object existence and bounded size
    object_ok = False
    local_path = None
    if s3_service.is_s3_enabled():
        try:
            client = s3_service.get_s3_client()
            if client is not None:
                head = client.head_object(Bucket=s3_service.get_s3_settings()["bucket"], Key=object_key)
                size = int(head.get("ContentLength") or 0)
                if 0 < size <= MAX_LOCAL_UPLOAD_BYTES:
                    object_ok = True
        except Exception as exc:
            logger.warning("S3 object check failed for %s: %s", object_key, exc)
    else:
        candidates = [
            s3_service.to_local_path(object_key),
            s3_service.UPLOADS_DIR / object_key.replace("uploads/", "", 1),
            s3_service.UPLOADS_DIR / upload_id / slot["filename"],
        ]
        for c in candidates:
            if c.exists() and c.is_file() and 0 < c.stat().st_size <= MAX_LOCAL_UPLOAD_BYTES:
                object_ok = True
                break

    if not object_ok:
        raise _bad_request("uploaded object not found or could not be verified", error_code="object_not_found")

    job_id = str(uuid.uuid4())
    received_at = database._now()
    metadata_json = metadata.model_dump_json() if metadata is not None else None

    try:
        with database.get_connection() as conn:
            conn.execute(
                "UPDATE upload_slots SET status = 'validated', updated_at = ? WHERE upload_id = ?",
                (received_at, upload_id),
            )
            conn.execute(
                "INSERT INTO jobs (job_id, parent_type, parent_id, status, received_at, updated_at, metadata_json) "
                "VALUES (?, 'upload', ?, 'queued', ?, ?, ?)",
                (job_id, upload_id, received_at, received_at, metadata_json),
            )
            for state in ("received", "validated", "queued"):
                conn.execute(
                    "INSERT INTO job_events (job_id, status, detail, at) VALUES (?, ?, ?, ?)",
                    (job_id, state, f"source_mode={source_mode.value}", received_at),
                )
    except Exception as exc:
        logger.exception("Could not persist finalize record for %s: %s", upload_id, exc)
        raise _bad_request("could not enqueue analysis") from exc

    return FinalizeResponse(
        upload_id=upload_id,
        status="queued",
        job_id=job_id,
        message="Upload validated and analysis queued",
    )


# --------------------------------------------------------------------------- #
# Session Endpoints
# --------------------------------------------------------------------------- #

@router.post(
    "/sessions",
    response_model=SessionState,
    summary="Create a live/replay session",
    description="Start a capture session with explicit mode, camera and calibration.",
)
async def create_session(
    body: Dict[str, Any],
) -> SessionState:
    """POST /v1/sessions — create live/replay session with mode, camera and calibration."""
    _ensure_v1_tables()
    mode_raw = body.get("mode")
    try:
        mode = SourceMode(mode_raw) if mode_raw else SourceMode.LIVE
    except ValueError:
        raise _bad_request(
            f"invalid mode: {mode_raw!r}. Allowed: {', '.join(m.value for m in SourceMode)}",
            error_code="invalid_mode",
        )

    session_id = str(uuid.uuid4())
    created_at = database._now()

    session = SessionState(
        session_id=session_id,
        mode=mode,
        camera_id=body.get("camera_id"),
        calibration_id=body.get("calibration_id"),
        created_at=created_at,
        frame_count=0,
        processed_count=0,
        rejected_count=0,
        dropped_count=0,
        last_capture_at=None,
        last_processed_at=None,
        is_stale=False,
    )

    try:
        with database.get_connection() as conn:
            conn.execute(
                "INSERT INTO sessions (session_id, mode, camera_id, calibration_id, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'live', ?, ?)",
                (session_id, mode.value, session.camera_id, session.calibration_id, created_at, created_at),
            )
    except Exception as exc:
        logger.exception("Could not persist session %s: %s", session_id, exc)
        raise _bad_request("could not create session") from exc

    return session


@router.post(
    "/sessions/{session_id}/frames",
    response_model=SessionState,
    summary="Accept a frame for a session",
    description="Accept one frame with original reference, capture times and telemetry.",
)
async def ingest_frame(
    session_id: str,
    request: Request,
) -> SessionState:
    """POST /v1/sessions/{session_id}/frames — accept sequence, capture times and telemetry."""
    _ensure_v1_tables()
    session = _get_session(session_id)
    if session is None:
        raise _not_found("session", session_id)

    content_type = request.headers.get("content-type") or ""
    if "multipart/form-data" not in content_type:
        raise _bad_request("multipart frame upload is required", error_code="missing_frame")

    try:
        form = await request.form()
    except Exception as exc:
        raise _bad_request("could not parse multipart form") from exc

    file = form.get("frame") or form.get("file")
    if file is None:
        raise _bad_request("multipart frame file is required", error_code="missing_frame")

    file_bytes = await file.read(MAX_LOCAL_UPLOAD_BYTES + 1)
    if len(file_bytes) > MAX_LOCAL_UPLOAD_BYTES:
        _increment_session_counter(session_id, "rejected_count")
        raise _bad_request("frame exceeds upload size limit", error_code="upload_too_large")
    raw_meta = form.get("metadata") or form.get("meta")

    frame_index = _next_frame_index(session_id)
    adapter = IngestionAdapter()
    ok, record, err = adapter.process_incoming_frame(
        session_id=session_id,
        frame_index=frame_index,
        source_mode=session.mode,
        raw_bytes=file_bytes,
        filename=getattr(file, "filename", "frame.jpg"),
        raw_metadata=raw_meta,
    )

    if not ok:
        _increment_session_counter(session_id, "rejected_count")
        raise _bad_request(err or "Frame validation failed", error_code="frame_validation_failed")

    # Update session counters
    _increment_session_counter(session_id, "frame_count")
    if record.get("dropped"):
        _increment_session_counter(session_id, "dropped_count")

    # Record frame in frames table
    try:
        with database.get_connection() as conn:
            conn.execute(
                "INSERT INTO frames (session_id, frame_index, source_mode, filename, received_at, metadata_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    frame_index,
                    session.mode.value,
                    record.get("filename", "frame.jpg"),
                    record.get("received_at", database._now()),
                    json.dumps(record.get("metadata")),
                ),
            )
    except Exception as exc:
        logger.warning("Could not record frame row: %s", exc)

    return _get_session(session_id) or session


@router.post(
    "/sessions/{session_id}/finish",
    response_model=SessionState,
    summary="Close capture and request aggregation",
    description="Close the capture session and request segment aggregation.",
)
async def finish_session(
    session_id: str,
) -> SessionState:
    """POST /v1/sessions/{session_id}/finish — close capture and request segment aggregation."""
    _ensure_v1_tables()
    session = _get_session(session_id)
    if session is None:
        raise _not_found("session", session_id)

    finished_at = database._now()
    try:
        with database.get_connection() as conn:
            conn.execute(
                "UPDATE sessions SET status='finished', finished_at=?, updated_at=? WHERE session_id=?",
                (finished_at, finished_at, session_id),
            )
    except Exception as exc:
        logger.exception("Could not finish session %s: %s", session_id, exc)
        raise _bad_request("could not finish session") from exc

    updated = _get_session(session_id)
    return updated or session


# --------------------------------------------------------------------------- #
# Job Lifecycle Endpoints
# --------------------------------------------------------------------------- #

@router.get(
    "/jobs/{job_id}",
    response_model=JobState,
    summary="Return durable job state",
    description="Return lifecycle state, error reason, attempt count and versions.",
)
async def get_job(job_id: str) -> JobState:
    """GET /v1/jobs/{job_id} — return durable lifecycle state and error reason."""
    _ensure_v1_tables()
    job = _get_job(job_id)
    if job is None:
        raise _not_found("job", job_id)
    return job


def _get_job(job_id: str) -> Optional[JobState]:
    try:
        with database.read_connection() as conn:
            row = conn.execute(
                "SELECT job_id, status, error_reason, attempt_count, received_at, "
                "started_at, completed_at, updated_at, versions_json "
                "FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                return None
            versions: Dict[str, str] = {}
            if row["versions_json"]:
                try:
                    versions = json.loads(row["versions_json"])
                except Exception:
                    versions = {}
            sample_row = conn.execute(
                "SELECT sample_id FROM samples WHERE route_id = ? ORDER BY created_at DESC LIMIT 1",
                (job_id,),
            ).fetchone()
            return JobState(
                job_id=row["job_id"],
                status=JobStatus(row["status"]),
                error_reason=row["error_reason"],
                attempt_count=int(row["attempt_count"] or 0),
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                updated_at=row["updated_at"],
                versions=versions,
                result_sample_id=sample_row["sample_id"] if sample_row is not None else None,
            )
    except Exception as exc:
        logger.exception("Could not load job %s: %s", job_id, exc)
        return None


# --------------------------------------------------------------------------- #
# Sample Endpoints
# --------------------------------------------------------------------------- #

@router.get(
    "/samples/{sample_id}",
    response_model=SegmentResult,
    summary="Return sample evidence and metrics",
    description="Return evidence, metrics, quality, score and narrative status.",
)
async def get_sample(sample_id: str) -> SegmentResult:
    """GET /v1/samples/{sample_id} — return evidence, metrics, quality, score and narrative status."""
    _ensure_v1_tables()
    sample = _get_sample(sample_id)
    if sample is None:
        raise _not_found("sample", sample_id)
    return sample


def _get_sample(sample_id: str) -> Optional[SegmentResult]:
    try:
        with database.read_connection() as conn:
            row = conn.execute(
                "SELECT sample_id, segment_id, route_id, image_path, image_url, mask_url, raw_url, "
                "captured_at, gps_json, geometry_valid, area_json, quality_json, "
                "metrics_json, evidence_json, score_json, reference_json, "
                "model_version, feature_version, scoring_version, created_at, error, canonical_json "
                "FROM samples WHERE sample_id = ?",
                (sample_id,),
            ).fetchone()
            if row is None:
                return None

            def _parse_field(raw: Any, model_cls: Any) -> Optional[Any]:
                if not raw:
                    return None
                try:
                    p = json.loads(raw)
                    return model_cls.model_validate(p) if p else None
                except Exception:
                    return None

            gps = _parse_field(row["gps_json"], schemas.GPSData)
            area = _parse_field(row["area_json"], schemas.AreaResult)
            quality = _parse_field(row["quality_json"], schemas.QualityResult)
            metrics = _parse_field(row["metrics_json"], schemas.AggregatedMetrics)
            evidence = _parse_field(row["evidence_json"], schemas.DistressEvidence)
            score = _parse_field(row["score_json"], schemas.ScoreResult)
            reference = _parse_field(row["reference_json"], schemas.ReferenceComparison)
            canonical = _parse_field(row["canonical_json"], schemas.CanonicalSampleRecord)

            return SegmentResult(
                segment_id=int(row["segment_id"]),
                route_id=row["route_id"],
                sample_id=row["sample_id"],
                image_path=row["image_path"],
                image_url=row["image_url"],
                mask_url=row["mask_url"],
                raw_url=row["raw_url"],
                captured_at=row["captured_at"],
                gps=gps,
                geometry_valid=bool(row["geometry_valid"]),
                observed_area=area,
                quality=quality,
                metrics=metrics,
                evidence=evidence,
                score=score,
                reference=reference,
                canonical=canonical,
                model_version=row["model_version"],
                feature_version=row["feature_version"],
                scoring_version=row["scoring_version"],
                created_at=row["created_at"],
                error=row["error"],
            )
    except Exception as exc:
        logger.exception("Could not load sample %s: %s", sample_id, exc)
        return None


# --------------------------------------------------------------------------- #
# Route Segments Endpoints (50m Bins & Coverage Truth)
# --------------------------------------------------------------------------- #

@router.get(
    "/sessions/{session_id}/segments",
    response_model=SegmentList,
    summary="Return bin summaries and coverage truth",
    description="Return 50 m bin summaries with coverage truth and unsampled stretches.",
)
async def get_session_segments(
    session_id: str,
    bin_length_m: float = Query(default=50.0, ge=5.0, le=5000.0),
) -> SegmentList:
    """GET /v1/sessions/{session_id}/segments — return bin summaries and coverage truth."""
    _ensure_v1_tables()
    session = _get_session(session_id)
    if session is None:
        raise _not_found("session", session_id)

    # Load all samples belonging to this session
    samples: List[SegmentResult] = []
    try:
        sample_ids: List[str] = []
        with database.read_connection() as conn:
            rows = conn.execute(
                "SELECT sample_id FROM samples WHERE route_id = ? ORDER BY segment_id ASC",
                (session_id,),
            ).fetchall()
            sample_ids = [r["sample_id"] for r in rows]

        for sid in sample_ids:
            s = _get_sample(sid)
            if s is not None:
                samples.append(s)
    except Exception as exc:
        logger.exception("Failed to load samples for session %s: %s", session_id, exc)

    return aggregate_route_segments(samples, bin_length_m=bin_length_m, route_id=session_id)


# --------------------------------------------------------------------------- #
# Reports Endpoints
# --------------------------------------------------------------------------- #

@router.post(
    "/reports",
    response_model=ReportResult,
    summary="Generate factual report and Bedrock wording",
    description="Generate a structured report and optional Bedrock narrative from stored facts.",
)
async def generate_report(
    body: Dict[str, Any],
) -> ReportResult:
    """POST /v1/reports — generate factual report and Bedrock wording."""
    _ensure_v1_tables()
    assessment_id = body.get("assessment_id") or body.get("sample_id") or body.get("job_id")
    include_narrative = bool(body.get("include_narrative", False))
    model_id = body.get("model_id")

    if not assessment_id:
        raise _bad_request("assessment_id, sample_id or job_id is required", error_code="missing_assessment_id")

    # Load sample or job facts from database
    stored_facts: Dict[str, Any] = {}
    sample = _get_sample(assessment_id)
    if sample is not None:
        stored_facts = extract_facts_from_sample(sample)
    else:
        # Check if it corresponds to a job
        job = _get_job(assessment_id)
        if job is not None:
            stored_facts = {
                "assessment_id": assessment_id,
                "quality_status": "accepted" if job.status == JobStatus.SUCCEEDED else "limited",
                "score_status": "unknown",
            }
        else:
            # Fallback to direct provided facts or default baseline
            stored_facts = {
                "assessment_id": assessment_id,
                "quality_status": body.get("quality_status", "accepted"),
                "score_status": body.get("score_status", "unknown"),
                "score_value": body.get("score_value"),
            }

    report = generate_report_for_assessment(
        assessment_id=assessment_id,
        stored_facts=stored_facts,
        include_narrative=include_narrative,
        model_id=model_id,
    )

    # Persist report in database
    try:
        with database.get_connection() as conn:
            conn.execute(
                "INSERT INTO reports (report_id, assessment_id, content_json, generated_at, bedrock_model_id, factual_input_hash) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    report.report_id,
                    report.assessment_id,
                    json.dumps(report.content.model_dump()),
                    report.generated_at,
                    report.bedrock_model_id,
                    report.factual_input_hash,
                ),
            )
    except Exception as exc:
        logger.warning("Could not persist report record: %s", exc)

    return report


# --------------------------------------------------------------------------- #
# Health Endpoint
# --------------------------------------------------------------------------- #

@router.get(
    "/health",
    response_model=HealthStatus,
    summary="v1-aligned service health",
    description="State model/worker/storage/integration readiness in the v1 shape.",
)
async def v1_health() -> HealthStatus:
    """GET /v1/health — state model/worker/storage/integration readiness."""
    from .. import pipeline

    db_ok = True
    try:
        with database.get_connection() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception:
        db_ok = False

    queue = get_ingestion_queue()
    services: Dict[str, Any] = {
        "database": {"status": "ok" if db_ok else "unreachable"},
        "s3": {"status": "configured" if s3_service.is_s3_enabled() else "not_configured"},
        "bedrock": {"status": "configured" if is_bedrock_configured() else "not_configured"},
        "model": {"status": "loaded" if pipeline.model_status().get("loaded") else "not_loaded"},
        "worker": {
            "status": "ready",
            "queue_size": len(queue),
            "stats": queue.stats.to_dict(),
        },
    }

    overall = "healthy" if db_ok else "degraded"
    return HealthStatus(
        status=overall,
        version="1.0.0",
        services=services,
    )


# --------------------------------------------------------------------------- #
# Session helpers
# --------------------------------------------------------------------------- #

def _get_session(session_id: str) -> Optional[SessionState]:
    try:
        with database.read_connection() as conn:
            row = conn.execute(
                "SELECT session_id, mode, camera_id, calibration_id, status, created_at, "
                "frame_count, processed_count, rejected_count, dropped_count, "
                "last_capture_at, last_processed_at, is_stale "
                "FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            return SessionState(
                session_id=row["session_id"],
                mode=SourceMode(row["mode"]),
                camera_id=row["camera_id"],
                calibration_id=row["calibration_id"],
                created_at=row["created_at"],
                frame_count=int(row["frame_count"] or 0),
                processed_count=int(row["processed_count"] or 0),
                rejected_count=int(row["rejected_count"] or 0),
                dropped_count=int(row["dropped_count"] or 0),
                last_capture_at=row["last_capture_at"],
                last_processed_at=row["last_processed_at"],
                is_stale=bool(row["is_stale"]),
            )
    except Exception as exc:
        logger.exception("Could not load session %s: %s", session_id, exc)
        return None


def _next_frame_index(session_id: str) -> int:
    try:
        with database.read_connection() as conn:
            row = conn.execute(
                "SELECT MAX(frame_index) as max_idx FROM frames WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row and row["max_idx"] is not None:
                return int(row["max_idx"]) + 1
    except Exception:
        pass
    return 1


def _increment_session_counter(session_id: str, column: str) -> None:
    if column not in {"frame_count", "processed_count", "rejected_count", "dropped_count"}:
        return
    try:
        with database.get_connection() as conn:
            conn.execute(
                f"UPDATE sessions SET {column} = {column} + 1, updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
                (session_id,),
            )
    except Exception as exc:
        logger.debug("Could not increment %s for %s: %s", column, session_id, exc)
