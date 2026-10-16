"""Hand-computable software checks, not evidence of road/model accuracy."""
import json

from unittest.mock import patch

import numpy as np
import pytest

from eval.distress_eval import evaluate, score_raster_manifest
from eval.group_metrics import mask_row, reporting_metrics


def fixture_report():
    masks = {
        "partial": np.array([[1, 1], [0, 0]], dtype=bool),
        "miss": np.ones((2, 2), dtype=bool),
        "alarm": np.zeros((2, 2), dtype=bool),
        "quiet": np.zeros((2, 2), dtype=bool),
    }
    predictions = {
        "partial": np.array([[1, 0], [1, 0]], dtype=bool),
        "miss": np.zeros((2, 2), dtype=bool),
        "alarm": np.eye(2, dtype=bool),
        "quiet": np.zeros((2, 2), dtype=bool),
    }
    manifest = {"role": "software_validation", "samples": [
        {"sample_id": k, "gt_mask": k, "group_id": "synthetic-" + str(i // 2)}
        for i, k in enumerate(masks)
    ]}
    with patch("eval.distress_eval._read_raster_mask", side_effect=masks.__getitem__):
        report = score_raster_manifest(manifest, predictions)
    return {"purpose": "software_validation", "synthetic": True,
            "real_accuracy_claim": False,
            "fixture": "Four hand-constructed 2x2 masks; two explicit synthetic groups",
            "report": report}


def test_hand_computed_pooled_and_frame_denominators():
    report = fixture_report()["report"]
    assert [report[k] for k in ("tp", "fp", "fn", "tn")] == [1, 3, 5, 7]
    assert report["dice_micro"] == pytest.approx(2 / 10)
    assert report["pixel_iou_micro"] == pytest.approx(1 / 9)
    assert report["pixel_precision_micro"] == .25
    assert report["pixel_recall_micro"] == pytest.approx(1 / 6)
    assert report["dice_mean"] == .375
    assert report["dice_positive_mean"] == .25
    assert report["n_negative_frames"] == report["n_positive_frames"] == 2
    assert report["n_false_alarm_frames"] == report["n_missed_positive_frames"] == 1
    assert report["negative_frame_false_alarm_rate"] == .5
    assert report["missed_positive_frame_rate"] == .5
    assert report["groups"]["synthetic-0"]["dice_positive_mean"] == .25
    assert report["n_groups"] == 2
    assert all(i["low"] is None for i in report["group_bootstrap"]["intervals"].values())


def test_unequal_sizes_pool_pixels_not_frame_scores():
    rows = [mask_row("small", np.ones((1, 1), bool), np.ones((1, 1), bool)),
            mask_row("large", np.zeros((10, 10), bool), np.ones((10, 10), bool))]
    report = reporting_metrics(rows)
    assert report["dice_mean"] == .5
    assert report["dice_micro"] == pytest.approx(2 / 102)
    assert report["missing_group_ids"] == ["small", "large"]


@pytest.mark.parametrize("positive", [True, False])
def test_single_class_denominators_are_null(positive):
    mask = np.full((2, 2), positive, dtype=bool)
    report = reporting_metrics([mask_row("a", mask, mask)])
    if positive:
        assert report["negative_frame_false_alarm_rate"] is None
        assert report["missed_positive_frame_rate"] == 0
    else:
        assert report["missed_positive_frame_rate"] is None
        assert report["dice_positive_mean"] is None
        assert report["dice_micro"] is None
        assert report["dice_mean"] == 1
        assert report["negative_frame_false_alarm_rate"] == 0


def test_group_bootstrap_is_deterministic_and_preserves_clusters():
    yes, no = np.ones((1, 1), bool), np.zeros((1, 1), bool)
    rows = [mask_row(str(i), yes if i % 2 else no, yes, f"site-{i}") for i in range(10)]
    report = reporting_metrics(rows)
    assert report == reporting_metrics(list(reversed(rows)))
    interval = report["group_bootstrap"]["intervals"]["dice_positive_mean"]
    assert interval["reason"] is None
    assert 0 <= interval["low"] < .5 < interval["high"] <= 1
    # Identical sibling duplication leaves the cluster-bootstrap statistic unchanged.
    assert reporting_metrics(rows * 3)["group_bootstrap"] == report["group_bootstrap"]
    for row in rows:
        row["group_id"] = "one-parent"
    assert reporting_metrics(rows * 20)["group_bootstrap"]["intervals"]["dice_micro"]["low"] is None


def test_missing_metadata_suppresses_intervals_and_ids_are_not_groups():
    yes = np.ones((1, 1), bool)
    rows = [mask_row(str(i), yes, yes, f"site-{i}") for i in range(10)]
    rows.append(mask_row("unknown", yes, yes, " "))
    report = reporting_metrics(rows)
    assert report["missing_group_ids"] == ["unknown"]
    assert not report["group_metadata_complete"]
    assert report["group_bootstrap"]["intervals"]["dice_micro"]["reason"] == "missing_group_metadata"
    rows.pop()
    assert reporting_metrics(rows)["group_bootstrap"]["intervals"]["negative_frame_false_alarm_rate"]["reason"] == "insufficient_supporting_groups"


def test_empty_manifest_rejected():
    with pytest.raises(ValueError, match="at least one sample"):
        score_raster_manifest({"samples": []}, {})


@pytest.mark.parametrize("shape", [(0, 2), (2, 0), (0, 0), (2,), (2, 2, 1)])
def test_invalid_mask_dimensions_rejected(shape):
    mask = np.zeros(shape, bool)
    with patch("eval.distress_eval._read_raster_mask", return_value=mask):
        with pytest.raises(ValueError, match="non-empty 2D"):
            score_raster_manifest({"samples": [{"sample_id": "a", "gt_mask": "unused"}]}, {"a": mask})


def test_yolo_additive_reporting_and_no_invented_groups(tmp_path):
    pred, gt = tmp_path / "pred", tmp_path / "gt"
    pred.mkdir()
    gt.mkdir()
    (gt / "miss.txt").write_text("0 0.1 0.1 0.5 0.1 0.5 0.5 0.1 0.5\n")
    report = evaluate(pred, gt_dir=gt).describe()
    assert report["dice_mean"] == 0
    metrics = report["metric_reporting"]
    assert metrics["fn"] > 0
    assert metrics["missed_positive_frame_rate"] == 1
    assert metrics["missing_group_ids"] == ["miss"]


def test_synthetic_fixture_is_deterministic_and_strict_json():
    # Reports are ignored generated artifacts, not a fresh-checkout test fixture.
    report = fixture_report()
    assert report == fixture_report()
    assert json.loads(json.dumps(report, allow_nan=False)) == report
    assert report["purpose"] == "software_validation"
    assert report["real_accuracy_claim"] is False


def test_zero_overlap_is_distinct_from_no_foreground_miss():
    gt = np.array([[1, 0]], dtype=bool)
    disjoint = np.array([[0, 1]], dtype=bool)
    empty = np.zeros_like(gt)
    rows = [mask_row("disjoint", disjoint, gt, "a"),
            mask_row("empty", empty, gt, "b"),
            mask_row("hit", gt, gt, "c")]
    report = reporting_metrics(rows)
    assert report["n_zero_overlap_positive_frames"] == 2
    assert report["zero_overlap_positive_frame_rate"] == pytest.approx(2 / 3)
    assert report["missed_positive_frame_rate"] == pytest.approx(1 / 3)
    assert report["groups"]["a"]["zero_overlap_positive_frame_rate"] == 1
    assert reporting_metrics([mask_row("negative", empty, empty)])["zero_overlap_positive_frame_rate"] is None
    assert report["group_bootstrap"]["intervals"]["zero_overlap_positive_frame_rate"]["low"] is None
