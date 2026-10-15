"""Ghost-Rider FastAPI application factory and server entrypoint.

Configures:
- Application lifespan (SQLite initialization, WAL mode, bounded queue)
- v1 API router (/v1)
- Health diagnostics router (/health and /health/deep)
- CORS middleware
- Static media mount (/uploads)
- Standardized error handling

Ownership: Backend & AWS AI
Reference: docs/final_plan.md (Section 11)
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import database, s3_service
from ..app.config import get_settings
from ..app.health import router as health_router
from .v1 import _ensure_v1_tables, router as v1_router

logger = logging.getLogger("ghost_rider.api.server")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for startup and shutdown procedures."""
    logger.info("Initializing Ghost-Rider backend service...")

    # Ensure uploads directory
    uploads_dir = s3_service.UPLOADS_DIR
    uploads_dir.mkdir(parents=True, exist_ok=True)

    # Initialize SQLite database and v1 tables
    try:
        database.init_db()
        _ensure_v1_tables()
        logger.info("Database initialized successfully at %s", database.get_db_path())
    except Exception as exc:
        logger.error("Database initialization failed: %s", exc)

    # Start the in-process worker for the single-host prototype. Production runs
    # the worker as its own systemd service; set GHOST_RIDER_INLINE_WORKER=false.
    inline_worker = (os.getenv("GHOST_RIDER_INLINE_WORKER", "true") or "true").strip().lower() not in (
        "0", "false", "no",
    )
    if inline_worker:
        try:
            from .. import worker

            worker.start_background_worker()
        except Exception as exc:
            logger.error("Could not start background worker: %s", exc)

    logger.info("Ghost-Rider API service startup complete. Listening for requests.")
    yield
    logger.info("Ghost-Rider API service shutting down.")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title="Ghost-Rider Road Quality API",
        description=(
            "Automated visible road condition assessment for Indian roads. "
            "Exposes durable uploads, live camera capture, route aggregation, "
            "and Amazon Bedrock factual narration."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount v1 router and health router
    app.include_router(v1_router)
    app.include_router(health_router)

    # Mount uploads directory for local static file serving
    uploads_dir = s3_service.UPLOADS_DIR
    uploads_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

    # Global health check at root
    @app.get("/", tags=["health"])
    async def root_health():
        return {
            "name": "Ghost-Rider API",
            "version": "1.0.0",
            "status": "online",
            "docs_url": "/docs",
            "v1_base": "/v1",
        }

    return app


# Module-level instance for ASGI servers (uvicorn backend.api.server:app)
app = create_app()
