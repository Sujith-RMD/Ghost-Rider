"""AWS S3 storage service for Ghost-Rider.

Responsibilities
----------------
* Upload raw road images and defect-mask overlays to S3.
* Hand out presigned GET URLs so the mobile app can render private objects.
* Degrade gracefully: when credentials/bucket are missing or the AWS call
  fails, every function returns a *usable* local URL (``/uploads/...``) that
  ``FastAPI.StaticFiles`` serves, so the pipeline never breaks because of S3.

Configuration is read through :mod:`app.config` (pydantic-settings), with a
last-resort ``os.getenv`` fallback so the module still works standalone.

Public surface
--------------
``upload_file_to_s3``          single upload, never raises (local URL fallback)
``get_presigned_url``          single presign, never raises (local URL fallback)
``get_batch_presigned_urls``   batched + cached presigning for map rendering
``resolve_media_url``          refresh a stored (possibly expired) URL
``ensure_bucket``              create/verify the bucket            (raises on failure)
``put_bucket_lifecycle_policy`` expire raw frames after N days       (raises on failure)
``get_bucket_lifecycle_policy`` inspect the current rule             (raises on failure)

Object key layout (kept in sync with the lifecycle rule in ``scripts/``):

* raw frames      -> ``{S3_RAW_PREFIX}{route_id}/{filename}``   (expired after 7 days)
* mask overlays   -> ``{S3_MASK_PREFIX}{route_id}/mask_{filename}`` (retained)

Environment variables (all defaulted in ``app/config.py``)
----------------------------------------------------------
``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY``  credentials (``AWS_ACCESS_KEY`` ok)
``AWS_REGION``          target region (default ``ap-southeast-2``)
``AWS_S3_BUCKET_NAME``  bucket for images (default ``ghost-rider-road-storage``)
``AWS_S3_ENDPOINT_URL`` optional S3-compatible endpoint (LocalStack / MinIO)
``S3_RETURN_PRESIGNED`` ``true`` (default) -> uploads return a presigned GET URL
``UPLOADS_DIR``         local media root backing ``/uploads``
``PRESIGNED_URL_TTL``   default presign TTL in seconds (3600)
``S3_RAW_PREFIX`` / ``S3_MASK_PREFIX``  object key prefixes
"""

from __future__ import annotations

import logging
import mimetypes
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence
from urllib.parse import urlparse

logger = logging.getLogger("ghost_rider.s3")

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_URL_PREFIX = "/uploads"

_ENV_LOADED = False


def load_project_env() -> None:
    """Best-effort ``.env`` loading (no-op when python-dotenv is unavailable).

    Called at import time so every module sees the same environment. Set
    ``GHOST_RIDER_DISABLE_DOTENV=1`` to skip it (tests/CI must not read a
    developer's ``.env`` and accidentally talk to real AWS).
    """
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    if os.getenv("GHOST_RIDER_DISABLE_DOTENV", "").strip().lower() in {"1", "true", "yes", "on"}:
        return
    try:  # optional dependency - never fatal
        from dotenv import load_dotenv
    except Exception:  # pragma: no cover - optional dependency
        return
    for candidate in (BASE_DIR / ".env", BASE_DIR.parent / ".env"):
        try:
            if candidate.is_file():
                load_dotenv(candidate, override=False)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Could not load %s: %s", candidate, exc)


load_project_env()

try:  # flat layout (``uvicorn main:app`` from backend/)
    from app.config import get_settings_safely
    from app.config import get_settings as _get_settings
    from app.config import reload_settings as _reload_settings
    from app.config import Settings as _Settings
    from app.config import BACKEND_DIR as _BACKEND_DIR  # noqa: F401  (re-exported)
except ImportError:  # package layout (``uvicorn backend.main:app`` from the repo root)
    from backend.app.config import get_settings_safely  # type: ignore[no-redef]
    from backend.app.config import get_settings as _get_settings  # type: ignore[no-redef]
    from backend.app.config import reload_settings as _reload_settings  # type: ignore[no-redef]
    from backend.app.config import Settings as _Settings  # type: ignore[no-redef]
    from backend.app.config import BACKEND_DIR as _BACKEND_DIR  # type: ignore[no-redef]


class S3UnavailableError(RuntimeError):
    """Raised by the *provisioning* helpers when S3 cannot be reached.

    The upload/presign helpers never raise (they degrade to local URLs); the
    bucket/lifecycle management helpers used by ``scripts/setup_aws_resources.py``
    must fail loudly instead of silently pretending the bucket is configured.
    """


