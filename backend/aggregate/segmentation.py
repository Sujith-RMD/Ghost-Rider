"""Classical aggregate segmentation baseline.

Owned by the ML role (``docs/ML_ROLE.md`` section 1).

This is the OpenCV/scikit-image illumination-normalisation, marker-controlled
watershed baseline required by final plan section 8.1. It must stay available
even after a learned challenger exists: if the learned model cannot beat it on
unseen parent groups, the baseline is kept.

Pipeline: robust illumination flattening -> polarity-aware foreground score ->
Otsu foreground -> small morphological cleanup -> distance-transform peak
markers (greedy non-maximum suppression) -> marker-controlled watershed, then the
watershed result is clipped back to the detected foreground so instances cannot
bleed into the binder regions between stones.

Known limitations (deliberate, not defects to hide):

* Touching particles are split only where the watershed finds a ridge; heavy
  merges are diagnosed through the split/merge diagnostics, not hidden.
* The foreground polarity is a per-dataset appearance assumption. It is a
  config field, never inferred per image from the score.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import pi, sqrt

import cv2
import numpy as np
import scipy.ndimage as ndi

__all__ = [
    "WatershedConfig",
    "InstanceProps",
    "segment_aggregate",
    "instance_properties",
    "renumber_labels",
]


@dataclass(frozen=True)
class WatershedConfig:
    """Configuration for :func:`segment_aggregate`.

    ``config_version`` travels into every produced measurement record so a
    change in segmentation behaviour is traceable (final plan section 9.2).
    """

    config_version: str = "agg-classical-v4"
    polarity: str = "brighter"
    """``brighter``: exposed aggregate is lighter than binder. ``darker``: the
    opposite. Must match the dataset/surface appearance, not per-image guessing."""

    flatten_sigma_fraction: float = 0.125
    """Large-blur sigma as a fraction of the shorter image side, used to remove
    illumination gradient while keeping chip-scale texture."""

    flatten_sigma_min: float = 6.0
    norm_lo_percentile: float = 0.5
    norm_hi_percentile: float = 99.5
    noise_kernel_px: int = 3
    """Ellipse kernel for a morphological OPEN that removes sub-particle specks.
    Values below 3 are skipped."""

    hole_fill_max_area_px: int = 16
    """Fill background holes up to this area that are enclosed by foreground.

    This replaces the morphological CLOSE that used to run here. A 3x3 close
    bridges any gap up to about 2 px, which destroyed the thin dark binder joint
    between two touching chips - measured on the synthetic touching fixture: 903
    of 1,380 joint pixels were flipped back to foreground, collapsing 59 chip
    components into 21 and taking instance F1 from 0.700 to 0.228. Filling
    enclosed holes keeps the intended effect (threshold holes inside a particle)
    without joining neighbours.
    """

    marker_method: str = "h_maxima"
    """How watershed markers are chosen.

    ``h_maxima`` (default): within each connected foreground region, markers are
    the connected components of ``distance >= (1 - h) * peak``. A flat ridge or
    plateau therefore yields **one** marker, so a chain of chips whose boundary is
    not visible is reported as one region instead of being invented into several.

    ``nms``: the previous greedy non-maximum-suppression seeding, kept so earlier
    numbers remain reproducible. It over-seeds flat plateaus: on the synthetic
    touching fixture it reported 18 extra particles per image where ``h_maxima``
    reports ~1.
    """

    marker_h_max_fraction: float = 0.5
    """Relative h-maxima depth for ``marker_method='h_maxima'``.

    Selected by ``python -m eval.aggregate_eval --sweep-markers`` on train seeds
    0-7 and reported on held-out seeds 5000-5007: held-out median instance F1
    0.839 with a median signed count error of -2.5, against 0.628 for the legacy
    ``nms`` seeding. The sweep's argmax was h=0.9 (0.877), which was *not* taken:
    at that depth the marker stage degenerates towards one particle per connected
    region, which under-splits any real merge whose joint is too faint to break
    the foreground. The rule keeps the smallest depth within 0.05 of the best.
    """

    marker_min_distance_px: int = 4
    """Minimum separation between accepted markers (``marker_method='nms'``)."""

    min_marker_radius_px: float = 1.0
    """Minimum distance-transform value for a pixel to be a marker candidate
    (``marker_method='nms'``)."""

    min_instance_area_px: int = 0
    """Drop instances smaller than this area after segmentation (0 = keep all).

    Final plan section 7.3: count only visible particles *above the validated
    minimum size*, and record that minimum. This is the segmentation-level form
    of that rule, expressed in pixels so it needs no scale; the declared physical
    minimum lives in ``MeasurementConfig.min_diameter_px``. It removes sub-particle
    texture specks from the label map itself, which is what makes a count honest.
    """

    def __post_init__(self) -> None:
        if self.polarity not in ("brighter", "darker"):
            raise ValueError("polarity must be 'brighter' or 'darker'")
        if not 0.0 <= self.norm_lo_percentile < self.norm_hi_percentile <= 100.0:
            raise ValueError("normalisation percentiles must satisfy 0 <= lo < hi <= 100")
        if self.marker_method not in ("h_maxima", "nms"):
            raise ValueError("marker_method must be 'h_maxima' or 'nms'")
        if not 0.0 <= float(self.marker_h_max_fraction) < 1.0:
            raise ValueError("marker_h_max_fraction must satisfy 0 <= h < 1")
        if int(self.marker_min_distance_px) < 1:
            raise ValueError("marker_min_distance_px must be >= 1")
        if float(self.min_marker_radius_px) <= 0.0:
            raise ValueError("min_marker_radius_px must be > 0")
        if float(self.flatten_sigma_fraction) <= 0.0:
            raise ValueError("flatten_sigma_fraction must be > 0")
        if int(self.min_instance_area_px) < 0:
            raise ValueError("min_instance_area_px must be >= 0")
        if int(self.hole_fill_max_area_px) < 0:
            raise ValueError("hole_fill_max_area_px must be >= 0")
        if 0 < int(self.min_instance_area_px) <= int(self.hole_fill_max_area_px):
            raise ValueError(
                "hole_fill_max_area_px must be smaller than min_instance_area_px, "
                "otherwise hole filling can swallow the smallest resolvable particle"
            )


@dataclass(frozen=True)
class InstanceProps:
    """Measured properties of one segmented aggregate instance (pixel space)."""

    instance_id: int
    area_px: int
    centroid_yx: tuple[float, float]
    equivalent_diameter_px: float
    bbox_yx: tuple[int, int, int, int]
    touches_border: bool

    def describe(self) -> dict:
        return {
            "instance_id": self.instance_id,
            "area_px": self.area_px,
            "centroid_yx": [self.centroid_yx[0], self.centroid_yx[1]],
            "equivalent_diameter_px": self.equivalent_diameter_px,
            "bbox_yx": list(self.bbox_yx),
            "touches_border": self.touches_border,
        }


def _to_gray(image: np.ndarray) -> np.ndarray:
    """Return a 2D float32 gray image from 2D, 3-channel (BGR) or 4-channel input."""
    arr = np.asarray(image)
    if arr.ndim == 3:
        if arr.shape[2] == 3:
            arr = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
        elif arr.shape[2] == 4:
            arr = cv2.cvtColor(arr, cv2.COLOR_BGRA2GRAY)
        else:
            raise ValueError(f"expected 2, 3 or 4 channels, got {arr.shape[2]}")
    elif arr.ndim != 2:
        raise ValueError(f"expected a 2D or 3D image, got shape {arr.shape}")
    if arr.size == 0:
        raise ValueError("image is empty")
    if not np.all(np.isfinite(arr)):
        raise ValueError("image contains non-finite values")
    return arr.astype(np.float32)


def _flatten_illumination(gray: np.ndarray, sigma: float) -> np.ndarray:
    """High-pass the image to remove illumination gradient, keeping texture."""
    blurred = cv2.GaussianBlur(gray, (0, 0), sigmaX=float(sigma), sigmaY=float(sigma))
    return gray - blurred


def _score_to_uint8(flat: np.ndarray, config: WatershedConfig) -> np.ndarray:
    """Robustly map a signed flatten response to 0..255 for Otsu thresholding."""
    lo, hi = np.percentile(
        flat, [config.norm_lo_percentile, config.norm_hi_percentile]
    )
    lo, hi = float(lo), float(hi)
    if hi - lo < 1e-9:
        lo, hi = float(flat.min()), float(flat.max())
    if hi - lo < 1e-9:
        return np.zeros(flat.shape, dtype=np.uint8)
    scaled = (flat - lo) / (hi - lo)
    return np.clip(scaled * 255.0, 0.0, 255.0).astype(np.uint8)


def _select_markers(distance: np.ndarray, config: WatershedConfig) -> np.ndarray:
    """Greedy non-maximum suppression on distance-transform peaks.

    Returns an int32 map with marker regions labelled 1..N. Greedy suppression
    is used instead of a plain local-maximum test so that symmetric plateaus
    (which occur when the distance maximum falls between pixel centres) collapse
    to a single marker instead of over-segmenting one particle.
    """
    local_max = (distance == ndi.maximum_filter(distance, size=3)) & (
        distance >= float(config.min_marker_radius_px)
    )
    ys, xs = np.nonzero(local_max)
    if len(ys) == 0:
        return np.zeros(distance.shape, dtype=np.int32)

    values = distance[ys, xs]
    order = np.argsort(-values, kind="stable")
    min_distance = float(config.marker_min_distance_px)
    kept_y: list[int] = []
    kept_x: list[int] = []
    kept_v: list[float] = []
    for index in order:
        y, x, value = int(ys[index]), int(xs[index]), float(values[index])
        if kept_y:
            dy = np.asarray(kept_y, dtype=np.float64) - y
            dx = np.asarray(kept_x, dtype=np.float64) - x
            if np.any(dy * dy + dx * dx < min_distance * min_distance):
                continue
        kept_y.append(y)
        kept_x.append(x)
        kept_v.append(value)

    markers = np.zeros(distance.shape, dtype=np.int32)
    for label, (y, x) in enumerate(zip(kept_y, kept_x), start=1):
        markers[y, x] = label
    return markers


def renumber_labels(labels: np.ndarray) -> np.ndarray:
    """Compact positive labels into a contiguous 1..N range (0 stays background)."""
    labels = np.asarray(labels)
    if labels.size == 0:
        return labels.astype(np.int32, copy=False)
    positive = np.unique(labels[labels > 0])
    if positive.size == 0:
        return np.zeros(labels.shape, dtype=np.int32)
    lookup = np.zeros(int(positive.max()) + 1, dtype=np.int32)
    lookup[positive] = np.arange(1, positive.size + 1, dtype=np.int32)
    clipped = np.where(labels > 0, labels, 0)
    return lookup[clipped]


def _select_markers_h_maxima(
    foreground: np.ndarray, distance: np.ndarray, config: WatershedConfig
) -> np.ndarray:
    """One marker per connected region of ``distance >= (1-h) * component peak``.

    Relative h-maxima are used instead of raw local maxima because a raw local
    maximum test plus greedy suppression both mis-handle the flat plateaus that a
    distance transform produces: a plateau is a *set* of equal maxima, so it gets
    either one arbitrary marker or a marker every ``marker_min_distance_px`` along
    its length. Anchoring the depth to each component's own peak also makes the
    rule independent of the absolute brightness or blob size.
    """
    binary = np.asarray(foreground) > 0
    if not binary.any():
        return np.zeros(binary.shape, dtype=np.int32)

    components, n_components = ndi.label(binary)
    markers = np.zeros(binary.shape, dtype=np.int32)
    if n_components == 0:
        return markers

    h = float(config.marker_h_max_fraction)
    # Per-component peak, mapped back onto every pixel. Index 0 (background) gets
    # an infinite threshold so background can never enter the thresholded set.
    peaks = np.asarray(
        ndi.maximum(distance, labels=components, index=np.arange(1, n_components + 1)),
        dtype=np.float64,
    )
    peak_map = np.concatenate([[np.inf], peaks])
    above = binary & (distance >= peak_map[components] * (1.0 - h))

    plateaus, n_plateaus = ndi.label(above)
    if n_plateaus == 0:
        return markers

    # One marker per plateau, placed at its deepest pixel. Both steps are single
    # scipy calls: a per-component Python loop over a real 512x512 pavement image
    # (thousands of components) turned a two-second evaluation into minutes.
    positions = np.atleast_2d(
        ndi.maximum_position(
            distance, labels=plateaus, index=np.arange(1, n_plateaus + 1)
        )
    )
    for label_id, (y, x) in enumerate(positions, start=1):
        markers[int(y), int(x)] = label_id
    return markers


def _fill_enclosed_holes(foreground: np.ndarray, max_area_px: int) -> np.ndarray:
    """Fill background regions enclosed by foreground whose area is <= the limit.

    Only regions that do *not* touch the image border are candidates, so this can
    never close a gap that opens onto real binder between particles.
    """
    limit = int(max_area_px)
    binary = np.asarray(foreground) > 0
    if limit <= 0 or not binary.any():
        return (binary.astype(np.uint8)) * 255

    labels, count = ndi.label(~binary)
    if count == 0:
        return binary.astype(np.uint8) * 255

    touches_border = set(
        np.unique(
            np.concatenate([labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]])
        ).tolist()
    )
    sizes = np.bincount(labels.ravel(), minlength=count + 1)
    fillable = [
        label_id
        for label_id in range(1, count + 1)
        if label_id not in touches_border and int(sizes[label_id]) <= limit
    ]
    filled = binary.copy()
    if fillable:
        filled |= np.isin(labels, fillable)
    return filled.astype(np.uint8) * 255


def _drop_small_instances(labels: np.ndarray, min_area_px: int) -> np.ndarray:
    """Zero out and renumber instances whose area is below ``min_area_px``.

    Removing an instance only deletes labels; the kept instances keep their exact
    pixel extent, so a filter can never rescale a measured particle.
    """
    threshold = int(min_area_px)
    if threshold <= 0:
        return labels
    counts = np.bincount(np.asarray(labels).ravel())
    small = np.nonzero((counts > 0) & (counts < threshold))[0]
    small = small[small > 0]
    if small.size == 0:
        return labels
    keep = np.asarray(labels).copy()
    keep[np.isin(keep, small)] = 0
    return renumber_labels(keep)


def segment_aggregate(image: np.ndarray, config: WatershedConfig | None = None) -> np.ndarray:
    """Segment exposed aggregate instances.

    Returns an int32 label map: ``0`` is background/gap/unresolved, and positive
    integers are instance identifiers starting at 1. Instances below
    ``config.min_instance_area_px`` are removed before the map is returned.
    """
    config = config or WatershedConfig()
    gray = _to_gray(image)
    if min(gray.shape) < 3:
        raise ValueError(f"image is too small to segment: shape {gray.shape}")

    sigma = max(
        float(config.flatten_sigma_min),
        float(config.flatten_sigma_fraction) * float(min(gray.shape)),
    )
    flat = _flatten_illumination(gray, sigma)
    if config.polarity == "darker":
        flat = -flat
    score = _score_to_uint8(flat, config)
    if not score.any():
        return np.zeros(gray.shape, dtype=np.int32)

    _, foreground = cv2.threshold(score, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel_px = int(config.noise_kernel_px)
    if kernel_px >= 3:
        if kernel_px % 2 == 0:
            kernel_px += 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_px, kernel_px))
        foreground = cv2.morphologyEx(foreground, cv2.MORPH_OPEN, kernel)
    # Fill enclosed holes instead of running a morphological close: the close
    # bridges the visible joint between touching chips and destroys the boundary
    # evidence the instance split depends on.
    foreground = _fill_enclosed_holes(foreground, config.hole_fill_max_area_px)
    fg_bool = foreground > 0
    if not fg_bool.any():
        return np.zeros(gray.shape, dtype=np.int32)

    distance = cv2.distanceTransform(foreground, cv2.DIST_L2, 5)
    if config.marker_method == "h_maxima":
        peaks = _select_markers_h_maxima(fg_bool, distance, config)
    else:
        peaks = _select_markers(distance, config)
    if peaks.max() == 0:
        # Foreground exists but no resolvable peak: report one merged instance
        # rather than silently returning nothing.
        labels = np.where(fg_bool, 1, 0).astype(np.int32)
        return _drop_small_instances(
            renumber_labels(labels), config.min_instance_area_px
        )

    # Watershed on the *negated distance transform*, not on the image gradient.
    #
    # Two reasons, both measured on synthetic disks before this change:
    # 1. A background marker on the image gradient floods a flat particle
    #    interior through the rim and steals area (a 12 px-radius disk measured
    #    293 px^2 instead of 441 px^2, a 34% size bias). Clipping to the
    #    foreground cannot repair that, because the pixels already carry the
    #    background label.
    # 2. With the distance transform, the neck between two touching particles is
    #    a ridge, which is exactly where a split belongs.
    # No background marker is used; the result is clipped to the detected
    # foreground so instances cannot bleed into binder regions.
    peak_distance = float(distance.max())
    normalised = distance / peak_distance if peak_distance > 0.0 else distance
    surface = np.clip(255.0 - normalised * 255.0, 0.0, 255.0).astype(np.uint8)
    surface_bgr = cv2.cvtColor(surface, cv2.COLOR_GRAY2BGR)
    labels = _basin_labels(fg_bool, peaks.astype(np.int32), surface_bgr)
    return _drop_small_instances(renumber_labels(labels), config.min_instance_area_px)


def _basin_labels(
    foreground: np.ndarray, markers: np.ndarray, surface_bgr: np.ndarray
) -> np.ndarray:
    """Assign foreground pixels to markers **without** crossing components.

    ``cv2.watershed`` floods the whole image from every marker at once, so the
    background acts as a bridge: a disconnected foreground component that holds
    its own correct marker can still end up labelled with a basin seeded somewhere
    else. Measured before this existed: two full-width bars with markers placed
    correctly at (50,1) and (80,0) came back as **one** 7920 px instance - a
    silent under-count that would hit real imagery wherever chips form separate
    blobs.

    Three cases, and only the second needs the flood:

    * one component, one marker -> the whole component is that instance;
    * one component, several markers -> a genuine cluster, so flood inside that
      component only (the common case stays cheap: on a 512x512 frame with
      thousands of specks almost every component has exactly one marker);
    * a component with no marker -> report it as one merged region rather than
      silently dropping real foreground.
    """
    components, n_components = ndi.label(foreground)
    if n_components == 0:
        return np.zeros(foreground.shape, dtype=np.int32)

    mk_y, mk_x = np.nonzero(markers > 0)
    if mk_y.size == 0:
        return components.astype(np.int32)

    comp_ids = components[mk_y, mk_x]
    lab_ids = markers[mk_y, mk_x]
    order = np.argsort(comp_ids, kind="stable")
    comp_sorted = comp_ids[order]
    lab_sorted = lab_ids[order]
    starts = np.flatnonzero(np.r_[True, comp_sorted[1:] != comp_sorted[:-1]])
    group_comp = comp_sorted[starts]
    group_lab = lab_sorted[starts]
    counts = np.diff(np.r_[starts, comp_sorted.size])

    result = np.zeros(foreground.shape, dtype=np.int32)

    # Case 1: exactly one marker -> the whole component is that instance.
    single = counts == 1
    if single.any():
        lut = np.zeros(n_components + 1, dtype=np.int32)
        lut[group_comp[single]] = group_lab[single]
        take = np.isin(components, group_comp[single])
        result[take] = lut[components[take]]

    # A background rim keeps the watershed boundary outside interior components.
    boxes = ndi.find_objects(components)
    for comp in group_comp[counts > 1].tolist():
        ys, xs = boxes[comp - 1]
        crop = (
            slice(max(0, ys.start - 1), min(foreground.shape[0], ys.stop + 1)),
            slice(max(0, xs.start - 1), min(foreground.shape[1], xs.stop + 1)),
        )
        region = components[crop] == comp
        sub_markers = np.where(region, markers[crop], 0).astype(np.int32)
        if sub_markers.max() == 0:
            continue
        cv2.watershed(np.ascontiguousarray(surface_bgr[crop]), sub_markers)
        take = region & (sub_markers > 0)
        result[crop][take] = sub_markers[take]

    # Case 3: a component with no marker keeps its pixels, as one merged region.
    covered = np.zeros(n_components + 1, dtype=bool)
    covered[group_comp] = True
    take = (components > 0) & ~covered[components]
    result[take] = components[take]

    return result


def instance_properties(labels: np.ndarray) -> list[InstanceProps]:
    """Per-instance area, centroid, equivalent diameter and border contact."""
    labels = np.asarray(labels)
    if labels.ndim != 2:
        raise ValueError(f"labels must be 2D, got shape {labels.shape}")
    positives = np.unique(labels[labels > 0])
    if positives.size == 0:
        return []

    counts = np.bincount(labels.ravel())
    centroids = ndi.center_of_mass(
        np.ones(labels.shape, dtype=np.uint8), labels, index=[int(v) for v in positives]
    )
    slices = ndi.find_objects(labels)
    height, width = labels.shape

    properties: list[InstanceProps] = []
    for value, centroid in zip(positives, centroids):
        instance_id = int(value)
        area_px = int(counts[instance_id]) if instance_id < len(counts) else 0
        if area_px <= 0:
            continue
        slice_y, slice_x = slices[instance_id - 1]
        bbox = (int(slice_y.start), int(slice_x.start), int(slice_y.stop), int(slice_x.stop))
        touches_border = bool(
            bbox[0] == 0 or bbox[1] == 0 or bbox[2] == height or bbox[3] == width
        )
        properties.append(
            InstanceProps(
                instance_id=instance_id,
                area_px=area_px,
                centroid_yx=(float(centroid[0]), float(centroid[1])),
                equivalent_diameter_px=sqrt(4.0 * area_px / pi),
                bbox_yx=bbox,
                touches_border=touches_border,
            )
        )
    return properties
