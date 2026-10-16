"""Ghost-Rider queue stats + DB table seeds for the v1 contract.

Ownership: Backend & AWS AI.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from . import database

logger = logging.getLogger("ghost_rider.queues")


def _table_columns(conn: Any, table: str) -> set:
    try:
        return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except Exception:
        return set()


def _ensure_column(conn: Any, table: str, column: str, ddl_type: str) -> None:
    """Additive migration: add ``column`` to ``table`` only if it is missing."""
    if table and column and column not in _table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")


def ensure_v1_tables() -> None:
    """Create the extra tables the v1 contract relies on that did not exist before."""
    statements = (
        """
        CREATE TABLE IF NOT EXISTS upload_slots (
            upload_id   TEXT PRIMARY KEY,
            object_key  TEXT NOT NULL,
            filename    TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'ready',
            created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            expires_at  TIMESTAMP,
            updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS jobs (
            job_id          TEXT PRIMARY KEY,
            parent_type     TEXT NOT NULL,
            parent_id       TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'queued',
            error_reason    TEXT,
            attempt_count   INTEGER NOT NULL DEFAULT 0,
            received_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            started_at      TIMESTAMP,
            completed_at    TIMESTAMP,
            updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            lease_expires_at TIMESTAMP,
            versions_json   TEXT,
            metadata_json   TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS job_events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id     TEXT NOT NULL,
            status     TEXT NOT NULL,
            detail     TEXT,
            at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS frames (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT NOT NULL,
            frame_index     INTEGER NOT NULL,
            source_mode     TEXT NOT NULL,
            filename        TEXT NOT NULL,
            received_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            metadata_json   TEXT,
            UNIQUE (session_id, frame_index)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id       TEXT PRIMARY KEY,
            mode             TEXT NOT NULL,
            camera_id        TEXT,
            calibration_id   TEXT,
            status           TEXT NOT NULL DEFAULT 'live',
            created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at      TIMESTAMP,
            frame_count      INTEGER NOT NULL DEFAULT 0,
            processed_count  INTEGER NOT NULL DEFAULT 0,
            rejected_count   INTEGER NOT NULL DEFAULT 0,
            dropped_count    INTEGER NOT NULL DEFAULT 0,
            last_capture_at  TIMESTAMP,
            last_processed_at TIMESTAMP,
            is_stale         INTEGER NOT NULL DEFAULT 0,
            updated_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS samples (
            sample_id        TEXT PRIMARY KEY,
            segment_id       INTEGER NOT NULL,
            route_id         TEXT,
            image_path       TEXT,
            image_url        TEXT,
            mask_url         TEXT,
            raw_url          TEXT,
            captured_at      TIMESTAMP,
            gps_json         TEXT,
            geometry_valid   INTEGER NOT NULL DEFAULT 0,
            area_json        TEXT,
            quality_json     TEXT,
            metrics_json     TEXT,
            evidence_json    TEXT,
            detection_json   TEXT,
            score_json       TEXT,
            reference_json   TEXT,
            model_version    TEXT,
            feature_version  TEXT,
            scoring_version  TEXT,
            created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            error            TEXT,
            canonical_json   TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS reports (
            report_id            TEXT PRIMARY KEY,
            assessment_id        TEXT NOT NULL,
            content_json         TEXT NOT NULL,
            generated_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            bedrock_model_id     TEXT,
            factual_input_hash   TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS processed_frames (
            idempotency_key TEXT PRIMARY KEY,
            session_id      TEXT NOT NULL,
            frame_index     INTEGER NOT NULL,
            model_version   TEXT NOT NULL,
            sample_id       TEXT,
            processed_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_frames_session ON frames (session_id, frame_index)",
        "CREATE INDEX IF NOT EXISTS idx_jobs_parent ON jobs (parent_type, parent_id)",
        "CREATE INDEX IF NOT EXISTS idx_samples_route ON samples (route_id, segment_id)",
        "CREATE INDEX IF NOT EXISTS idx_processed_frames_session ON processed_frames (session_id, frame_index)",
    )

    try:
        with database.get_connection() as conn:
            for statement in statements:
                try:
                    conn.execute(statement)
                except Exception as exc:
                    logger.warning("Could not create v1 table: %s", exc)
            # Additive migrations for databases created before these columns existed.
            for column, ddl_type in (("lease_expires_at", "TIMESTAMP"), ("metadata_json", "TEXT")):
                try:
                    _ensure_column(conn, "jobs", column, ddl_type)
                except Exception as exc:
                    logger.warning("Could not migrate jobs.%s: %s", column, exc)
            for column, ddl_type in (("canonical_json", "TEXT"), ("detection_json", "TEXT")):
                try:
                    _ensure_column(conn, "samples", column, ddl_type)
                except Exception as exc:
                    logger.warning("Could not migrate samples.%s: %s", column, exc)
    except Exception as exc:
        logger.warning("Could not initialize v1 tables: %s", exc)


def queue_stats() -> Dict[str, Any]:
    """Expose current ingestion queue counters."""
    try:
        from .ingestion.queue import get_ingestion_queue
        queue = get_ingestion_queue()
        stats = queue.stats
        return {
            "queue_size": len(queue),
            "max_size": queue.max_size,
            "received": stats.received,
            "processed": stats.processed,
            "rejected": stats.rejected,
            "dropped": stats.dropped,
        }
    except Exception as exc:
        logger.debug("Could not read queue stats: %s", exc)
        return {"error": f"{type(exc).__name__}: {exc}"}