def _resolve_uploads_dir() -> Path:
    """Media root from settings, falling back to env/default when settings fail."""
    settings = get_settings_safely()
    if settings is not None:
        return settings.uploads_path
    return Path(os.getenv("UPLOADS_DIR") or (BASE_DIR / "uploads")).resolve()


def _resolve_prefix(attribute: str, env_name: str, default: str) -> str:
    """Normalise an object-key prefix so it always ends with a single ``/``."""
    settings = get_settings_safely()
    value = getattr(settings, attribute, None) if settings is not None else None
    if value in (None, ""):
        value = os.getenv(env_name) or default
    raw = str(value).strip().lstrip("/")
    if raw and not raw.endswith("/"):
        raw += "/"
    return raw


UPLOADS_DIR = _resolve_uploads_dir()
RAW_OBJECT_PREFIX = _resolve_prefix("S3_RAW_PREFIX", "S3_RAW_PREFIX", "uploads/")
MASK_OBJECT_PREFIX = _resolve_prefix("S3_MASK_PREFIX", "S3_MASK_PREFIX", "masks/")


def object_key_prefix(kind: str) -> str:
    """Return the configured key prefix for ``"raw"`` frames or ``"masks"``."""
    return MASK_OBJECT_PREFIX if str(kind).lower() in {"mask", "masks", "overlay"} else RAW_OBJECT_PREFIX


def reload_configuration() -> None:
    """Re-read ``app.config`` settings (credential rotation without a restart)."""
    global UPLOADS_DIR, RAW_OBJECT_PREFIX, MASK_OBJECT_PREFIX
    _reload_settings()
    UPLOADS_DIR = _resolve_uploads_dir()
    RAW_OBJECT_PREFIX = _resolve_prefix("S3_RAW_PREFIX", "S3_RAW_PREFIX", "uploads/")
    MASK_OBJECT_PREFIX = _resolve_prefix("S3_MASK_PREFIX", "S3_MASK_PREFIX", "masks/")
    _client_slots.clear()

# --------------------------------------------------------------------------- #
# Optional boto3 import - the API must still boot without AWS SDK installed.
# --------------------------------------------------------------------------- #
try:  # pragma: no cover - exercised through the fallback path in tests
    import boto3
    from botocore.config import Config as BotoConfig
    from botocore.exceptions import (
        BotoCoreError,
        ClientError,
        EndpointConnectionError,
        NoCredentialsError,
        NoRegionError,
        PartialCredentialsError,
        ReadTimeoutError,
    )

    BOTO3_AVAILABLE = True
except Exception as _import_exc:  # pragma: no cover
    boto3 = None  # type: ignore[assignment]
    BotoConfig = None  # type: ignore[assignment]
    BotoCoreError = ClientError = Exception  # type: ignore[assignment,misc]
    EndpointConnectionError = NoCredentialsError = Exception  # type: ignore[assignment,misc]
    NoRegionError = PartialCredentialsError = ReadTimeoutError = Exception  # type: ignore[assignment,misc]
    BOTO3_AVAILABLE = False
    logger.warning("boto3 is not available (%s); S3 features are disabled.", _import_exc)

DEFAULT_PRESIGN_TTL = int(os.getenv("PRESIGNED_URL_TTL", "3600") or 3600)

_client_lock = threading.Lock()
# slot name -> (cache key, client).  "standard" is used by the request path,
# "probe" is a short-timeout client reserved for health checks.
_client_slots: Dict[str, tuple] = {}

_PRESIGN_CACHE: "OrderedDict[tuple, tuple]" = OrderedDict()
_PRESIGN_CACHE_LOCK = threading.Lock()
PRESIGN_CACHE_MAX_ENTRIES = 2048
PRESIGN_CACHE_TTL_CAP = 300.0  # never cache a signed URL for longer than 5 minutes


