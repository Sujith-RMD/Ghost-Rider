"""Deep system diagnostics for the Ghost-Rider backend.

``GET /health``       - liveness only, no I/O, safe for a load balancer.
``GET /health/deep``  - probes every dependency and returns the documented shape::

    {
      "status": "healthy" | "degraded" | "unhealthy",
      "checks": {
        "database":   {"status": "ok", "latency_ms": 1.1},
        "s3":         {"status": "ok" | "degraded_local_fallback", "bucket": "..."},
        "bedrock":    {"status": "ok" | "fallback_templates_active", "model": "..."},
        "yolo_model": {"status": "ok", "weights": "yolov8n-seg.pt"}
      }
    }

Design notes
------------
* **Nothing raises.**  Every probe is isolated; a broken dependency becomes a
  reported status instead of a 500, because this endpoint is what an operator
  (or an auto-healing Alarman) calls when things are already wrong.
* **AWS probes are cached and time-boxed.**  ``head_bucket`` / a 1-token Bedrock
  ``converse`` are the only network calls; they run on dedicated short-timeout
  clients and results are cached for ``HEALTH_PROBE_TTL`` seconds so frequent
  polling cannot amplify an outage or burn Bedrock quota.
* **No secrets.**  Only bucket names, regions, model ids, paths and states are
  returned - never credentials or tokens.
* ``?probe=none`` skips all network I/O (configuration-only view),
  ``?probe=aws`` forces a fresh probe, ``?probe=auto`` (default) uses the cache.
"""

from __future__ import annotations

import logging
import shutil
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple

from fastapi import APIRouter, Query

try:  # flat layout: `app` is a top-level package, services sit beside it
    import bedrock_service
    import database
    import pipeline
    import s3_service
except ImportError:  # package layout: backend.app.health
    from backend import bedrock_service, database, pipeline, s3_service  # type: ignore[no-redef]

try:
    from . import __version__
    from .config import get_settings
except ImportError:  # pragma: no cover - package layout fallback
    from app import __version__  # type: ignore[no-redef]
    from app.config import get_settings  # type: ignore[no-redef]

logger = logging.getLogger("ghost_rider.health")

router = APIRouter(prefix="/health", tags=["health"])

STATUS_OK = "ok"
STATUS_S3_FALLBACK = "degraded_local_fallback"
STATUS_BEDROCK_FALLBACK = "fallback_templates_active"
STATUS_ERROR = "error"
STATUS_UNAVAILABLE = "unavailable"

_PROBE_LOCK = threading.Lock()
_PROBE_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def _cached_probe(name: str, ttl: float, factory: Callable[[], Dict[str, Any]],
                  *, force: bool) -> Dict[str, Any]:
    """Run ``factory`` at most once per ``ttl`` seconds (thread-safe)."""
    now = time.time()
    with _PROBE_LOCK:
        cached = _PROBE_CACHE.get(name)
        if cached and not force and (now - cached[0]) < max(0.0, ttl):
            return dict(cached[1])

    result: Dict[str, Any]
    try:
        result = factory()
    except Exception as exc:  # pragma: no cover - factory never raises by design
        logger.warning("Health probe '%s' crashed: %s: %s", name, type(exc).__name__, exc)
        result = {"probe_error": f"{type(exc).__name__}: {exc}"}

    with _PROBE_LOCK:
        _PROBE_CACHE[name] = (now, dict(result))
    return result


def clear_probe_cache() -> None:
    """Drop cached AWS probe results (used by tests and by ``?probe=aws``)."""
    with _PROBE_LOCK:
        _PROBE_CACHE.clear()


def _error_code(exc: BaseException) -> str:
    """Best-effort AWS error code from a botocore exception."""
    try:
        return str(((getattr(exc, "response", {}) or {}).get("Error", {}) or {}).get("Code", "")) or type(exc).__name__
    except Exception:  # pragma: no cover - defensive
        return type(exc).__name__


# --------------------------------------------------------------------------- #
# Individual checks
# --------------------------------------------------------------------------- #
def check_database() -> Dict[str, Any]:
    """Round-trip the SQLite database (read-only) and report row counts."""
    started = time.perf_counter()
    try:
        latency_ms = database.ping()
        counts = database.table_counts()
        path = database.get_db_path()
        return {
            "status": STATUS_OK,
            "latency_ms": round(latency_ms, 3),
            "database_path": str(path),
            "exists": path.exists(),
            "tables": counts,
            "total_rows": sum(int(value) for value in counts.values()),
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        }
    except Exception as exc:
        logger.error("Database health check failed: %s: %s", type(exc).__name__, exc)
        return {
            "status": STATUS_ERROR,
            "latency_ms": None,
            "database_path": str(database.get_db_path()),
            "error": f"{type(exc).__name__}: {exc}",
        }


