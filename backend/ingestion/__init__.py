"""Ghost-Rider camera ingestion and queueing package.

Ownership: Backend & AWS AI
"""

from .adapter import (
    IngestionAdapter,
    compute_file_sha256,
    generate_idempotency_key,
    validate_image_bytes,
)
from .queue import (
    BoundedIngestionQueue,
    QueueItem,
    QueueStats,
    get_ingestion_queue,
)
from .telemetry import (
    compute_telemetry_hash,
    parse_and_validate_telemetry,
)

__all__ = [
    "IngestionAdapter",
    "BoundedIngestionQueue",
    "QueueItem",
    "QueueStats",
    "get_ingestion_queue",
    "compute_file_sha256",
    "generate_idempotency_key",
    "validate_image_bytes",
    "compute_telemetry_hash",
    "parse_and_validate_telemetry",
]