# --------------------------------------------------------------------------- #
# Configuration helpers
# --------------------------------------------------------------------------- #
def get_s3_settings() -> dict:
    """Resolve the S3 configuration from :mod:`app.config`.

    Settings are cached process-wide (rebuild with :func:`reload_configuration`),
    and the raw environment is consulted as a last resort so the module keeps
    working even if settings validation fails.
    """
    settings = get_settings_safely()
    env = os.getenv

    def _value(attribute: str, *env_names: str, default: str = "") -> str:
        value = getattr(settings, attribute, None) if settings is not None else None
        if value in (None, ""):
            for name in env_names:
                raw = env(name)
                if raw not in (None, ""):
                    value = raw
                    break
        return str(value if value is not None else default).strip()

    region = _value("AWS_REGION", "AWS_REGION", "AWS_DEFAULT_REGION", default="us-east-1") or "us-east-1"
    return {
        "access_key": _value("AWS_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID", "AWS_ACCESS_KEY"),
        "secret_key": _value("AWS_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY", "AWS_SECRET_KEY"),
        "region": region,
        "bucket": _value("AWS_S3_BUCKET_NAME", "AWS_S3_BUCKET_NAME", "S3_BUCKET_NAME"),
        "endpoint_url": _value("AWS_S3_ENDPOINT_URL", "AWS_S3_ENDPOINT_URL") or None,
        "session_token": _value("AWS_SESSION_TOKEN", "AWS_SESSION_TOKEN") or None,
    }


def _resolve_default_credentials() -> Any:
    """Resolve credentials from boto3's default chain (profile or instance role)."""
    try:
        session = boto3.Session(profile_name=os.getenv("AWS_PROFILE") or None)
        return session.get_credentials()
    except Exception as exc:
        logger.debug("No default AWS credentials resolved: %s", exc)
        return None


def is_s3_enabled() -> bool:
    """True when a bucket is configured and credentials are obtainable.

    Credentials may be explicit keys (env/``.env``), a shared profile, or an
    EC2/ECS **instance role** resolved through boto3's default chain. The plan
    requires IAM instance roles in the deployed environment, where no static keys
    exist, so this must not require ``AWS_ACCESS_KEY_ID`` to be set.
    """
    if not BOTO3_AVAILABLE:
        return False
    settings = get_s3_settings()
    if not settings["bucket"]:
        return False
    if settings["access_key"] and settings["secret_key"]:
        return True
    return _resolve_default_credentials() is not None


def get_s3_client(*, fast: bool = False) -> Optional[Any]:
    """Return a cached boto3 S3 client, or ``None`` when S3 is unusable.

    ``fast=True`` builds a dedicated short-timeout client (connect 2s / read 3s /
    no retries) used by the ``/health/deep`` probe so a degraded AWS region cannot
    stall a health check for the length of the request path's retry budget.
    """
    if not is_s3_enabled():
        return None

    slot = "probe" if fast else "standard"
    settings = get_s3_settings()
    cache_key = (
        settings["access_key"][:6],
        settings["region"],
        settings["bucket"],
        settings["endpoint_url"],
        os.getenv("AWS_PROFILE") or "",
        slot,
    )

    with _client_lock:
        cached = _client_slots.get(slot)
        if cached is not None and cached[0] == cache_key:
            return cached[1]
        try:
            if fast:
                client_config = BotoConfig(
                    retries={"max_attempts": 1, "mode": "standard"},
                    connect_timeout=2,
                    read_timeout=3,
                    signature_version="s3v4",
                )
            else:
                client_config = BotoConfig(
                    retries={"max_attempts": 3, "mode": "standard"},
                    connect_timeout=5,
                    read_timeout=20,
                    signature_version="s3v4",
                )
            client_kwargs: Dict[str, Any] = {
                "region_name": settings["region"],
                "endpoint_url": settings["endpoint_url"],
                "config": client_config,
            }
            # Only pass explicit keys when present; otherwise let boto3 use its
            # default chain (shared profile or EC2/ECS instance role).
            if settings["access_key"] and settings["secret_key"]:
                client_kwargs["aws_access_key_id"] = settings["access_key"]
                client_kwargs["aws_secret_access_key"] = settings["secret_key"]
                if settings["session_token"]:
                    client_kwargs["aws_session_token"] = settings["session_token"]
            client = boto3.client("s3", **client_kwargs)
            _client_slots[slot] = (cache_key, client)
            logger.info("S3 %s client ready (bucket=%s, region=%s).",
                        slot, settings["bucket"], settings["region"])
            return client
        except Exception as exc:
            _client_slots.pop(slot, None)
            logger.error("Failed to create S3 client: %s: %s", type(exc).__name__, exc)
            return None


def reset_clients() -> None:
    """Forget cached S3 clients (used after credential rotation and by tests)."""
    with _client_lock:
        _client_slots.clear()


