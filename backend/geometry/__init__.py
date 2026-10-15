"""Road-plane geometry: scale, transforms, uncertainty.

Owned by the ML role (``docs/ML_ROLE.md`` section 1).
"""

from __future__ import annotations

from backend.geometry.grade import (
    GradeMeasurement,
    GradeSource,
    GradeValidity,
    grade_degrees_from_percent,
    grade_percent_from_degrees,
)
from backend.geometry.plane import (
    LocalScale,
    apply_homography,
    as_homography,
    invert_homography,
    local_scale,
    normalize_homography,
    plane_homography,
    polygon_area,
    project_points_to_plane,
)
from backend.geometry.scale import (
    PlanarScale,
    ScaleSource,
    UnscaledError,
    equivalent_diameter_mm,
)

__all__ = [
    "GradeMeasurement",
    "GradeSource",
    "GradeValidity",
    "LocalScale",
    "PlanarScale",
    "ScaleSource",
    "UnscaledError",
    "apply_homography",
    "as_homography",
    "equivalent_diameter_mm",
    "grade_degrees_from_percent",
    "grade_percent_from_degrees",
    "invert_homography",
    "local_scale",
    "normalize_homography",
    "plane_homography",
    "polygon_area",
    "project_points_to_plane",
]

