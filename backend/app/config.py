"""Centralised, typed configuration for the Ghost-Rider backend.

A single :class:`Settings` object (pydantic-settings) is the one source of truth
for every environment variable the service reads.  Values are resolved in this
order:

1. real environment variables (``AWS_REGION=ap-southeast-2``)
2. ``backend/.env`` then ``<repo>/.env``
3. the documented defaults below

Usage
-----
::

    from app.config import get_settings            # flat layout (uvicorn main:app)
    settings = get_settings()
    settings.uploads_path, settings.s3_configured

``get_settings()`` is cached so the whole process shares one immutable object;
call :func:`reload_settings` after mutating ``os.environ`` (tests, credential
rotation) to rebuild it.

Secrets are never exposed by :meth:`Settings.redacted` - use it for logs and for
the health endpoint.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

try:  # flat layout (``uvicorn main:app`` runs with backend/ on sys.path)
    from bedrock_models import promote_nova_model_id
except ImportError:  # package layout (``backend.app.config``)
    from backend.bedrock_models import promote_nova_model_id  # type: ignore[no-redef]

logger = logging.getLogger("ghost_rider.config")

# ``app/config.py`` -> ``backend/`` -> repository root
BACKEND_DIR: Path = Path(__file__).resolve().parent.parent
PROJECT_DIR: Path = BACKEND_DIR.parent

# Tests/CI set ``GHOST_RIDER_DISABLE_DOTENV=1`` so a developer's ``backend/.env``
# (real AWS credentials) never leaks into the test run.
_DOTENV_DISABLED = os.getenv("GHOST_RIDER_DISABLE_DOTENV", "").strip().lower() in {"1", "true", "yes", "on"}

ENV_FILES: tuple[Path, ...] = () if _DOTENV_DISABLED else (BACKEND_DIR / ".env", PROJECT_DIR / ".env")


class Settings(BaseSettings):
    """Every runtime knob of the Ghost-Rider backend.

    Field names are deliberately upper-case so they map 1:1 onto the environment
    variables that operations teams are told to set (``AWS_REGION``,
    ``BEDROCK_MODEL_ID``, ...).
    """

    model_config = SettingsConfigDict(
        env_file=ENV_FILES,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        env_ignore_empty=True,  # `FOO=` in .env means "unset", not "empty string"
    )

    # ------------------------------------------------------------------ AWS --
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_SESSION_TOKEN: Optional[str] = None
    AWS_REGION: str = Field(
        default="ap-southeast-2",
        validation_alias=AliasChoices("AWS_REGION", "AWS_DEFAULT_REGION"),
    )
    BEDROCK_REGION: Optional[str] = None
    AWS_S3_BUCKET_NAME: str = Field(
        default="ghost-rider-road-storage",
        validation_alias=AliasChoices("AWS_S3_BUCKET_NAME", "S3_BUCKET_NAME"),
    )
    AWS_S3_ENDPOINT_URL: Optional[str] = None  # LocalStack / MinIO / S3-compatible

    # --------------------------------------------------------------- Bedrock --
    BEDROCK_MODEL_ID: str = "amazon.nova-micro-v1:0"
    BEDROCK_FALLBACK_MODEL_IDS: str = "anthropic.claude-3-haiku-20240307-v1:0"
    BEDROCK_ENABLED: bool = True
    BEDROCK_MAX_TOKENS: int = 220
    BEDROCK_TEMPERATURE: float = 0.2
    BEDROCK_MAX_ATTEMPTS: int = 3
    BEDROCK_RETRY_BASE_DELAY: float = 0.5
    BEDROCK_RETRY_MAX_DELAY: float = 6.0
    BEDROCK_TOTAL_BUDGET_SEC: float = 20.0
    BEDROCK_CACHE_SIZE: int = 256
    BEDROCK_CACHE_TTL: float = 3600.0

    # ------------------------------------------------------------------- CV --
    YOLO_WEIGHTS_PATH: str = Field(
        default="yolov8n-seg.pt",
        validation_alias=AliasChoices("YOLO_WEIGHTS_PATH", "YOLO_SEG_WEIGHTS"),
    )
    YOLO_CONF: float = 0.25
    YOLO_IOU: float = 0.45
    YOLO_IMGSZ: int = 640
    DISTRESS_MODEL_PATH: str = "models/india_rdd2022_yolov8n/best.pt"
    CAMERA_MOUNT_PITCH_DEG: float = 25.0
    CAMERA_HEIGHT_M: float = 1.3
    CAMERA_HFOV_DEG: float = 70.0
    CAMERA_IMAGE_SIZE: str = ""
    PIXEL_AREA_CALIBRATION: float = 1.0
    MIN_MASK_PIXELS: int = 50
    OVERLAY_ALPHA: float = 0.45
    SEGMENT_LENGTH_M: float = 10.0

    # -------------------------------------------------------------- storage --
    UPLOADS_DIR: str = ""  # empty -> <backend>/uploads
    GHOST_RIDER_DB_PATH: str = ""  # empty -> <backend>/road_quality.db
    MAX_UPLOAD_MB: float = 25.0
    PRESIGNED_URL_TTL: int = 3600
    S3_RETURN_PRESIGNED: bool = True
    S3_RAW_PREFIX: str = "uploads/"  # object key prefix for raw frames (expirable)
    S3_MASK_PREFIX: str = "masks/"   # object key prefix for defect overlays (retained)
    S3_LIFECYCLE_PREFIX: str = "uploads/"
    S3_LIFECYCLE_EXPIRE_DAYS: int = 7

    # --------------------------------------------------------------- server --
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:4173,http://127.0.0.1:4173"
    )  # comma-separated; production deployments set their actual frontend origin
    LOCAL_UPLOADS_PUBLIC: bool = True  # development fallback only; deployment disables it
    WARMUP_MODEL: bool = True
    HEALTH_PROBE_TTL: float = 30.0  # seconds a cached AWS probe result stays valid

    # ----------------------------------------------------------- validators --
    @field_validator(
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "BEDROCK_REGION",
        "AWS_S3_ENDPOINT_URL",
        mode="before",
    )
    @classmethod
    def _blank_is_none(cls, value: Any) -> Any:
        """Treat blank strings (``AWS_ACCESS_KEY_ID=``) as unset."""
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator(
        "AWS_REGION",
        "AWS_S3_BUCKET_NAME",
        "BEDROCK_MODEL_ID",
        "BEDROCK_FALLBACK_MODEL_IDS",
        "YOLO_WEIGHTS_PATH",
        mode="before",
    )
    @classmethod
    def _strip_text(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def _normalise_log_level(cls, value: Any) -> Any:
        text = str(value or "INFO").strip().upper()
        return text if text in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"} else "INFO"

    @model_validator(mode="after")
    def _promote_nova_inference_profile(self) -> "Settings":
        """Use the regional cross-region inference profile for Amazon Nova.

        ``ap-southeast-2`` (and other ``ap-*``/``eu-*`` regions) reject on-demand
        invocation of the bare ``amazon.nova-*-v1:0`` id with a
        ``ValidationException``; the geo-prefixed profile id is required. Verified
        live: ``apac.amazon.nova-micro-v1:0`` works in ``ap-southeast-2``. Explicitly
        configured profile ids and non-Nova models are left unchanged.
        """
        promoted = promote_nova_model_id(self.BEDROCK_MODEL_ID, self.bedrock_region)
        if promoted and promoted != self.BEDROCK_MODEL_ID:
            logger.debug(
                "BEDROCK_MODEL_ID %s -> %s (cross-region inference profile for %s)",
                self.BEDROCK_MODEL_ID,
                promoted,
                self.bedrock_region,
            )
            self.BEDROCK_MODEL_ID = promoted
        return self

    # -------------------------------------------------- resolved properties --
    @property
    def uploads_path(self) -> Path:
        """Absolute directory that backs ``/uploads``."""
        raw = (self.UPLOADS_DIR or "").strip()
        if not raw:
            return (BACKEND_DIR / "uploads").resolve()
        path = Path(raw).expanduser()
        return path.resolve() if path.is_absolute() else (BACKEND_DIR / path).resolve()

    @property
    def database_path(self) -> Path:
        """Absolute path of the SQLite database file."""
        raw = (self.GHOST_RIDER_DB_PATH or "").strip()
        if not raw:
            return (BACKEND_DIR / "road_quality.db").resolve()
        path = Path(raw).expanduser()
        return path.resolve() if path.is_absolute() else (BACKEND_DIR / path).resolve()

    @property
    def yolo_weights(self) -> Path:
        """Resolved segmentation checkpoint (relative paths are backend-relative)."""
        raw = (self.YOLO_WEIGHTS_PATH or "yolov8n-seg.pt").strip()
        path = Path(raw).expanduser()
        return path.resolve() if path.is_absolute() else (BACKEND_DIR / path).resolve()

    @property
    def distress_model_path(self) -> Path:
        """Resolved optional India distress detector checkpoint."""
        path = Path(self.DISTRESS_MODEL_PATH).expanduser()
        return path.resolve() if path.is_absolute() else (PROJECT_DIR / path).resolve()

    @property
    def bedrock_region(self) -> str:
        return (self.BEDROCK_REGION or self.AWS_REGION).strip() or "us-east-1"

    @property
    def cors_origin_list(self) -> List[str]:
        """``CORS_ORIGINS`` split into a list (``*`` stays a single wildcard)."""
        raw = (self.CORS_ORIGINS or "").strip()
        if raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def bedrock_models(self) -> List[str]:
        """Primary model first, then every configured fallback (de-duplicated)."""
        models: List[str] = []
        for candidate in (self.BEDROCK_MODEL_ID, *self.BEDROCK_FALLBACK_MODEL_IDS.split(",")):
            name = (candidate or "").strip()
            if name and name not in models:
                models.append(name)
        return models

    @property
    def aws_credentials_present(self) -> bool:
        return bool(self.AWS_ACCESS_KEY_ID and self.AWS_SECRET_ACCESS_KEY)

    @property
    def s3_configured(self) -> bool:
        return bool(self.aws_credentials_present and self.AWS_S3_BUCKET_NAME)

    @property
    def bedrock_configured(self) -> bool:
        return bool(self.BEDROCK_ENABLED and self.aws_credentials_present)

    @property
    def max_upload_bytes(self) -> int:
        return int(max(0.0, float(self.MAX_UPLOAD_MB)) * 1024 * 1024)

    # ------------------------------------------------------------ utilities --
    def redacted(self) -> Dict[str, Any]:
        """Config snapshot safe to log or to return from an endpoint."""
        return {
            "aws_region": self.AWS_REGION,
            "bedrock_region": self.bedrock_region,
            "s3_bucket": self.AWS_S3_BUCKET_NAME,
            "s3_endpoint_url": self.AWS_S3_ENDPOINT_URL,
            "s3_configured": self.s3_configured,
            "bedrock_model": self.BEDROCK_MODEL_ID,
            "bedrock_models": self.bedrock_models,
            "bedrock_configured": self.bedrock_configured,
            "credentials": "configured" if self.aws_credentials_present else "missing",
            "session_token": "configured" if self.AWS_SESSION_TOKEN else "absent",
            "yolo_weights": str(self.yolo_weights),
            "camera_mount_pitch_deg": self.CAMERA_MOUNT_PITCH_DEG,
            "camera_height_m": self.CAMERA_HEIGHT_M,
            "pixel_area_calibration": self.PIXEL_AREA_CALIBRATION,
            "uploads_dir": str(self.uploads_path),
            "database_path": str(self.database_path),
            "host": self.HOST,
            "port": self.PORT,
            "log_level": self.LOG_LEVEL,
            "cors_origins": self.cors_origin_list,
            "max_upload_bytes": self.max_upload_bytes,
            "s3_raw_prefix": self.S3_RAW_PREFIX,
            "s3_mask_prefix": self.S3_MASK_PREFIX,
            "s3_lifecycle_prefix": self.S3_LIFECYCLE_PREFIX,
            "s3_lifecycle_expire_days": self.S3_LIFECYCLE_EXPIRE_DAYS,
        }

    def warnings(self) -> List[str]:
        """Configuration problems worth surfacing at startup / in health checks."""
        problems: List[str] = []
        if not self.aws_credentials_present:
            problems.append(
                "AWS credentials are missing: S3 uploads fall back to local /uploads URLs and "
                "Bedrock recommendations use the deterministic rule templates."
            )
        elif not self.AWS_S3_BUCKET_NAME:
            problems.append("AWS_S3_BUCKET_NAME is empty: S3 storage is disabled.")
        if self.cors_origin_list == ["*"]:
            problems.append(
                "CORS_ORIGINS is '*' with credentials enabled: browsers reject wildcard origins "
                "for credentialed requests. Restrict it to the app origins before production."
            )
        if not self.yolo_weights.exists():
            problems.append(
                f"YOLO weights not found at {self.yolo_weights}: ultralytics will try to "
                "download them on first use (adds startup latency)."
            )
        if self.BEDROCK_MAX_ATTEMPTS < 1:
            problems.append("BEDROCK_MAX_ATTEMPTS < 1 has no effect; using 1 attempt.")
        if not self.S3_LIFECYCLE_PREFIX:
            problems.append("S3_LIFECYCLE_PREFIX is empty: the lifecycle rule would expire the whole bucket.")
        return problems

    def log_summary(self, logger_: Optional[logging.Logger] = None) -> None:
        """Emit the redacted config plus warnings to a logger."""
        target = logger_ or logger
        target.info("Configuration: %s", self.redacted())
        for problem in self.warnings():
            target.warning("Configuration warning: %s", problem)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide cached :class:`Settings` instance."""
    return Settings()


def reload_settings() -> Settings:
    """Drop the cached settings and rebuild them from the current environment."""
    get_settings.cache_clear()
    return get_settings()


def get_settings_safely() -> Optional[Settings]:
    """Like :func:`get_settings` but never raises (validation problems -> ``None``)."""
    try:
        return get_settings()
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Could not load settings (%s: %s); using fail-safe defaults.", type(exc).__name__, exc)
        return None


__all__ = [
    "BACKEND_DIR",
    "PROJECT_DIR",
    "Settings",
    "get_settings",
    "get_settings_safely",
    "reload_settings",
]