# --------------------------------------------------------------------------- #
# Key / URL helpers
# --------------------------------------------------------------------------- #
def sanitize_object_name(object_name: str) -> str:
    """Normalise an object name into a safe S3 key (no drive letters, no ``..``)."""
    raw = str(object_name or "").replace("\\", "/")
    parts = [
        segment
        for segment in raw.split("/")
        if segment not in ("", ".", "..") and not segment.endswith(":")
    ]
    if not parts:
        return "unclassified"
    key = "/".join(parts)
    return key[:900]


def build_object_key(file_path: Any, object_name: Optional[str] = None) -> str:
    """Resolve the S3 key for a local file / explicit object name.

    ``object_name`` wins when supplied; otherwise the path is made relative to
    the local ``uploads`` root so the bucket mirrors the on-disk layout.
    """
    if object_name:
        key = sanitize_object_name(object_name)
        if not Path(key).suffix and file_path:
            suffix = Path(str(file_path)).suffix
            if suffix:
                key = f"{key}{suffix}"
        return key

    path = Path(str(file_path or "unclassified"))
    try:
        return sanitize_object_name(path.resolve().relative_to(UPLOADS_DIR).as_posix())
    except Exception:
        return sanitize_object_name(path.name or "unclassified")


def to_local_url(path_or_key: Any) -> str:
    """Convert a filesystem path *or* an object key into a ``/uploads/...`` URL.

    Used as the universal fallback, so it must never raise.
    """
    try:
        raw = str(path_or_key or "").replace("\\", "/").strip()
        if not raw:
            return ""
        source = Path(raw)
        if source.is_absolute():
            try:
                return f"{UPLOAD_URL_PREFIX}/{source.resolve().relative_to(UPLOADS_DIR.resolve()).as_posix()}"
            except ValueError:
                pass
        parts = [segment for segment in raw.split("/") if segment not in ("", ".", "..")]
        if "uploads" in parts:
            index = len(parts) - 1 - parts[::-1].index("uploads")
            tail = parts[index + 1 :]
        elif parts and parts[0].endswith(":"):
            # Absolute path outside the media root: only the file name can be
            # served by /uploads, so do not leak the host filesystem layout.
            tail = parts[-1:]
        else:
            tail = parts
        if not tail:
            return UPLOAD_URL_PREFIX
        return f"{UPLOAD_URL_PREFIX}/{'/'.join(tail)}"
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("to_local_url fallback failed for %r: %s", path_or_key, exc)
        return UPLOAD_URL_PREFIX


def to_local_path(object_key: str) -> Path:
    """Inverse of :func:`to_local_url`: map an object key to its on-disk media path.

    Used by the local (non-S3) upload path and by tests to locate the file a
    client uploaded for a given object key. The configured raw/mask prefixes are
    stripped first, so ``uploads/<id>/frame.jpg`` and ``masks/<id>/mask.jpg``
    resolve under the local media root. This never raises: a malformed key simply
    resolves to the media root.
    """
    try:
        key = extract_object_key(object_key)
        for prefix in (RAW_OBJECT_PREFIX, MASK_OBJECT_PREFIX):
            if prefix and key.startswith(prefix):
                key = key[len(prefix):]
                break
        key = key.lstrip("/")
        if not key:
            return UPLOADS_DIR
        return UPLOADS_DIR / key
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("to_local_path fallback failed for %r: %s", object_key, exc)
        return UPLOADS_DIR


def get_public_url(object_key: str) -> str:
    """Virtual-hosted / path-style HTTPS URL for an object key."""
    settings = get_s3_settings()
    key = sanitize_object_name(object_key)
    if not settings["bucket"]:
        return to_local_url(key)
    if settings["endpoint_url"]:
        return f"{settings['endpoint_url'].rstrip('/')}/{settings['bucket']}/{key}"
    return f"https://{settings['bucket']}.s3.{settings['region']}.amazonaws.com/{key}"


def extract_object_key(url_or_key: str) -> str:
    """Recover an S3 object key from a presigned/public URL (or pass keys through)."""
    raw = str(url_or_key or "").strip()
    if not raw:
        return ""
    if not raw.lower().startswith(("http://", "https://")):
        return sanitize_object_name(raw)

    parsed = urlparse(raw)
    path = parsed.path.lstrip("/")
    settings = get_s3_settings()
    bucket = settings["bucket"]

    if path.startswith(f"{bucket}/"):  # path-style endpoint
        path = path[len(bucket) + 1 :]
    elif bucket and parsed.hostname and parsed.hostname.startswith(f"{bucket}."):  # virtual-hosted
        pass  # path already holds the key
    return sanitize_object_name(path)


