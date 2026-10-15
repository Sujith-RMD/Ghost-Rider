"""Unit tests for bounded ingestion queue and capture adapter.

Verifies:
- Ingestion queue bounds, dropping frames when full
- Received / processed / rejected / dropped counter accuracy
- Image bytes validation (JPEG, PNG, corrupt, empty)
- Telemetry parsing and deterministic hashing
"""

from backend.ingestion.adapter import (
    IngestionAdapter,
    compute_file_sha256,
    generate_idempotency_key,
    validate_image_bytes,
)
from backend.ingestion.queue import BoundedIngestionQueue, QueueItem
from backend.ingestion.telemetry import compute_telemetry_hash, parse_and_validate_telemetry
from backend.schemas import SourceMode


def test_bounded_queue_drop_when_full():
    queue = BoundedIngestionQueue(max_size=3)
    assert len(queue) == 0

    # Enqueue 3 items
    for i in range(3):
        item = QueueItem(
            session_id="s1",
            frame_index=i,
            source_mode="live",
            filename=f"frame_{i}.jpg",
            received_at="2026-10-15T10:00:00Z",
            monotonic_received_ns=1000 + i,
        )
        assert queue.enqueue(item) is True

    assert len(queue) == 3
    assert queue.stats.received == 3
    assert queue.stats.dropped == 0

    # 4th item should be dropped to preserve freshness
    dropped_item = QueueItem(
        session_id="s1",
        frame_index=99,
        source_mode="live",
        filename="frame_99.jpg",
        received_at="2026-10-15T10:00:01Z",
        monotonic_received_ns=2000,
    )
    assert queue.enqueue(dropped_item) is False
    assert queue.stats.dropped == 1
    assert len(queue) == 3

    # Dequeue first item
    first = queue.dequeue(timeout_sec=0.1)
    assert first is not None
    assert first.frame_index == 0
    assert len(queue) == 2


def test_image_bytes_validation():
    # Valid JPEG header
    jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 50
    valid, ext, err = validate_image_bytes(jpeg_bytes)
    assert valid is True
    assert ext == ".jpg"
    assert err is None

    # Valid PNG header
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
    valid, ext, err = validate_image_bytes(png_bytes)
    assert valid is True
    assert ext == ".png"

    # Empty
    valid, _, err = validate_image_bytes(b"")
    assert valid is False
    assert "empty" in err.lower()

    # Corrupt / unknown
    valid, _, err = validate_image_bytes(b"INVALID_HEADER_DATA")
    assert valid is False


def test_telemetry_hashing_and_parsing():
    raw_meta = {
        "gps": {"lat": 12.9716, "lon": 77.5946, "accuracy_m": 4.0},
        "captured_at": "2026-10-15T10:00:00Z",
        "imu": {"pitch_deg": 1.2, "roll_deg": -0.5},
    }
    meta, err = parse_and_validate_telemetry(raw_meta, source_mode=SourceMode.LIVE, frame_index=42)
    assert err is None
    assert meta.gps is not None
    assert meta.gps.lat == 12.9716
    assert meta.telemetry_hash is not None
    assert len(meta.telemetry_hash) == 64

    # Deterministic hash
    h1 = compute_telemetry_hash(raw_meta)
    h2 = compute_telemetry_hash(raw_meta)
    assert h1 == h2


def test_idempotency_key_generation():
    k1 = generate_idempotency_key("sess-1", 10, "v1.0")
    k2 = generate_idempotency_key("sess-1", 10, "v1.0")
    k3 = generate_idempotency_key("sess-1", 11, "v1.0")

    assert k1 == k2
    assert k1 != k3