def check_s3(*, probe: bool) -> Dict[str, Any]:
    """Report S3 readiness, optionally verifying the bucket with ``head_bucket``."""
    settings = get_settings()
    info: Dict[str, Any] = {
        "bucket": settings.AWS_S3_BUCKET_NAME or None,
        "region": settings.AWS_REGION,
        "endpoint_url": settings.AWS_S3_ENDPOINT_URL,
        "raw_prefix": settings.S3_RAW_PREFIX,
        "mask_prefix": settings.S3_MASK_PREFIX,
        "local_fallback_prefix": s3_service.UPLOAD_URL_PREFIX,
        "verified": False,
    }

    if not settings.s3_configured:
        info["status"] = STATUS_S3_FALLBACK
        info["reason"] = "s3_not_configured"
        info["detail"] = "Uploads and mask overlays are served from the local /uploads URL."
        return info

    if not probe:
        info["status"] = STATUS_OK
        info["detail"] = "Credentials and bucket are configured (probe skipped)."
        return info

    def _probe_bucket() -> Dict[str, Any]:
        client = s3_service.get_s3_client(fast=True)
        if client is None:
            return {"verified": False, "error": "client_unavailable"}
        try:
            client.head_bucket(Bucket=settings.AWS_S3_BUCKET_NAME)
            return {"verified": True}
        except Exception as exc:
            code = _error_code(exc)
            # head_bucket needs s3:ListBucket. A denial means "the bucket may well
            # work for PutObject/GetObject" - it is not proof of an outage, so it
            # is reported as unverified instead of degraded.
            if code in {"403", "AccessDenied", "AccessDeniedException", "Forbidden"}:
                return {
                    "verified": False,
                    "note": ("head_bucket denied (needs s3:ListBucket); object "
                             "PutObject/GetObject access is unaffected"),
                    "error": code,
                }
            if code in {"404", "NoSuchBucket", "NotFound"}:
                return {"verified": False, "error": "NoSuchBucket", "missing_bucket": True}
            return {"verified": False, "error": code}

    result = _cached_probe("s3.head_bucket", settings.HEALTH_PROBE_TTL, _probe_bucket, force=False)
    info.update(result)

    if result.get("verified"):
        info["status"] = STATUS_OK
        info["detail"] = "head_bucket succeeded."
    elif result.get("missing_bucket"):
        info["status"] = STATUS_S3_FALLBACK
        info["detail"] = (
            f"Bucket '{settings.AWS_S3_BUCKET_NAME}' does not exist - run "
            "scripts/setup_aws_resources.py. Uploads fall back to local /uploads URLs."
        )
    elif result.get("error") in {"client_unavailable"} or "Throttling" in str(result.get("error", "")):
        info["status"] = STATUS_S3_FALLBACK
        info["detail"] = f"S3 client could not be used ({result.get('error')}); local fallback active."
    else:
        info["status"] = STATUS_OK
        info["detail"] = str(result.get("note") or "Bucket reachability unverified.")
    return info


def check_bedrock(*, probe: bool) -> Dict[str, Any]:
    """Report Bedrock readiness, optionally verifying model access with a tiny call."""
    settings = get_settings()
    stats = bedrock_service.health_status()
    info: Dict[str, Any] = {
        "model": settings.BEDROCK_MODEL_ID,
        "region": settings.bedrock_region,
        "fallback_models": settings.bedrock_models,
        "max_attempts": settings.BEDROCK_MAX_ATTEMPTS,
        "verified": False,
        "retry_stats": stats.get("retry_stats"),
        "cached_recommendations": stats.get("cached_recommendations"),
    }

    if not settings.bedrock_configured:
        info["status"] = STATUS_BEDROCK_FALLBACK
        info["reason"] = "bedrock_not_configured" if settings.BEDROCK_ENABLED else "bedrock_disabled"
        info["detail"] = "Deterministic civil-engineering rule templates are active."
        return info

    if not probe:
        info["status"] = STATUS_OK
        info["detail"] = "Credentials are configured (probe skipped)."
        return info

    def _probe_model() -> Dict[str, Any]:
        client = bedrock_service.get_bedrock_client(fast=True)
        if client is None:
            return {"verified": False, "error": "client_unavailable"}
        settings_local = get_settings()
        try:
            client.converse(
                modelId=settings_local.BEDROCK_MODEL_ID,
                messages=[{"role": "user", "content": [{"text": "ping"}]}],
                inferenceConfig={"maxTokens": 5, "temperature": 0},
            )
            return {"verified": True}
        except Exception as exc:
            code = _error_code(exc)
            lowered = code.lower()
            if "throttl" in lowered or "toomanyrequests" in lowered:
                return {"verified": True, "note": f"model reachable but throttled ({code})"}
            return {"verified": False, "error": code}

    result = _cached_probe("bedrock.converse", settings.HEALTH_PROBE_TTL, _probe_model, force=False)
    info.update(result)

    if result.get("verified"):
        info["status"] = STATUS_OK
        info["detail"] = str(result.get("note") or "converse probe succeeded.")
    else:
        info["status"] = STATUS_BEDROCK_FALLBACK
        info["detail"] = (
            f"Model '{settings.BEDROCK_MODEL_ID}' was not usable ({result.get('error')}); "
            "enable model access in the Bedrock console or rely on the rule templates."
        )
    return info


