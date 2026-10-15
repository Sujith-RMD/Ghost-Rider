"""SQLite persistence layer for Ghost-Rider.

Uses only the Python standard library (``sqlite3``) so the engine has zero
external database dependencies.  The database file ``road_quality.db`` is
created automatically the first time this module is imported (and again by the
FastAPI lifespan hook), together with the ``routes``, ``route_images`` and
``segments`` tables.

Schema
------
``routes``        : route_id (PK), created_at, status, status_detail,
                    overall_score, overall_status, recommendation, updated_at.
``route_images``  : one row per uploaded photo - filename, local path, GPS,
                    IMU pitch/roll and the raw metadata JSON.
``segments``      : the 10 m assessment results written by the pipeline -
                    score, status, defect_area_m2, mask_url, recommendation
                    (+ ``details_json`` with the full per-segment payload).

All helpers accept and return plain dictionaries, are safe to call from
FastAPI background threads (WAL mode + per-call connections) and never leak
SQL exceptions silently: they log and re-raise so the API can return 500s.

Environment variables
---------------------
``GHOST_RIDER_DB_PATH``  Override the database location (tests / deployments).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

logger = logging.getLogger("ghost_rider.database")

# --------------------------------------------------------------------------- #
# Paths / configuration
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent

try:  # reuse the shared .env loader (optional dependency, never fatal)
    from .s3_service import load_project_env
except ImportError:
    try:
        from s3_service import load_project_env
    except ImportError:  # pragma: no cover - standalone import

        def load_project_env() -> None:  # type: ignore[misc]
            return None


load_project_env()

try:  # flat layout (``uvicorn main:app`` from backend/)
    from app.config import get_settings_safely
except ImportError:  # package layout (``uvicorn backend.main:app``)
    from backend.app.config import get_settings_safely  # type: ignore[no-redef]

DEFAULT_DB_PATH = BASE_DIR / "road_quality.db"


def get_db_path() -> Path:
    """Resolve the database path from :mod:`app.config` (env fallback)."""
    settings = get_settings_safely()
    if settings is not None:
        return settings.database_path
    raw = (os.getenv("GHOST_RIDER_DB_PATH") or "").strip()
    if raw:
        path = Path(raw).expanduser()
        return path if path.is_absolute() else (BASE_DIR / path).resolve()
    return DEFAULT_DB_PATH


# ``GHOST_RIDER_DB_PATH`` is read lazily; DB_PATH is kept for convenience and
# documentation purposes (import-time snapshot).
DB_PATH = get_db_path()

_init_lock = threading.RLock()
_initialised = False

ROUTE_STATUS_CREATED = "created"
ROUTE_STATUS_QUEUED = "queued"
ROUTE_STATUS_PROCESSING = "processing"
ROUTE_STATUS_COMPLETED = "completed"
ROUTE_STATUS_FAILED = "failed"

SEGMENT_LENGTH_M = 10.0

SCHEMA_STATEMENTS: Sequence[str] = (
    """
    CREATE TABLE IF NOT EXISTS routes (
        route_id        TEXT PRIMARY KEY,
        created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        status          TEXT NOT NULL DEFAULT 'created',
        status_detail   TEXT,
        overall_score   INTEGER,
        overall_status  TEXT,
        recommendation  TEXT,
        updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS route_images (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        route_id      TEXT NOT NULL,
        segment_id    INTEGER NOT NULL,
        filename      TEXT NOT NULL,
        image_path    TEXT NOT NULL,
        image_url     TEXT,
        gps_lat       REAL,
        gps_lon       REAL,
        pitch_deg     REAL,
        roll_deg      REAL,
        metadata_json TEXT,
        created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (route_id, segment_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS segments (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        route_id        TEXT NOT NULL,
        segment_id      INTEGER NOT NULL,
        score           INTEGER,
        status          TEXT,
        defect_area_m2  REAL,
        mask_url        TEXT,
        recommendation  TEXT,
        details_json    TEXT,
        created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (route_id, segment_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_route_images_route ON route_images (route_id, segment_id)",
    "CREATE INDEX IF NOT EXISTS idx_segments_route ON segments (route_id, segment_id)",
)


# --------------------------------------------------------------------------- #
# Connection handling
# --------------------------------------------------------------------------- #
@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Yield a transaction-scoped connection with row access by name.

    Commits on clean exit, rolls back on any exception, always closes.
    """
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=30.0, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.execute("COMMIT")
    except Exception:
        try:
            connection.execute("ROLLBACK")
        except Exception:  # pragma: no cover - connection already broken
            pass
        raise
    finally:
        connection.close()


@contextmanager
def read_connection() -> Iterator[sqlite3.Connection]:
    """Read-only connection for diagnostics.

    Deliberately avoids ``BEGIN IMMEDIATE`` so a ``/health/deep`` poll can never
    block (or be blocked by) a running pipeline write.  Opens the file with
    ``mode=ro`` and falls back to a normal handle (SELECT-only, no write lock)
    when SQLite refuses a read-only WAL handle (missing ``-shm`` file).
    """
    path = get_db_path()
    connection: Optional[sqlite3.Connection] = None
    try:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("SELECT 1").fetchone()  # force the handle to open now
    except sqlite3.Error as exc:
        logger.debug("Read-only handle unavailable (%s); using a SELECT-only handle.", exc)
        if connection is not None:
            try:
                connection.close()
            except sqlite3.Error:  # pragma: no cover - already closed
                pass
        connection = sqlite3.connect(str(path), timeout=5.0)
        connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def init_db() -> Path:
    """Create the database file plus every table/index. Idempotent."""
    global _initialised

    with _init_lock:
        path = get_db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with get_connection() as connection:
                for statement in SCHEMA_STATEMENTS:
                    connection.execute(statement)
            _initialised = True
            logger.info("SQLite ready at %s", path)
        except sqlite3.Error as exc:
            logger.error("Could not initialise the database at %s: %s", path, exc)
            raise
    return path


def is_initialised() -> bool:
    """True once :func:`init_db` has succeeded at least once in this process."""
    return _initialised and get_db_path().exists()


# Ensure the file/tables exist as soon as the module is imported.
init_db()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    return dict(row) if row is not None else None


def _load_json(raw: Any, fallback: Any = None) -> Any:
    if raw in (None, ""):
        return fallback
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        logger.debug("Could not decode stored JSON payload: %r", raw)
        return fallback


def _dump_json(payload: Any) -> Optional[str]:
    if payload is None:
        return None
    try:
        return json.dumps(payload, default=str)
    except (TypeError, ValueError) as exc:
        logger.warning("Could not serialise payload to JSON (%s); dropping it.", exc)
        return None


# --------------------------------------------------------------------------- #
# Route helpers
# --------------------------------------------------------------------------- #
def create_route(route_id: Optional[str] = None) -> Dict[str, Any]:
    """Insert a new route session and return its record."""
    identifier = route_id or str(uuid.uuid4())
    timestamp = _now()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO routes (route_id, created_at, status, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(route_id) DO UPDATE SET status = 'created', updated_at = excluded.updated_at
            """,
            (identifier, timestamp, ROUTE_STATUS_CREATED, timestamp),
        )
    logger.info("Created route session %s", identifier)
    return {
        "route_id": identifier,
        "created_at": timestamp,
        "status": ROUTE_STATUS_CREATED,
        "status_detail": None,
        "overall_score": None,
        "overall_status": None,
        "recommendation": None,
    }


def save_route(route_id: str, status: Optional[str] = None, **fields: Any) -> Dict[str, Any]:
    """Convenience wrapper: create the route if missing, then apply ``fields``."""
    existing = get_route(route_id)
    if existing is None:
        create_route(route_id)
    if status or fields:
        update_route_status(route_id, status or ROUTE_STATUS_CREATED, **fields)
    return get_route(route_id) or {}


def get_route(route_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single route record, or ``None`` when unknown."""
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM routes WHERE route_id = ?", (route_id,)).fetchone()
    return _row_to_dict(row)


def route_exists(route_id: str) -> bool:
    with get_connection() as connection:
        row = connection.execute("SELECT 1 FROM routes WHERE route_id = ? LIMIT 1", (route_id,)).fetchone()
    return row is not None


def update_route_status(route_id: str, status: str, *, status_detail: Optional[str] = None,
                        overall_score: Optional[int] = None, overall_status: Optional[str] = None,
                        recommendation: Optional[str] = None) -> bool:
    """Update the lifecycle status (and optionally the summary fields) of a route.

    ``None`` values leave the existing column untouched.
    """
    assignments = ["status = ?", "updated_at = ?"]
    parameters: List[Any] = [status, _now()]

    for column, value in (
        ("status_detail", status_detail),
        ("overall_score", overall_score),
        ("overall_status", overall_status),
        ("recommendation", recommendation),
    ):
        if value is not None:
            assignments.append(f"{column} = ?")
            parameters.append(value)

    parameters.append(route_id)
    with get_connection() as connection:
        cursor = connection.execute(
            f"UPDATE routes SET {', '.join(assignments)} WHERE route_id = ?",  # noqa: S608 - fixed column list
            parameters,
        )
        updated = cursor.rowcount > 0
    if not updated:
        logger.warning("Tried to update unknown route %s", route_id)
    return updated


def claim_route_for_processing(route_id: str, detail: str = "queued for processing") -> bool:
    """Atomically move a route to ``processing``; ``False`` if already claimed.

    A plain read-then-write check is racy: ``uvicorn --workers 2`` runs the API in
    two processes, so two concurrent ``POST /process`` calls could both start a
    pipeline for the same route. SQLite's compare-and-set inside a single UPDATE
    makes the claim atomic across processes.
    """
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE routes
               SET status = ?, status_detail = ?, updated_at = ?
             WHERE route_id = ? AND status IS NOT ?
            """,
            (ROUTE_STATUS_PROCESSING, detail, _now(), route_id, ROUTE_STATUS_PROCESSING),
        )
        claimed = cursor.rowcount == 1
    if not claimed:
        logger.info("Route %s is already being processed; claim rejected.", route_id)
    return claimed


def list_routes(limit: int = 100) -> List[Dict[str, Any]]:
    """Most recent routes first, with their segment/image counters."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT r.*,
                   (SELECT COUNT(*) FROM route_images i WHERE i.route_id = r.route_id) AS image_count,
                   (SELECT COUNT(*) FROM segments s     WHERE s.route_id = r.route_id) AS segment_count
            FROM routes r
            ORDER BY r.created_at DESC, r.route_id DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
    return [dict(row) for row in rows]


# --------------------------------------------------------------------------- #
# Uploaded image helpers
# --------------------------------------------------------------------------- #
def next_segment_id(route_id: str) -> int:
    """Next free 10 m segment number for a route (1-based)."""
    with get_connection() as connection:
        row = connection.execute(
            "SELECT COALESCE(MAX(segment_id), 0) AS max_segment FROM route_images WHERE route_id = ?",
            (route_id,),
        ).fetchone()
    return int(row["max_segment"] or 0) + 1


def add_route_image(route_id: str, filename: str, image_path: str, *, segment_id: Optional[int] = None,
                    image_url: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Append one uploaded photo (and its IMU/GPS metadata) to a route."""
    imu = metadata.get("imu") if isinstance(metadata, dict) and isinstance(metadata.get("imu"), dict) else {}
    gps = metadata.get("gps") if isinstance(metadata, dict) and isinstance(metadata.get("gps"), dict) else {}

    def _num(value: Any) -> Optional[float]:
        try:
            if value is None or isinstance(value, bool):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    resolved_segment = int(segment_id) if segment_id else next_segment_id(route_id)
    payload = (
        route_id,
        resolved_segment,
        str(filename),
        str(image_path),
        image_url,
        _num(gps.get("lat")),
        _num(gps.get("lon")),
        _num(imu.get("pitch_deg")),
        _num(imu.get("roll_deg")),
        _dump_json(metadata or {}),
        _now(),
    )
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO route_images
                (route_id, segment_id, filename, image_path, image_url,
                 gps_lat, gps_lon, pitch_deg, roll_deg, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(route_id, segment_id) DO UPDATE SET
                filename      = excluded.filename,
                image_path    = excluded.image_path,
                image_url     = excluded.image_url,
                gps_lat       = excluded.gps_lat,
                gps_lon       = excluded.gps_lon,
                pitch_deg     = excluded.pitch_deg,
                roll_deg      = excluded.roll_deg,
                metadata_json = excluded.metadata_json
            """,
            payload,
        )
        row = connection.execute(
            "SELECT * FROM route_images WHERE route_id = ? AND segment_id = ?",
            (route_id, resolved_segment),
        ).fetchone()
    logger.info("Stored image %s for route %s (segment %d)", filename, route_id, resolved_segment)
    return _row_to_dict(row) or {}


def get_route_images(route_id: str) -> List[Dict[str, Any]]:
    """All uploaded photos of a route in segment order, metadata decoded."""
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM route_images WHERE route_id = ? ORDER BY segment_id ASC, id ASC",
            (route_id,),
        ).fetchall()
    images: List[Dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        record["metadata"] = _load_json(record.get("metadata_json"), {}) or {}
        images.append(record)
    return images


def get_uploaded_segments_payload(route_id: str) -> List[Dict[str, Any]]:
    """Build the ``images_data`` list consumed by ``pipeline.run_full_pipeline``."""
    payload: List[Dict[str, Any]] = []
    for record in get_route_images(route_id):
        metadata = record.get("metadata") or {}
        if not metadata:  # rebuild from the flat columns when the JSON is gone
            metadata = {
                "gps": {"lat": record.get("gps_lat"), "lon": record.get("gps_lon")},
                "imu": {"pitch_deg": record.get("pitch_deg") or 0.0,
                        "roll_deg": record.get("roll_deg") or 0.0},
            }
        payload.append(
            {
                "image_path": record.get("image_path"),
                "metadata": metadata,
                "segment_id": record.get("segment_id"),
                "route_id": route_id,
            }
        )
    return payload


# --------------------------------------------------------------------------- #
# Pipeline result helpers
# --------------------------------------------------------------------------- #
def save_segment_results(route_id: str, segments: Iterable[Dict[str, Any]]) -> int:
    """Upsert pipeline output rows into ``segments``; returns the number written."""
    written = 0
    timestamp = _now()
    with get_connection() as connection:
        for index, segment in enumerate(segments or []):
            if not isinstance(segment, dict):
                continue
            try:
                segment_id = int(segment.get("segment_id") or index + 1)
            except (TypeError, ValueError):
                segment_id = index + 1
            score = segment.get("score")
            try:
                score = int(score) if score is not None else None
            except (TypeError, ValueError):
                score = None
            try:
                defect_area = float(segment.get("defect_area_m2") or 0.0)
            except (TypeError, ValueError):
                defect_area = 0.0

            connection.execute(
                """
                INSERT INTO segments
                    (route_id, segment_id, score, status, defect_area_m2, mask_url,
                     recommendation, details_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(route_id, segment_id) DO UPDATE SET
                    score           = excluded.score,
                    status          = excluded.status,
                    defect_area_m2  = excluded.defect_area_m2,
                    mask_url        = excluded.mask_url,
                    recommendation  = excluded.recommendation,
                    details_json    = excluded.details_json,
                    updated_at      = excluded.updated_at
                """,
                (
                    route_id,
                    segment_id,
                    score,
                    segment.get("status"),
                    defect_area,
                    segment.get("mask_url"),
                    segment.get("recommendation"),
                    _dump_json(segment),
                    timestamp,
                    timestamp,
                ),
            )
            written += 1
    logger.info("Wrote %d segment result(s) for route %s", written, route_id)
    return written


def get_route_segments(route_id: str) -> List[Dict[str, Any]]:
    """Stored segment rows with their full pipeline detail payload merged in."""
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM segments WHERE route_id = ? ORDER BY segment_id ASC",
            (route_id,),
        ).fetchall()

    segments: List[Dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        details = _load_json(record.get("details_json"), {})
        if isinstance(details, dict) and details:
            # Row columns first (so the documented schema columns are always
            # present), then the richer pipeline payload on top.  The raw blob is
            # dropped to keep API responses small - its content is inline now.
            merged = {**record, **details}
            merged.pop("details_json", None)
            segments.append(merged)
        else:
            segments.append(record)
    return segments


def get_route_summary(route_id: str) -> Optional[Dict[str, Any]]:
    """Complete route payload: route row, counters, aggregates and segments."""
    route = get_route(route_id)
    if route is None:
        return None

    segments = get_route_segments(route_id)
    images = get_route_images(route_id)
    scores = [int(seg.get("score") or 0) for seg in segments if seg.get("score") is not None]
    total_defect = round(sum(float(seg.get("defect_area_m2") or 0) for seg in segments), 4)
    total_pothole = round(sum(float(seg.get("pothole_area_m2") or 0) for seg in segments), 4)
    total_crack = round(sum(float(seg.get("crack_area_m2") or 0) for seg in segments), 4)

    overall_score = route.get("overall_score")
    if overall_score is None:
        overall_score = int(round(sum(scores) / len(scores))) if scores else None

    overall_status = route.get("overall_status")
    if not overall_status and scores:
        if any(str(seg.get("status")) == "Bad" for seg in segments):
            overall_status = "Bad"
        elif overall_score is not None and overall_score >= 70:
            overall_status = "Good"
        elif overall_score is not None and overall_score >= 40:
            overall_status = "Fair"
        else:
            overall_status = "Bad"

    return {
        "route": route,
        "route_id": route_id,
        "status": route.get("status"),
        "status_detail": route.get("status_detail"),
        "created_at": route.get("created_at"),
        "updated_at": route.get("updated_at"),
        "overall_score": overall_score,
        "overall_status": overall_status,
        "recommendation": route.get("recommendation"),
        "segment_length_m": SEGMENT_LENGTH_M,
        "counts": {
            "images": len(images),
            "segments": len(segments),
            "good_segments": sum(1 for seg in segments if seg.get("status") == "Good"),
            "fair_segments": sum(1 for seg in segments if seg.get("status") == "Fair"),
            "bad_segments": sum(1 for seg in segments if seg.get("status") == "Bad"),
            "pothole_segments": sum(1 for seg in segments if seg.get("has_pothole")),
            "failed_segments": sum(1 for seg in segments if seg.get("error")),
        },
        "totals": {
            "defect_area_m2": total_defect,
            "pothole_area_m2": total_pothole,
            "crack_area_m2": total_crack,
        },
        "images": images,
        "segments": segments,
    }


def delete_route(route_id: str) -> bool:
    """Remove a route with its images and segment rows. Used by tests/cleanup."""
    with get_connection() as connection:
        connection.execute("DELETE FROM segments WHERE route_id = ?", (route_id,))
        connection.execute("DELETE FROM route_images WHERE route_id = ?", (route_id,))
        cursor = connection.execute("DELETE FROM routes WHERE route_id = ?", (route_id,))
        deleted = cursor.rowcount > 0
    logger.info("Deleted route %s (rows removed: %s)", route_id, deleted)
    return deleted


def ping() -> float:
    """Round-trip the database read-only and return the latency in milliseconds."""
    started = time.perf_counter()
    with read_connection() as connection:
        connection.execute("SELECT 1").fetchone()
    return round((time.perf_counter() - started) * 1000.0, 3)


def table_counts() -> Dict[str, int]:
    """Row count per table (read-only; safe while a pipeline is writing)."""
    counts: Dict[str, int] = {}
    with read_connection() as connection:
        for table in ("routes", "route_images", "segments"):
            row = connection.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()  # noqa: S608 - fixed names
            counts[table] = int(row["c"] or 0)
    return counts


def stats() -> Dict[str, Any]:
    """Row counts per table - used by the health endpoints and by tests."""
    counts = table_counts()
    path = get_db_path()
    return {
        "database_path": str(path),
        "exists": path.exists(),
        "routes": counts.get("routes", 0),
        "images": counts.get("route_images", 0),
        "segments": counts.get("segments", 0),
    }
