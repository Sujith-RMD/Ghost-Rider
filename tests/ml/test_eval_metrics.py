"""Tests for the evaluation metric math.

Metric code is what turns a prediction into a reported number, so it is checked
against hand-computable cases (perfect, empty, disjoint, ignore, threshold) rather
than trusted. Written before the harness was run on any real data.
"""

from __future__ import annotations

import numpy as np
import pytest

from eval.dataset_audit import select_annotation_patches
from eval.aggregate_eval import (
    _select_h_within_tolerance,
    count_errors,
    evaluate,
    evaluate_synthetic_cases,
    make_synthetic_case,
    match_instances,
    semantic_scores,
)


# ---------------------------------------------------------------- pixel scores


def test_perfect_prediction_scores_one():
    gt = np.zeros((10, 10), dtype=bool)
    gt[2:5, 2:5] = True
    scores = semantic_scores(gt.copy(), gt)
    assert scores["f1"] == pytest.approx(1.0)
    assert scores["iou"] == pytest.approx(1.0)
    assert scores["precision"] == pytest.approx(1.0)
    assert scores["recall"] == pytest.approx(1.0)


def test_empty_prediction_scores_zero_recall():
    gt = np.zeros((10, 10), dtype=bool)
    gt[2:5, 2:5] = True
    scores = semantic_scores(np.zeros((10, 10), dtype=bool), gt)
    assert scores["recall"] == 0.0
    assert scores["f1"] == 0.0
    assert scores["fn"] == 9


def test_disjoint_prediction_scores_zero():
    gt = np.zeros((10, 10), dtype=bool)
    gt[0:3, 0:3] = True
    pred = np.zeros((10, 10), dtype=bool)
    pred[5:8, 5:8] = True
    scores = semantic_scores(pred, gt)
    assert scores["tp"] == 0
    assert scores["f1"] == 0.0


def test_half_overlap_has_expected_precision_and_recall():
    gt = np.zeros((4, 4), dtype=bool)
    gt[0:4, 0:2] = True  # 8 px
    pred = np.zeros((4, 4), dtype=bool)
    pred[0:4, 1:3] = True  # 8 px, overlap 4 px
    scores = semantic_scores(pred, gt)
    assert scores["tp"] == 4
    assert scores["precision"] == pytest.approx(0.5)
    assert scores["recall"] == pytest.approx(0.5)
    assert scores["f1"] == pytest.approx(0.5)
    assert scores["iou"] == pytest.approx(4 / 12)


def test_both_empty_scores_zero_not_one():
    empty = np.zeros((5, 5), dtype=bool)
    scores = semantic_scores(empty, empty)
    assert scores["f1"] == 0.0
    assert scores["iou"] == 0.0


def test_ignore_mask_removes_pixels_from_both_sides():
    gt = np.zeros((10, 10), dtype=bool)
    gt[0:5, :] = True
    pred = np.zeros((10, 10), dtype=bool)
    pred[0:5, :] = True
    # Marking the top half ignored must exclude it rather than scoring it as correct.
    ignore = np.zeros((10, 10), dtype=bool)
    ignore[0:5, :] = True
    scores = semantic_scores(pred, gt, ignore)
    assert scores["tp"] == 0
    assert scores["fn"] == 0
    assert scores["f1"] == 0.0


def test_shape_mismatch_rejected():
    with pytest.raises(ValueError):
        semantic_scores(np.zeros((4, 4), dtype=bool), np.zeros((5, 5), dtype=bool))
    with pytest.raises(ValueError):
        semantic_scores(
            np.zeros((4, 4), dtype=bool), np.zeros((4, 4), dtype=bool), np.zeros((3, 3), dtype=bool)
        )


# ------------------------------------------------------------- instance scores


def test_instance_perfect_match_is_f1_one():
    labels = np.zeros((20, 20), dtype=np.int32)
    labels[2:6, 2:6] = 1
    labels[10:14, 10:14] = 2
    scores = match_instances(labels, labels.copy())
    assert scores["tp"] == 2
    assert scores["fp"] == 0
    assert scores["fn"] == 0
    assert scores["f1"] == pytest.approx(1.0)


def test_one_merged_prediction_is_one_fp_and_one_fn_not_a_pass():
    # Two separate particles predicted as a single merged blob: a pooled IoU can
    # look only mildly wrong, so the instance score must show the miss.
    gt = np.zeros((20, 20), dtype=np.int32)
    gt[2:14, 2:8] = 1
    gt[2:14, 10:16] = 2
    pred = np.zeros((20, 20), dtype=np.int32)
    pred[2:14, 2:16] = 1
    scores = match_instances(pred, gt, iou_threshold=0.5)
    assert scores["tp"] == 0
    assert scores["fp"] == 1
    assert scores["fn"] == 2
    assert scores["f1"] == 0.0


