"""Ghost-Rider REST API - automated road quality assessment backend.

Exposes the four core endpoints plus a route listing helper:

``GET  /``                        health check (service + model status)
``GET  /routes``                  recent route sessions
``POST /routes``                  create a route session + local upload folder
``POST /routes/{route_id}/images``  upload a photo with GPS/IMU metadata
``POST /routes/{route_id}/process`` run the CV pipeline in the background
``GET  /routes/{route_id}/results`` full route payload (scores, masks, advice)

Static media is served from ``/uploads`` so the local fallback URLs produced by
``s3_service`` render out of the box in the mobile client and Swagger UI.

Run locally::

    cd backend
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

Environment variables
---------------------
``GHOST_RIDER_HOST`` / ``GHOST_RIDER_PORT``  Bind address for ``python main.py``.
``MAX_UPLOAD_MB``        Per-file upload limit (default 25).
``UPLOADS_DIR``          Media root (default ``backend/uploads``).
``LOG_LEVEL``            Logging level (default ``INFO``).
``WARMUP_MODEL``         ``false`` to skip loading YOLO during startup.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError

try:  # package-style import (uvicorn backend.main:app from the repo root)
    from . import database, pipeline, s3_service
    from .app import __version__ as PACKAGE_VERSION
    from .app.config import get_settings
    from .app.health import router as health_router
    from .bedrock_service import health_status as bedrock_health
    from .s3_service import is_s3_enabled, resolve_media_url
except ImportError:  # flat import (uvicorn main:app from inside backend/)
    import database  # type: ignore[no-redef]
    import pipeline  # type: ignore[no-redef]
    import s3_service  # type: ignore[no-redef]
    from app import __version__ as PACKAGE_VERSION  # type: ignore[no-redef]
    from app.config import get_settings  # type: ignore[no-redef]
    from app.health import router as health_router  # type: ignore[no-redef]
    from bedrock_service import health_status as bedrock_health  # type: ignore[no-redef]
    from s3_service import is_s3_enabled, resolve_media_url  # type: ignore[no-redef]

# Single source of truth for every environment variable (see app/config.py).
SETTINGS = get_settings()
UPLOADS_DIR = SETTINGS.uploads_path

logging.basicConfig(
    level=getattr(logging, SETTINGS.LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("ghost_rider.api")

API_VERSION = PACKAGE_VERSION
MAX_UPLOAD_BYTES = SETTINGS.max_upload_bytes
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
IMAGE_MAGIC = (
    b"\xff\xd8\xff",            # JPEG
    b"\x89PNG\r\n\x1a\n",       # PNG
    b"BM",                      # BMP
)
WARMUP_MODEL = SETTINGS.WARMUP_MODEL


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class GPSData(BaseModel):
    """GPS fix attached to an uploaded frame."""

    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in degrees")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude in degrees")
    speed_mps: Optional[float] = Field(default=None, ge=0.0)
    heading_deg: Optional[float] = Field(default=None, ge=-360.0, le=360.0)
    accuracy_m: Optional[float] = Field(default=None, ge=0.0)


class IMUData(BaseModel):
    """Device orientation captured with the frame (degrees)."""

    pitch_deg: float = Field(default=0.0, ge=-90.0, le=90.0)
    roll_deg: float = Field(default=0.0, ge=-180.0, le=180.0)
    yaw_deg: Optional[float] = Field(default=None, ge=-360.0, le=360.0)
    accel_z: Optional[float] = None


class ImageMetadata(BaseModel):
    """Metadata payload accepted by the image upload endpoint."""

    model_config = ConfigDict(extra="allow")

    gps: Optional[GPSData] = None
    imu: IMUData = Field(default_factory=IMUData)
    captured_at: Optional[str] = None
    device_id: Optional[str] = None
    frame_index: Optional[int] = None


class RouteCreatedResponse(BaseModel):
    route_id: str
    status: str
    created_at: str
    upload_url: str
    segment_length_m: float


class ImageUploadResponse(BaseModel):
    status: str
    route_id: str
    image_id: int
    segment_id: int
    filename: str
    stored_path: str
    size_bytes: int
    image_url: str
    metadata: ImageMetadata


class ProcessAcceptedResponse(BaseModel):
    status: str
    route_id: str
    image_count: int
    message: str


# --------------------------------------------------------------------------- #
# Application lifecycle
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Prepare the database, media root and (optionally) warm the YOLO model."""
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        database.init_db()
    except Exception as exc:  # pragma: no cover - surfaces at startup
        logger.error("Database initialisation failed: %s", exc)

    if WARMUP_MODEL:
        try:
            # Loading torch weights blocks for a few seconds; keep the event loop free.
            await asyncio.get_running_loop().run_in_executor(None, pipeline.load_model)
            logger.info("Model warmup finished: %s", pipeline.model_status())
        except Exception as exc:  # pragma: no cover - warmup must never be fatal
            logger.warning("Model warmup failed (%s: %s); it will retry on first request.",
                           type(exc).__name__, exc)

    SETTINGS.log_summary(logger)
    logger.info(
        "Ghost-Rider API %s ready | uploads=%s | db=%s | s3=%s | bedrock=%s | model_loaded=%s | "
        "workers-note=%s",
        API_VERSION, UPLOADS_DIR, database.get_db_path(), is_s3_enabled(),
        bedrock_health().get("bedrock_enabled"), pipeline.model_status().get("loaded"),
        "each uvicorn worker loads its own YOLO model and SQLite connection",
    )
    logger.info("Deep diagnostics available at GET /health/deep (probe=auto|aws|none).")
    yield
    logger.info("Ghost-Rider API shutting down.")


