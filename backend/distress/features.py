"""Distress measurements from binary/polygon crack and pothole masks.

Owned by the ML role (``docs/ML_ROLE.md`` section 1).

Implements the two distress features that final plan section 7.3 assigns to
this module and that the task tracker calls **D8**:

* **crack density** - metric skeleton length divided by inspected surface area;
* **defect extent** - a mask's projected area divided by valid inspected area.

Skeleton length is measured by summing *step* distances rather than counting
skeleton pixels. A 1-px-wide diagonal line of ``n`` steps spans ``n * sqrt(2)``
pixels, so counting pixels under-reports diagonal cracks by 29%. Each pixel
adjacency is counted exactly once by inspecting only the forward neighbourhood
(right, down, and the two forward diagonals).

Restriction carried from the plan: this measures the *visible projected
footprint*. It is not pothole depth, volume, or structural severity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import scipy.ndimage as ndi

from backend.aggregate.features import skeletonize_2d
from backend.geometry.scale import PlanarScale

__all__ = [
    "DISTRESS_METHOD_VERSION",
    "DistressMetrics",
    "rasterize_polygon",
    "rasterize_label_file",
    "crack_skeleton_length_m",
    "defect_extent_fraction",
    "distress_metrics",
]

DISTRESS_METHOD_VERSION = "distress-v2"

# Forward neighbourhood only, so every adjacency is visited exactly once.
_STEP_OFFSETS = (
    (0, 1, 1.0),
    (1, 0, 1.0),
    (1, 1, math.sqrt(2.0)),
    (1, -1, math.sqrt(2.0)),
)


@dataclass(frozen=True)
class DistressMetrics:
    """Crack length density and defect extent for one inspected region."""

    skeleton_length_m: float | None
    crack_density_m_per_m2: float | None
    defect_area_m2: float | None
    extent_fraction: float | None
    inspected_area_m2: float | None
    skeleton_pixels: int
    mask_pixels: int
    method: str
    config_version: str
    limitation: str | None = None

    def describe(self) -> dict:
        return {
            "skeleton_length_m": self.skeleton_length_m,
            "crack_density_m_per_m2": self.crack_density_m_per_m2,
            "defect_area_m2": self.defect_area_m2,
            "extent_fraction": self.extent_fraction,
            "inspected_area_m2": self.inspected_area_m2,
            "skeleton_pixels": self.skeleton_pixels,
            "mask_pixels": self.mask_pixels,
            "method": self.method,
            "config_version": self.config_version,
            "limitation": self.limitation,
        }


def rasterize_polygon(
    shape: tuple[int, int],
    coords_xy: np.ndarray,
) -> np.ndarray:
    """Rasterise one polygon given in normalised ``x, y`` image coordinates.

    Returns a boolean mask. Coordinates outside ``[0, 1]`` are clamped, so a
    segmented polygon that grazes the frame edge is still drawn rather than
    silently dropped.
    """
    if len(shape) != 2:
        raise ValueError(f"shape must be (height, width), got {shape}")
    pts = np.asarray(coords_xy, dtype=np.float64).reshape(-1, 2)
    if pts.shape[0] < 3:
        return np.zeros(shape, dtype=bool)
    height, width = int(shape[0]), int(shape[1])
    px = np.clip(pts[:, 0] * width, 0.0, width - 1.0)
    py = np.clip(pts[:, 1] * height, 0.0, height - 1.0)
    poly = np.rint(np.column_stack([px, py])).astype(np.int32)
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(mask, [poly], 1)
    return mask.astype(bool)


def rasterize_label_file(
    shape: tuple[int, int],
    label_path,
    class_filter: set[int] | None = None,
) -> dict[int, np.ndarray]:
    """Parse a YOLO segmentation label file into per-class boolean masks.

    Ultralytics segmentation lines are ``class_id x1 y1 x2 y2 ...`` with
    normalised coordinates. A malformed line is skipped and reported through
    the returned ``skipped`` count rather than aborting the whole file.
    """
    path = Path(label_path)
    if not path.exists():
        raise FileNotFoundError(label_path)

    shapes: dict[int, list[np.ndarray]] = {}
    skipped = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) < 7 or len(parts) % 2 == 0:
                # needs class id plus at least three coordinate pairs
                skipped += 1
                continue
            try:
                class_id = int(float(parts[0]))
                values = [float(p) for p in parts[1:]]
            except ValueError:
                skipped += 1
                continue
            if class_filter is not None and class_id not in class_filter:
                continue
            coords = np.asarray(values, dtype=np.float64).reshape(-1, 2)
            if not np.all(np.isfinite(coords)):
                skipped += 1
                continue
            shapes.setdefault(class_id, []).append(
                rasterize_polygon(shape, coords)
            )

    masks: dict[int, np.ndarray] = {}
    for class_id, polygons in shapes.items():
        combined = np.zeros(shape, dtype=bool)
        for polygon in polygons:
            combined |= polygon
        masks[class_id] = combined
    return masks


def crack_skeleton_length_m(
    crack_mask: np.ndarray,
    scale: PlanarScale,
    inspected_mask: np.ndarray | None = None,
) -> tuple[float | None, int]:
    """Skeleton length of a binary crack mask, in metres.

    Returns ``(length_m, skeleton_pixels)``. ``length_m`` is ``None`` when the
    imagery is unscaled, never ``0`` - an unscaled image has no metric length.

    Diagonal steps are counted as ``sqrt(2)`` so a diagonal crack is not
    under-reported. Each pixel adjacency is visited exactly once by inspecting
    only the forward neighbourhood.
    """
    mask = _as_bool_mask(crack_mask, "crack_mask")
    inspected = (
        _as_bool_mask(inspected_mask, "inspected_mask")
        if inspected_mask is not None
        else np.ones(mask.shape, dtype=bool)
    )
    if inspected.shape != mask.shape:
        raise ValueError(
            f"inspected_mask shape {inspected.shape} does not match crack_mask {mask.shape}"
        )

    skeleton = skeletonize_2d(mask & inspected)
    skeleton_pixels = int(np.count_nonzero(skeleton))
    if skeleton_pixels == 0:
        return (None if not scale.is_scaled else 0.0), 0

    if not scale.is_scaled:
        return None, skeleton_pixels

    length_mm = 0.0
    height, width = skeleton.shape
    ys, xs = np.nonzero(skeleton)
    skeleton_set = skeleton  # boolean lookup is the cheapest membership test
    for y, x in zip(ys.tolist(), xs.tolist()):
        for dy, dx, weight in _STEP_OFFSETS:
            ny, nx = y + dy, x + dx
            if 0 <= ny < height and 0 <= nx < width:
                if skeleton_set[ny, nx]:
                    length_mm += math.hypot(
                        dx * float(scale.sx_mm_per_px),
                        dy * float(scale.sy_mm_per_px),
                    )

    length_m = length_mm / 1000.0
    return float(length_m), skeleton_pixels


def defect_extent_fraction(
    defect_mask: np.ndarray,
    inspected_mask: np.ndarray | None = None,
) -> float | None:
    """Projected defect area as a fraction of the inspected area.

    Overlapping masks are unioned first, so this cannot exceed 1.0. Returns
    ``None`` when there is no inspected area to divide by, and ``0.0`` for a
    genuinely measured absence of distress.
    """
    mask = _as_bool_mask(defect_mask, "defect_mask")
    inspected = (
        _as_bool_mask(inspected_mask, "inspected_mask")
        if inspected_mask is not None
        else np.ones(mask.shape, dtype=bool)
    )
    if inspected.shape != mask.shape:
        raise ValueError(
            f"inspected_mask shape {inspected.shape} does not match defect_mask {mask.shape}"
        )
    inspected_count = int(np.count_nonzero(inspected))
    if inspected_count == 0:
        return None
    return float(np.count_nonzero(mask & inspected)) / float(inspected_count)


def distress_metrics(
    crack_mask: np.ndarray,
    scale: PlanarScale,
    inspected_mask: np.ndarray | None = None,
    config_version: str = DISTRESS_METHOD_VERSION,
) -> DistressMetrics:
    """Both distress features in one record, with null-vs-zero discipline."""
    mask = _as_bool_mask(crack_mask, "crack_mask")
    inspected = (
        _as_bool_mask(inspected_mask, "inspected_mask")
        if inspected_mask is not None
        else np.ones(mask.shape, dtype=bool)
    )
    if inspected.shape != mask.shape:
        raise ValueError(
            f"inspected_mask shape {inspected.shape} does not match crack_mask {mask.shape}"
        )

    length_m, skeleton_pixels = crack_skeleton_length_m(mask, scale, inspected)
    extent = defect_extent_fraction(mask, inspected)

    inspected_area_m2 = scale.area_m2(int(np.count_nonzero(inspected)))
    limitation: str | None = None

    if not scale.is_scaled:
        limitation = "unscaled imagery: crack length and density reported as unavailable, not zero"

    mask_pixels = int(np.count_nonzero(mask & inspected))
    defect_area_m2 = scale.area_m2(mask_pixels)

    # Density needs a metric length AND a non-zero metric area. Either missing
    # means unavailable, and that stays distinct from a measured zero.
    if length_m is not None and inspected_area_m2:
        density = length_m / inspected_area_m2
    else:
        density = None

    if skeleton_pixels == 0:
        limitation = limitation or "no crack skeleton in the inspected region"

    return DistressMetrics(
        skeleton_length_m=length_m,
        crack_density_m_per_m2=density,
        defect_area_m2=defect_area_m2,
        extent_fraction=extent,
        inspected_area_m2=inspected_area_m2,
        skeleton_pixels=skeleton_pixels,
        mask_pixels=mask_pixels,
        method="skeleton_length_steps + projected_area_over_inspected",
        config_version=config_version,
        limitation=limitation,
    )


def _as_bool_mask(mask, name: str) -> np.ndarray:
    array = np.asarray(mask)
    if array.ndim == 3:
        array = array[..., 0]
    if array.ndim != 2:
        raise ValueError(f"{name} must be 2D, got shape {array.shape}")
    return array.astype(bool)
