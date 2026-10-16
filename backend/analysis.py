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
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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

    from .aggregate.measurement import MeasurementConfig, measure_surface
    from .aggregate.tiling import TilingConfig, measure_tiled, segment_tiled_with_stages
    from .distress.features import DISTRESS_METHOD_VERSION, distress_metrics
    from .geometry.scale import PlanarScale
    from .quality.validity import classify_quality

    ML_AVAILABLE = True
except Exception as _exc:  # pragma: no cover - missing CV stack
    cv2 = None  # type: ignore[assignment]
    measure_surface = None  # type: ignore[assignment]
    measure_tiled = None  # type: ignore[assignment]
    segment_tiled_with_stages = None  # type: ignore[assignment]
    distress_metrics = None  # type: ignore[assignment]
    PlanarScale = None  # type: ignore[assignment]
    classify_quality = None  # type: ignore[assignment]
    ML_AVAILABLE = False
    logger.warning("ML analysis stack unavailable (%s); results will be unknown-only.", _exc)


# Real camera frames are far larger than one practical watershed tile; the ML
# team's tiling entry point stitches native-resolution tiles and merges
# straddling instances so nothing is counted twice. Frames at or below the tile
# size degenerate to a single tile (no behavioural change).
DEFAULT_TILING = TilingConfig() if ML_AVAILABLE else None


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


def _distress_metrics_result(measured_distress: Any) -> Dict[str, Optional[float]]:
    """Translate a :class:`DistressMetrics` record into contract fields.

    Only the fields the contract defines are filled; the remaining measures
    (crack density, extent fraction) surface through the canonical record's
    free-form feature list. Unscaled imagery yields ``None`` — never a
    fabricated zero (the ML module guarantees this).
    """
    if measured_distress is None:
        return {"crack_skeleton_length_m": None, "crack_total_area_m2": None}
    return {
        "crack_skeleton_length_m": measured_distress.skeleton_length_m,
        "crack_total_area_m2": measured_distress.defect_area_m2,
    }


def measure_frame(image: np.ndarray,
                  metadata: Optional[FrameMetadata] = None,
                  crack_mask: Optional[np.ndarray] = None,
                  distress_mask: Optional[np.ndarray] = None,
                  include_processing_stages: bool = False,
                  valid_surface_mask: Optional[np.ndarray] = None) -> Dict[str, Any]:
    """Run the real pipeline on a decoded image. Never raises.

    Returns a dict with ``quality``, ``observed_area``, ``metrics``,
    ``geometry_valid``, ``limitations`` and ``image_shape`` — ready to be
    spread into a :class:`SegmentResult` / canonical record alongside the
    worker's identifiers/provenance.

    ``crack_mask`` / ``distress_mask`` are booleans masks of the same H×W as
    the image. A runtime crack/pothole detector (the ML training track) will
    supply them; until then they are ``None`` and distress fields stay ``null``.
    """
    outcome: Dict[str, Any] = {
        "quality": None,
        "observed_area": None,
        "metrics": None,
        "geometry_valid": False,
        "limitations": [],
        "image_shape": tuple(int(v) for v in image.shape[:2]),
        "distress": None,
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

        if valid_surface_mask is None:
            valid_surface = np.ones(image.shape[:2], dtype=bool)
        else:
            valid_surface = np.asarray(valid_surface_mask)
            if valid_surface.ndim != 2 or valid_surface.shape != image.shape[:2]:
                outcome["limitations"].append("invalid_surface_roi_shape")
                return outcome
            valid_surface = valid_surface.astype(bool)
        if include_processing_stages:
            measurement_config = MeasurementConfig()
            labels, stages = segment_tiled_with_stages(
                image, DEFAULT_TILING, measurement_config.watershed
            )
            measurements = measure_surface(
                image=labels,
                valid_surface_mask=valid_surface,
                scale=scale,
                config=measurement_config,
                distress_mask=distress_mask,
                labels=labels,
            )
            outcome["processing_stages"] = stages
        else:
            measurements, _labels = measure_tiled(
                image,
                valid_surface,
                scale,
                tiling=DEFAULT_TILING,
                distress_mask=distress_mask,
            )
        outcome["observed_area"] = _area_result(measurements, scale)
        metrics = _metrics_result(measurements)
        outcome["metrics"] = metrics
        outcome["geometry_valid"] = bool(scale.is_scaled)
        outcome["limitations"].extend(measurements.limitations or [])
        outcome["limitations"].append(
            "manual_surface_roi_applied" if valid_surface_mask is not None
            else "valid_surface_mask_is_full_frame:no_plane_detector_yet"
        )

        if crack_mask is not None:
            distress_record = distress_metrics(crack_mask, scale, valid_surface)
            outcome["distress_record"] = distress_record
            outcome["distress"] = _distress_metrics_result(distress_record)
            if metrics is not None:
                for field, value in outcome["distress"].items():
                    setattr(metrics, field, value)
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
        error=next(
            (reason for reason in measured.get("limitations", [])
             if reason == "ml_stack_unavailable" or reason.startswith("measurement_error:")),
            None,
        ),
    )