# --------------------------------------------------------------------------- #
# Core operations
# --------------------------------------------------------------------------- #
def upload_file_to_s3(file_path: str, object_name: str) -> str:
    """Upload ``file_path`` to S3 under ``object_name`` and return its URL.

    Returns
    -------
    str
        A presigned GET URL on success (or the public HTTPS URL when
        ``S3_RETURN_PRESIGNED=false``).  On ANY failure - missing credentials,
        missing bucket, missing local file, network/permission error - the
        error is logged and the local ``/uploads/...`` path is returned so the
        mobile client can still render the image from the API host.
    """
    path = Path(str(file_path))

    if not path.is_file():
        logger.warning("Upload skipped, local file missing: %s", file_path)
        return to_local_url(file_path)

    if not is_s3_enabled():
        logger.info("S3 not configured - serving %s from local storage.", path.name)
        return to_local_url(file_path)

    settings = get_s3_settings()
    client = get_s3_client()
    if client is None:
        logger.warning("S3 client unavailable - serving %s from local storage.", path.name)
        return to_local_url(file_path)

    key = build_object_key(path, object_name)
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"

    try:
        client.upload_file(
            str(path),
            settings["bucket"],
            key,
            ExtraArgs={"ContentType": content_type, "CacheControl": "public, max-age=604800"},
        )
        logger.info("Uploaded %s -> s3://%s/%s", path.name, settings["bucket"], key)
    except (ClientError, BotoCoreError, NoCredentialsError, PartialCredentialsError, NoRegionError,
            EndpointConnectionError, ReadTimeoutError, OSError) as exc:
        logger.error("S3 upload failed for %s (%s: %s). Falling back to local URL.",
                     path.name, type(exc).__name__, exc)
        return to_local_url(file_path)
    except Exception as exc:  # pragma: no cover - unexpected SDK failure
        logger.error("Unexpected S3 upload error for %s (%s: %s). Falling back to local URL.",
                     path.name, type(exc).__name__, exc)
        return to_local_url(file_path)

    wants_presigned = (os.getenv("S3_RETURN_PRESIGNED", "true") or "true").strip().lower() not in ("0", "false", "no")
    if wants_presigned:
        presigned = get_presigned_url(key)
        if presigned:
            return presigned
    return get_public_url(key)


def get_presigned_url(object_key: str, expires_in: int = DEFAULT_PRESIGN_TTL) -> str:
    """Generate an HTTP GET presigned URL for ``object_key``.

    Falls back to the local ``/uploads/...`` URL when S3 is not configured or
    the signing call fails, and never raises.
    """
    key = extract_object_key(object_key)

    if not is_s3_enabled():
        logger.info("S3 not configured - returning local URL for key '%s'.", key)
        return to_local_url(key)

    client = get_s3_client()
    if client is None:
        return to_local_url(key)

    settings = get_s3_settings()
    try:
        ttl = int(expires_in)
    except (TypeError, ValueError):
        ttl = DEFAULT_PRESIGN_TTL
    ttl = max(60, min(ttl, 604800))  # AWS allows 1s..7d

    try:
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings["bucket"], "Key": key},
            ExpiresIn=ttl,
        )
        if url:
            return url
        logger.warning("Empty presigned URL for key '%s'.", key)
        return to_local_url(key)
    except (ClientError, BotoCoreError, NoCredentialsError, PartialCredentialsError, NoRegionError,
            EndpointConnectionError, ReadTimeoutError) as exc:
        logger.error("Presign failed for '%s' (%s: %s). Falling back to local URL.",
                     key, type(exc).__name__, exc)
        return to_local_url(key)
    except Exception as exc:  # pragma: no cover - unexpected SDK failure
        logger.error("Unexpected presign error for '%s' (%s: %s).", key, type(exc).__name__, exc)
        return to_local_url(key)


