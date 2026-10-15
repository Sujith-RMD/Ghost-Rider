"""Arithmetic and policy regressions; synthetic fixtures are not road validation."""
import numpy as np
import pytest

from backend.aggregate.auto_annotation import auto_annotate_patch
from backend.aggregate.features import gap_statistics, particle_size_stats
from backend.aggregate.measurement import MeasurementConfig, measure_surface
from backend.geometry.plane import apply_homography
from backend.geometry.scale import PlanarScale, ScaleSource
from eval.aggregate_eval import evaluate, match_instances


def scale(sx=1, sy=1):
    return PlanarScale.calibrated(sx, sy, ScaleSource.SOURCE_CALIBRATED, "synthetic")


def bars():
    labels = np.zeros((60, 60), dtype=np.int32)
    labels[5:55, 5:15] = 1
    labels[5:55, 25:35] = 2
    return labels


def test_particle_sizes_select_roi_centroids_but_keep_full_instance_area():
    labels = np.zeros((20, 30), dtype=np.int32)
    labels[5:15, 2:12] = 1
    labels[5:15, 20:24] = 2
    roi = np.zeros_like(labels, dtype=bool)
    roi[:, 6:10] = True
    result = particle_size_stats(labels, scale(), roi)
    assert result["count_considered"] == 1
    assert result["diameter_px"]["median"] == pytest.approx(np.sqrt(400 / np.pi))


def test_metric_gap_uses_axis_scales_not_equal_area_scale():
    labels = bars()
    base = gap_statistics(labels, scale())
    horizontal = gap_statistics(labels, scale(2, 1))
    vertical = gap_statistics(labels.T, scale(2, 1))
    assert horizontal.median_mm == pytest.approx(base.median_px * 2)
    assert vertical.median_mm == pytest.approx(base.median_px)


def test_auto_annotation_uses_directional_metric_gap(monkeypatch):
    monkeypatch.setattr("backend.aggregate.auto_annotation.segment_aggregate", lambda *args: bars())
    with pytest.warns(UserWarning):
        result = auto_annotate_patch(bars(), scale(2, 1))
    assert result.gap_width_mm == pytest.approx(result.gap_width_px * 2)


def test_measurement_size_sample_matches_counting_roi():
    labels = np.zeros((30, 30), dtype=np.int32)
    labels[10:15, 10:15] = 1
    labels[0:2, 0:2] = 2
    result = measure_surface(labels, np.ones_like(labels, dtype=bool), scale(),
                             MeasurementConfig(min_diameter_px=0), labels=labels)
    assert result.n_instances_in_roi == result.particle_size["count_considered"] == 1


def test_sparse_instance_ids_are_not_phantom_objects():
    pred = np.array([[0, 1000000, 1000000]], dtype=np.int64)
    gt = np.array([[0, 37, 37]], dtype=np.int64)
    result = match_instances(pred, gt)
    assert (result["tp"], result["fp"], result["fn"]) == (1, 0, 0)
    assert result["matches"] == [{"pred": 1000000, "gt": 37, "iou": 1.0}]


def test_ignore_mask_applies_to_instance_and_count_evaluation():
    pred = np.array([[1, 1, 0, 2, 2]])
    gt = np.array([[1, 1, 0, 0, 0]])
    result = evaluate(pred, gt, ignore_mask=np.array([[0, 0, 0, 1, 1]], dtype=bool))
    assert result["instance"]["fp"] == 0
    assert result["count"]["absolute_error"] == 0


def test_threshold_zero_does_not_match_disjoint_instances():
    result = match_instances(np.array([[1, 0]]), np.array([[0, 1]]), 0)
    assert result["tp"] == 0


def test_instance_matching_maximizes_valid_matches_not_greedy_iou():
    pred = np.array([[1] * 10 + [2] * 4])
    gt = np.array([[1] * 6 + [2] * 4 + [1] * 4])
    assert match_instances(pred, gt, 0.25)["tp"] == 2


def test_homography_is_invariant_to_its_arbitrary_scalar():
    points = np.array([[2., 3.]])
    assert np.allclose(apply_homography(np.eye(3) * 1e-8, points), points)


def test_area_masks_are_restricted_to_observed_surface():
    labels = np.zeros((10, 10), dtype=np.int32)
    valid = np.zeros_like(labels, dtype=bool)
    valid[:5] = True
    result = measure_surface(labels, valid, scale(), MeasurementConfig(roi_margin_px=0),
                             ignore_mask=~valid, distress_mask=~valid, labels=labels)
    assert result.ignored_area_m2 == 0
    assert result.distress_area_m2 == 0