# --------------------------------------------------------------------------- #
# Canonical sample record (final plan §11.5)
# --------------------------------------------------------------------------- #

def _feature_list(metrics: Any, distress: Any, estimator_version: str) -> List[Any]:
    """Flatten measured metrics into the canonical free-form feature list.

    Each measured value becomes one feature row with an explicit unit; values
    that are ``None`` (unknown/uncalibrated) are **omitted** rather than stored
    as zero — the canonical record keeps null-vs-zero semantics at the row
    level instead of inside a value.
    """
    from .schemas import MetricResult

    if metrics is None and distress is None:
        return []

    def _row(name: str, value: Any, unit: str, notes: Optional[str] = None) -> Any:
        return MetricResult(
            name=name, value=float(value), unit=unit, valid=True,
            estimator_version=estimator_version, notes=notes,
        )

    features: List[Any] = []

    if distress is not None:
        # Full distress record (density / extent) measured from a crack mask.
        for field, name, unit in (
            ("skeleton_length_m", "crack_skeleton_length", "m"),
            ("crack_density_m_per_m2", "crack_density", "m/m2"),
            ("defect_area_m2", "crack_area", "m2"),
            ("extent_fraction", "crack_extent", "ratio"),
        ):
            value = getattr(distress, field, None)
            if value is not None:
                features.append(_row(name, value, unit))

    if metrics is None:
        return features

    features.append(_row("chip_count", metrics.chip_count, "count"))
    if metrics.chip_density_per_m2 is not None:
        features.append(_row("chip_count_density", metrics.chip_density_per_m2, "count/m2"))
    if metrics.aggregate_coverage is not None:
        features.append(_row("aggregate_coverage", metrics.aggregate_coverage, "ratio"))
    if metrics.median_chip_diameter_mm is not None:
        features.append(_row("median_chip_diameter", metrics.median_chip_diameter_mm, "mm"))
    if metrics.min_chip_diameter_mm is not None:
        features.append(_row("min_resolvable_chip_diameter", metrics.min_chip_diameter_mm, "mm"))
    for gap_field, gap_name in (
        ("gap_median_mm", "gap_median"),
        ("gap_iqr_mm", "gap_iqr"),
        ("gap_p90_mm", "gap_p90"),
    ):
        value = getattr(metrics, gap_field, None)
        if value is not None:
            features.append(_row(gap_name, value, "mm"))
    if metrics.gap_sample_count is not None:
        features.append(_row("gap_sample_count", metrics.gap_sample_count, "count"))

    return features


