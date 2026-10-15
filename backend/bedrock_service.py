"""AWS Bedrock recommendation service for Ghost-Rider.

Turns a numeric pavement assessment into two actionable sentences of civil
engineering advice.  The service is deliberately *fail-safe*: any AWS problem
(missing credentials, throttling, model access denied, network timeout,
malformed response) silently degrades to a deterministic rule-based template
keyed on the segment score, so the pipeline always produces a recommendation.

Reliability
-----------
Every model call goes through :func:`_invoke_with_retry`, which applies
**exponential backoff with jitter** (``BEDROCK_MAX_ATTEMPTS`` attempts, default 3)
to *retryable* failures only - throttling, 5xx, model timeouts and connection
spikes.  Non-retryable failures (validation errors, missing model access,
bad credentials) fail fast and move to the next model or straight to the rule
templates.  ``Retry-After`` / ``retryAfterSeconds`` hints are honoured, and a
whole-segment time budget (``BEDROCK_TOTAL_BUDGET_SEC``, default 20s) stops the
retry ladder from stalling a background route job.

Ladder: each model x each call path (Converse, then raw ``invoke_model``) with
``max_attempts`` retries each, primary model first, then every fallback model.
Counters live in :data:`RETRY_STATS` and are surfaced by ``/health/deep``.

Environment variables (defaults in ``app/config.py``)
-----------------------------------------------------
``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY``  Credentials.
``BEDROCK_REGION`` or ``AWS_REGION``               Region (default ``ap-south-1``).
``BEDROCK_MODEL_ID``                               Primary model (Nova micro).
``BEDROCK_FALLBACK_MODEL_IDS``                     Comma separated fallbacks.
``BEDROCK_MAX_ATTEMPTS`` / ``BEDROCK_RETRY_BASE_DELAY`` / ``BEDROCK_RETRY_MAX_DELAY``
``BEDROCK_TOTAL_BUDGET_SEC``                       Retry budget per recommendation.
``BEDROCK_MAX_TOKENS`` / ``BEDROCK_TEMPERATURE``   Generation settings.
``BEDROCK_ENABLED``                                ``false`` forces offline mode.
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import socket
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ghost_rider.bedrock")

try:
    from .s3_service import load_project_env
except ImportError:  # executed as a flat module (uvicorn main:app from backend/)
    try:
        from s3_service import load_project_env
    except ImportError:  # pragma: no cover - standalone import
        def load_project_env() -> None:  # type: ignore[misc]
            return None

load_project_env()

try:
    from app.config import get_settings_safely
except ImportError:  # package layout (``uvicorn backend.main:app``)
    from backend.app.config import get_settings_safely  # type: ignore[no-redef]

try:
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
except Exception as _import_exc:  # pragma: no cover - optional dependency
    boto3 = None  # type: ignore[assignment]
    BotoConfig = None  # type: ignore[assignment]
    BotoCoreError = ClientError = Exception  # type: ignore[assignment,misc]
    EndpointConnectionError = NoCredentialsError = Exception  # type: ignore[assignment,misc]
    NoRegionError = PartialCredentialsError = ReadTimeoutError = Exception  # type: ignore[assignment,misc]
    BOTO3_AVAILABLE = False
    logger.warning("boto3 is not available (%s); Bedrock recommendations will use the rule engine.",
                   _import_exc)

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
DEFAULT_MODEL_ID = "amazon.nova-micro-v1:0"
SECONDARY_MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"

AWS_ERRORS = (
    ClientError,
    BotoCoreError,
    NoCredentialsError,
    PartialCredentialsError,
    NoRegionError,
    EndpointConnectionError,
    ReadTimeoutError,
    TimeoutError,
)

# Transient AWS conditions worth retrying (throttling, capacity, network spikes).
RETRYABLE_ERROR_CODES = {
    "ThrottlingException",
    "Throttling",
    "ThrottledException",
    "TooManyRequestsException",
    "RequestThrottled",
    "ServiceUnavailableException",
    "ServiceUnavailable",
    "InternalServerException",
    "InternalException",
    "InternalFailure",
    "ModelTimeoutException",
    "ModelNotReadyException",
    "RequestTimeout",
    "RequestTimeoutException",
    "ServiceQuotaExceededException",
    "LimitExceededException",
}

# Permanent conditions - retrying wastes time/quota and delays the fallback.
NON_RETRYABLE_ERROR_CODES = {
    "ValidationException",
    "InvalidRequestException",
    "AccessDeniedException",
    "UnauthorizedException",
    "UnrecognizedClientException",
    "InvalidSignatureException",
    "MissingAuthenticationTokenException",
    "ResourceNotFoundException",
    "ModelNotEnabledException",
    "ModelErrorException",
    "SerializationException",
}

# Production counters (surfaced by /health/deep and by logs).
RETRY_STATS: Dict[str, int] = {
    "attempts": 0,
    "retries": 0,
    "successes": 0,
    "exhausted": 0,
    "budget_exhausted": 0,
    "fallback_templates": 0,
}
_STATS_LOCK = threading.Lock()


def _bump(counter: str, amount: int = 1) -> None:
    """Increment a diagnostics counter thread-safely."""
    with _STATS_LOCK:
        RETRY_STATS[counter] = RETRY_STATS.get(counter, 0) + amount


def reset_retry_stats() -> None:
    """Zero the diagnostics counters (tests / post-incident reset)."""
    with _STATS_LOCK:
        for key in RETRY_STATS:
            RETRY_STATS[key] = 0


def error_code(exc: BaseException) -> str:
    """Best-effort AWS error code for a botocore exception."""
    try:
        code = str(((getattr(exc, "response", {}) or {}).get("Error", {}) or {}).get("Code", ""))
        return code or type(exc).__name__
    except Exception:  # pragma: no cover - defensive
        return type(exc).__name__


def _http_status(exc: BaseException) -> Optional[int]:
    try:
        metadata = (getattr(exc, "response", {}) or {}).get("ResponseMetadata", {}) or {}
        status = metadata.get("HTTPStatusCode")
        return int(status) if status is not None else None
    except Exception:  # pragma: no cover - defensive
        return None


def is_retryable_error(exc: BaseException) -> bool:
    """True for transient failures (throttling, 5xx, timeouts, connection errors)."""
    code = error_code(exc)
    if code in NON_RETRYABLE_ERROR_CODES:
        return False
    if code in RETRYABLE_ERROR_CODES:
        return True
    if isinstance(exc, (NoCredentialsError, PartialCredentialsError, NoRegionError)):
        return False
    if isinstance(exc, (EndpointConnectionError, ReadTimeoutError, TimeoutError, socket.timeout,
                        ConnectionError)):
        return True
    status = _http_status(exc)
    if status is not None and (status >= 500 or status == 429):
        return True
    return False


def _retry_after_seconds(exc: BaseException) -> Optional[float]:
    """Extract a ``Retry-After`` hint from the response headers or error payload."""
    try:
        response = getattr(exc, "response", {}) or {}
        headers = (response.get("ResponseMetadata", {}) or {}).get("HTTPHeaders", {}) or {}
        for key, value in headers.items():
            if str(key).lower() == "retry-after":
                return max(0.0, min(float(value), 30.0))
        message = str((response.get("Error", {}) or {}).get("Message", ""))
        # matches  retryAfterSeconds: 12 / 'retryAfterSeconds=12' / "...12" etc.
        match = re.search(r"retryAfterSeconds\D*([0-9.]+)", message, re.IGNORECASE)
        if match:
            return max(0.0, min(float(match.group(1)), 30.0))
    except Exception:  # pragma: no cover - defensive
        return None
    return None


def backoff_delay(attempt: int, exc: Optional[BaseException] = None,
                  cfg: Optional[Dict[str, Any]] = None) -> float:
    """Exponential backoff with full jitter, honouring any ``Retry-After`` hint.

    ``delay = min(base * 2^(attempt-1), cap)`` plus up to 25% jitter; a server
    ``Retry-After`` wins when it is longer than the computed delay (still capped).
    """
    config = cfg or get_bedrock_settings()
    base = max(0.0, float(config.get("retry_base_delay", 0.5) or 0.0))
    cap = max(0.05, float(config.get("retry_max_delay", 6.0) or 6.0))
    exponent = max(0, int(attempt) - 1)
    delay = min(base * (2 ** exponent), cap) if base else 0.0

    retry_after = _retry_after_seconds(exc) if exc is not None else None
    if retry_after is not None:
        delay = min(max(delay, retry_after), cap)

    jitter = random.uniform(0.0, delay * 0.25) if delay > 0 else 0.0
    return round(delay + jitter, 4)

SYSTEM_PROMPT = (
    "You are a Senior Civil Engineering Consultant specialising in pavement "
    "condition assessment, asphalt rehabilitation and road drainage maintenance. "
    "You give terse, field-ready maintenance directives to municipal road crews."
)

# Exact deterministic fallbacks required by the Ghost-Rider specification.
FALLBACK_HIGH = "Road surface structural integrity is optimal. Perform routine seasonal inspection."
FALLBACK_MEDIUM = ("Moderate asphalt degradation detected. "
                   "Schedule crack sealing and surface re-patching.")
FALLBACK_LOW = ("Critical pavement failure. Immediate cold-mix asphalt patching "
                "and sub-base compaction required.")

_client_lock = threading.Lock()
_client_slots: Dict[str, tuple] = {}

# Small TTL cache: background processing can re-run a route (retry / re-process)
# and we do not want to pay Bedrock twice for identical segment data.
_CACHE_LOCK = threading.Lock()
_CACHE: "OrderedDict[tuple, tuple]" = OrderedDict()
_cache_settings = get_settings_safely()
CACHE_MAX_ENTRIES = int(getattr(_cache_settings, "BEDROCK_CACHE_SIZE", 256) or 256)
CACHE_TTL_SECONDS = float(getattr(_cache_settings, "BEDROCK_CACHE_TTL", 3600) or 3600)


# --------------------------------------------------------------------------- #
# Client / configuration helpers
# --------------------------------------------------------------------------- #
def get_bedrock_settings() -> Dict[str, Any]:
    """Resolve Bedrock configuration through ``app.config`` (cached).

    Falls back to raw environment variables when settings validation fails, so a
    mistyped unrelated variable can never take the recommendation engine down.
    """
    settings = get_settings_safely()
    env = os.getenv

    def _text(attribute: str, *env_names: str, default: str = "") -> str:
        value = getattr(settings, attribute, None) if settings is not None else None
        if value in (None, ""):
            for name in env_names:
                raw = env(name)
                if raw not in (None, ""):
                    value = raw
                    break
        return str(value if value is not None else default).strip()

    def _number(attribute: str, env_name: str, default: float, caster) -> float:
        value = getattr(settings, attribute, None) if settings is not None else None
        if value in (None, ""):
            value = env(env_name)
        try:
            return caster(value)
        except (TypeError, ValueError):
            return default

    def _flag(attribute: str, env_name: str, default: bool) -> bool:
        value = getattr(settings, attribute, None) if settings is not None else None
        if value is None:
            raw = env(env_name)
            value = None if raw in (None, "") else str(raw).strip().lower() not in ("0", "false", "no", "off")
        return bool(default if value is None else value)

    primary = _text("BEDROCK_MODEL_ID", "BEDROCK_MODEL_ID", default=DEFAULT_MODEL_ID) or DEFAULT_MODEL_ID
    fallback_raw = _text("BEDROCK_FALLBACK_MODEL_IDS", "BEDROCK_FALLBACK_MODEL_IDS",
                         default=SECONDARY_MODEL_ID)
    models: List[str] = []
    for candidate in (primary, *fallback_raw.split(",")):
        name = (candidate or "").strip()
        if name and name not in models:
            models.append(name)

    region = (
        _text("BEDROCK_REGION", "BEDROCK_REGION")
        or _text("AWS_REGION", "AWS_REGION", "AWS_DEFAULT_REGION", default="us-east-1")
        or "us-east-1"
    )

    return {
        "access_key": _text("AWS_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID", "AWS_ACCESS_KEY"),
        "secret_key": _text("AWS_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY", "AWS_SECRET_KEY"),
        "session_token": _text("AWS_SESSION_TOKEN", "AWS_SESSION_TOKEN") or None,
        "region": region,
        "model_id": primary,
        "models": models,
        "max_tokens": int(_number("BEDROCK_MAX_TOKENS", "BEDROCK_MAX_TOKENS", 220.0, int)),
        "temperature": float(_number("BEDROCK_TEMPERATURE", "BEDROCK_TEMPERATURE", 0.2, float)),
        "max_attempts": max(1, int(_number("BEDROCK_MAX_ATTEMPTS", "BEDROCK_MAX_ATTEMPTS", 3.0, int))),
        "retry_base_delay": max(0.0, float(_number("BEDROCK_RETRY_BASE_DELAY", "BEDROCK_RETRY_BASE_DELAY", 0.5, float))),
        "retry_max_delay": max(0.05, float(_number("BEDROCK_RETRY_MAX_DELAY", "BEDROCK_RETRY_MAX_DELAY", 6.0, float))),
        "budget_sec": max(1.0, float(_number("BEDROCK_TOTAL_BUDGET_SEC", "BEDROCK_TOTAL_BUDGET_SEC", 20.0, float))),
        "enabled": _flag("BEDROCK_ENABLED", "BEDROCK_ENABLED", True),
    }


def is_bedrock_enabled() -> bool:
    """True only when boto3 is installed, enabled and credentials are present."""
    settings = get_bedrock_settings()
    return bool(BOTO3_AVAILABLE and settings["enabled"] and settings["access_key"] and settings["secret_key"])


def model_candidates() -> List[str]:
    """Ordered, de-duplicated list of model ids to attempt."""
    return list(get_bedrock_settings()["models"])


def get_bedrock_client(*, fast: bool = False) -> Optional[Any]:
    """Return a cached ``bedrock-runtime`` client, or ``None`` when unusable.

    SDK-level retries are pinned to a single attempt: :func:`_invoke_with_retry`
    owns the retry policy so attempts, delays and counters stay observable (one
    logical attempt == one network call).  ``fast=True`` builds the short-timeout
    client used by ``/health/deep``.
    """
    if not is_bedrock_enabled():
        return None

    slot = "probe" if fast else "standard"
    settings = get_bedrock_settings()
    cache_key = (settings["access_key"][:6], settings["region"], slot)

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
                )
            else:
                client_config = BotoConfig(
                    retries={"max_attempts": 1, "mode": "standard"},
                    connect_timeout=5,
                    read_timeout=25,
                )
            client = boto3.client(
                "bedrock-runtime",
                aws_access_key_id=settings["access_key"],
                aws_secret_access_key=settings["secret_key"],
                aws_session_token=settings["session_token"],
                region_name=settings["region"],
                config=client_config,
            )
            _client_slots[slot] = (cache_key, client)
            logger.info("Bedrock %s client ready (region=%s).", slot, settings["region"])
            return client
        except Exception as exc:
            _client_slots.pop(slot, None)
            logger.error("Failed to create Bedrock client: %s: %s", type(exc).__name__, exc)
            return None


def reset_clients() -> None:
    """Forget cached Bedrock clients (credential rotation / tests)."""
    with _client_lock:
        _client_slots.clear()


# --------------------------------------------------------------------------- #
# Deterministic rule engine (always available)
# --------------------------------------------------------------------------- #
def rule_based_recommendation(score: float) -> str:
    """Score-driven template used whenever an LLM call is impossible."""
    try:
        numeric = float(score)
    except (TypeError, ValueError):
        numeric = 0.0

    if numeric >= 70:
        return FALLBACK_HIGH
    if numeric >= 40:
        return FALLBACK_MEDIUM
    return FALLBACK_LOW


# --------------------------------------------------------------------------- #
# Prompt construction + response post-processing
# --------------------------------------------------------------------------- #
def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or isinstance(value, bool):
            return default
        return round(float(value), 3)
    except (TypeError, ValueError):
        return default


def build_prompt(segment_data: Dict[str, Any]) -> str:
    """Turn the segment payload into a strict, two-sentence engineering prompt."""
    score = _safe_float(segment_data.get("score"), 0.0)
    status = str(segment_data.get("status") or "Unknown")
    pothole = _safe_float(segment_data.get("pothole_area_m2"))
    crack = _safe_float(segment_data.get("crack_area_m2"))
    pitch = _safe_float(segment_data.get("pitch_deg"))
    roll = _safe_float(segment_data.get("roll_deg"))
    segment_id = segment_data.get("segment_id")
    gps = segment_data.get("gps") or {}

    lines = [
        "PAVEMENT SEGMENT ASSESSMENT (Ghost-Rider automated survey)",
        f"- Road Condition Index (RCI) score: {score}/100",
        f"- Classification: {status}",
        f"- Pothole mask area: {pothole} m2",
        f"- Crack mask area: {crack} m2",
        f"- Device pitch (tilt): {pitch} deg",
        f"- Device roll: {roll} deg",
    ]
    if segment_id is not None:
        lines.append(f"- Segment: {segment_id} (10 m interval)")
    if isinstance(gps, dict) and gps.get("lat") is not None and gps.get("lon") is not None:
        lines.append(f"- GPS: {_safe_float(gps.get('lat'))}, {_safe_float(gps.get('lon'))}")

    lines.append("")
    lines.append(
        "Write your answer as EXACTLY TWO complete sentences and nothing else. "
        "Sentence 1: the single most urgent immediate repair action (choose the correct "
        "method: cold-mix asphalt patching, sub-base compaction, crack sealing, "
        "slurry/micro-surfacing, or drainage maintenance). "
        "Sentence 2: the follow-up action or the inspection interval needed to keep the "
        "segment serviceable. No bullet points, no headings, no markdown, no preamble, "
        "no numbers in a list."
    )
    return "\n".join(lines)


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_MARKDOWN_NOISE = re.compile(r"(\*\*|__|`|#+\s*|^\s*[-*•]\s*)", re.MULTILINE)


def clean_sentences(text: str, max_sentences: int = 2) -> str:
    """Strip markdown/bullets and keep at most ``max_sentences`` sentences."""
    if not text:
        return ""
    cleaned = _MARKDOWN_NOISE.sub("", str(text))
    cleaned = cleaned.replace("\r", " ").replace("\n", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""

    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(cleaned) if s.strip()]
    if not sentences:
        return cleaned

    kept: List[str] = []
    for sentence in sentences:
        kept.append(sentence if sentence.endswith((".", "!", "?")) else f"{sentence}.")
        if len(kept) >= max_sentences:
            break
    return " ".join(kept)


def _extract_text(response: Dict[str, Any]) -> str:
    """Pull the assistant text out of a Bedrock Converse response."""
    output = (response or {}).get("output") or {}
    message = output.get("message") or {}
    chunks: List[str] = []
    for block in message.get("content") or []:
        if isinstance(block, dict) and block.get("text"):
            chunks.append(str(block["text"]))
    return " ".join(chunks).strip()


def _extract_nova_text(response: Dict[str, Any]) -> str:
    """Pull the text out of a raw ``amazon.nova-*`` ``invoke_model`` response."""
    body = (response or {}).get("body")
    if body is None:
        return ""
    try:
        payload = json.loads(body.read())
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Could not parse Nova response body: %s", exc)
        return ""
    output = payload.get("output") or {}
    message = output.get("message") or {}
    chunks = [str(block.get("text", "")) for block in message.get("content") or [] if isinstance(block, dict)]
    return " ".join(chunk for chunk in chunks if chunk).strip()


# --------------------------------------------------------------------------- #
# Bedrock invocation
# --------------------------------------------------------------------------- #
def _invoke_converse(client: Any, model_id: str, prompt: str, settings: dict) -> str:
    """Preferred path: the model-agnostic Converse API (Nova, Claude 3, Titan)."""
    request = {
        "modelId": model_id,
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {
            "maxTokens": max(64, int(settings["max_tokens"])),
            "temperature": max(0.0, min(float(settings["temperature"]), 1.0)),
        },
    }
    try:
        response = client.converse(system=[{"text": SYSTEM_PROMPT}], **request)
    except ClientError as exc:
        code = str((exc.response or {}).get("Error", {}).get("Code", ""))
        if code in ("ValidationException", "InvalidRequestException"):
            logger.debug("Model %s rejected the system prompt; retrying without it.", model_id)
            response = client.converse(**request)
        else:
            raise
    return _extract_text(response)


def _invoke_nova_raw(client: Any, model_id: str, prompt: str, settings: dict) -> str:
    """Fallback path for older SDKs / Nova models without Converse support."""
    body = json.dumps(
        {
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "system": [{"text": SYSTEM_PROMPT}],
            "inferenceConfig": {
                "max_new_tokens": max(64, int(settings["max_tokens"])),
                "temperature": max(0.0, min(float(settings["temperature"]), 1.0)),
                "top_p": 0.9,
            },
        }
    )
    response = client.invoke_model(
        modelId=model_id,
        accept="application/json",
        contentType="application/json",
        body=body,
    )
    return _extract_nova_text(response)


def _invoke_with_retry(invoker: Any, client: Any, model_id: str, prompt: str,
                       cfg: Dict[str, Any], deadline: float) -> Tuple[str, int]:
    """Call ``invoker`` with exponential-backoff retries.

    Retries only transient failures (:func:`is_retryable_error`) and stops when the
    per-recommendation budget is spent.  Returns ``(text, attempts)``; re-raises the
    last exception when every attempt failed so the ladder can try the next path.
    """
    max_attempts = int(cfg.get("max_attempts", 3) or 3)
    attempts = 0

    while attempts < max_attempts:
        attempts += 1
        _bump("attempts")
        try:
            text = invoker(client, model_id, prompt, cfg)
        except Exception as exc:
            code = error_code(exc)
            retryable = is_retryable_error(exc)
            if not retryable or attempts >= max_attempts:
                reason = "non-retryable" if not retryable else "attempts exhausted"
                logger.warning("Bedrock %s failed for %s [%s] (%s/%d, %s).",
                               invoker.__name__, model_id, code, type(exc).__name__, attempts, reason)
                if attempts >= max_attempts:
                    _bump("exhausted")
                raise
            if time.monotonic() >= deadline:
                _bump("budget_exhausted")
                logger.warning("Bedrock budget exhausted after %d attempt(s) for %s [%s].",
                               attempts, model_id, code)
                raise
            delay = backoff_delay(attempts, exc, cfg)
            _bump("retries")
            logger.warning("Bedrock %s attempt %d/%d for %s failed [%s]; retrying in %.2fs.",
                           invoker.__name__, attempts, max_attempts, model_id, code, delay)
            time.sleep(delay)
            continue

        if text:
            _bump("successes")
            return text, attempts

        # Empty completion: treat as a transient model hiccup.
        logger.warning("Bedrock %s returned an empty completion for %s (attempt %d/%d).",
                       invoker.__name__, model_id, attempts, max_attempts)
        if attempts >= max_attempts or time.monotonic() >= deadline:
            _bump("exhausted")
            return "", attempts
        delay = backoff_delay(attempts, None, cfg)
        _bump("retries")
        time.sleep(delay)

    return "", attempts


def _invoke_bedrock(prompt: str) -> str:
    """Walk the retry ladder: each model x each call path, with backoff.

    Returns the first usable completion, or ``''`` when the whole ladder fails
    (the caller then uses the deterministic rule templates).
    """
    client = get_bedrock_client()
    if client is None:
        logger.warning("Bedrock client unavailable - using rule-based recommendation.")
        return ""

    cfg = get_bedrock_settings()
    deadline = time.monotonic() + float(cfg.get("budget_sec", 20.0) or 20.0)
    models = list(cfg.get("models") or model_candidates())

    for model_id in models:
        for invoker in (_invoke_converse, _invoke_nova_raw):
            if time.monotonic() >= deadline:
                _bump("budget_exhausted")
                logger.warning("Bedrock budget of %.1fs spent before %s/%s; using rule templates.",
                               cfg.get("budget_sec"), model_id, invoker.__name__)
                return ""
            try:
                text, attempts = _invoke_with_retry(invoker, client, model_id, prompt, cfg, deadline)
                if text:
                    logger.info("Bedrock recommendation produced by %s via %s (%d attempt(s)).",
                                model_id, invoker.__name__, attempts)
                    return text
                logger.warning("Model %s produced nothing via %s; trying the next path.",
                               model_id, invoker.__name__)
            except AWS_ERRORS as exc:
                logger.warning("Bedrock %s failed for %s [%s]; trying the next path.",
                               invoker.__name__, model_id, error_code(exc))
            except Exception as exc:  # pragma: no cover - unexpected SDK failure
                logger.warning("Unexpected Bedrock error for %s via %s (%s: %s); next path.",
                               model_id, invoker.__name__, type(exc).__name__, exc)
    return ""


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def _count_fallback() -> None:
    _bump("fallback_templates")


def generate_road_recommendation(segment_data: dict) -> str:
    """Return exactly two actionable repair sentences for a road segment.

    Parameters
    ----------
    segment_data:
        ``score``, ``status``, ``pothole_area_m2``, ``crack_area_m2`` and
        ``pitch_deg`` are the meaningful keys; ``segment_id``, ``roll_deg`` and
        ``gps`` are used as extra prompt context when present.

    Returns
    -------
    str
        Two sentences from Bedrock, or the deterministic rule-based template
        when Bedrock is not configured/reachable.  Never raises.
    """
    if not isinstance(segment_data, dict):
        logger.warning("generate_road_recommendation received %r; coercing to {}", type(segment_data))
        segment_data = {}

    score = _safe_float(segment_data.get("score"), 0.0)
    fallback = rule_based_recommendation(score)

    cache_key = (
        round(score, 1),
        _safe_float(segment_data.get("pothole_area_m2")),
        _safe_float(segment_data.get("crack_area_m2")),
        _safe_float(segment_data.get("pitch_deg"), -999.0),
        str(segment_data.get("status") or ""),
    )
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    if not is_bedrock_enabled():
        logger.info("Bedrock disabled/unconfigured - rule-based recommendation for score %.1f.", score)
        _count_fallback()
        _cache_set(cache_key, fallback)
        return fallback

    try:
        raw_text = _invoke_bedrock(build_prompt(segment_data))
    except Exception as exc:  # pragma: no cover - last-resort guard
        logger.error("Bedrock invocation crashed (%s: %s); using rule-based recommendation.",
                     type(exc).__name__, exc)
        raw_text = ""

    text = clean_sentences(raw_text, max_sentences=2)
    if not text:
        logger.warning("Falling back to the rule engine for score %.1f.", score)
        _count_fallback()
        text = fallback
    elif len(_SENTENCE_SPLIT.split(text)) < 2:
        # Guarantee the contract (exactly two sentences) even if the model was terse.
        text = clean_sentences(f"{text} {fallback}", max_sentences=2)

    _cache_set(cache_key, text)
    return text


def _cache_get(key: tuple) -> Optional[str]:
    if CACHE_MAX_ENTRIES <= 0:
        return None
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if entry is None:
            return None
        value, stored_at = entry
        if time.time() - stored_at > CACHE_TTL_SECONDS:
            _CACHE.pop(key, None)
            return None
        _CACHE.move_to_end(key)
        return value


def _cache_set(key: tuple, value: str) -> None:
    if CACHE_MAX_ENTRIES <= 0:
        return
    with _CACHE_LOCK:
        _CACHE[key] = (value, time.time())
        _CACHE.move_to_end(key)
        while len(_CACHE) > CACHE_MAX_ENTRIES:
            _CACHE.popitem(last=False)


def clear_cache() -> None:
    """Drop the in-memory recommendation cache (useful between test runs)."""
    with _CACHE_LOCK:
        _CACHE.clear()


def health_status() -> dict:
    """Non-blocking status blob for the health endpoint (no network calls)."""
    settings = get_bedrock_settings()
    return {
        "boto3_installed": BOTO3_AVAILABLE,
        "bedrock_enabled": is_bedrock_enabled(),
        "region": settings["region"],
        "model": settings["model_id"],
        "models": model_candidates(),
        "max_attempts": settings["max_attempts"],
        "budget_sec": settings["budget_sec"],
        "cached_recommendations": len(_CACHE),
        "retry_stats": dict(RETRY_STATS),
    }
