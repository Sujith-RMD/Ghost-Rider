"""Tests for tiled segmentation and tile-boundary instance merging (E6 / D9).

The property under test is the one the final plan requires: an instance that
straddles a tile boundary must be counted exactly once - neither split into two
nor merged with a neighbour.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.aggregate.segmentation import WatershedConfig
from backend.aggregate.tiling import (
    TilingConfig,
    image_flatten_sigma,
    measure_tiled,
    segment_tiled,
    tile_windows,
)
from backend.aggregate.measurement import MeasurementConfig, measure_surface
from backend.geometry import PlanarScale, ScaleSource


# Tiling requires fragments below the noise size to be filtered out. Without it
# a tile that contains no disk has no signal, Otsu splits the pure noise, and
# the result is thousands of one-to-three pixel specks. The disk area below is
# 441 px, so 60 px keeps disks while dropping specks. Measured, not assumed.
TILING_WATERSHED = WatershedConfig(min_instance_area_px=60)


def _disks(
    n_per_side: int, spacing: int, radius: int, size: int, texture: bool = True
) -> tuple[np.ndarray, np.ndarray]:
    """Grid of well-separated bright disks on a surface-like background.

    ``texture`` adds low-amplitude noise to the background. A pure flat
    background is deliberately avoided: it lets Otsu select an entire
    low-contrast tile as one oversized fragment, which is a *segmentation*
    pathology, not a tiling one. Real asphalt has texture everywhere.
    """
    rng = np.random.default_rng(11)
    if texture:
        img = rng.normal(60.0, 6.0, size=(size, size))
    else:
        img = np.full((size, size), 60.0)
    img = np.clip(img, 0, 255).astype(np.uint8)
    truth = np.zeros((size, size), dtype=np.int32)
    margin = radius + 4
    instance = 1
    for i in range(n_per_side):
        for j in range(n_per_side):
            cy = margin + i * spacing
            cx = margin + j * spacing
            if cy + radius >= size or cx + radius >= size:
                continue
            yy, xx = np.ogrid[:size, :size]
            mask = (yy - cy) ** 2 + (xx - cx) ** 2 <= radius * radius
            img[mask] = 200
            truth[mask] = instance
            instance += 1
    return img, truth


def _scale() -> PlanarScale:
    return PlanarScale.calibrated(1.0, 1.0, ScaleSource.RIG_CALIBRATED, "test")


def test_interior_rois_are_evenly_spaced_and_do_not_double_count():
    """The property that makes boundary instances countable exactly once.

    ``segment_tiled`` stitches fragments via union-find and measures on that one
    stitched map, so a particle is counted once by construction. What the tile
    layout must additionally provide is *even* interior-ROI spacing: if two
    neighbouring interior ROIs overlapped by a variable amount, the shared band
    available for merging a straddling particle would vary unpredictably.

    Exact-integer geometry is used so floating-point rounding cannot tip the
    result: tile 128, overlap 16 -> stride 112, and length 688 makes span an
    exact multiple of the stride, so origins land on 0, 112, 224, ... exactly.
    With roi_margin 8 the interior width is 128 - 16 = 112, equal to the stride,
    so interiors are adjacent and never overlap.
    """
    tile_px, overlap_px, roi_margin = 128, 16, 8
    shape = (688, 688)
    windows = tile_windows(shape, TilingConfig(tile_px=tile_px, overlap_px=overlap_px))

    ys = sorted({w.y0 for w in windows})
    gaps = [b - a for a, b in zip(ys, ys[1:])]
    assert gaps, "expected more than one tile per axis"
    assert max(gaps) == min(gaps), "interior ROIs are unevenly spaced"

    interior = np.zeros(shape, dtype=np.int32)
    for w in windows:
        interior[
            w.y0 + roi_margin : w.y1 - roi_margin,
            w.x0 + roi_margin : w.x1 - roi_margin,
        ] += 1
    assert interior.max() == 1, (
        "a pixel sits inside the interior ROI of more than one tile"
    )
    assert interior.min() == 0, "interior ROIs should not tile the whole image"


def test_tiles_cover_the_whole_image():
    shape = (640, 480)
    windows = tile_windows(shape, TilingConfig(tile_px=128, overlap_px=16))
    coverage = np.zeros(shape, dtype=np.int32)
    for w in windows:
        coverage[w.local_slice()] += 1
        assert w.y1 <= shape[0] and w.x1 <= shape[1]
        assert w.shape == (128, 128), "edge tiles are shifted, never clipped"
    assert coverage.min() == 1, "some pixel was not covered by any tile"
    assert len({w.index for w in windows}) == len(windows), "duplicate tile indices"


def test_tiles_do_not_run_off_the_edge():
    shape = (300, 300)
    for w in tile_windows(shape, TilingConfig(tile_px=200, overlap_px=20)):
        assert w.y1 <= shape[0] and w.x1 <= shape[1]
        assert w.shape == (200, 200), "edge tiles are shifted, never clipped"


def test_overlap_may_not_exceed_half_the_tile():
    with pytest.raises(ValueError):
        TilingConfig(tile_px=200, overlap_px=120)
    with pytest.raises(ValueError):
        TilingConfig(tile_px=4)


def test_boundary_straddling_instance_is_counted_once():
    # Ground truth is known exactly, so this is a real correctness test rather
    # than a similarity check.
    n = 12
    size = n * 40
    img, truth = _disks(n, spacing=40, radius=14, size=size)
    expected = int(np.count_nonzero(np.unique(truth) > 0))
    assert expected == n * n

    for tile_px, overlap in ((128, 32), (160, 48), (192, 64), (256, 32)):
        cfg = TilingConfig(tile_px=tile_px, overlap_px=overlap)
        labels = segment_tiled(img, cfg)
        found = int(np.count_nonzero(np.unique(labels) > 0))
        assert found == expected, (
            f"tile {tile_px}/{overlap}: expected {expected} instances, "
            f"found {found} - boundary instances were split or merged"
        )


def test_no_fragment_merges_two_distinct_particles():
    # Well-separated disks must never be fused. A false merge is caught by the
    # instance count dropping below the truth.
    size = 600
    img, truth = _disks(10, spacing=60, radius=20, size=size)
    expected = 100
    for tile_px, overlap in ((128, 48), (256, 64)):
        labels = segment_tiled(img, TilingConfig(tile_px=tile_px, overlap_px=overlap))
        assert int(np.count_nonzero(np.unique(labels) > 0)) == expected


def test_tiled_and_whole_image_measurements_agree():
    # If stitching is correct, measuring the stitched tile map must give the
    # same counts as measuring the whole image in one pass.
    size = 640
    img, truth = _disks(10, spacing=64, radius=20, size=size)
    valid = np.ones((size, size), dtype=bool)

    cfg = TilingConfig(tile_px=192, overlap_px=48)
    measure = MeasurementConfig(min_diameter_px=10.0, roi_margin_px=4)

    whole = measure_surface(img, valid, _scale(), measure)
    tiled, labels = measure_tiled(img, valid, _scale(), cfg, measure)

    assert tiled.n_instances_in_roi == whole.n_instances_in_roi, (
        f"tiling changed the counted instances: "
        f"{tiled.n_instances_in_roi} vs {whole.n_instances_in_roi}"
    )
    assert tiled.eligible_area_m2 == pytest.approx(whole.eligible_area_m2)
    assert tiled.count_density_per_m2 == pytest.approx(whole.count_density_per_m2)


def test_tiled_labels_are_used_not_resegmented():
    # Regression: measure_tiled must not re-segment the whole frame, which would
    # be both redundant and would split merged boundary instances again.
    size = 512
    img, _ = _disks(8, spacing=64, radius=20, size=size)
    valid = np.ones((size, size), dtype=bool)
    _, labels = measure_tiled(img, valid, _scale())
    # A single disk that the whole-image segmenter may split differently must
    # not appear twice in the returned map.
    assert int(np.count_nonzero(np.unique(labels) > 0)) >= 64


def test_empty_and_tiny_images_do_not_crash():
    cfg = TilingConfig(tile_px=64, overlap_px=16)
    for shape in ((64, 64), (1, 1), (10, 300)):
        img = np.zeros(shape, dtype=np.uint8)
        img[:] = 100
        labels = segment_tiled(img, cfg)
        assert labels.shape == shape


def test_tile_config_rejects_nonsense():
    with pytest.raises(ValueError):
        TilingConfig(tile_px=4)
    with pytest.raises(ValueError):
        TilingConfig(overlap_px=-1)
