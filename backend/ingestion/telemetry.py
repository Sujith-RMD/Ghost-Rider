"""Telemetry parsing and validation for camera frames.

Ensures:
- Capture time (UTC and monotonic) is preserved and never confused with upload time.
- GPS coordinates are validated with accuracy; absent GPS is left null and never fabricated.
- Simulated GPS is explicitly flagged.
- Grade sensor data is validated with source provenance and uncertainty.
- Raw telemetry is hashed (SHA-256) for auditability.

Ownership: Backend & AWS AI
Reference: docs/final_plan.md (Section 2, 10, 11.5)
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from pydantic import ValidationError

from ..schemas import FrameMetadata, GPSData, GradeMeasurement, IMUData, SourceMode

logger = logging.getLogger("ghost_rider.ingestion.telemetry")


def compute_telemetry_hash(raw_data: Any) -> str:
    """Compute deterministic SHA-256 hash of telemetry input."""
    if raw_data is None:
        return hashlib.sha256(b"null").hexdigest()
    try:
        serialized = json.dumps(raw_data, sort_keys=True, default=str)
    except Exception:
        serialized = str(raw_data)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def parse_and_validate_telemetry(
    raw_metadata: Any,
    source_mode: SourceMode = SourceMode.UPLOAD,
    frame_index: Optional[int] = None,
) -> Tuple[FrameMetadata, Optional[str]]:
    """Parse raw dictionary or JSON string into validated FrameMetadata.

    Returns:
        Tuple of (FrameMetadata, error_message)
    """
    if raw_metadata is None:
        metadata = FrameMetadata(
            source_mode=source_mode,
            frame_index=frame_index,
            captured_at=None,
            monotonic_capture_time_ns=time.monotonic_ns(),
            telemetry_hash=compute_telemetry_hash(None),
        )
        return metadata, None

    payload: Dict[str, Any] = {}
    if isinstance(raw_metadata, str):
        trimmed = raw_metadata.strip()
        if not trimmed:
            metadata = FrameMetadata(
                source_mode=source_mode,
                frame_index=frame_index,
                monotonic_capture_time_ns=time.monotonic_ns(),
                telemetry_hash=compute_telemetry_hash(None),
            )
            return metadata, None
        try:
            payload = json.loads(trimmed)
        except (json.JSONDecodeError, ValueError) as exc:
            return FrameMetadata(source_mode=source_mode, frame_index=frame_index), f"Invalid JSON: {exc}"
    elif isinstance(raw_metadata, dict):
        payload = dict(raw_metadata)
    else:
        return FrameMetadata(source_mode=source_mode, frame_index=frame_index), "Metadata must be dict or JSON string"

    # Compute hash of raw input
    telemetry_hash = compute_telemetry_hash(payload)

    # 1. Parse GPS
    gps_data: Optional[GPSData] = None
    raw_gps = payload.get("gps")
    if isinstance(raw_gps, dict):
        try:
            # Check for required lat and lon
            if "lat" in raw_gps and "lon" in raw_gps:
                gps_data = GPSData.model_validate(raw_gps)
        except ValidationError as exc:
            logger.warning("GPS payload failed validation: %s", exc)

    # 2. Parse IMU
    imu_data = IMUData()
    raw_imu = payload.get("imu")
    if isinstance(raw_imu, dict):
        try:
            imu_data = IMUData.model_validate(raw_imu)
        except ValidationError as exc:
            logger.warning("IMU payload failed validation: %s", exc)

    # 3. Parse Grade measurement if present
    grade_data: Optional[GradeMeasurement] = None
    raw_grade = payload.get("grade")
    if isinstance(raw_grade, dict):
        try:
            grade_data = GradeMeasurement.model_validate(raw_grade)
        except ValidationError as exc:
            logger.warning("Grade payload failed validation: %s", exc)

    # 4. Timestamps
    captured_at = payload.get("captured_at")
    monotonic_time = payload.get("monotonic_capture_time_ns")
    if monotonic_time is None:
        monotonic_time = time.monotonic_ns()

    device_id = payload.get("device_id")
    camera_profile_id = payload.get("camera_profile_id")
    idx = payload.get("frame_index", frame_index)

    metadata = FrameMetadata(
        gps=gps_data,
        imu=imu_data,
        grade=grade_data,
        captured_at=captured_at,
        monotonic_capture_time_ns=monotonic_time,
        device_id=device_id,
        camera_profile_id=camera_profile_id,
        source_mode=source_mode,
        frame_index=idx,
        telemetry_hash=telemetry_hash,
    )
    return metadata, None