def test_one_split_prediction_scores_two_false_alarms():
    # An *even* split gives each half IoU exactly 0.5, which matches at a 0.5
    # threshold (see test_instance_threshold_boundary_is_respected). To exercise
    # the penalty honestly the halves must fall below the threshold: each is
    # 60 px of a 144 px particle, so IoU 60/144 = 0.417.
    gt = np.zeros((20, 20), dtype=np.int32)
    gt[2:14, 2:14] = 1
    pred = np.zeros((20, 20), dtype=np.int32)
    pred[2:14, 2:7] = 1  # 12 x 5 = 60 px
    pred[2:14, 7:12] = 2  # 12 x 5 = 60 px
    scores = match_instances(pred, gt, iou_threshold=0.5)
    assert scores["tp"] == 0
    assert scores["fp"] == 2
    assert scores["fn"] == 1


def test_even_split_still_matches_at_the_threshold():
    # Documents the boundary deliberately: a 50/50 split yields IoU exactly 0.5,
    # so it is credited at a 0.5 threshold. This is why the split penalty test
    # above uses unequal halves.
    gt = np.zeros((20, 20), dtype=np.int32)
    gt[2:14, 2:14] = 1
    pred = np.zeros((20, 20), dtype=np.int32)
    pred[2:14, 2:8] = 1
    pred[2:14, 8:14] = 2
    scores = match_instances(pred, gt, iou_threshold=0.5)
    assert scores["tp"] == 1
    assert scores["matches"][0]["iou"] == pytest.approx(0.5)


def test_instance_no_predictions_is_all_misses():
    gt = np.zeros((10, 10), dtype=np.int32)
    gt[2:5, 2:5] = 1
    gt[6:9, 6:9] = 2
    scores = match_instances(np.zeros((10, 10), dtype=np.int32), gt)
    assert scores["tp"] == 0
    assert scores["fn"] == 2
    assert scores["precision"] == 0.0


def test_instance_threshold_boundary_is_respected():
    gt = np.zeros((10, 10), dtype=np.int32)
    gt[0:4, 0:4] = 1  # 16 px
    pred = np.zeros((10, 10), dtype=np.int32)
    pred[0:2, 0:4] = 1  # 8 px overlap, IoU 8/16 = 0.5
    assert match_instances(pred, gt, iou_threshold=0.5)["tp"] == 1
    assert match_instances(pred, gt, iou_threshold=0.51)["tp"] == 0


def test_invalid_iou_threshold_rejected():
    labels = np.zeros((4, 4), dtype=np.int32)
    with pytest.raises(ValueError):
        match_instances(labels, labels, iou_threshold=1.5)


def test_greedy_matching_does_not_reuse_a_prediction():
    # A single large prediction overlapping two ground-truth particles must only
    # ever be credited once.
    gt = np.zeros((20, 20), dtype=np.int32)
    gt[0:10, 0:10] = 1
    gt[0:10, 10:20] = 2
    pred = np.zeros((20, 20), dtype=np.int32)
    pred[0:10, 0:20] = 1
    scores = match_instances(pred, gt, iou_threshold=0.5)
    assert scores["tp"] <= 1
    assert len(scores["matches"]) <= 1


# ---------------------------------------------------------------- count errors


def test_count_error_reports_signed_and_absolute():
    gt = np.zeros((20, 20), dtype=np.int32)
    gt[0:5, 0:5] = 1
    gt[10:15, 10:15] = 2
    pred = np.zeros((20, 20), dtype=np.int32)
    pred[0:5, 0:5] = 1
    errors = count_errors(pred, gt)
    assert errors["n_gt"] == 2
    assert errors["n_pred"] == 1
    assert errors["signed_error"] == -1
    assert errors["absolute_error"] == 1
    assert errors["relative_error"] == pytest.approx(0.5)


def test_count_error_is_null_relative_when_no_truth():
    empty = np.zeros((5, 5), dtype=np.int32)
    errors = count_errors(empty, empty)
    assert errors["relative_error"] is None


# -------------------------------------------------------------- full evaluate


def test_evaluate_returns_all_three_metric_families():
    gt = np.zeros((20, 20), dtype=np.int32)
    gt[2:8, 2:8] = 1
    result = evaluate(gt.copy(), gt)
    assert result["pixel"]["f1"] == pytest.approx(1.0)
    assert result["instance"]["f1"] == pytest.approx(1.0)
    assert result["count"]["signed_error"] == 0


# ---------------------------------------------------------- synthetic fixture


def test_synthetic_case_provides_exact_ground_truth():
    case = make_synthetic_case(seed=1, width=128, height=128, n_particles=20)
    assert case["image"].shape == (128, 128, 3)
    assert case["gt_labels"].shape == (128, 128)
    assert case["n_gt"] == int(np.count_nonzero(np.unique(case["gt_labels"]) > 0))
    assert case["n_gt"] > 0
    # Ground-truth labels must be contiguous so counts are honest.
    positives = np.unique(case["gt_labels"][case["gt_labels"] > 0])
    assert list(positives) == list(range(1, len(positives) + 1))


