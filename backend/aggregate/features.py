"""Physical aggregate features computed from instance label maps.

Owned by the ML role (``docs/ML_ROLE.md`` section 1).

Implements the final plan section 7.3 feature definitions this module is
responsible for:

* count density with an eligible area and a visible minimum size;
* particle equivalent diameter as a *projected 2D* size;
* aggregate union coverage (union, never a sum of possibly overlapping masks);
* confident adjacent-boundary gap statistics;
* fixed-scale texture proxies (GLCM contrast/homogeneity, gradient energy, LBP summary).

Null-vs-zero discipline (final plan section 2): an unavailable area yields
``None``, while a genuinely measured empty region yields ``0.0``.

Gap method (documented so it can be challenged later, final plan section 7.3):
the non-aggregate region is skeletonised (Zhang-Suen thinning). At each medial
site ``p`` the width is the centre-to-centre distance between the facing
aggregate pixels:

1. ``a`` is the nearest aggregate pixel to ``p`` (distance ``d``);
2. ``q = 2p - a`` is the reflected point across ``p``;
3. ``b`` is the nearest aggregate pixel to ``q``;
4. ``width = |p - a| + |p - b|``.

A site only qualifies when ``a`` and ``b`` belong to *different* instances, which
excludes ROI edges, broad open regions and single isolated particles.

Why not ``2 x distance_transform`` at the medial axis: on a discrete grid the
medial site sits between pixel centres, so the doubled distance lands one pixel
short of the opposing boundary and under-reports by about one pixel. Reflecting
to ``q`` and re-querying the nearest aggregate pixel is robust to that. The
reported width is a pixel-space separation between facing boundary pixels, so it
includes those two pixels; the declared lower reporting limit is reported
separately as ``min_gap_px``. This is *not* binder thickness, void depth or the
width of every dark region.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import pi, sqrt

import cv2
import numpy as np
import scipy.ndimage as ndi
from skimage import morphology as skimage_morphology

from backend.geometry.scale import PlanarScale, equivalent_diameter_mm

GAP_METHOD_VERSION = "gap-medial-v2"
"""Version of the documented medial-axis opposing-instance gap method.