def get_presigned_put_url(object_key: str, content_type: Optional[str] = None,
                          expires_in: int = DEFAULT_PRESIGN_TTL) -> Optional[str]:
    """Generate a short-lived HTTP **PUT** presigned URL for uploading ``object_key``.

    Returns ``None`` when S3 is not configured or signing fails, so the caller can
    fall back to the bounded local upload endpoint. Never raises. When
    ``content_type`` is supplied it is bound into the signature, so a client cannot
    store an arbitrary media type under the slot's key.
    """
    key = extract_object_key(object_key)

    if not is_s3_enabled():
        return None
    client = get_s3_client()
    if client is None:
        return None

    settings = get_s3_settings()
    try:
        ttl = int(expires_in)
    except (TypeError, ValueError):
        ttl = DEFAULT_PRESIGN_TTL
    ttl = max(60, min(ttl, 604800))

    params: dict = {"Bucket": settings["bucket"], "Key": key}
    if content_type:
        params["ContentType"] = str(content_type)

    try:
        url = client.generate_presigned_url("put_object", Params=params, ExpiresIn=ttl)
        if url:
            return url
        logger.warning("Empty presigned PUT URL for key '%s'.", key)
        return None
    except (ClientError, BotoCoreError, NoCredentialsError, PartialCredentialsError, NoRegionError,
            EndpointConnectionError, ReadTimeoutError) as exc:
        logger.error("PUT presign failed for '%s' (%s: %s).", key, type(exc).__name__, exc)
        return None
    except Exception as exc:  # pragma: no cover - unexpected SDK failure
        logger.error("Unexpected PUT presign error for '%s' (%s: %s).", key, type(exc).__name__, exc)
        return None


def resolve_media_url(url_or_key: str, expires_in: int = DEFAULT_PRESIGN_TTL) -> str:
    """Return a *fresh*, renderable URL for a stored value.

    Local ``/uploads`` paths and the empty string are returned untouched;
    S3 URLs are re-signed so previously stored (possibly expired) presigned
    links keep working when the results endpoint is polled later.
    """
    raw = str(url_or_key or "").strip()
    if not raw or raw.startswith(UPLOAD_URL_PREFIX):
        return raw
    if raw.lower().startswith(("http://", "https://")):
        if not is_s3_enabled():
            return raw
        key = extract_object_key(raw)
        return get_presigned_url(key, expires_in) if key else raw
    return to_local_url(raw)


# --------------------------------------------------------------------------- #
# Batch presigning (map / gallery rendering)
# --------------------------------------------------------------------------- #
def _presign_cache_get(cache_key: tuple) -> Optional[str]:
    with _PRESIGN_CACHE_LOCK:
        entry = _PRESIGN_CACHE.get(cache_key)
        if entry is None:
            return None
        url, stored_at = entry
        if (time.time() - stored_at) > cache_key[-1]:
            _PRESIGN_CACHE.pop(cache_key, None)
            return None
        _PRESIGN_CACHE.move_to_end(cache_key)
        return url


def _presign_cache_set(cache_key: tuple, url: str) -> None:
    with _PRESIGN_CACHE_LOCK:
        _PRESIGN_CACHE[cache_key] = (url, time.time())
        _PRESIGN_CACHE.move_to_end(cache_key)
        while len(_PRESIGN_CACHE) > PRESIGN_CACHE_MAX_ENTRIES:
            _PRESIGN_CACHE.popitem(last=False)


def clear_presign_cache() -> None:
    """Drop cached presigned URLs (tests, and after a credential rotation)."""
    with _PRESIGN_CACHE_LOCK:
        _PRESIGN_CACHE.clear()