def test_synthetic_case_is_reproducible_from_its_seed():
    first = make_synthetic_case(seed=7, width=96, height=96, n_particles=12)
    second = make_synthetic_case(seed=7, width=96, height=96, n_particles=12)
    assert np.array_equal(first["gt_labels"], second["gt_labels"])
    assert np.array_equal(first["image"], second["image"])


def test_synthetic_ground_truth_has_no_overlapping_labels():
    case = make_synthetic_case(seed=3, width=160, height=160, n_particles=40, touching_fraction=0.8)
    # Each pixel carries at most one label by construction.
    labels = case["gt_labels"]
    assert labels.min() >= 0


# ---------------------------------- fixture honesty: is the boundary visible?
#
# A fixture that draws touching chips at identical intensity demands a split no
# human could make, and then reports the inevitable failure as a model defect.
# Final plan section 6.3 says an unresolvable boundary is an `ignore` case, not a
# miss, so the fixture has to state which of the two it is building.


def _case(scenario: str) -> dict:
    return make_synthetic_case(
        seed=1, width=256, height=256, n_particles=25, scenario=scenario
    )


def test_separated_scenario_has_no_contacts():
    assert _case("separated")["contact_pairs"] == 0


def test_touching_scenario_contacts_chips_and_draws_a_visible_boundary():
    case = _case("touching")
    assert case["contact_pairs"] > 0
    assert int(case["seam_mask"].sum()) > 0
    # Contrast between chip interior and the joint drawn between touching chips.
    assert case["boundary_contrast"] >= 40.0


def test_merged_scenario_has_contacts_but_no_visible_boundary():
    case = _case("merged")
    assert case["contact_pairs"] > 0
    assert int(case["seam_mask"].sum()) == 0
    assert case["boundary_contrast"] < 15.0


def test_merged_scenario_reports_no_instance_score_because_truth_is_not_resolvable():
    report = evaluate_synthetic_cases(n_cases=3, seed=1, scenario="merged")
    assert report["instance_gt_resolvable"] is False
    assert report["median_instance_f1"] is None
    # The foreground question is still answerable, so pixel scores remain.
    assert report["median_pixel_f1"] is not None


def test_touching_scenario_reports_instance_scores():
    report = evaluate_synthetic_cases(n_cases=2, seed=1, scenario="touching")
    assert report["instance_gt_resolvable"] is True
    assert report["median_instance_f1"] is not None


# --------------------------------------------- marker selection rule (pure logic)


def test_selection_prefers_the_smallest_h_within_tolerance():
    # Selection may not be the argmax: a large h degenerates towards one particle
    # per connected region, which under-splits real merges. The rule therefore
    # takes the smallest h that is indistinguishable from the best.
    scores = [(0.2, 0.800, 0), (0.5, 0.850, -2), (0.9, 0.877, -5)]
    assert _select_h_within_tolerance(scores, 0.05) == 0.5
    assert _select_h_within_tolerance(scores, 0.02) == 0.9
    assert _select_h_within_tolerance(scores, 0.5) == 0.2


def test_selection_rejects_an_empty_or_impossible_request():
    with pytest.raises(ValueError):
        _select_h_within_tolerance([], 0.05)


# ------------------------------------- patch selection for the human review sheet


def test_annotation_patches_are_distinct_in_bounds_and_deterministic():
    # Final plan section 5.1 step 4: 10 patches, double-annotated. Both annotators
    # must see the *same* patches, so the choice has to be reproducible.
    first = select_annotation_patches(n_images=100, count=10, crop_px=256, image_size=(512, 512), seed=0)
    second = select_annotation_patches(n_images=100, count=10, crop_px=256, image_size=(512, 512), seed=0)
    assert first == second
    assert len(first) == 10
    assert len({entry["image_index"] for entry in first}) == 10
    for entry in first:
        assert 0 <= entry["top"] <= 512 - 256
        assert 0 <= entry["left"] <= 512 - 256


def test_annotation_patch_locations_change_with_the_seed():
    a = select_annotation_patches(n_images=40, count=5, crop_px=128, image_size=(256, 256), seed=0)
    b = select_annotation_patches(n_images=40, count=5, crop_px=128, image_size=(256, 256), seed=9)
    assert a != b


def test_annotation_patch_request_is_validated():
    with pytest.raises(ValueError):
        select_annotation_patches(n_images=10, count=0)
    with pytest.raises(ValueError):
        select_annotation_patches(n_images=10, count=11)
    with pytest.raises(ValueError):
        select_annotation_patches(n_images=10, count=1, crop_px=999, image_size=(64, 64))