``v2`` (2026-10-16) uses scikit-image's thinning instead of a local
implementation; the canonical two-bar fixture still measures exactly 11.0 px,
but dense fixtures shifted (median 37.88 -> 37.16 px, sites 353 -> 347).
"""

TEX_METHOD_VERSION = "texture-proxy-v1"
"""Version of the fixed-scale texture proxy methods."""

__all__ = [
    "GAP_METHOD_VERSION",
    "TEX_METHOD_VERSION",
    "GapStatistics",
    "TextureStatistics",
    "skeletonize_2d",
    "gap_endpoints",
    "count_density_per_m2",
    "aggregate_coverage",
    "particle_size_stats",
    "gap_statistics",
    "texture_statistics",
]


@dataclass(frozen=True)
class GapStatistics:
    """Summary of confident adjacent-boundary separations."""

    median_mm: float | None
    iqr_mm: float | None
    p90_mm: float | None
    median_px: float | None
    sample_count: int
    min_gap_px: float
    method: str
    config_version: str
    limitation: str | None = None

    def describe(self) -> dict:
        return {
            "median_mm": self.median_mm,
            "iqr_mm": self.iqr_mm,
            "p90_mm": self.p90_mm,
            "median_px": self.median_px,
            "sample_count": self.sample_count,
            "min_gap_px": self.min_gap_px,
            "method": self.method,
            "config_version": self.config_version,
            "limitation": self.limitation,
        }


@dataclass(frozen=True)
class TextureStatistics:
    """Summary of fixed-scale texture proxy measurements.

    All measurements are computed at fixed physical offsets (mm) as specified
    in the final plan section 7.3. Values are unitless texture proxies;
    they depend on scale and lighting and must not be relabeled as mm roughness.
    """

    glcm_contrast_mm: float | None
    glcm_homogeneity_mm: float | None
    glcm_energy_mm: float | None
    glcm_correlation_mm: float | None
    gradient_energy_mm: float | None
    lbp_uniformity_mm: float | None
    method: str
    config_version: str
    limitation: str | None = None

    def describe(self) -> dict:
        return {
            "glcm_contrast_mm": self.glcm_contrast_mm,
            "glcm_homogeneity_mm": self.glcm_homogeneity_mm,
            "glcm_energy_mm": self.glcm_energy_mm,
            "glcm_correlation_mm": self.glcm_correlation_mm,
            "gradient_energy_mm": self.gradient_energy_mm,
            "lbp_uniformity_mm": self.lbp_uniformity_mm,
            "method": self.method,
            "config_version": self.config_version,
            "limitation": self.limitation,
        }


def skeletonize_2d(binary: np.ndarray, max_iterations: int = 512) -> np.ndarray:
    """Zhang-Suen thinning, delegated to scikit-image.

    scikit-image became an approved ML dependency (D4, 2026-10-16) and is the
    reference implementation, so this no longer carries ~50 lines of locally
    owned algorithm (decision D6/J8).

    The swap was **measured, not assumed**. The previous local implementation
    agreed with scikit-image exactly on simple shapes (straight bar, diagonal,
    disk) but differed on every complex one: up to 303 differing pixels on a
    96x96 noise mask, and 14 on a thin ring. Downstream that moved the measured
    gap: on the dense-chip fixture the median went 37.88 px -> 37.16 px and the
    qualifying site count 353 -> 347, while the canonical two-bar fixture stayed
    exactly 11.0 px. Because measured output moved, ``GAP_METHOD_VERSION``
    changed to ``gap-medial-v2`` rather than being silently re-used (final plan
    section 9.2). scikit-image is also about 18x faster here.

    ``max_iterations`` is retained for API compatibility and is unused: the
    implementation is scikit-image's, which terminates on its own.
    """
    image = (np.asarray(binary) > 0).astype(np.uint8)
    if image.ndim != 2:
        raise ValueError(f"binary must be 2D, got shape {image.shape}")
    if image.size == 0:
        raise ValueError("binary is empty")
    if not image.any():
        return image.astype(bool)

    return np.asarray(skimage_morphology.skeletonize(image), dtype=bool)


def _glcm_features(
    gray: np.ndarray,
    distances_px: tuple[int, ...],
    angles: tuple[float, ...],
    levels: int = 256,
) -> dict[str, np.ndarray]:
    """Compute GLCM features at pixel-space distances and angles.

    Returns dict with keys: contrast, homogeneity, energy, correlation.
    Each value is a 2D array of shape (len(distances_px), len(angles)); entries
    are 0/neutral where a requested offset produced no valid pixel pairs.

    Quantizes to ``levels`` grey levels, builds a symmetric co-occurrence
    histogram per offset, then derives the four standard Haralick-style
    scalars. A ``bincount`` histogram is used rather than ``np.add.at`` because
    it is an order of magnitude faster on large images.
    """
    arr = np.asarray(gray)
    if arr.ndim != 2:
        raise ValueError(f"expected a 2D image, got shape {arr.shape}")
    if int(levels) < 2:
        raise ValueError("levels must be >= 2")

    if arr.dtype == np.uint8:
        quantized = arr
    else:
        low = float(arr.min())
        high = float(arr.max())
        if high - low < 1e-9:
            quantized = np.zeros(arr.shape, dtype=np.uint8)
        else:
            quantized = ((arr - low) / (high - low) * (levels - 1)).astype(np.uint8)

    height, width = quantized.shape
    n_d, n_a = len(distances_px), len(angles)
    out = {
        "contrast": np.zeros((n_d, n_a), dtype=np.float64),
        "homogeneity": np.zeros((n_d, n_a), dtype=np.float64),
        "energy": np.zeros((n_d, n_a), dtype=np.float64),
        "correlation": np.zeros((n_d, n_a), dtype=np.float64),
    }

    # Neutral defaults guard against an all-zero row being read as 0 contrast
    # on a texture-free image; they are only used when an offset is unusable.
    for a in range(n_a):
        out["homogeneity"][:, a] = 1.0

    i_mat, j_mat = np.indices((levels, levels))
    diff_sq = (i_mat - j_mat) ** 2
    inv_plus = 1.0 / (1.0 + diff_sq)

    for di, distance in enumerate(distances_px):
        if distance < 1:
            continue
        for ai, angle in enumerate(angles):
            dy = int(round(distance * np.sin(angle)))
            dx = int(round(distance * np.cos(angle)))
            if dy == 0 and dx == 0:
                continue

            # Valid overlap region. Slicing the image directly (never a
            # coordinate grid) guarantees matching shapes for any combination
            # of (dx, dy) signs. The bounds are chosen so that both the base
            # window and the window displaced by (dy, dx) stay in frame:
            #   dy > 0 keeps base rows [0, H-dy)   and uses displaced [dy, H)
            #   dy < 0 keeps base rows [-dy, H)    and uses displaced [0, H+dy)
            y_lo = max(0, -dy)
            y_hi = height - max(0, dy)
            x_lo = max(0, -dx)
            x_hi = width - max(0, dx)

            if y_hi <= y_lo or x_hi <= x_lo:
                continue

            v1 = quantized[y_lo:y_hi, x_lo:x_hi].ravel()
            v2 = quantized[y_lo + dy:y_hi + dy, x_lo + dx:x_hi + dx].ravel()

            if v1.size == 0:
                continue

            codes = v1.astype(np.int64) * levels + v2.astype(np.int64)
            glcm = np.bincount(codes, minlength=levels * levels).astype(np.float64)
            glcm = glcm.reshape(levels, levels)
            glcm = glcm + glcm.T  # symmetric
            total = glcm.sum()
            if total <= 0.0:
                continue
            glcm /= total

            p_ij_row = glcm.sum(axis=1)
            p_ij_col = glcm.sum(axis=0)
            level_vec = np.arange(levels, dtype=np.float64)

            contrast = float(np.sum(glcm * diff_sq))
            homogeneity = float(np.sum(glcm * inv_plus))
            energy = float(np.sum(glcm * glcm))

            mu_i = float(np.dot(level_vec, p_ij_row))
            mu_j = float(np.dot(level_vec, p_ij_col))
            var_i = float(np.dot((level_vec - mu_i) ** 2, p_ij_row))
            var_j = float(np.dot((level_vec - mu_j) ** 2, p_ij_col))
            denom = sqrt(var_i * var_j)
            if denom > 1e-9:
                covariance = float(
                    np.sum(glcm * (i_mat - mu_i) * (j_mat - mu_j))
                )
                correlation = covariance / denom
            else:
                correlation = 0.0

            out["contrast"][di, ai] = contrast
            out["homogeneity"][di, ai] = homogeneity
            out["energy"][di, ai] = energy
            out["correlation"][di, ai] = correlation

    return out


def _glcm_aggregate(gray: np.ndarray, distances_mm: tuple[float, ...], scale: PlanarScale, angles: tuple[float, ...] = (0.0, np.pi/4, np.pi/2, 3*np.pi/4)) -> dict[str, float | None]:
    """Compute GLCM features at fixed physical distances (mm) using the scale."""
    if not scale.is_scaled:
        return {"contrast": None, "homogeneity": None, "energy": None, "correlation": None}
    mm_per_px = scale.equivalent_mm_per_px
    distances_px = tuple(int(round(d / mm_per_px)) for d in distances_mm)
    if not distances_px:
        return {"contrast": None, "homogeneity": None, "energy": None, "correlation": None}
    gray_u8 = gray.astype(np.uint8)
    glcm = _glcm_features(gray_u8, distances_px, angles)
    # Aggregate over angles and distances (mean)
    return {
        "contrast": float(np.mean(glcm["contrast"])) if glcm["contrast"].size else None,
        "homogeneity": float(np.mean(glcm["homogeneity"])) if glcm["homogeneity"].size else None,
        "energy": float(np.mean(glcm["energy"])) if glcm["energy"].size else None,
        "correlation": float(np.mean(glcm["correlation"])) if glcm["correlation"].size else None,
    }


def _gradient_energy(gray: np.ndarray, scale: PlanarScale) -> float | None:
    """Mean squared Sobel gradient magnitude, normalised by the pixel area.

    Known and deliberate limitation: a 3x3 Sobel kernel is a *null operator* at
    the checkerboard (Nyquist) frequency. A surface whose aggregate/binder
    pattern alternates at roughly one pixel can therefore read as low gradient
    energy even though it is the most textured case. This is recorded rather than
    patched by switching kernels, because choosing a kernel that peaks at Nyquist
    trades sensitivity to real coarse texture for sensitivity to aliasing.

    Returns a unitless quantity in 1/mm^2, or ``None`` when unscaled. It is not
    millimetre roughness (final plan section 7.3).
    """
    if not scale.is_scaled:
        return None
    mm_per_px = scale.equivalent_mm_per_px
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad_mag = np.hypot(gx, gy)
    energy = float(np.mean(grad_mag ** 2))
    if mm_per_px > 0:
        energy = energy / (mm_per_px ** 2)
    return energy


def _lbp_uniformity(gray: np.ndarray, radius_mm: float, scale: PlanarScale, n_points: int = 8) -> float | None:
    """Fraction of pixels whose LBP code is a *uniform* pattern.

    Uniformity is the standard LBP homogeneity measure: a code is uniform when
    its circular bit sequence has at most two 0<->1 transitions. The result is
    a fraction in ``[0, 1]`` where 1 means every pixel is locally flat or
    describes an edge, and lower values mean more varied local structure.

    Unitless, radius in physical millimetres. It is not a texture-depth measure
    (final plan section 7.3).
    """
    if not scale.is_scaled or radius_mm <= 0:
        return None
    mm_per_px = scale.equivalent_mm_per_px
    radius_px = max(1, int(round(radius_mm / mm_per_px)))
    arr = np.asarray(gray)
    if arr.ndim != 2:
        raise ValueError(f"expected a 2D image, got shape {arr.shape}")
    if arr.size == 0:
        return None

    angles = np.linspace(0.0, 2.0 * np.pi, n_points, endpoint=False)
    dy = np.round(radius_px * np.sin(angles)).astype(int)
    dx = np.round(radius_px * np.cos(angles)).astype(int)

    codes = np.zeros(arr.shape, dtype=np.uint8)
    for k in range(n_points):
        displaced = np.roll(arr, shift=(int(dy[k]), int(dx[k])), axis=(0, 1))
        codes |= (displaced >= arr).astype(np.uint8) << np.uint8(k)

    # Count circular bit transitions in each code. A shift by one bit makes the
    # sequence wrap, so comparing against the rotation visits each adjacent pair
    # including (last, first).
    transitions = np.zeros(codes.shape, dtype=np.uint32)
    for k in range(n_points):
        shifted = np.roll(codes, shift=-(k + 1), axis=-1)
        transitions += (shifted != codes).astype(np.uint32)

    uniform_count = int(np.count_nonzero(transitions <= 2))
    total = int(codes.size)
    if total == 0:
        return None
    return float(uniform_count) / float(total)


def count_density_per_m2(count: int, eligible_area_m2: float | None) -> float | None:
    """Count per square metre, or ``None`` when the area is unavailable.

    A zero count over a measured area is a measured absence and returns ``0.0``.
    """
    if eligible_area_m2 is None:
        return None
    area = float(eligible_area_m2)
    if not np.isfinite(area) or area < 0.0:
        raise ValueError("eligible_area_m2 must be a finite non-negative number")
    count = int(count)
    if count < 0:
        raise ValueError("count must be non-negative")
    if area == 0.0:
        return None
    return count / area


def aggregate_coverage(
    labels: np.ndarray, eligible_mask: np.ndarray | None = None
) -> float | None:
    """Union of aggregate masks divided by the eligible area.

    Uses the union, not a sum of per-instance areas, so overlapping or
    overlapping-after-reconstruction masks cannot double-count (final plan 7.3).
    """
    labels = np.asarray(labels)
    if labels.ndim != 2:
        raise ValueError(f"labels must be 2D, got shape {labels.shape}")
    aggregate = labels > 0
    if eligible_mask is not None:
        eligible = np.asarray(eligible_mask).astype(bool)
        if eligible.shape != aggregate.shape:
            raise ValueError(
                f"eligible_mask shape {eligible.shape} does not match labels {aggregate.shape}"
            )
    else:
        eligible = np.ones(aggregate.shape, dtype=bool)
    eligible_count = int(eligible.sum())
    if eligible_count == 0:
        return None
    return float(np.count_nonzero(aggregate & eligible)) / float(eligible_count)


def particle_size_stats(
    labels: np.ndarray,
    scale: PlanarScale,
    eligible_mask: np.ndarray | None = None,
    min_diameter_px: float = 0.0,
) -> dict:
    """Projected equivalent-diameter statistics for counted instances (mm).

    ``min_diameter_px`` is the declared visible minimum size; particles below it
    are excluded and reported, because the minimum size changes the density and
    therefore requires a new reference version (final plan section 7.3).
    """
    labels = np.asarray(labels)
    if labels.ndim != 2:
        raise ValueError(f"labels must be 2D, got shape {labels.shape}")
    if min_diameter_px < 0.0:
        raise ValueError("min_diameter_px must be >= 0")

    area_per_instance = _instance_area_px(labels)
    if eligible_mask is not None:
        eligible = np.asarray(eligible_mask, dtype=bool)
        if eligible.shape != labels.shape:
            raise ValueError("eligible_mask shape does not match labels")
        selected = {}
        for label, area in area_per_instance.items():
            cy, cx = ndi.center_of_mass(labels == label)
            y, x = int(round(cy)), int(round(cx))
            if eligible[y, x]:
                selected[label] = area
        area_per_instance = selected
    areas_px = [float(area) for area in area_per_instance.values() if area > 0]
    diameters_px = [sqrt(4.0 * area / pi) for area in areas_px]
    keep = [d >= float(min_diameter_px) for d in diameters_px]
    kept_px = [d for d, ok in zip(diameters_px, keep) if ok]
    kept_areas = [a for a, ok in zip(areas_px, keep) if ok]
    excluded = len(diameters_px) - len(kept_px)

    pixel_area_mm2 = scale.pixel_area_mm2
    if pixel_area_mm2 is None:
        diameters_mm: list[float] = []
    else:
        diameters_mm = [equivalent_diameter_mm(area * pixel_area_mm2) for area in kept_areas]

    return {
        "count_considered": len(kept_px),
        "excluded_below_min_size": excluded,
        "diameter_px": _summary_stats(kept_px),
        "diameter_mm": _summary_stats(diameters_mm) if diameters_mm else _summary_stats([]),
        "scale_available": pixel_area_mm2 is not None,
    }


def _summary_stats(values: list[float]) -> dict:
    """Median/IQR/p90/min/max, or nulls for an empty sample."""
    if not values:
        return {"median": None, "iqr": None, "p90": None, "min": None, "max": None}
    array = np.asarray(values, dtype=np.float64)
    q25, q50, q90 = np.percentile(array, [25, 50, 90])
    return {
        "median": float(q50),
        "iqr": float(q75_q25(array)),
        "p90": float(q90),
        "min": float(array.min()),
        "max": float(array.max()),
    }


def q75_q25(values: np.ndarray) -> float:
    """Interquartile range of an array."""
    q75, q25 = np.percentile(np.asarray(values, dtype=np.float64), [75, 25])
    return float(q75 - q25)


def _instance_area_px(labels: np.ndarray) -> dict[int, int]:
    positives = np.unique(labels[labels > 0])
    if positives.size == 0:
        return {}
    counts = np.bincount(labels.ravel())
    return {int(v): int(counts[int(v)]) for v in positives if int(v) < len(counts)}


def _qualifying_gap_sites(
    labels: np.ndarray,
    eligible_mask: np.ndarray | None = None,
    ignore_mask: np.ndarray | None = None,
    min_gap_px: float = 3.0,
) -> dict:
    """Medial-axis sites whose facing boundaries belong to two distinct instances.

    Returns the qualifying sites plus the endpoints that produced each width, so
    a caller can report *where* a gap was measured instead of only how wide it was.
    This is the single implementation of the documented method: both
    :func:`gap_statistics` and the provisional annotator use it.
    """
    labels = np.asarray(labels)
    shape = labels.shape
    aggregate = labels > 0
    empty_i = np.zeros(0, dtype=np.int64)
    empty_f = np.zeros(0, dtype=np.float64)

    def _none(limitation: str) -> dict:
        return {
            "sites": np.zeros(shape, dtype=bool),
            "site_y": empty_i,
            "site_x": empty_i,
            "near_y": empty_i,
            "near_x": empty_i,
            "opposite_y": empty_i,
            "opposite_x": empty_i,
            "widths_px": empty_f,
            "limitation": limitation,
        }

    if not aggregate.any():
        return _none("no_aggregate_instances_detected")

    gap_region = ~aggregate
    if eligible_mask is not None:
        eligible = np.asarray(eligible_mask).astype(bool)
        if eligible.shape != shape:
            raise ValueError(
                f"eligible_mask shape {eligible.shape} does not match labels {shape}"
            )
        gap_region &= eligible
    if ignore_mask is not None:
        ignore = np.asarray(ignore_mask).astype(bool)
        if ignore.shape != shape:
            raise ValueError(f"ignore_mask shape {ignore.shape} does not match labels {shape}")
        gap_region &= ~ignore
    if not gap_region.any():
        return _none("eligible gap region is empty")

    # Distance to the nearest aggregate pixel, plus that pixel's coordinates.
    distance, indices = ndi.distance_transform_edt(~aggregate, return_indices=True)
    nearest_y, nearest_x = indices[0], indices[1]

    skeleton = skeletonize_2d(gap_region)
    sites = skeleton & gap_region & (distance > 0.0)
    if not sites.any():
        return _none("no medial-axis sites found in the eligible gap region")

    site_y, site_x = np.nonzero(sites)
    site_distance = distance[site_y, site_x]
    near_y = nearest_y[site_y, site_x]
    near_x = nearest_x[site_y, site_x]

    # Opposite boundary: reflect the site across its own nearest aggregate pixel
    # (p - d * u == 2p - nearest) and re-query the nearest aggregate pixel there.
    height, width = shape
    reflected_y = np.clip(2 * site_y - near_y, 0, height - 1)
    reflected_x = np.clip(2 * site_x - near_x, 0, width - 1)
    opposite_y = nearest_y[reflected_y, reflected_x]
    opposite_x = nearest_x[reflected_y, reflected_x]

    near_label = labels[near_y, near_x]
    opposite_label = labels[opposite_y, opposite_x]
    opposite_distance = np.hypot(
        opposite_y.astype(np.float64) - site_y,
        opposite_x.astype(np.float64) - site_x,
    )
    qualifies = (
        (near_label > 0)
        & (opposite_label > 0)
        & (near_label != opposite_label)
        & (opposite_distance > 0.0)
    )
    widths = (site_distance + opposite_distance)[qualifies]
    keep = widths >= float(min_gap_px)
    if not keep.any():
        return _none(
            "no site had opposing boundaries belonging to two distinct instances "
            "above the minimum reportable gap"
        )
    return {
        "sites": sites,
        "site_y": site_y[qualifies][keep],
        "site_x": site_x[qualifies][keep],
        "near_y": near_y[qualifies][keep],
        "near_x": near_x[qualifies][keep],
        "opposite_y": opposite_y[qualifies][keep],
        "opposite_x": opposite_x[qualifies][keep],
        "widths_px": widths[keep],
        "limitation": None,
    }


def gap_endpoints(
    labels: np.ndarray,
    eligible_mask: np.ndarray | None = None,
    ignore_mask: np.ndarray | None = None,
    min_gap_px: float = 3.0,
) -> dict | None:
    """The clearest gap site: endpoints landing on two distinct instances.

    Used where a *location* is needed, not just a distribution. The site chosen is
    the qualifying one whose width is closest to the median, so the reported
    example is representative rather than the widest or narrowest gap found.
    Returns ``None`` when nothing qualifies - an honest "no resolvable gap here",
    never a zero.
    """
    site = _qualifying_gap_sites(
        labels, eligible_mask=eligible_mask, ignore_mask=ignore_mask, min_gap_px=min_gap_px
    )
    if site["limitation"] is not None or site["widths_px"].size == 0:
        return None
    widths = site["widths_px"]
    index = int(np.argmin(np.abs(widths - float(np.median(widths)))))
    return {
        "endpoint_a_xy": (int(site["near_x"][index]), int(site["near_y"][index])),
        "endpoint_b_xy": (int(site["opposite_x"][index]), int(site["opposite_y"][index])),
        "width_px": float(widths[index]),
        "site_xy": (int(site["site_x"][index]), int(site["site_y"][index])),
        "site_count": int(widths.size),
        "min_gap_px": float(min_gap_px),
        "method": "medial_axis_opposing_distinct_instances",
    }


def gap_statistics(
    labels: np.ndarray,
    scale: PlanarScale,
    eligible_mask: np.ndarray | None = None,
    ignore_mask: np.ndarray | None = None,
    min_gap_px: float = 3.0,
    config_version: str = GAP_METHOD_VERSION,
) -> GapStatistics:
    """Confident adjacent-boundary gap statistics.

    ``min_gap_px`` is the declared lower reporting limit. Sites thinner than it
    are not reported, because a gap near the pixel scale is not a trustworthy
    width measurement (final plan sections 5.1 item 6 and 13.2).
    """
    labels = np.asarray(labels)
    if labels.ndim != 2:
        raise ValueError(f"labels must be 2D, got shape {labels.shape}")
    if float(min_gap_px) < 1.0:
        raise ValueError("min_gap_px must be >= 1 pixel")

    aggregate = labels > 0
    if not aggregate.any():
        return GapStatistics(
            median_mm=None,
            iqr_mm=None,
            p90_mm=None,
            median_px=None,
            sample_count=0,
            min_gap_px=float(min_gap_px),
            method="medial_axis_opposing_distinct_instances",
            config_version=config_version,
            limitation="no_aggregate_instances_detected",
        )

    shape = labels.shape
    gap_region = ~aggregate
    if eligible_mask is not None:
        eligible = np.asarray(eligible_mask).astype(bool)
        if eligible.shape != shape:
            raise ValueError(
                f"eligible_mask shape {eligible.shape} does not match labels {shape}"
            )
        gap_region &= eligible
    if ignore_mask is not None:
        ignore = np.asarray(ignore_mask).astype(bool)
        if ignore.shape != shape:
            raise ValueError(
                f"ignore_mask shape {ignore.shape} does not match labels {shape}"
            )
        gap_region &= ~ignore


    site = _qualifying_gap_sites(
        labels,
        eligible_mask=eligible_mask,
        ignore_mask=ignore_mask,
        min_gap_px=min_gap_px,
    )
    limitation = site["limitation"]
    widths_px = site["widths_px"]
    if widths_px.size == 0:
        limitation = (
            "no site had opposing boundaries belonging to two distinct instances "
            "above the minimum reportable gap"
        )
        return GapStatistics(
            median_mm=None,
            iqr_mm=None,
            p90_mm=None,
            median_px=None,
            sample_count=0,
            min_gap_px=float(min_gap_px),
            method="medial_axis_opposing_distinct_instances",
            config_version=config_version,
            limitation=limitation,
        )

    mm_per_px = scale.equivalent_mm_per_px
    if mm_per_px is None:
        widths_mm = None
        limitation = "unscaled imagery: gap reported in pixels only, no metric width"
    else:
        # Transform each measured leg, not an equal-area surrogate length.
        sx, sy = float(scale.sx_mm_per_px), float(scale.sy_mm_per_px)
        widths_mm = np.hypot(
            (site["near_x"] - site["site_x"]) * sx,
            (site["near_y"] - site["site_y"]) * sy,
        ) + np.hypot(
            (site["opposite_x"] - site["site_x"]) * sx,
            (site["opposite_y"] - site["site_y"]) * sy,
        )

    return GapStatistics(
        median_mm=None if widths_mm is None else float(np.median(widths_mm)),
        iqr_mm=None if widths_mm is None else float(q75_q25(widths_mm)),
        p90_mm=None if widths_mm is None else float(np.percentile(widths_mm, 90)),
        median_px=float(np.median(widths_px)),
        sample_count=int(widths_px.size),
        min_gap_px=float(min_gap_px),
        method="medial_axis_opposing_distinct_instances",
        config_version=config_version,
        limitation=limitation,
    )


def texture_statistics(
    gray: np.ndarray,
    scale: PlanarScale,
    distances_mm: tuple[float, ...] = (1.0, 2.0, 5.0),
    angles: tuple[float, ...] = (0.0, np.pi / 4, np.pi / 2, 3 * np.pi / 4),
    lbp_radius_mm: float = 3.0,
    config_version: str = TEX_METHOD_VERSION,
) -> TextureStatistics:
    """Compute fixed-scale texture proxy measurements.

    All measurements are computed at fixed physical offsets using the provided
    scale. Returns unitless texture proxies; they depend on scale and lighting
    and must not be relabeled as mm roughness (final plan section 7.3).
    """
    if gray.ndim == 3:
        if gray.shape[2] == 3:
            gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
        elif gray.shape[2] == 4:
            gray = cv2.cvtColor(gray, cv2.COLOR_BGRA2GRAY)
        else:
            raise ValueError(f"expected 2, 3 or 4 channels, got {gray.shape[2]}")
    elif gray.ndim != 2:
        raise ValueError(f"expected a 2D or 3D image, got shape {gray.shape}")

    gray = gray.astype(np.float32)
    if not np.isfinite(gray).all():
        raise ValueError("image contains non-finite values")

    limitation: str | None = None
    if not scale.is_scaled:
        limitation = "unscaled imagery: texture proxies reported in pixels only, no metric scale"
        return TextureStatistics(
            glcm_contrast_mm=None,
            glcm_homogeneity_mm=None,
            glcm_energy_mm=None,
            glcm_correlation_mm=None,
            gradient_energy_mm=None,
            lbp_uniformity_mm=None,
            method="fixed_scale_glcm_gradient_lbp",
            config_version=config_version,
            limitation=limitation,
        )

    # GLCM at fixed physical distances
    glcm = _glcm_aggregate(gray, distances_mm, scale)
    # Gradient energy at fixed scale
    grad_energy = _gradient_energy(gray.astype(np.uint8), scale)
    # LBP uniformity at fixed physical radius
    lbp_uni = _lbp_uniformity(gray.astype(np.uint8), lbp_radius_mm, scale)

    return TextureStatistics(
        glcm_contrast_mm=glcm["contrast"],
        glcm_homogeneity_mm=glcm["homogeneity"],
        glcm_energy_mm=glcm["energy"],
        glcm_correlation_mm=glcm["correlation"],
        gradient_energy_mm=grad_energy,
        lbp_uniformity_mm=lbp_uni,
        method="fixed_scale_glcm_gradient_lbp",
        config_version=config_version,
        limitation=limitation,
    )
