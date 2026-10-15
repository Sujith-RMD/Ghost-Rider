"""Focused regressions from the distress implementation review."""
import json
import sys
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from backend.distress.features import crack_skeleton_length_m
from backend.geometry import PlanarScale, ScaleSource
from eval.distress_eval import evaluate, evaluate_manifest
from training.evaluate_crosssource import predict_masks, score
from training.prepare_crkhw100_test import build
from training.train_distress_yoloseg import build_data_yaml


def raster_manifest(tmp_path, masks):
    samples = []
    for i, mask in enumerate(masks):
        path = tmp_path / f"gt{i}.png"
        assert cv2.imwrite(str(path), mask.astype(np.uint8) * 255)
        samples.append({"sample_id": str(i), "gt_mask": str(path),
                        "crack_fraction": 0.999})  # deliberately stale metadata
    return {"samples": samples, "n_negatives": 999}


@pytest.mark.parametrize("direction, expected", [("h", .018), ("v", .027), ("d", 9 * np.hypot(2, 3) / 1000)])
def test_anisotropic_skeleton_uses_each_axis(direction, expected):
    mask = np.zeros((20, 20), dtype=bool)
    if direction == "h":
        mask[5, 3:13] = True
    elif direction == "v":
        mask[3:13, 5] = True
    else:
        mask[np.arange(3, 13), np.arange(3, 13)] = True
    scale = PlanarScale.calibrated(2, 3, ScaleSource.RIG_CALIBRATED, "test")
    assert crack_skeleton_length_m(mask, scale)[0] == pytest.approx(expected)


def test_crosssource_preserves_native_raster_holes(tmp_path, monkeypatch):
    native = np.ones((1, 8, 8), dtype=float)
    native[:, 2:6, 2:6] = 0
    tensor = SimpleNamespace(cpu=lambda: SimpleNamespace(numpy=lambda: native))
    result = SimpleNamespace(orig_shape=(8, 8), masks=SimpleNamespace(data=tensor))
    class FakeYOLO:
        def __init__(self, weights):
            pass
        def predict(self, **kwargs):
            assert kwargs["retina_masks"]
            return [result]
    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=FakeYOLO))
    pred = predict_masks(tmp_path / "weights.pt", [tmp_path / "sample.png"], .25)
    assert np.array_equal(pred["sample"], native[0] > .5)


def test_raster_scorers_agree_and_compute_p90_and_actual_extent(tmp_path):
    gt = np.eye(8, dtype=bool)
    manifest = raster_manifest(tmp_path, [gt, gt])
    predictions = {"0": gt, "1": np.zeros_like(gt)}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    direct = evaluate_manifest(path, predictions)
    cross = score(manifest, predictions)
    assert direct["dice_mean"] == cross["dice_mean"] == .5
    assert cross["dice_p10"] == pytest.approx(.1)
    assert cross["dice_p90"] == pytest.approx(.9)
    assert cross["extent_gt_mean"] == .125
    assert not cross["false_alarm_measurable"]
    assert len(cross["samples"]) == 2


def test_raster_missing_or_nonboolean_predictions_rejected(tmp_path):
    gt = np.eye(8, dtype=bool)
    manifest = raster_manifest(tmp_path, [gt])
    with pytest.raises(ValueError, match="missing predictions"):
        score(manifest, {})
    with pytest.raises(ValueError, match="boolean"):
        score(manifest, {"0": gt.astype(np.uint8) * 255})


def test_absent_yolo_detections_count_as_misses(tmp_path):
    pred = tmp_path / "pred"
    gt = tmp_path / "gt"
    pred.mkdir()
    gt.mkdir()
    (gt / "miss.txt").write_text("0 0.1 0.1 0.5 0.1 0.5 0.5 0.1 0.5\n")
    report = evaluate(pred, gt_dir=gt)
    assert report.n_images == 1
    assert report.dice_mean == 0
    assert report.pixel_recall_mean == 0
    assert report.instance_best_match_iou_mean == 0
    assert report.unlabelled_gt_images == ["miss.txt"]


def test_preparation_rejects_misaligned_or_missing_gt(tmp_path):
    images, gt = tmp_path / "images", tmp_path / "gt"
    images.mkdir()
    gt.mkdir()
    cv2.imwrite(str(images / "a.png"), np.zeros((8, 8, 3), np.uint8))
    cv2.imwrite(str(gt / "a.png"), np.zeros((4, 4), np.uint8))
    with pytest.raises(ValueError, match="shape mismatch"):
        build(images, gt, tmp_path / "manifest.json")
    cv2.imwrite(str(gt / "a.png"), np.zeros((8, 8), np.uint8))
    cv2.imwrite(str(images / "b.png"), np.zeros((8, 8, 3), np.uint8))
    with pytest.raises(ValueError, match="without ground truth"):
        build(images, gt, tmp_path / "manifest.json")


def test_training_yaml_keeps_development_separate(tmp_path):
    yaml = pytest.importorskip("yaml")
    for split in ("train", "val"):
        (tmp_path / "data" / "images" / split).mkdir(parents=True)
    path = build_data_yaml(tmp_path / "data", tmp_path / "out")
    data = yaml.safe_load(path.read_text())
    assert data["train"] == "images/train"
    assert data["val"] == "images/val"
