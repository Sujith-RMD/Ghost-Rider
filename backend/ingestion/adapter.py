"""Unified ingestion adapter for upload, live camera, and replay frames.

Ownership: Backend & AWS AI
Reference: docs/final_plan.md (Section 2, 11.3, 11.5)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ..schemas import FrameMetadata, SourceMode
from .queue import QueueItem, get_ingestion_queue
from .telemetry import parse_and_validate_telemetry

logger = logging.getLogger("ghost_rider.ingestion.adapter")

IMAGE_MAGIC = (
    (b"\xff\xd8\xff", ".jpg"),            # JPEG
    (b"\x89PNG\r\n\x1a\n", ".png"),       # PNG
    (b"BM", ".bmp"),                      # BMP
    (b"RIFF", ".webp"),                   # WebP container
)

MAX_FRAME_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB limit


def validate_image_bytes(content: bytes) -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate image bytes by length and magic header.

    Returns:
        (is_valid, detected_extension, error_message)
    """
    if not content:
        return False, None, "Image content is empty"
    if len(content) > MAX_FRAME_SIZE_BYTES:
        return False, None, f"Image size exceeds maximum limit of {MAX_FRAME_SIZE_BYTES} bytes"

    for magic, ext in IMAGE_MAGIC:
        if content.startswith(magic):
            # For RIFF, ensure it's WEBP
            if magic == b"RIFF" and len(content) >= 12 and content[8:12] != b"WEBP":
                continue
            return True, ext, None

    return False, None, "Unsupported image format or corrupt header"


def compute_file_sha256(content: bytes) -> str:
    """Compute SHA-256 hash of image file content."""
    return hashlib.sha256(content).hexdigest()


def generate_idempotency_key(session_id: str, frame_index: int, model_version: str) -> str:
    """Generate canonical idempotency key for (session_id, frame_sequence, model_version)."""
    raw = f"{session_id}:{frame_index}:{model_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class IngestionAdapter:
    """Unified adapter coordinating frame admission, persistence, and queueing."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        if base_dir is None:
            self.base_dir = Path(__file__).resolve().parent.parent / "uploads"
        else:
            self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.queue = get_ingestion_queue()

    def process_incoming_frame(
        self,
        session_id: str,
        frame_index: int,
        source_mode: SourceMode,
        raw_bytes: bytes,
        filename: str = "frame.jpg",
        raw_metadata: Any = None,
    ) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """Validate, persist locally, parse telemetry, and enqueue a frame.

        Returns:
            (success, frame_record, error_message)
        """
        # 1. Validate image format
        is_valid, ext, err = validate_image_bytes(raw_bytes)
        if not is_valid:
            self.queue.mark_rejected()
            logger.warning("Frame validation failed for %s:%d: %s", session_id, frame_index, err)
            return False, {}, err

        # 2. Compute file hash
        file_sha256 = compute_file_sha256(raw_bytes)

        # 3. Parse and validate telemetry
        metadata, telem_err = parse_and_validate_telemetry(
            raw_metadata=raw_metadata,
            source_mode=source_mode,
            frame_index=frame_index,
        )
        if telem_err:
            logger.warning("Telemetry warning for %s:%d: %s", session_id, frame_index, telem_err)

        # 4. Save frame file to session folder
        session_folder = self.base_dir / session_id
        session_folder.mkdir(parents=True, exist_ok=True)
        target_name = f"frame_{frame_index:06d}{ext or '.jpg'}"
        saved_path = session_folder / target_name
        try:
            saved_path.write_bytes(raw_bytes)
        except Exception as exc:
            logger.exception("Failed to write frame to %s: %s", saved_path, exc)
            return False, {}, f"Disk write error: {exc}"

        received_at = datetime.now(timezone.utc).isoformat()
        monotonic_now = time.monotonic_ns()

        record: Dict[str, Any] = {
            "session_id": session_id,
            "frame_index": frame_index,
            "source_mode": source_mode.value,
            "filename": target_name,
            "image_path": str(saved_path),
            "file_sha256": file_sha256,
            "received_at": received_at,
            "metadata": metadata.model_dump(),
        }

        # 5. Enqueue in bounded live queue
        item = QueueItem(
            session_id=session_id,
            frame_index=frame_index,
            source_mode=source_mode.value,
            filename=target_name,
            received_at=received_at,
            monotonic_received_ns=monotonic_now,
            image_path=str(saved_path),
            metadata_json=json.dumps(metadata.model_dump()),
            raw_bytes=None,  # Frame is persisted to disk, free memory
        )

        enqueued = self.queue.enqueue(item)
        record["enqueued"] = enqueued
        if not enqueued:
            record["dropped"] = True
            return True, record, "Frame received and stored, but dropped from live inference queue (queue full)"

        return True, record, None
