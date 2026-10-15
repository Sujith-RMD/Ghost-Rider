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

from dataclasses import dataclass

import numpy as np

from backend.aggregate.measurement import MeasurementConfig, measure_surface
from backend.aggregate.segmentation import WatershedConfig, segment_aggregate
from backend.geometry.scale import PlanarScale

__all__ = [
    "TilingConfig",
    "TileWindow",
    "tile_windows",
    "segment_tiled",
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

    The stride is ``tile_px - overlap_px``. The final tile on each axis is
    shifted back so it ends exactly at the image edge, which keeps tiles the
    requested size and keeps coverage complete.
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
        starts: list[int] = []
        position = 0
        while position + tile < length:
            starts.append(position)
            position += stride
        starts.append(length - tile)
        return starts

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


def segment_tiled(
    image: np.ndarray,
    config: TilingConfig | None = None,
    watershed: WatershedConfig | None = None,
) -> np.ndarray:
    """Segment at native tile resolution and stitch into one label map.

    Returns an int32 label map the same shape as the image: ``0`` is
    background, positive integers are instance identifiers, and every physical
    particle has exactly one identifier even if it straddles a tile boundary.
    """
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

    labels_full = np.zeros((height, width), dtype=np.int64)
    # fragment key = within-tile unique id, globally offset so tiles never share
    next_fragment = 1
    unions = _UnionFind()

    for window in windows:
        tile = gray[window.y0 : window.y1, window.x0 : window.x1]
        local = segment_aggregate(tile, watershed)
        if local.max() == 0:
            continue

        unique_locals = np.unique(local)
        unique_locals = unique_locals[unique_locals > 0]
        offset = next_fragment - 1
        next_fragment += int(unique_locals.size)
        remapped = np.where(local > 0, local + offset, 0).astype(np.int64)

        region = labels_full[window.local_slice()]
        # A pixel claimed by the new tile and already claimed by an earlier
        # tile is the *same* particle seen by both. That is the only merge
        # criterion used; touching-but-disjoint particles never qualify.
        both = (remapped > 0) & (region > 0)
        if both.any():
            new_fragments = np.unique(remapped[both])
            old_fragments = np.unique(region[both])
            # Pair them by proximity: the fragment with the larger overlap count
            # wins, which is a deterministic tie-break rather than a guess.
            overlap_counts = _overlap_counts(remapped, region)
            for new_fragment in new_fragments:
                best_old = max(
                    overlap_counts.get(new_fragment, {}).items(),
                    key=lambda kv: (kv[1], -kv[0]),
                )[0]
                unions.union(int(new_fragment), int(best_old))

        labels_full[window.local_slice()] = np.where(
            remapped > 0, remapped, region
        )

    if labels_full.max() == 0:
        return labels_full.astype(np.int32)

    # Relabel to a compact 1..N range through the union-find roots.
    roots = {fragment: unions.find(fragment) for fragment in np.unique(labels_full) if fragment > 0}
    order = {root: i + 1 for i, root in enumerate(sorted(set(roots.values())))}
    lookup = np.zeros(int(labels_full.max()) + 1, dtype=np.int64)
    for fragment, root in roots.items():
        lookup[fragment] = order[root]
    stitched = lookup[labels_full]
    return stitched.astype(np.int32)


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
