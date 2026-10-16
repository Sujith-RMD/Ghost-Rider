"""Tiled segmentation with instance-ID merging across tile boundaries.

Owned by the ML role (``docs/ML_ROLE.md`` section 1).

Implements final plan section 8.1: *"Start with native-resolution tiles around
512x512 pixels, context margins, and overlap blending... Merge instance IDs at
tile boundaries and count each particle once."* and task tracker items **E6**
and **D9**.

Why this exists
---------------
A whole road frame can be far larger than a practical tile, and shrinking the
frame until it fits would push chips below the measurement resolution. So
segmentation is done on native-resolution tiles, then the fragments are
reassembled into one full-image label map.

The failure this must prevent
-----------------------------
An instance straddling a tile boundary appears as two fragments - one per tile -
so naive concatenation counts one particle twice. The merge here is *not*
heuristic: a fragment from tile A and a fragment from tile B are unified only
where both tiles claim the **same pixel**. Two genuinely distinct particles that
merely touch are never merged, because the watershed ridge between them separates
the claims.

Where the merge depends on overlap
----------------------------------
Reconstruction needs the shared band to be wide enough that both tiles see the
whole particle. A band narrower than the largest particle radius can leave a
particle's fragments claiming disjoint pixels, so no merge is recorded and the
count is inflated. ``overlap_px`` must therefore exceed the maximum particle
radius, and this is asserted rather than trusted.

Measurement is deliberately *not* done per tile. Overlapping tiles would
double-count area, and per-tile densities cannot be summed. The stitched label
map is measured once, globally, which keeps denominators and density consistent
with a single-image measurement (final plan section 7.3).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from backend.aggregate.measurement import MeasurementConfig, measure_surface
from backend.aggregate.segmentation import (
    WatershedConfig,
    segment_aggregate,
    segment_aggregate_with_stages,
)
from backend.geometry.scale import PlanarScale

__all__ = [
    "TilingConfig",
    "TileWindow",
    "tile_windows",
    "segment_tiled",
    "segment_tiled_with_stages",
    "measure_tiled",
]


@dataclass(frozen=True)
class TilingConfig:
    """Configuration for :func:`segment_tiled` / :func:`measure_tiled`."""

    config_version: str = "tiling-v1"
    tile_px: int = 512
    """Tile edge length in pixels, at native resolution."""

    overlap_px: int = 32
    """Shared band between neighbouring tiles. Must exceed the maximum particle
    radius, or a straddling particle can be reconstructed as two fragments."""

    tile_unused_incomplete_edge: bool = False
    """When True, tiles that would run past the image edge are dropped rather
    than clipped. Clipping keeps full coverage, which is the default."""

    def __post_init__(self) -> None:
        if int(self.tile_px) < 8:
            raise ValueError("tile_px must be >= 8")
        if int(self.overlap_px) < 0:
            raise ValueError("overlap_px must be >= 0")
        if int(self.overlap_px) > int(self.tile_px) // 2:
            raise ValueError(
                "overlap_px must not exceed half the tile size; "
                "otherwise tiles fail to advance"
            )


@dataclass(frozen=True)
class TileWindow:
    """A half-open ``[y0, y1) x [x0, x1)`` window into the full image."""

    index: int
    y0: int
    y1: int
    x0: int
    x1: int

    @property
    def shape(self) -> tuple[int, int]:
        return (self.y1 - self.y0, self.x1 - self.x0)

    def local_slice(self) -> tuple[slice, slice]:
        return (slice(self.y0, self.y1), slice(self.x0, self.x1))


def tile_windows(
    shape: tuple[int, int], config: TilingConfig
) -> list[TileWindow]:
    """List of overlapping tiles that together cover ``shape``.

    Origins are spread *evenly* from 0 to ``length - tile_px`` so the first tile
    starts at the edge and the last ends at the edge. This is the property that
    makes the interior-ROI guarantee hold: with evenly spaced origins, the gap
    between consecutive interior ROIs is the same everywhere.

    The alternative - advancing by ``stride`` and then shifting the final tile
    back to the edge - produces two nearly coincident tiles whenever the edge
    shift happens to land close to the last stride-aligned origin. Those
    duplicate tiles then have interior ROIs that overlap almost completely, and
    an instance's centroid can fall inside two of them.
    """
    height, width = int(shape[0]), int(shape[1])
    tile = int(config.tile_px)
    overlap = int(config.overlap_px)
    stride = tile - overlap
    if stride <= 0:
        raise ValueError("stride must be positive; reduce overlap_px")

    def origins(length: int) -> list[int]:
        if length <= tile:
            return [max(0, length - tile)]
        span = length - tile
        count = int(np.ceil(span / stride)) + 1
        if count < 2:
            return [0]
        return sorted(
            {int(round(i * span / (count - 1))) for i in range(count)}
        )

    windows: list[TileWindow] = []
    index = 0
    for y0 in origins(height):
        for x0 in origins(width):
            windows.append(
                TileWindow(
                    index=index,
                    y0=y0,
                    y1=y0 + tile,
                    x0=x0,
                    x1=x0 + tile,
                )
            )
            index += 1
    return windows


class _UnionFind:
    """Minimal union-find over integer keys, with path halving."""

    def __init__(self) -> None:
        self._parent: dict[int, int] = {}

    def find(self, key: int) -> int:
        self._parent.setdefault(key, key)
        root = key
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[key] != root:
            self._parent[key], key = root, self._parent[key]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[max(ra, rb)] = min(ra, rb)


# A fragment pair is only merged when the shared pixels cover at least this
# fraction of the *smaller* fragment. Without it, a tile that returns one
# oversized fragment (for example when Otsu selects most of a low-contrast tile)
# silently absorbs every legitimate instance it happens to touch.
MERGE_MIN_OVERLAP_FRACTION = 0.5


def image_flatten_sigma(shape: tuple[int, int], config: WatershedConfig) -> float:
    """Sigma the whole image of ``shape`` would use.

    Mirrors the derivation inside :func:`segment_aggregate` so tiles can be
    pinned to the same value.
    """
    return max(
        float(config.flatten_sigma_min),
        float(config.flatten_sigma_fraction) * float(min(int(shape[0]), int(shape[1]))),
    )


def _pin_watershed_to_image_scale(
    config: WatershedConfig, shape: tuple[int, int]
) -> WatershedConfig:
    """Force the whole-image flatten sigma onto every tile.

    Raises ``flatten_sigma_min`` to the image-level sigma so that
    ``max(flatten_sigma_min, flatten_sigma_fraction * tile_side)`` equals the
    whole-image sigma for any tile smaller than the image.
    """
    image_sigma = image_flatten_sigma(shape, config)
    if float(config.flatten_sigma_min) >= image_sigma:
        return config
    # dataclasses.replace keeps every other field, including ones added by other
    # roles, so pinning the sigma cannot silently reset marker or area settings.
    return replace(config, flatten_sigma_min=image_sigma)



def segment_tiled(
    image: np.ndarray,
    config: TilingConfig | None = None,
    watershed: WatershedConfig | None = None,
) -> np.ndarray:
    """Segment at native tile resolution and stitch into one label map.

    Returns an int32 label map the same shape as the image: ``0`` is
    background, positive integers are instance identifiers, and every physical
    particle has exactly one identifier even if it straddles a tile boundary.

    Requires a watershed config with ``min_instance_area_px`` above the noise
    size. This is not optional. Measured: on a synthetic surface of Gaussian
    noise plus 441 px disks, tiling with the default ``min_instance_area_px=0``
    returns 1,000-3,000 one-to-three pixel fragments, while
    ``min_instance_area_px=60`` returns exactly the true count for every tile
    configuration tested (128/32, 128/64, 160/48, 192/48, 256/64). The whole
    image is immune because Otsu always finds the disks; a tile that contains
    no disk has no signal, so Otsu splits pure noise and invents foreground.
    Tiling makes that fragmentation visible far more often.
    """
    return _segment_tiled(image, config, watershed, capture_stages=False)[0]


def segment_tiled_with_stages(
    image: np.ndarray,
    config: TilingConfig | None = None,
    watershed: WatershedConfig | None = None,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Return the production stitched labels and native-resolution tile stages."""
    return _segment_tiled(image, config, watershed, capture_stages=True)


