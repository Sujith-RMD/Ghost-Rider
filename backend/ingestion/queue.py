"""Bounded ingestion queue for live and replay road-camera frames.

When the queue is full, new frames are dropped and logged so a stale result
cannot appear current, and the system never exhausts worker memory.
Received, processed, rejected, and dropped counters are tracked durably.

Ownership: Backend & AWS AI
Reference: docs/final_plan.md (Section 11.3)
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ghost_rider.ingestion.queue")


@dataclass
class QueueItem:
    """Item held in the ingestion queue."""

    session_id: str
    frame_index: int
    source_mode: str
    filename: str
    received_at: str
    monotonic_received_ns: int
    image_path: Optional[str] = None
    metadata_json: Optional[str] = None
    raw_bytes: Optional[bytes] = None


@dataclass
class QueueStats:
    """Ingestion queue operational counters."""

    received: int = 0
    processed: int = 0
    rejected: int = 0
    dropped: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "received": self.received,
            "processed": self.processed,
            "rejected": self.rejected,
            "dropped": self.dropped,
        }


class BoundedIngestionQueue:
    """Thread-safe bounded in-memory queue with backpressure handling."""

    def __init__(self, max_size: int = 256) -> None:
        self.max_size = max(1, max_size)
        self._queue: List[QueueItem] = []
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._closed = False
        self.stats = QueueStats()

    def enqueue(self, item: QueueItem) -> bool:
        """Enqueue an item. Returns False and increments dropped count if full."""
        with self._cv:
            if self._closed:
                logger.warning("Queue is closed; rejecting frame %s:%d", item.session_id, item.frame_index)
                return False

            if len(self._queue) >= self.max_size:
                self.stats.dropped += 1
                logger.warning(
                    "Ingestion queue full (%d/%d); dropped frame %s:%d to preserve freshness",
                    len(self._queue),
                    self.max_size,
                    item.session_id,
                    item.frame_index,
                )
                return False

            self._queue.append(item)
            self.stats.received += 1
            self._cv.notify()
            return True

    def dequeue(self, timeout_sec: float = 1.0) -> Optional[QueueItem]:
        """Dequeue an item with timeout. Returns None if timed out."""
        with self._cv:
            deadline = time.monotonic() + timeout_sec if timeout_sec > 0 else 0.0
            while not self._queue and not self._closed:
                if timeout_sec > 0:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return None
                    self._cv.wait(timeout=remaining)
                else:
                    self._cv.wait()

            if self._queue:
                return self._queue.pop(0)
            return None

    def mark_processed(self) -> None:
        """Increment processed count."""
        with self._lock:
            self.stats.processed += 1

    def mark_rejected(self) -> None:
        """Increment rejected count (e.g. QC failure, corrupt image)."""
        with self._lock:
            self.stats.rejected += 1

    def close(self) -> None:
        """Close queue to new items and unblock waiting threads."""
        with self._cv:
            self._closed = True
            self._cv.notify_all()

    def clear(self) -> None:
        """Clear queue items and reset counters (mainly for testing)."""
        with self._lock:
            self._queue.clear()
            self.stats = QueueStats()

    def __len__(self) -> int:
        with self._lock:
            return len(self._queue)

    def is_empty(self) -> bool:
        with self._lock:
            return len(self._queue) == 0


# Global shared instance
_GLOBAL_QUEUE = BoundedIngestionQueue(max_size=256)


def get_ingestion_queue() -> BoundedIngestionQueue:
    """Return the global bounded queue instance."""
    return _GLOBAL_QUEUE
