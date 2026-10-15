"""Image validity and supported-domain checks.

Owned by the ML role (``docs/ML_ROLE.md`` section 1).

Final plan section 7.2 requires affected metrics to be *rejected or suppressed*
for decode failure, absent scale, excessive blur, clipping/glare, invalid
surface, changed zoom/crop, unstable plane and inadequate source resolution, and
section 11.5 puts an explicit ``accepted``/``limited``/``rejected`` status plus
reason codes in the canonical record. This module supplies that verdict and its
evidence.

Two honesty rules are built into the design rather than left to the caller:

1. **A missing scale is not an image defect, but it is not metric evidence
   either.** It produces ``limited`` with ``scale_missing``, and
   ``is_metric_evidence`` is false. A clean image with no scale can still support
   appearance-only observations; it can never support mm, cm^2 or count/m^2.
2. **The thresholds are not calibrated.** Final plan section 7.2 explicitly warns
   that one universal Laplacian threshold can mistake smooth good asphalt for
   blur, and requires thresholds calibrated from accepted/rejected examples *per
   rig* (task C11). No rig exists yet, so ``QualityPolicy.thresholds_calibrated``
   is ``False`` by default and the flag travels into every report. Nothing here
   may be presented as a calibrated rejection policy.

The one real measurement available - the CRKWH100 audit, where Laplacian variance
was 51 (min) / 435 (median) / 2,721 (max) over 100 images - is why the provisional
sharpness floor is deliberately low: a high default would reject real pavement
images before any per-rig calibration exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

__all__ = [
    "QUALITY_STATUSES",
    "REASON_CODES",
    "QualityPolicy",
    "QualityReport",
    "classify_quality",
    "image_metrics",
]

QUALITY_STATUSES = ("accepted", "limited", "rejected")
"""The status vocabulary of final plan section 11.5. No other value is valid."""

REASON_CODES = {
    "decode_failed": "decode_failed",
    "unsupported_channels": "unsupported_channels",
    "inadequate_source_resolution": "inadequate_source_resolution",
    "insufficient_sharpness": "insufficient_sharpness",
    "clipped_highlights": "clipped_highlights",
    "clipped_shadows": "clipped_shadows",
    "low_dynamic_range": "low_dynamic_range",
    "scale_missing": "scale_missing",
}
"""Reason codes. ``scale_missing`` is the only one that is not an image defect."""

_REJECT_CLASS = {
    REASON_CODES["decode_failed"],
    REASON_CODES["unsupported_channels"],
    REASON_CODES["inadequate_source_resolution"],
    REASON_CODES["insufficient_sharpness"],
    REASON_CODES["clipped_highlights"],
    REASON_CODES["clipped_shadows"],
}
_LIMIT_CLASS = {
    REASON_CODES["low_dynamic_range"],
    REASON_CODES["scale_missing"],
}


@dataclass(frozen=True)
class QualityPolicy:
    """Provisional validity thresholds and the explicit calibration flag."""

    policy_version: str = "quality-v1"

    thresholds_calibrated: bool = False
    """``False`` means these numbers are engineering defaults, not a validated
    rejection policy. Final plan section 7.2 requires per-rig calibration from
    labelled accepted/rejected examples (task C11, blocked on camera access), so
    every report repeats this flag and no caller has to remember it."""

    min_source_px: int = 256
    """Shortest permitted side. Below the declared minimum measurable particle
    there is no point segmenting, so the sample is rejected rather than scored."""

    min_laplacian_variance: float = 10.0
    """Provisional sharpness floor. Deliberately low: the only measured real
    range (CRKWH100) is 51 minimum, and a universal higher floor would reject real
    pavement before per-rig calibration exists."""

    min_dynamic_range: int = 40
    """Provisional 1st-99th percentile spread below which the image is ``limited``
    rather than rejected: contrast is poor, but the pixels are still real."""

    clip_fraction_reject: float = 0.10
    """Fraction of pixels at an intensity extreme that makes the frame unusable.
    Glare removes the surface, and black crush removes the texture."""

    supported_channels: tuple[int, ...] = (1, 3, 4)

    def __post_init__(self) -> None:
        if int(self.min_source_px) < 1:
            raise ValueError("min_source_px must be >= 1")
        if float(self.min_laplacian_variance) < 0.0:
            raise ValueError("min_laplacian_variance must be >= 0")
        if int(self.min_dynamic_range) < 0:
            raise ValueError("min_dynamic_range must be >= 0")
        if not 0.0 <= float(self.clip_fraction_reject) <= 1.0:
            raise ValueError("clip_fraction_reject must be in [0, 1]")
        if not self.supported_channels:
            raise ValueError("supported_channels must not be empty")


@dataclass(frozen=True)
class QualityReport:
    """One validity verdict with its evidence and its calibration status."""

    status: str
    reason_codes: tuple[str, ...]
    metrics: dict
    policy_version: str
    thresholds_calibrated: bool
    has_scale: bool
    is_metric_evidence: bool
    _extra: dict = field(default_factory=dict, repr=False)

    def describe(self) -> dict:
        return {
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "policy_version": self.policy_version,
            "thresholds_calibrated": self.thresholds_calibrated,
            "has_scale": self.has_scale,
            "is_metric_evidence": self.is_metric_evidence,
            "metrics": dict(self.metrics),
        }


def _to_gray_float(image: np.ndarray) -> np.ndarray:
    """Mean-intensity 2D float view, so any channel count is measurable."""
    arr = np.asarray(image)
    if arr.ndim == 3:
        return arr.astype(np.float64).mean(axis=2)
    return arr.astype(np.float64)


def image_metrics(image: np.ndarray | None) -> dict:
    """Measurable image facts, or an explicit decode failure.

    Final plan section 6.1 item 2 requires a failure to be *recorded* rather than
    silently skipped, so an unreadable input returns ``decode_ok: False`` instead
    of raising and taking the batch down with it. Sizes and sharpness are reported
    with their units; the sharpness number is a Laplacian variance in grey-level^2
    and is never a millimetre measurement.
    """
    if image is None:
        return {
            "decode_ok": False,
            "width": None,
            "height": None,
            "channels": None,
            "laplacian_variance": None,
            "dynamic_range": None,
            "clipped_high_fraction": None,
            "clipped_low_fraction": None,
            "mean_intensity": None,
        }

    arr = np.asarray(image)
    if arr.size == 0 or arr.ndim not in (2, 3) or min(arr.shape[:2]) < 1:
        return {
            "decode_ok": False,
            "width": None,
            "height": None,
            "channels": None,
            "laplacian_variance": None,
            "dynamic_range": None,
            "clipped_high_fraction": None,
            "clipped_low_fraction": None,
            "mean_intensity": None,
        }

    channels = 1 if arr.ndim == 2 else int(arr.shape[2])
    gray = _to_gray_float(arr)

    if np.issubdtype(arr.dtype, np.integer):
        info = np.iinfo(arr.dtype)
        low_limit, high_limit = float(info.min), float(info.max)
    else:
        # Float imagery has no fixed intensity scale, so extremes are the observed
        # ones and the clipping fractions are reported as 0 rather than invented.
        low_limit = high_limit = None

    if low_limit is None:
        clipped_high = clipped_low = 0.0
    else:
        clipped_high = float(np.count_nonzero(gray >= high_limit) / gray.size)
        clipped_low = float(np.count_nonzero(gray <= low_limit) / gray.size)

    # Laplacian on an 8-bit source: this OpenCV build rejects a float32 source
    # with a CV_64F destination ("unsupported combination of source format"), and
    # an 8-bit source keeps the definition identical to the one used for the
    # CRKWH100 audit numbers this module cites.
    laplacian = cv2.Laplacian(np.clip(gray, 0.0, 255.0).astype(np.uint8), cv2.CV_64F)
    p1, p99 = np.percentile(gray, [1.0, 99.0])
    return {
        "decode_ok": True,
        "width": int(arr.shape[1]),
        "height": int(arr.shape[0]),
        "channels": channels,
        "laplacian_variance": float(laplacian.var()),
        "dynamic_range": float(p99 - p1),
        "clipped_high_fraction": clipped_high,
        "clipped_low_fraction": clipped_low,
        "mean_intensity": float(gray.mean()),
    }


def classify_quality(
    image: np.ndarray | None,
    policy: QualityPolicy | None = None,
    has_scale: bool = True,
) -> QualityReport:
    """Decide ``accepted`` / ``limited`` / ``rejected`` and say why.

    ``has_scale`` is supplied by the caller (geometry, not pixels) and only ever
    produces ``limited``: an unscaled image is not a broken image, it is an image
    that cannot carry metric claims.
    """
    policy = policy or QualityPolicy()
    metrics = image_metrics(image)

    if not metrics["decode_ok"]:
        return QualityReport(
            status="rejected",
            reason_codes=(REASON_CODES["decode_failed"],),
            metrics=metrics,
            policy_version=policy.policy_version,
            thresholds_calibrated=policy.thresholds_calibrated,
            has_scale=bool(has_scale),
            is_metric_evidence=False,
        )

    reasons: list[str] = []
    if int(metrics["channels"]) not in policy.supported_channels:
        reasons.append(REASON_CODES["unsupported_channels"])
    if min(int(metrics["width"]), int(metrics["height"])) < int(policy.min_source_px):
        reasons.append(REASON_CODES["inadequate_source_resolution"])
    if float(metrics["laplacian_variance"]) < float(policy.min_laplacian_variance):
        reasons.append(REASON_CODES["insufficient_sharpness"])
    if float(metrics["clipped_high_fraction"]) >= float(policy.clip_fraction_reject):
        reasons.append(REASON_CODES["clipped_highlights"])
    if float(metrics["clipped_low_fraction"]) >= float(policy.clip_fraction_reject):
        reasons.append(REASON_CODES["clipped_shadows"])
    if float(metrics["dynamic_range"]) < float(policy.min_dynamic_range):
        reasons.append(REASON_CODES["low_dynamic_range"])
    if not has_scale:
        reasons.append(REASON_CODES["scale_missing"])

    if any(code in _REJECT_CLASS for code in reasons):
        status = "rejected"
    elif any(code in _LIMIT_CLASS for code in reasons):
        status = "limited"
    else:
        status = "accepted"

    return QualityReport(
        status=status,
        reason_codes=tuple(reasons),
        metrics=metrics,
        policy_version=policy.policy_version,
        thresholds_calibrated=policy.thresholds_calibrated,
        has_scale=bool(has_scale),
        is_metric_evidence=(status == "accepted" and bool(has_scale)),
    )
