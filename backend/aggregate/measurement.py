"""Aggregate measurement record: one image in, versioned features out.

Owned by the ML role (``docs/ML_ROLE.md`` section 1).

This is the thin vertical slice that final plan section 14 calls the "real
image-to-measurement slice": image -> segmentation -> instance metrics ->
physical features -> versioned JSON.

It deliberately does *not* apply quality accept/reject decisions (that is
``backend/quality/``), a known-good reference (``backend/reference/``) or a score
(``backend/scoring/``). It reports measured values, their units, their
provenance and an explicit list of limitations.

Denominator safeguard (final plan section 7.3): observed road area,
texture-eligible intact area, ignored area and distress area are recorded
separately, so excluding a pothole from texture never erases its damage
contribution.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import scipy.ndimage as ndi

from backend.aggregate.features import (
    GAP_METHOD_VERSION,
    aggregate_coverage,
    count_density_per_m2,
    gap_statistics,
    particle_size_stats,
)
from backend.aggregate.segmentation import (
    WatershedConfig,
    instance_properties,
    segment_aggregate,
)
from backend.geometry.scale import PlanarScale

__all__ = [
    "MeasurementConfig",
    "SurfaceMeasurements",
    "measure_surface",
]


@dataclass(frozen=True)
class MeasurementConfig:
    """Configuration for :func:`measure_surface`.

    ``config_version`` and the nested watershed ``config_version`` are written
    into every record so a change in measurement behaviour is traceable and can
    force a reference/score revalidation (final plan section 9.2).
    """

    config_version: str = "measure-v1"
    min_diameter_px: float = 3.0
    """Declared visible minimum particle diameter. Excluding smaller particles
    changes the reported density, so changing this requires a new reference."""

    min_gap_px: float = 3.0
    """Declared lower reporting limit for gaps (final plan section 13.2)."""

    roi_margin_px: int = 4
    """Interior counting ROI margin. Instances are segmented with the full frame
    as context but counted only when their centroid falls inside the eroded ROI."""

    watershed: WatershedConfig = WatershedConfig()

    def __post_init__(self) -> None:
        if float(self.min_diameter_px) < 0.0:
            raise ValueError("min_diameter_px must be >= 0")
        if float(self.min_gap_px) < 1.0:
            raise ValueError("min_gap_px must be >= 1 pixel")
        if int(self.roi_margin_px) < 0:
            raise ValueError("roi_margin_px must be >= 0")


@dataclass(frozen=True)
class SurfaceMeasurements:
    """Measured aggregate features for one image.

    Every physical field is ``None`` when it is unavailable (typically missing
    scale) and ``0.0``/``0`` only when it was genuinely measured as absent.
    """

    config_version: str
    segmentation_version: str
    scale: PlanarScale

    n_instances_in_roi: int
    n_instances_total: int

    observed_area_m2: float | None
    eligible_area_m2: float | None
    ignored_area_m2: float | None
    distress_area_m2: float | None

    count_density_per_m2: float | None
    coverage_fraction: float | None
    particle_size: dict = field(default_factory=dict)
    gap: dict = field(default_factory=dict)

    min_measurable_diameter_mm: float | None = None
    min_measurable_gap_mm: float | None = None
    limitations: list[str] = field(default_factory=list)

    def describe(self) -> dict:
        """JSON-serializable record. ``None`` means unavailable, never zero."""
        payload = {
            "config_version": self.config_version,
            "segmentation_version": self.segmentation_version,
            "geometry": self.scale.describe(),
            "counts": {
                "n_instances_in_roi": self.n_instances_in_roi,
                "n_instances_total": self.n_instances_total,
            },
            "areas_m2": {
                "observed": self.observed_area_m2,
                "texture_eligible": self.eligible_area_m2,
                "ignored": self.ignored_area_m2,
                "distress": self.distress_area_m2,
            },
            "count_density_per_m2": self.count_density_per_m2,
            "coverage_fraction": self.coverage_fraction,
            "particle_size": self.particle_size,
            "gap": self.gap,
            "min_measurable_diameter_mm": self.min_measurable_diameter_mm,
            "min_measurable_gap_mm": self.min_measurable_gap_mm,
            "limitations": list(self.limitations),
        }
        return payload


def _as_mask(mask: np.ndarray, shape: tuple[int, int], name: str) -> np.ndarray:
    array = np.asarray(mask)
    if array.ndim == 3:
        array = array[..., 0]
    if array.shape != shape:
        raise ValueError(f"{name} shape {array.shape} does not match image {shape}")
    return array.astype(bool)


def measure_surface(
    image: np.ndarray,
    valid_surface_mask: np.ndarray,
    scale: PlanarScale,
    config: MeasurementConfig | None = None,
    ignore_mask: np.ndarray | None = None,
    distress_mask: np.ndarray | None = None,
    labels: np.ndarray | None = None,
) -> SurfaceMeasurements:
    """Measure aggregate features for one image.

    Parameters
    ----------
    image:
        2D grayscale or 3-channel BGR image of the road surface.
    valid_surface_mask:
        True where the plane is usable road surface (setup 4, final plan 6.3).
    scale:
        Physical scale with explicit provenance. Unscaled imagery yields pixel
        metrics and ``None`` for every metric quantity.
    ignore_mask:
        Unresolvable boundaries, glare, water, occlusion. Excluded from the
        eligible denominator and from gap sites.
    distress_mask:
        Cracks/potholes/patches. Excluded from the *texture* denominator but
        still reported separately as its own area.
    labels:
        Optional precomputed instance label map from
        :func:`backend.aggregate.tiling.segment_tiled`. When supplied,
        segmentation is *not* re-run, so a particle that was merged across a
        tile boundary stays merged. ``image`` is then only used for its shape,
        and may be any array of that shape.
    """
    config = config or MeasurementConfig()
    if not isinstance(scale, PlanarScale):
        raise TypeError("scale must be a PlanarScale")

    arr = np.asarray(image)
    if arr.ndim == 3:
        gray_shape = arr.shape[:2]
    elif arr.ndim == 2:
        gray_shape = arr.shape
    else:
        raise ValueError(f"expected a 2D or 3D image, got shape {arr.shape}")

    valid = _as_mask(valid_surface_mask, gray_shape, "valid_surface_mask")
    ignore = (
        _as_mask(ignore_mask, gray_shape, "ignore_mask")
        if ignore_mask is not None
        else np.zeros(gray_shape, dtype=bool)
    )
    distress = (
        _as_mask(distress_mask, gray_shape, "distress_mask")
        if distress_mask is not None
        else np.zeros(gray_shape, dtype=bool)
    )

    eligible = valid & ~ignore & ~distress
    limitations: list[str] = []

    margin = int(config.roi_margin_px)
    if margin > 0:
        roi = ndi.binary_erosion(eligible, iterations=margin)
    else:
        roi = eligible.copy()
    if not roi.any():
        # Fall back to the eligible mask so a thin valid strip still yields
        # measurements, but record that the interior margin could not be applied.
        if eligible.any():
            roi = eligible
            limitations.append("roi_margin_not_applicable_too_thin")
        else:
            limitations.append("no_texture_eligible_area")

    if labels is None:
        labels = segment_aggregate(image, config.watershed)
    else:
        labels = np.asarray(labels)
        if labels.ndim != 2:
            raise ValueError(f"labels must be 2D, got shape {labels.shape}")
        if labels.shape != gray_shape:
            raise ValueError(
                f"labels shape {labels.shape} does not match image shape {gray_shape}"
            )
    total_instances = int(np.count_nonzero(np.unique(labels) > 0))
    size_stats = particle_size_stats(
        labels, scale, eligible_mask=roi, min_diameter_px=config.min_diameter_px
    )
    min_diameter_px = float(config.min_diameter_px)
    mm_per_px = scale.equivalent_mm_per_px

    # Count instances whose centroid lies inside the interior ROI and which meet
    # the declared visible minimum size (final plan section 7.3).
    in_roi = 0
    for props in instance_properties(labels):
        cy, cx = props.centroid_yx
        y = int(round(cy))
        x = int(round(cx))
        if not (0 <= y < gray_shape[0] and 0 <= x < gray_shape[1]):
            continue
        if not roi[y, x]:
            continue
        if props.equivalent_diameter_px < min_diameter_px:
            continue
        in_roi += 1

    roi_pixels = int(np.count_nonzero(roi))
    eligible_area_m2 = scale.area_m2(roi_pixels)
    observed_area_m2 = scale.area_m2(int(np.count_nonzero(valid)))
    ignored_area_m2 = scale.area_m2(int(np.count_nonzero(ignore)))
    distress_area_m2 = scale.area_m2(int(np.count_nonzero(distress)))

    coverage = aggregate_coverage(labels, roi)
    gaps = gap_statistics(
        labels,
        scale,
        eligible_mask=roi,
        ignore_mask=None,
        min_gap_px=config.min_gap_px,
        config_version=GAP_METHOD_VERSION,
    )

    if not scale.is_scaled:
        limitations.append("unscaled_geometry_metric_values_unavailable")
    if total_instances == 0:
        limitations.append("no_aggregate_instances_detected")
    if gaps.limitation:
        limitations.append(f"gap:{gaps.limitation}")

    return SurfaceMeasurements(
        config_version=config.config_version,
        segmentation_version=config.watershed.config_version,
        scale=scale,
        n_instances_in_roi=in_roi,
        n_instances_total=total_instances,
        observed_area_m2=observed_area_m2,
        eligible_area_m2=eligible_area_m2,
        ignored_area_m2=ignored_area_m2,
        distress_area_m2=distress_area_m2,
        count_density_per_m2=count_density_per_m2(in_roi, eligible_area_m2),
        coverage_fraction=coverage,
        particle_size=size_stats,
        gap=gaps.describe(),
        min_measurable_diameter_mm=(
            None if mm_per_px is None else min_diameter_px * float(mm_per_px)
        ),
        min_measurable_gap_mm=(
            None if mm_per_px is None else float(config.min_gap_px) * float(mm_per_px)
        ),
        limitations=limitations,
    )
