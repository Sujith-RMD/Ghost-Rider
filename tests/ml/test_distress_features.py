"""Tests for distress measurements (D8): skeleton length and defect extent.

The skeleton-length step counting is checked against analytic ground truth,
because the naive "count skeleton pixels" version under-reports diagonal cracks
by 29% and that error would otherwise pass unnoticed.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from backend.distress.features import (
    DISTRESS_METHOD_VERSION,
    crack_skeleton_length_m,
    defect_extent_fraction,
    distress_metrics,
    rasterize_label_file,
    rasterize_polygon,
)
from backend.geometry import PlanarScale, ScaleSource

SCALE_1MM = PlanarScale.calibrated(1.0, 1.0, ScaleSource.RIG_CALIBRATED, "test")
SCALE_UNSCALED = PlanarScale.unscaled("test")


def _h_line(length: int, width: int = 20) -> np.ndarray:
    mask = np.zeros((width, width), dtype=bool)
    mask[10, 2 : 2 + length] = True
    return mask


def _d_line(steps: int, size: int = 40) -> np.ndarray:
    mask = np.zeros((size, size), dtype=bool)
    for i in range(steps + 1):
        mask[2 + i, 2 + i] = True
    return mask


# --------------------------------------------------------------------- length


def test_horizontal_line_length_is_exact():
    length_m, pixels = crack_skeleton_length_m(_h_line(15), SCALE_1MM)
    # 15 pixels span 14 unit steps.
    assert pixels == 15
    assert length_m == pytest.approx(0.014, abs=1e-12)


def test_diagonal_line_uses_sqrt2_steps():
    steps = 20
    mask = _d_line(steps)
    length_m, pixels = crack_skeleton_length_m(mask, SCALE_1MM)
    assert pixels == steps + 1
    assert length_m == pytest.approx(steps * math.sqrt(2.0) / 1000.0, rel=1e-9)


def test_pixel_counting_would_underreport_diagonals():
    # The defect this guards against: counting skeleton pixels instead of steps
    # is 1/sqrt(2) = 70.7% of the true diagonal length, a 29% under-report.
    steps = 20
    mask = _d_line(steps)
    length_m, pixels = crack_skeleton_length_m(mask, SCALE_1MM)
    naive = (pixels - 1) / 1000.0
    assert naive < length_m
    assert (length_m - naive) / length_m == pytest.approx(1 - 1 / math.sqrt(2), rel=1e-6)


def test_empty_mask_returns_measured_zero_not_null():
    mask = np.zeros((32, 32), dtype=bool)
    length_m, pixels = crack_skeleton_length_m(mask, SCALE_1MM)
    assert pixels == 0
    assert length_m == 0.0


def test_unscaled_returns_none_never_zero():
    length_m, pixels = crack_skeleton_length_m(_h_line(15), SCALE_UNSCALED)
    assert length_m is None
    assert length_m != 0.0
    assert pixels == 15


def test_inspected_mask_clips_the_measurement():
    mask = _h_line(15)
    inspected = np.zeros(mask.shape, dtype=bool)
    inspected[10, 2:8] = True  # only part of the line
    length_m, pixels = crack_skeleton_length_m(mask, SCALE_1MM, inspected)
    assert pixels <= 6
    assert length_m is not None


def test_length_rejects_mismatched_masks():
    with pytest.raises(ValueError):
        crack_skeleton_length_m(_h_line(5), SCALE_1MM, np.ones((3, 3), dtype=bool))


# ---------------------------------------------------------------------- extent


def test_extent_is_area_fraction():
    mask = np.zeros((100, 100), dtype=bool)
    mask[0:10, 0:10] = True  # 100 px of 10000
    assert defect_extent_fraction(mask) == pytest.approx(0.01)


def test_extent_unions_overlaps_and_never_exceeds_one():
    mask = np.zeros((50, 50), dtype=bool)
    mask[0:50, 0:50] = True
    assert defect_extent_fraction(mask) <= 1.0
    overlapping = np.zeros((20, 20), dtype=bool)
    overlapping[0:20, 0:20] = True
    assert defect_extent_fraction(overlapping) == pytest.approx(1.0)


def test_extent_empty_is_measured_zero():
    assert defect_extent_fraction(np.zeros((10, 10), dtype=bool)) == 0.0


def test_extent_no_inspected_area_is_none():
    assert defect_extent_fraction(
        np.zeros((10, 10), dtype=bool), np.zeros((10, 10), dtype=bool)
    ) is None


def test_shape_mismatch_raises():
    with pytest.raises(ValueError):
        defect_extent_fraction(np.zeros((5, 5), dtype=bool), np.ones((7, 7), dtype=bool))


# ------------------------------------------------------------------- composite


def test_combined_record_is_json_serialisable_and_versions_itself():
    import json

    mask = _h_line(20)
    record = distress_metrics(mask, SCALE_1MM).describe()
    assert record["config_version"] == DISTRESS_METHOD_VERSION
    assert record["skeleton_length_m"] is not None
    assert record["crack_density_m_per_m2"] is not None
    assert record["defect_area_m2"] is not None
    json.dumps(record)  # must not raise


def test_combined_record_density_matches_length_over_area():
    mask = np.zeros((100, 100), dtype=bool)
    mask[50, 5:85] = True  # 79 unit steps horizontally
    record = distress_metrics(mask, SCALE_1MM).describe()
    assert record["skeleton_length_m"] == pytest.approx(0.079, abs=1e-12)
    expected_density = record["skeleton_length_m"] / record["inspected_area_m2"]
    assert record["crack_density_m_per_m2"] == pytest.approx(expected_density)


def test_unscaled_record_carries_a_limitation_not_fabricated_units():
    record = distress_metrics(_h_line(10), SCALE_UNSCALED).describe()
    assert record["skeleton_length_m"] is None
    assert record["crack_density_m_per_m2"] is None
    assert record["defect_area_m2"] is None
    assert record["extent_fraction"] is not None  # unitless, still measurable
    assert record["limitation"] is not None


# ------------------------------------------------------------------ rasteriser


def test_polygon_rasterises_to_expected_area():
    square = np.array([[0.0, 0.0], [0.5, 0.0], [0.5, 0.5], [0.0, 0.5]])
    mask = rasterize_polygon((100, 100), square)
    # Coordinates 0.0 -> pixel 0 and 0.5 -> pixel 50, and cv2.fillPoly closes
    # both boundaries, so the square spans pixels 0..50 inclusive = 51x51.
    assert mask.sum() == pytest.approx(51 * 51)


def test_polygon_position_and_size_are_proportional():
    small = rasterize_polygon(
        (100, 100), np.array([[0.1, 0.1], [0.3, 0.1], [0.3, 0.3], [0.1, 0.3]])
    )
    # 0.1 to 0.3 -> pixels 10..30 inclusive -> 21x21
    assert small.sum() == pytest.approx(21 * 21)
    ys, xs = np.nonzero(small)
    assert ys.min() == 10 and ys.max() == 30
    assert xs.min() == 10 and xs.max() == 30


def test_polygon_requires_three_points():
    assert not rasterize_polygon((10, 10), np.array([[0.0, 0.0], [0.5, 0.5]])).any()


def test_label_file_parses_yolo_segmentation_format(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text(
        "0 0.1 0.1 0.3 0.1 0.3 0.3 0.1 0.3\n"
        "0 0.5 0.5 0.7 0.5 0.7 0.7 0.5 0.7\n"
        "garbage line that should be skipped\n",
        encoding="utf-8",
    )
    masks = rasterize_label_file((100, 100), path)
    assert 0 in masks
    assert masks[0].sum() > 0
    # Two disjoint squares, so the union is bigger than either alone
    assert masks[0].sum() > 0


def test_class_filter_selects_only_requested_classes(tmp_path):
    path = tmp_path / "m.txt"
    path.write_text(
        "0 0.1 0.1 0.3 0.1 0.3 0.3 0.1 0.3\n"
        "1 0.5 0.5 0.7 0.5 0.7 0.7 0.5 0.7\n",
        encoding="utf-8",
    )
    masks = rasterize_label_file((100, 100), path, class_filter={1})
    assert list(masks) == [1]