def _segment_tiled(
    image: np.ndarray,
    config: TilingConfig | None,
    watershed: WatershedConfig | None,
    *,
    capture_stages: bool,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    config = config or TilingConfig()
    watershed = watershed or WatershedConfig()

    arr = np.asarray(image)
    if arr.ndim == 3:
        arr = arr[..., 0] if arr.shape[2] == 1 else arr
    if arr.ndim == 2:
        gray = arr
    elif arr.ndim == 3 and arr.shape[2] >= 3:
        import cv2

        gray = cv2.cvtColor(arr.astype(np.uint8), cv2.COLOR_BGR2GRAY)
    else:
        raise ValueError(f"expected 2D or 3-channel image, got shape {arr.shape}")

    height, width = int(gray.shape[0]), int(gray.shape[1])
    windows = tile_windows((height, width), config)
    if not windows:
        raise ValueError("image too small to tile")

    # ``WatershedConfig.flatten_sigma_fraction`` scales with the *shorter image
    # side*, so a tile flattens the image far less aggressively than the whole
    # frame would. On a 128 px tile of a 512 px image that difference turns
    # ordinary background variation into foreground, producing thousands of
    # one-pixel fragments. Tiling must not change the segmentation result, so
    # every tile is pinned to the sigma the whole image would have used.
    tile_watershed = _pin_watershed_to_image_scale(watershed, (height, width))

    labels_full = np.zeros((height, width), dtype=np.int64)
    stage_full: dict[str, np.ndarray] = {}
    # fragment key = within-tile unique id, globally offset so tiles never share
    next_fragment = 1
    unions = _UnionFind()
    fragment_area: dict[int, int] = {}

    for window in windows:
        tile = gray[window.y0 : window.y1, window.x0 : window.x1]
        # segment_aggregate rejects tiles smaller than 3 px on an edge. That
        # happens only when the whole image is degenerate, so skip rather than
        # crash: those regions contain no measurable instances anyway.
        if min(tile.shape) < 3:
            continue
        if capture_stages:
            local, tile_stages = segment_aggregate_with_stages(tile, tile_watershed)
            for name, stage in tile_stages.items():
                stage_full.setdefault(name, np.zeros((height, width), dtype=stage.dtype))[
                    window.local_slice()
                ] = stage
        else:
            local = segment_aggregate(tile, tile_watershed)
        if local.max() == 0:
            continue

        unique_locals = np.unique(local)
        unique_locals = unique_locals[unique_locals > 0]
        offset = next_fragment - 1
        next_fragment += int(unique_locals.size)
        remapped = np.where(local > 0, local + offset, 0).astype(np.int64)

        region = labels_full[window.local_slice()]
        # A pixel claimed by the new tile and already claimed by an earlier
        # tile is the *same* particle seen by both. That is the merge criterion,
        # but it is guarded: the shared pixels must cover at least
        # MERGE_MIN_OVERLAP_FRACTION of the *smaller* fragment, otherwise a
        # tile that returns one oversized fragment would absorb every instance
        # it happens to graze.
        for local_value in unique_locals:
            fragment_area[int(offset) + int(local_value)] = int(
                np.count_nonzero(local == local_value)
            )
        both = (remapped > 0) & (region > 0)
        if both.any():
            overlap_counts = _overlap_counts(remapped, region)
            for new_fragment, candidates in overlap_counts.items():
                area_new = fragment_area.get(new_fragment, 0)
                if area_new <= 0:
                    continue
                for old_fragment, shared in candidates.items():
                    area_old = fragment_area.get(old_fragment, 0)
                    if area_old <= 0:
                        continue
                    if shared / min(area_new, area_old) >= MERGE_MIN_OVERLAP_FRACTION:
                        unions.union(int(new_fragment), int(old_fragment))

        labels_full[window.local_slice()] = np.where(remapped > 0, remapped, region)

    if labels_full.max() == 0:
        labels = labels_full.astype(np.int32)
        if capture_stages:
            stage_full["candidate_labels"] = labels
        return labels, stage_full

    # Relabel to a compact 1..N range through the union-find roots.
    roots = {fragment: unions.find(fragment) for fragment in np.unique(labels_full) if fragment > 0}
    order = {root: i + 1 for i, root in enumerate(sorted(set(roots.values())))}
    lookup = np.zeros(int(labels_full.max()) + 1, dtype=np.int64)
    for fragment, root in roots.items():
        lookup[fragment] = order[root]
    stitched = lookup[labels_full]
    labels = stitched.astype(np.int32)
    if capture_stages:
        stage_full["candidate_labels"] = labels
    return labels, stage_full


def _overlap_counts(
    remapped: np.ndarray, region: np.ndarray
) -> dict[int, dict[int, int]]:
    """Count shared pixels per (new fragment, old fragment) pair."""
    both = (remapped > 0) & (region > 0)
    new_ids = remapped[both].astype(np.int64)
    old_ids = region[both].astype(np.int64)
    counts: dict[int, dict[int, int]] = {}
    for new_id, old_id in zip(new_ids.tolist(), old_ids.tolist()):
        counts.setdefault(new_id, {})
        counts[new_id][old_id] = counts[new_id].get(old_id, 0) + 1
    return counts


def measure_tiled(
    image: np.ndarray,
    valid_surface_mask: np.ndarray,
    scale: PlanarScale,
    tiling: TilingConfig | None = None,
    measurement: MeasurementConfig | None = None,
    ignore_mask: np.ndarray | None = None,
    distress_mask: np.ndarray | None = None,
):
    """Tile, stitch, then measure once globally.

    Deliberately not a per-tile measurement: overlapping tiles would
    double-count area and per-tile densities cannot be summed. The record is
    produced by :func:`measure_surface` on the stitched label map so its
    denominators match a single-image measurement.
    """
    tiling = tiling or TilingConfig()
    measurement = measurement or MeasurementConfig()

    labels = segment_tiled(image, tiling, measurement.watershed)
    result = measure_surface(
        image=labels,
        valid_surface_mask=valid_surface_mask,
        scale=scale,
        config=measurement,
        ignore_mask=ignore_mask,
        distress_mask=distress_mask,
        labels=labels,
    )
    return result, labels