def get_batch_presigned_urls(object_keys: Iterable[str], expires_in: int = DEFAULT_PRESIGN_TTL,
                            *, refresh: bool = False) -> Dict[str, str]:
    """Sign many object keys at once and return ``{input: renderable_url}``.

    Built for map/gallery rendering, where a single route can reference hundreds
    of mask overlays.  The mapping keys are the *original* inputs, so callers can
    look the URL up with exactly what they passed in.

    Behaviour and guarantees
    ------------------------
    * Signing itself is a local cryptographic operation (no HTTP round trip), so
      batching removes per-key overhead and, more importantly, centralises the
      error handling; results are additionally cached for
      ``min(expires_in - 60s, PRESIGN_CACHE_TTL_CAP)`` so repeated renders in the
      same window do not re-sign.
    * Duplicate entries are signed once; blank/``None`` keys are skipped.
    * Local ``/uploads/...`` values are returned unchanged.
    * When S3 is not configured or signing fails, every key degrades to its
      local ``/uploads/...`` URL - the function never raises and never returns a
      half-populated mapping.
    """
    requested: List[str] = []
    for raw in object_keys or []:
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            requested.append(text)

    if not requested:
        return {}

    try:
        ttl = max(60, min(int(expires_in), 604800))
    except (TypeError, ValueError):
        ttl = DEFAULT_PRESIGN_TTL
    cache_ttl = max(30.0, min(float(ttl) - 60.0, PRESIGN_CACHE_TTL_CAP))

    unique_keys: List[str] = []
    for value in requested:
        if value.startswith(UPLOAD_URL_PREFIX) or value.lower().startswith(("http://", "https://") ):
            continue
        key = extract_object_key(value)
        if key and key not in unique_keys:
            unique_keys.append(key)

    mapping: Dict[str, str] = {}
    signed: Dict[str, str] = {}

    if not is_s3_enabled():
        logger.info("S3 not configured - returning %d local URL(s) for the batch request.", len(requested))
        for value in requested:
            mapping[value] = resolve_media_url(value, ttl) or to_local_url(value)
        return mapping

    for key in unique_keys:
        cache_key = (key, ttl, cache_ttl)
        if not refresh:
            cached_url = _presign_cache_get(cache_key)
            if cached_url:
                signed[key] = cached_url
                continue
        url = get_presigned_url(key, ttl)
        signed[key] = url
        if url and not url.startswith(UPLOAD_URL_PREFIX):
            _presign_cache_set(cache_key, url)

    for value in requested:
        if value.startswith(UPLOAD_URL_PREFIX):
            mapping[value] = value
            continue
        if value.lower().startswith(("http://", "https://")):
            mapping[value] = resolve_media_url(value, ttl) or value
            continue
        mapping[value] = signed.get(extract_object_key(value)) or to_local_url(value)

    logger.info("Batch presign: %d requested, %d unique key(s), %d unique url(s).",
                len(requested), len(unique_keys), len(set(mapping.values())))
    return mapping


# --------------------------------------------------------------------------- #
# Bucket / lifecycle provisioning (used by scripts/setup_aws_resources.py)
# --------------------------------------------------------------------------- #
def ensure_bucket(bucket: Optional[str] = None, region: Optional[str] = None,
                  *, create: bool = True) -> Dict[str, Any]:
    """Create the bucket when missing and return its status.

    Unlike the upload helpers this function **raises** :class:`S3UnavailableError`
    when S3 is not configured or the AWS call fails, because silently returning a
    local path here would hide a provisioning failure.
    """
    if not BOTO3_AVAILABLE:
        raise S3UnavailableError("boto3 is not installed")
    if not is_s3_enabled():
        raise S3UnavailableError(
            "S3 is not configured: set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY and AWS_S3_BUCKET_NAME"
        )

    settings = get_s3_settings()
    target_bucket = (bucket or settings["bucket"]).strip()
    target_region = (region or settings["region"] or "us-east-1").strip()
    client = get_s3_client()
    if client is None:
        raise S3UnavailableError("could not create an S3 client")

    try:
        client.head_bucket(Bucket=target_bucket)
        logger.info("Bucket %s already exists (region=%s).", target_bucket, target_region)
        return {"bucket": target_bucket, "region": target_region, "created": False}
    except ClientError as exc:
        code = str((exc.response or {}).get("Error", {}).get("Code", ""))
        if code not in {"404", "NoSuchBucket", "NotFound"}:
            if code in {"403", "AccessDenied"}:
                # Owned by someone else or no ListBucket permission - do not try to create it.
                logger.warning("head_bucket on %s returned %s; assuming it exists.", target_bucket, code)
                return {"bucket": target_bucket, "region": target_region, "created": False, "verified": False}
            raise S3UnavailableError(f"head_bucket failed for {target_bucket}: {code or exc}") from exc
    except (BotoCoreError, EndpointConnectionError, NoCredentialsError, NoRegionError) as exc:
        raise S3UnavailableError(f"head_bucket failed for {target_bucket}: {type(exc).__name__}: {exc}") from exc

    if not create:
        raise S3UnavailableError(f"bucket {target_bucket} does not exist and --no-create was requested")

    try:
        if target_region == "us-east-1":
            client.create_bucket(Bucket=target_bucket)
        else:
            client.create_bucket(
                Bucket=target_bucket,
                CreateBucketConfiguration={"LocationConstraint": target_region},
            )
        logger.info("Created bucket s3://%s in %s.", target_bucket, target_region)
        return {"bucket": target_bucket, "region": target_region, "created": True}
    except (ClientError, BotoCoreError) as exc:
        raise S3UnavailableError(f"could not create bucket {target_bucket}: {exc}") from exc