app = FastAPI(
    title="Ghost-Rider Road Quality API",
    description="Automated road condition assessment: YOLOv8 segmentation, homography "
                "area physics, Road Condition Index scoring and Bedrock repair advice.",
    version=API_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=SETTINGS.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Deep dependency diagnostics: GET /health (liveness) and GET /health/deep.
app.include_router(health_router)

# Local media (raw frames + mask overlays) served straight from disk so the
# /uploads/... fallback URLs returned by s3_service always resolve.
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _error(status_code: int, code: str, message: str, **extra: Any) -> HTTPException:
    """Build a structured HTTPException (consistent error envelope)."""
    detail: Dict[str, Any] = {"error": code, "message": message}
    detail.update({key: value for key, value in extra.items() if value is not None})
    return HTTPException(status_code=status_code, detail=detail)


def _parse_metadata(raw: Optional[str]) -> ImageMetadata:
    """Validate the multipart ``metadata`` field (nested or flat keys)."""
    if raw is None or not str(raw).strip():
        return ImageMetadata()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _error(400, "invalid_metadata_json", f"metadata is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise _error(400, "invalid_metadata", "metadata must be a JSON object")

    imu = dict(payload.get("imu")) if isinstance(payload.get("imu"), dict) else {}
    for key in ("pitch_deg", "roll_deg", "yaw_deg"):
        if key in payload and key not in imu:
            imu[key] = payload[key]
    if imu:
        payload["imu"] = imu

    gps = dict(payload.get("gps")) if isinstance(payload.get("gps"), dict) else {}
    for key in ("lat", "lon"):
        if key in payload and key not in gps:
            gps[key] = payload[key]
    if gps:
        payload["gps"] = gps

    try:
        return ImageMetadata.model_validate(payload)
    except ValidationError as exc:
        raise _error(400, "invalid_metadata", "metadata failed validation", issues=exc.errors()) from exc


def _safe_filename(filename: Optional[str]) -> str:
    """Reduce a client filename to a safe base name with an allowed extension."""
    raw = Path(str(filename or "frame.jpg")).name.replace("\\", "/").split("/")[-1]
    stem = "".join(ch if (ch.isalnum() or ch in "._- ") else "_" for ch in raw).strip(" ._")[:80]
    extension = Path(raw).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        extension = ".jpg"
    if not stem:
        stem = "frame"
    if stem.lower().endswith(extension):
        stem = stem[: -len(extension)]
    return f"{stem or 'frame'}{extension}"


def _looks_like_image(path: Path) -> bool:
    """Cheap magic-number check so a renamed text file cannot poison the pipeline."""
    try:
        with path.open("rb") as handle:
            header = handle.read(16)
    except OSError:
        return False
    if header.startswith(IMAGE_MAGIC):
        return True
    return header[:4] == b"RIFF" and header[8:12] == b"WEBP"


async def _store_upload(upload: UploadFile, destination: Path) -> int:
    """Stream an UploadFile to disk enforcing the size limit. Returns bytes."""
    size = 0
    try:
        with destination.open("wb") as handle:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    handle.close()
                    destination.unlink(missing_ok=True)
                    raise _error(
                        413, "file_too_large",
                        f"upload exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
                    )
                handle.write(chunk)
    finally:
        try:
            await upload.close()
        except Exception:  # pragma: no cover - already closed
            pass
    return size


# --------------------------------------------------------------------------- #
# Background pipeline
# --------------------------------------------------------------------------- #
def _run_pipeline_task(route_id: str) -> None:
    """Background job: run the CV pipeline, persist results, update the route.

    Executed in FastAPI's threadpool (sync function), so the YOLO model, sqlite
    connections and boto3 clients are all used from a worker thread safely.
    """
    started = time.perf_counter()
    logger.info("Pipeline task started for route %s", route_id)
    try:
        database.update_route_status(
            route_id, database.ROUTE_STATUS_PROCESSING, status_detail="pipeline running"
        )
        images = database.get_uploaded_segments_payload(route_id)
        if not images:
            database.update_route_status(
                route_id, database.ROUTE_STATUS_FAILED, status_detail="no images uploaded"
            )
            logger.warning("Route %s has no uploaded images; aborting.", route_id)
            return

        payload = pipeline.run_full_pipeline(images, route_id=route_id)
        written = database.save_segment_results(route_id, payload.get("segments") or [])
        database.update_route_status(
            route_id,
            database.ROUTE_STATUS_COMPLETED,
            status_detail=f"{written} segment(s) assessed in {round(time.perf_counter() - started, 2)}s",
            overall_score=payload.get("overall_score"),
            overall_status=payload.get("overall_status"),
            recommendation=payload.get("recommendation"),
        )
        logger.info("Pipeline task finished for route %s (%d segments, %.1fs)",
                    route_id, written, time.perf_counter() - started)
    except Exception as exc:
        logger.exception("Pipeline task failed for route %s: %s", route_id, exc)
        try:
            database.update_route_status(
                route_id,
                database.ROUTE_STATUS_FAILED,
                status_detail=f"{type(exc).__name__}: {str(exc)[:400]}",
            )
        except Exception as inner:  # pragma: no cover - the DB itself is down
            logger.error("Could not record failure for route %s: %s", route_id, inner)


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/", summary="Health check")
async def read_root() -> Dict[str, Any]:
    """Liveness + configuration overview (use /health/deep for dependency probes)."""
    service_states: Dict[str, Any] = {
        "s3": s3_service.health_status(),
        "bedrock": bedrock_health(),
        "pipeline": pipeline.model_status(),
    }
    try:
        service_states["database"] = database.stats()
    except Exception as exc:
        service_states["database"] = {"error": f"{type(exc).__name__}: {exc}"}

    return {
        "message": "Ghost-Rider Road Quality Assessment Backend Running",
        "version": API_VERSION,
        "status": "ok",
        "services": service_states,
        "config": SETTINGS.redacted(),
        "endpoints": {
            "docs": "/docs",
            "health": "/health",
            "deep_health": "/health/deep",
            "create_route": "POST /routes",
            "upload_image": "POST /routes/{route_id}/images",
            "process_route": "POST /routes/{route_id}/process",
            "results": "GET /routes/{route_id}/results",
        },
    }


@app.get("/routes", summary="List recent route sessions")
async def list_routes(limit: int = Query(default=50, ge=1, le=500)) -> Dict[str, Any]:
    routes = database.list_routes(limit=limit)
    return {"count": len(routes), "routes": routes}


@app.post("/routes", response_model=RouteCreatedResponse, summary="Create a route session")
async def create_route() -> RouteCreatedResponse:
    """Create a new recording session and its local upload folder."""
    record = database.create_route()
    route_id = record["route_id"]
    route_dir = UPLOADS_DIR / route_id
    try:
        route_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        database.update_route_status(route_id, database.ROUTE_STATUS_FAILED,
                                     status_detail=f"could not create upload folder: {exc}")
        raise _error(500, "storage_unavailable", "could not create the route upload folder") from exc

    return RouteCreatedResponse(
        route_id=route_id,
        status=record["status"],
        created_at=record["created_at"],
        upload_url=f"/routes/{route_id}/images",
        segment_length_m=database.SEGMENT_LENGTH_M,
    )


@app.post("/routes/{route_id}/images", response_model=ImageUploadResponse,
          summary="Upload a road frame with GPS/IMU metadata")
async def upload_image(
    route_id: str,
    file: UploadFile = File(..., description="JPEG/PNG road frame"),
    metadata: Optional[str] = Form(default=None, description='JSON: {"gps":{"lat":..,"lon":..},'
                                                           '"imu":{"pitch_deg":..,"roll_deg":..}}'),
) -> ImageUploadResponse:
    """Persist one frame for a route and record its metadata."""
    if not database.route_exists(route_id):
        raise _error(404, "route_not_found", f"route {route_id} does not exist")

    parsed_metadata = _parse_metadata(metadata)
    safe_name = _safe_filename(file.filename)
    route_dir = UPLOADS_DIR / route_id
    route_dir.mkdir(parents=True, exist_ok=True)

    segment_id = database.next_segment_id(route_id)
    unique_name = f"seg{segment_id:04d}_{uuid.uuid4().hex[:8]}{Path(safe_name).suffix}"
    destination = route_dir / unique_name

    size = await _store_upload(file, destination)
    if size == 0:
        destination.unlink(missing_ok=True)
        raise _error(400, "empty_upload", "the uploaded file is empty")
    if not _looks_like_image(destination):
        destination.unlink(missing_ok=True)
        raise _error(415, "unsupported_media_type",
                     "the uploaded file is not a readable JPEG/PNG/WEBP/BMP image")

    image_url = s3_service.to_local_url(destination)
    record = database.add_route_image(
        route_id,
        filename=safe_name,
        image_path=str(destination),
        segment_id=segment_id,
        image_url=image_url,
        metadata=parsed_metadata.model_dump(),
    )

    logger.info("Route %s segment %d stored %s (%d bytes)", route_id, segment_id, unique_name, size)
    return ImageUploadResponse(
        status="success",
        route_id=route_id,
        image_id=int(record.get("id") or 0),
        segment_id=segment_id,
        filename=safe_name,
        stored_path=str(destination),
        size_bytes=size,
        image_url=image_url,
        metadata=parsed_metadata,
    )


@app.post("/routes/{route_id}/process", response_model=ProcessAcceptedResponse,
          summary="Start background analysis of a route")
async def process_route(route_id: str, background_tasks: BackgroundTasks) -> ProcessAcceptedResponse:
    """Queue the CV/Bedrock pipeline for every uploaded frame of the route."""
    route = database.get_route(route_id)
    if route is None:
        raise _error(404, "route_not_found", f"route {route_id} does not exist")

    images = database.get_route_images(route_id)
    if not images:
        raise _error(400, "no_images", "upload at least one image before processing")

    # Atomic compare-and-set: with ``uvicorn --workers 2`` two processes can serve
    # concurrent requests, so a read-then-write status check would race and start
    # the pipeline twice for the same route.
    if not database.claim_route_for_processing(route_id):
        raise _error(409, "already_processing", "this route is already being processed")

    background_tasks.add_task(_run_pipeline_task, route_id)
    logger.info("Route %s queued for processing (%d images)", route_id, len(images))

    return ProcessAcceptedResponse(
        status="processing_started",
        route_id=route_id,
        image_count=len(images),
        message="Analysis started in the background; poll /routes/{route_id}/results.",
    )


@app.get("/routes/{route_id}/results", summary="Full route assessment payload")
async def get_results(
    route_id: str,
    presign: bool = Query(default=True, description="Re-sign stored S3 mask URLs"),
    expires_in: int = Query(default=3600, ge=60, le=604800, description="Presigned URL TTL (seconds)"),
) -> Dict[str, Any]:
    """Overall score, 10 m segments, 50 m rollups, mask URLs and recommendations."""
    summary = database.get_route_summary(route_id)
    if summary is None:
        raise _error(404, "route_not_found", f"route {route_id} does not exist")

    segments: List[Dict[str, Any]] = []
    for segment in summary["segments"]:
        item = dict(segment)
        if presign:
            for key in ("mask_url", "raw_url"):
                if item.get(key):
                    try:
                        item[key] = resolve_media_url(item[key], expires_in)
                    except Exception as exc:  # pragma: no cover - resolve never raises
                        logger.debug("Could not refresh %s for segment %s: %s", key, item.get("segment_id"), exc)
        item["mask_local_url"] = item.get("mask_local_url") or s3_service.to_local_url(
            item.get("mask_path") or item.get("mask_url") or ""
        )
        item["raw_local_url"] = item.get("raw_local_url") or s3_service.to_local_url(
            item.get("image_path") or ""
        )
        segments.append(item)

    groups_50m = pipeline.build_50m_groups(segments)
    status = summary.get("status") or database.ROUTE_STATUS_CREATED

    payload: Dict[str, Any] = {
        "route_id": route_id,
        "status": status,
        "status_detail": summary.get("status_detail"),
        "processing": status == database.ROUTE_STATUS_PROCESSING,
        "created_at": summary.get("created_at"),
        "updated_at": summary.get("updated_at"),
        "overall_score": summary.get("overall_score"),
        "overall_status": summary.get("overall_status"),
        "recommendation": summary.get("recommendation"),
        "segment_length_m": summary.get("segment_length_m", database.SEGMENT_LENGTH_M),
        "group_length_m": summary.get("segment_length_m", database.SEGMENT_LENGTH_M) * 5,
        "counts": summary.get("counts", {}),
        "totals": summary.get("totals", {}),
        "images": summary.get("images", []),
        "segments": segments,
        "segments_50m": groups_50m,
        "recommendations": {
            "overall": summary.get("recommendation"),
            "per_segment": [
                {
                    "segment_id": item.get("segment_id"),
                    "score": item.get("score"),
                    "status": item.get("status"),
                    "recommendation": item.get("recommendation"),
                }
                for item in segments
            ],
            "worst_segment": next(
                (item.get("segment_id") for item in
                 sorted(segments, key=lambda seg: float(seg.get("score") or 0))), None
            ),
        },
    }

    if status == database.ROUTE_STATUS_COMPLETED and not segments:
        payload["warning"] = "route marked completed but no segment rows were stored"

    if status == database.ROUTE_STATUS_PROCESSING:
        return JSONResponse(status_code=200, content=payload,
                            headers={"Retry-After": "5"})
    return payload


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
if __name__ == "__main__":  # pragma: no cover - manual start
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("GHOST_RIDER_HOST", SETTINGS.HOST),
        port=int(os.getenv("GHOST_RIDER_PORT", str(SETTINGS.PORT)) or SETTINGS.PORT),
        reload=False,
    )