def check_yolo(*, probe: bool = False) -> Dict[str, Any]:
    """Report the segmentation model state (and optionally load it)."""
    settings = get_settings()
    status = pipeline.model_status()
    weights_path = settings.yolo_weights
    loaded = bool(status.get("loaded"))

    if not loaded and probe:
        loaded = pipeline.load_model() is not None
        status = pipeline.model_status()

    classes = status.get("classes")
    state = STATUS_OK if (loaded or weights_path.exists()) else STATUS_UNAVAILABLE
    return {
        "status": state,
        "weights": settings.YOLO_WEIGHTS_PATH,
        "weights_path": str(weights_path),
        "exists": weights_path.exists(),
        "loaded": bool(status.get("loaded")),
        "classes": len(classes) if isinstance(classes, list) else None,
        "class_names": classes if isinstance(classes, list) and len(classes) <= 12 else None,
        "ultralytics_installed": bool(status.get("ultralytics_installed")),
        "error": status.get("error"),
    }


def check_storage() -> Dict[str, Any]:
    """Verify the media directory is writable and report free disk space."""
    settings = get_settings()
    uploads = settings.uploads_path
    try:
        uploads.mkdir(parents=True, exist_ok=True)
        probe_file = uploads / ".health-write-test"
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink(missing_ok=True)
        usage = shutil.disk_usage(str(uploads))
        free_mb = round(usage.free / (1024 * 1024), 1)
        return {
            "status": STATUS_OK,
            "uploads_dir": str(uploads),
            "writable": True,
            "free_mb": free_mb,
            "total_mb": round(usage.total / (1024 * 1024), 1),
            "detail": "low disk space" if free_mb < 512 else "ok",
        }
    except Exception as exc:
        logger.error("Storage health check failed: %s: %s", type(exc).__name__, exc)
        return {
            "status": STATUS_ERROR,
            "uploads_dir": str(uploads),
            "writable": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #
def _overall_status(checks: Dict[str, Dict[str, Any]]) -> str:
    """healthy = everything verified/OK, degraded = working via a fallback."""
    if checks.get("database", {}).get("status") != STATUS_OK:
        return "unhealthy"
    if checks.get("storage", {}).get("status") == STATUS_ERROR:
        return "unhealthy"
    acceptable = {STATUS_OK, STATUS_S3_FALLBACK, STATUS_BEDROCK_FALLBACK}
    if any(check.get("status") not in acceptable for check in checks.values()):
        return "degraded"
    if checks.get("s3", {}).get("status") == STATUS_OK and checks.get("bedrock", {}).get("status") == STATUS_OK:
        return "healthy"
    return "degraded"


def run_deep_checks(probe: str = "auto") -> Dict[str, Any]:
    """Run every dependency check and aggregate them (never raises)."""
    settings = get_settings()
    network_probe = probe in {"auto", "aws"}
    force = probe == "aws"
    if force:
        clear_probe_cache()

    started = time.perf_counter()
    checks: Dict[str, Dict[str, Any]] = {
        "database": check_database(),
        "s3": check_s3(probe=network_probe),
        "bedrock": check_bedrock(probe=network_probe),
        "yolo_model": check_yolo(probe=probe == "aws"),
        "storage": check_storage(),
    }
    status = _overall_status(checks)
    warnings = settings.warnings()

    return {
        "status": status,
        "mode": "full_cloud" if (settings.s3_configured and settings.bedrock_configured) else "fallback",
        "version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "probe": probe,
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        "checks": checks,
        "config": settings.redacted(),
        "warnings": warnings,
        "notes": [
            "status=degraded means the API is fully functional using documented fallbacks "
            "(local /uploads URLs and/or rule-based recommendations).",
            "AWS probes are cached for HEALTH_PROBE_TTL seconds; use ?probe=aws to force a fresh check.",
        ],
    }


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@router.get("", summary="Liveness probe (no I/O)")
async def health_liveness() -> Dict[str, Any]:
    """Cheap liveness probe - safe to poll from a target group every few seconds."""
    return {
        "status": STATUS_OK,
        "service": "Ghost-Rider Road Quality API",
        "version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


@router.get("/deep", summary="Deep dependency diagnostics")
async def health_deep(
    probe: str = Query(
        default="auto",
        pattern="^(auto|aws|none)$",
        description="auto = cached AWS probes, aws = force fresh probes, none = configuration only",
    ),
) -> Dict[str, Any]:
    """Probe database, S3, Bedrock, the YOLO model and local storage."""
    return run_deep_checks(probe=probe)


__all__ = [
    "check_bedrock",
    "check_database",
    "check_s3",
    "check_storage",
    "check_yolo",
    "clear_probe_cache",
    "router",
    "run_deep_checks",
]
