"""Image validity and supported-domain checks (ML-owned).

See :mod:`backend.quality.validity` for the implementation and the two honesty
rules it enforces: a missing scale limits rather than rejects, and the thresholds
are explicitly not calibrated until a camera rig exists (task C11).
"""

from __future__ import annotations

from backend.quality.validity import (
    QUALITY_STATUSES,
    REASON_CODES,
    QualityPolicy,
    QualityReport,
    classify_quality,
    image_metrics,
)

__all__ = [
    "QUALITY_STATUSES",
    "REASON_CODES",
    "QualityPolicy",
    "QualityReport",
    "classify_quality",
    "image_metrics",
]
