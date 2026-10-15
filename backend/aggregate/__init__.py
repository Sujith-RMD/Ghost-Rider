"""Aggregate (exposed chip) segmentation and physical measurement.

Owned by the ML role (``docs/ML_ROLE.md`` section 1).
"""

from __future__ import annotations

from backend.aggregate.features import (
    GAP_METHOD_VERSION,
    GapStatistics,
    aggregate_coverage,
    count_density_per_m2,
    gap_statistics,
    particle_size_stats,
    skeletonize_2d,
)
from backend.aggregate.measurement import (
    MeasurementConfig,
    SurfaceMeasurements,
    measure_surface,
)
from backend.aggregate.segmentation import (
    InstanceProps,
    WatershedConfig,
    instance_properties,
    renumber_labels,
    segment_aggregate,
)

__all__ = [
    "GAP_METHOD_VERSION",
    "GapStatistics",
    "InstanceProps",
    "MeasurementConfig",
    "SurfaceMeasurements",
    "WatershedConfig",
    "aggregate_coverage",
    "count_density_per_m2",
    "gap_statistics",
    "instance_properties",
    "measure_surface",
    "particle_size_stats",
    "renumber_labels",
    "segment_aggregate",
    "skeletonize_2d",
]