def build_canonical_record(*, sample_id: str,
                           route_id: Optional[str],
                           sequence_id: Optional[int],
                           metadata: Optional[FrameMetadata],
                           measured: Dict[str, Any],
                           image_path: Optional[str],
                           file_sha256: Optional[str],
                           received_at: Optional[str],
                           model_version: Optional[str],
                           feature_version: Optional[str],
                           scoring_version: Optional[str]) -> Optional[Any]:
    """Build the canonical sample record (final plan §11.5), or ``None``.

    Returns ``None`` when the mandatory provenance (file hash + original URI)
    is unavailable — the canonical record is then simply absent rather than
    partially fabricated.
    """
    from .schemas import (
        CanonicalSampleRecord,
        MetricResult,
        SampleAudit,
        SampleCamera,
        SampleCoverage,
        SampleGeometry,
        SampleIdentity,
        SampleLocation,
        SampleNarrative,
        SampleProvenance,
        SampleTime,
        ScoreResult,
    )

    measured = measured or {}
    original_uri = image_path
    if not file_sha256 or not original_uri:
        return None
    quality = measured.get("quality")
    if quality is None:
        # The canonical record's quality field is mandatory: it is only built
        # when the pipeline actually measured one (rejected frames included).
        return None

    metrics = measured.get("metrics")
    area = measured.get("observed_area")
    image_shape = measured.get("image_shape") or (None, None)
    distress = measured.get("distress_record")

    gps = metadata.gps if metadata else None
    scale = resolve_scale(metadata)
    location = SampleLocation(
        lat=gps.lat if gps else None,
        lon=gps.lon if gps else None,
        accuracy_m=gps.accuracy_m if gps else None,
        route_distance_m=None,          # no odometry/GPS polyline yet
        distance_source=None,
        is_simulated=bool(gps.simulated) if gps else False,
    )
    geometry = SampleGeometry(
        scale_source=str(scale.source.value),
        sx_sy_or_h=[scale.sx_mm_per_px, scale.sy_mm_per_px] if scale.is_scaled else None,
        valid_roi=None,                  # full-frame ROI until a plane detector exists
        observed_area_m2=area.observed_area_m2 if area else None,
        error_bound_pct=(
            max(scale.relative_area_uncertainty() or 0.0, 0.0) * 100.0
            if scale.is_scaled else None
        ),
    )

    features = _feature_list(metrics, distress, feature_version or "unknown")

    return CanonicalSampleRecord(
        identity=SampleIdentity(
            sample_id=sample_id,
            session_id=route_id,
            source_dataset=None,
            parent_id=image_path,
            sequence_id=sequence_id,
        ),
        provenance=SampleProvenance(
            file_sha256=file_sha256,
            original_uri=original_uri,
            split_group=None,
        ),
        time=SampleTime(
            captured_at_utc=metadata.captured_at if metadata else None,
            monotonic_capture_time_ns=metadata.monotonic_capture_time_ns if metadata else None,
            received_at=received_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            processed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
        camera=SampleCamera(
            camera_id=metadata.device_id if metadata else None,
            calibration_id=metadata.camera_profile_id if metadata else None,
            width_px=image_shape[1],
            height_px=image_shape[0],
            crop_state=None,
        ),
        location=location,
        geometry=geometry,
        quality=quality,
        features=features,
        assessment=ScoreResult(status="unknown"),  # scoring module not delivered yet
        coverage=SampleCoverage(
            frame_interval_m=None,        # needs GPS spacing between frames
            inspected_strip_m=None,       # needs calibrated strip width
            unique_area_m2=None,          # registration unreliable → unknown
            coverage_method="conservative_spacing",
        ),
        audit=SampleAudit(
            model_hash=None,
            code_commit=os.getenv("GHOST_RIDER_COMMIT") or None,
            config_hash=None,
        ),
        narrative=SampleNarrative(status="not_requested"),
    )


__all__ = [
    "ML_AVAILABLE",
    "build_canonical_record",
    "build_segment_result",
    "decode_image",
    "measure_frame",
    "resolve_scale",
]