def build_lifecycle_rule(prefix: Optional[str] = None, expire_days: Optional[int] = None,
                         rule_id: str = "ghost-rider-expire-raw-uploads") -> Dict[str, Any]:
    """Build the lifecycle rule dict that expires raw frames after N days."""
    settings = get_settings_safely()
    resolved_prefix = (prefix if prefix is not None else RAW_OBJECT_PREFIX).strip()
    if expire_days is None:
        expire_days = getattr(settings, "S3_LIFECYCLE_EXPIRE_DAYS", 7)
    days = max(1, int(expire_days))
    rule: Dict[str, Any] = {
        "ID": rule_id,
        "Status": "Enabled",
        "Expiration": {"Days": days},
        # Abort partial multipart uploads so dead uploads do not accrue cost.
        "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": max(1, min(days, 7))},
    }
    if resolved_prefix:  # an empty Prefix means "the whole bucket" and must be omitted
        rule["Filter"] = {"Prefix": resolved_prefix}
    return rule


def put_bucket_lifecycle_policy(prefix: Optional[str] = None, expire_days: Optional[int] = None,
                                bucket: Optional[str] = None, *, merge: bool = True) -> Dict[str, Any]:
    """Apply the raw-image expiry rule (idempotent; raises on failure)."""
    settings = get_s3_settings()
    target_bucket = (bucket or settings["bucket"]).strip()
    client = get_s3_client()
    if client is None:
        raise S3UnavailableError(
            "S3 is not configured: cannot apply the lifecycle policy "
            "(set AWS credentials and AWS_S3_BUCKET_NAME)"
        )

    rule = build_lifecycle_rule(prefix, expire_days)
    rules: List[Dict[str, Any]] = []
    if merge:
        existing = None
        try:
            existing = client.get_bucket_lifecycle_configuration(Bucket=target_bucket)
        except ClientError as exc:
            code = str((exc.response or {}).get("Error", {}).get("Code", ""))
            if code not in {"NoSuchLifecycleConfiguration", "NoSuchBucket", "404", "NotFound", "AccessDenied"}:
                raise S3UnavailableError(f"could not read the lifecycle policy: {code or exc}") from exc
        if existing:
            rules = [item for item in (existing.get("Rules") or []) if item.get("ID") != rule["ID"]]
    rules.append(rule)

    try:
        client.put_bucket_lifecycle_configuration(
            Bucket=target_bucket, LifecycleConfiguration={"Rules": rules}
        )
    except (ClientError, BotoCoreError) as exc:
        raise S3UnavailableError(f"could not apply the lifecycle policy: {exc}") from exc

    logger.info("Lifecycle rule '%s' applied to s3://%s (prefix=%r, expire=%sd).",
                rule["ID"], target_bucket, rule["Filter"].get("Prefix"),
                rule["Expiration"]["Days"])
    return {
        "bucket": target_bucket,
        "rule_id": rule["ID"],
        "prefix": rule["Filter"].get("Prefix", ""),
        "expire_days": rule["Expiration"]["Days"],
        "total_rules": len(rules),
    }


def get_bucket_lifecycle_policy(bucket: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fetch the bucket's lifecycle configuration (``None`` when none exists)."""
    settings = get_s3_settings()
    target_bucket = (bucket or settings["bucket"]).strip()
    client = get_s3_client()
    if client is None:
        return None
    try:
        return client.get_bucket_lifecycle_configuration(Bucket=target_bucket)
    except ClientError as exc:
        code = str((exc.response or {}).get("Error", {}).get("Code", ""))
        if code in {"NoSuchLifecycleConfiguration", "NoSuchBucket", "404", "NotFound"}:
            return None
        logger.warning("Could not read the lifecycle configuration for %s: %s", target_bucket, code or exc)
        return None
    except (BotoCoreError, EndpointConnectionError, NoCredentialsError, NoRegionError) as exc:
        logger.warning("Could not read the lifecycle configuration for %s: %s", target_bucket, exc)
        return None


def health_status() -> dict:
    """Lightweight, non-blocking status blob used by the health endpoint."""
    settings = get_s3_settings()
    return {
        "boto3_installed": BOTO3_AVAILABLE,
        "s3_enabled": is_s3_enabled(),
        "bucket": settings["bucket"] or None,
        "region": settings["region"],
        "endpoint_url": settings["endpoint_url"],
        "raw_prefix": RAW_OBJECT_PREFIX,
        "mask_prefix": MASK_OBJECT_PREFIX,
        "uploads_dir": str(UPLOADS_DIR),
    }
