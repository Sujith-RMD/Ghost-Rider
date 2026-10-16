"""Trivial baselines should expose, not disguise, class imbalance."""
import hashlib
import json

import cv2
import numpy as np
import pytest

from eval.distress_baselines import evaluate_baselines, main


def write_manifest(tmp_path):
    mask = tmp_path / "gt.png"
    assert cv2.imwrite(str(mask), np.array([[255, 0], [0, 0]], dtype=np.uint8))
    manifest = tmp_path / "manifest.json"
    data = {"samples": [{"sample_id": "positive", "gt_mask": str(mask),
                         "gt_sha256": hashlib.sha256(mask.read_bytes()).hexdigest()}]}
    manifest.write_text(json.dumps(data), encoding="utf-8")
    return manifest


def test_fixed_baselines_cannot_be_claimed_as_model_accuracy(tmp_path):
    report = evaluate_baselines(write_manifest(tmp_path))
    assert not report["trained_model_evaluated"]
    assert report["foreground_fraction_micro"] == .25
    bg = report["baseline_reports"]["always_background"]
    fg = report["baseline_reports"]["always_foreground"]
    assert bg["dice_micro"] == 0
    assert bg["dice_positive_mean"] == 0
    assert bg["pixel_precision_mean"] == 1  # legacy undefined-denominator convention
    assert bg["pixel_precision_micro"] is None
    assert bg["pixel_recall_micro"] == 0
    assert fg["dice_micro"] == .4
    assert fg["pixel_recall_micro"] == 1
    assert fg["negative_frame_false_alarm_rate"] is None
    assert fg["group_bootstrap"]["intervals"]["dice_micro"]["low"] is None


def test_changed_ground_truth_hash_fails(tmp_path):
    manifest = write_manifest(tmp_path)
    data = json.loads(manifest.read_text())
    data["samples"][0]["gt_sha256"] = "wrong"
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="hash mismatch"):
        evaluate_baselines(manifest)


def test_duplicate_samples_fail(tmp_path):
    manifest = write_manifest(tmp_path)
    data = json.loads(manifest.read_text())
    data["samples"] *= 2
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="duplicate"):
        evaluate_baselines(manifest)


def test_cli_saves_report(tmp_path):
    manifest = write_manifest(tmp_path)
    output = tmp_path / "reports" / "baselines.json"
    assert main(["--manifest", str(manifest), "--out", str(output)]) == 0
    assert json.loads(output.read_text())["purpose"] == "fixed_trivial_baseline_diagnostics"
