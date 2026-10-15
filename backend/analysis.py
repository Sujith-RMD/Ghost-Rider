"""Real analysis pipeline wiring for the Ghost-Rider worker.

This module is the backend-side **translation layer** between the ML-owned
modules (:mod:`backend.quality`, :mod:`backend.geometry`,
:mod:`backend.aggregate`) and the API contract (:mod:`backend.schemas`). The
worker calls :func:`decode_image` / :func:`measure_frame`; it never imports the
ML algorithms directly.

Pipeline (per frame):

1. **decode** the image (cv2, Windows-path safe via ``np.fromfile``);
2. **quality gate** — ``backend.quality.classify_quality`` (rejected frames get
   no measurements at all, only the reason codes);
3. **scale** — ``PlanarScale``. No calibration store exists yet (the ML AI owns
   physical calibration), so frames are measured **unscaled**: physical units
   stay ``null`` rather than being invented (final plan: uncalibrated input
   must not gain physical units);
4. **measure** — ``backend.aggregate.measure_surface`` over an all-ones valid
   surface mask (no plane/ROI detector exists yet; the mask is recorded as a
   limitation so measurements are honest about their scope);
5. **translate** — the ML dataclasses/dicts become contract models with strict
   null-vs-zero semantics: counts/ratios are real without scale; anything in
   mm/m²/count-per-m² is ``None`` until calibrated.

The import of the CV stack is guarded so the API still boots (and the worker
still records honest *unknown* results) when opencv/scipy are missing.

Ownership: Backend & AWS AI
Reference: docs/final_plan.md (Sections 2, 11.1); the ML AI owns the
algorithms themselves — this file only wires and translates them.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import numpy as np

from .schemas import (
    AggregatedMetrics,
    AreaResult,
    FrameMetadata,
    QualityResult,
    QualityStatus,
    SegmentResult,
)

logger = logging.getLogger("ghost_rider.analysis")

try:  # pragma: no cover - import guard, exercised implicitly by the test suite
    import cv2

    from .aggregate.measurement import measure_surface
    from .geometry.scale import PlanarScale
    from .quality.validity import classify_quality

    ML_AVAILABLE = True
except Exception as _exc:  # pragma: no cover - missing CV stack
    cv2 = None  # type: ignore[assignment]
    measure_surface = None  # type: ignore[assignment]
    PlanarScale = None  # type: ignore[assignment]
    classify_quality = None  # type: ignore[assignment]
    ML_AVAILABLE = False
    logger.warning("ML analysis stack unavailable (%s); results will be unknown-only.", _exc)


def decode_image(path: Any) -> Optional[np.ndarray]:
    """Decode an image from disk.

    Uses ``np.fromfile`` + ``cv2.imdecode`` so non-ASCII Windows paths decode
    correctly. Returns ``None`` when the file is missing, empty, or undecodable
    (never raises).
    """
    if not ML_AVAILABLE:
        return None
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
        if data.size == 0:
            return None
        image = cv2.imdecode(data, cv2.IMREAD_UNCHANGED)
        return image
    except Exception as exc:
        logger.debug("Could not decode %s: %s", path, exc)
        return None


def resolve_scale(metadata: Optional[FrameMetadata]) -> Any:
    """Build the measurement scale for a frame.

    No calibration store exists yet (the ML AI owns physical calibration), so
    every frame is measured **unscaled** — physical units stay ``null`` instead
    of being invented. ``camera_profile_id`` is recorded as provenance so a
    future calibration store can migrate frames without losing their origin.
    """
    profile = getattr(metadata, "camera_profile_id", None) if metadata else None
    provenance = f"uncalibrated; camera_profile_id={profile}" if profile else "uncalibrated"
    return PlanarScale.unscaled(provenance=provenance)


def _quality_result(report: Any) -> QualityResult:
    """Translate the ML ``QualityReport`` into the contract ``QualityResult``."""
    metrics = report.metrics or {}
    return QualityResult(
        status=QualityStatus(str(report.status)),
        reasons=[str(code) for code in (report.reason_codes or ())],
        min_source_resolution=None,
        sharpness_score=metrics.get("laplacian_variance"),
        glare_present="clipped_highlights" in (report.reason_codes or ()),
        ignored_fraction=None,
    )


def _area_result(measurements: Any, scale: Any) -> Optional[AreaResult]:
    """Translate measured areas (all ``None`` while the scale is unknown)."""
    if measurements is None:
        return None
    return AreaResult(
        observed_area_m2=measurements.observed_area_m2,
        eligible_area_m2=measurements.eligible_area_m2,
        ignored_area_m2=measurements.ignored_area_m2,
        distress_area_m2=measurements.distress_area_m2,
        scale_source=str(scale.source.value),
        scale_uncertainty=scale.relative_area_uncertainty(),
    )


def _metrics_result(measurements: Any) -> Optional[AggregatedMetrics]:
    """Translate aggregate measurements into contract metrics.

    Counts and ratios are dimension-less and stay real without calibration;
    every mm/m²/count-per-m² value is ``None`` until a scale exists.
    """
    if measurements is None:
        return None
    particle = measurements.particle_size or {}
    diameters_mm = particle.get("diameter_mm") or {}
    gap = measurements.gap or {}
    return AggregatedMetrics(
        chip_count=measurements.n_instances_in_roi,
        chip_density_per_m2=measurements.count_density_per_m2,
        min_chip_diameter_mm=measurements.min_measurable_diameter_mm,
        median_chip_diameter_mm=diameters_mm.get("median"),
        aggregate_coverage=measurements.coverage_fraction,
        gap_median_mm=gap.get("median_mm"),
        gap_iqr_mm=gap.get("iqr_mm"),
        gap_p90_mm=gap.get("p90_mm"),
        gap_sample_count=gap.get("sample_count"),
    )


def measure_frame(image: np.ndarray,
                  metadata: Optional[FrameMetadata] = None) -> Dict[str, Any]:
    """Run the real pipeline on a decoded image. Never raises.

    Returns a dict with ``quality``, ``observed_area``, ``metrics``,
    ``geometry_valid`` and ``limitations`` — ready to be spread into a
    :class:`SegmentResult` alongside the worker's identifiers/provenance.
    """
    outcome: Dict[str, Any] = {
        "quality": None,
        "observed_area": None,
        "metrics": None,
        "geometry_valid": False,
        "limitations": [],
    }

    if not ML_AVAILABLE:
        outcome["limitations"].append("ml_stack_unavailable")
        return outcome

    try:
        scale = resolve_scale(metadata)
        report = classify_quality(image, has_scale=scale.is_scaled)
        outcome["quality"] = _quality_result(report)

        if str(report.status) == "rejected":
            # Rejected frames carry reason codes only — no metric evidence.
            outcome["limitations"].append("quality_rejected")
            return outcome

        valid_surface = np.ones(image.shape[:2], dtype=bool)
        measurements = measure_surface(image, valid_surface, scale)
        outcome["observed_area"] = _area_result(measurements, scale)
        outcome["metrics"] = _metrics_result(measurements)
        outcome["geometry_valid"] = bool(scale.is_scaled)
        outcome["limitations"].extend(measurements.limitations or [])
        outcome["limitations"].append(
            "valid_surface_mask_is_full_frame:no_plane_detector_yet"
        )
    except Exception as exc:  # pragma: no cover - ML failure must not crash the worker
        logger.warning("measure_frame failed (%s: %s); recording unknown measurements.",
                       type(exc).__name__, exc)
        outcome["limitations"].append(f"measurement_error:{type(exc).__name__}")

    return outcome


def build_segment_result(*, segment_id: int,
                         route_id: Optional[str],
                         metadata: Optional[FrameMetadata],
                         image_path: Optional[str],
                         image_url: Optional[str],
                         raw_url: Optional[str],
                         model_version: Optional[str],
                         feature_version: Optional[str],
                         scoring_version: Optional[str],
                         mask_url: Optional[str] = None,
                         sample_id: Optional[str] = None,
                         created_at: Optional[str] = None,
                         measured: Optional[Dict[str, Any]] = None) -> SegmentResult:
    """Compose the contract :class:`SegmentResult` for one analysed frame.

    ``measured`` is the :func:`measure_frame` outcome (or ``None`` when no
    image could be decoded — every measurement then stays unknown).
    """
    measured = measured or {}
    return SegmentResult(
        segment_id=segment_id,
        route_id=route_id,
        sample_id=sample_id,
        image_path=image_path,
        image_url=image_url,
        raw_url=raw_url,
        mask_url=mask_url,
        captured_at=metadata.captured_at if metadata else None,
        gps=metadata.gps if metadata else None,
        grade=metadata.grade if metadata else None,
        geometry_valid=bool(measured.get("geometry_valid", False)),
        observed_area=measured.get("observed_area"),
        quality=measured.get("quality"),
        metrics=measured.get("metrics"),
        evidence=None,
        score=None,
        reference=None,
        model_version=model_version,
        feature_version=feature_version,
        scoring_version=scoring_version,
        created_at=created_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        error=None,
    )


__all__ = [
    "ML_AVAILABLE",
    "build_segment_result",
    "decode_image",
    "measure_frame",
    "resolve_scale",
]
