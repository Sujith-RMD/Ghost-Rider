"""Mocked inference only: no model downloads or real accuracy claims."""
import hashlib
import json
import sys
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from training import evaluate_crosssource as evaluator


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    weights = tmp_path / "weights.pt"
    weights.write_bytes(b"mock checkpoint bytes")
    samples = []
    for i in range(2):
        folder = tmp_path / str(i)
        folder.mkdir()
        image, gt = folder / "same.png", folder / "gt.png"
        assert cv2.imwrite(str(image), np.zeros((2, 2, 3), np.uint8))
        assert cv2.imwrite(str(gt), np.eye(2, dtype=np.uint8) * 255)
        samples.append({"sample_id": f"explicit-{i}", "image": str(image), "gt_mask": str(gt)})
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"samples": samples}), encoding="utf-8")
    calls = []

    class FakeYOLO:
        def __init__(self, path):
            calls.append(("load", path))

        def predict(self, **kwargs):
            calls.append(("predict", kwargs))
            raster = np.eye(2, dtype=float)[None]
            return [SimpleNamespace(orig_shape=(2, 2), speed={"inference": 4.0},
                                    masks=SimpleNamespace(data=SimpleNamespace(
                                        cpu=lambda: SimpleNamespace(numpy=lambda: raster))))]

    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=FakeYOLO))
    return weights, manifest, samples, calls


def test_actual_hashes_mapping_confidence_and_timing(inputs, monkeypatch):
    weights, manifest, samples, calls = inputs
    # Load=2s; sample calls=3s and 5s; total=12s, including inter-call overhead.
    ticks = iter([0., 2., 3., 6., 7., 12., 12.])
    monkeypatch.setattr(evaluator.time, "perf_counter", lambda: next(ticks))
    report = evaluator.run_inference(weights, manifest, .42)
    run = report["inference_run"]
    assert run["weights_sha256"] == hashlib.sha256(weights.read_bytes()).hexdigest()
    assert run["manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert run["confidence"] == .42
    assert run["sample_images"] == {s["sample_id"]: s["image"] for s in samples}
    assert [s["sample_id"] for s in report["samples"]] == ["explicit-0", "explicit-1"]
    assert report["dice_mean"] == 1
    assert calls[1][1]["conf"] == .42
    assert calls[1][1]["retina_masks"] is True
    timing = run["timing"]
    assert timing["model_load_seconds"] == 2
    assert timing["elapsed_seconds"] == 12
    assert timing["wall_p50_seconds"] == 4
    assert timing["wall_p95_seconds"] == pytest.approx(4.9)
    assert [r["model_inference_seconds"] for r in timing["per_sample"]] == [.004, .004]
    assert "CPU mask" in timing["scope"]
    assert "not wall time" in timing["model_only_scope"]
    assert run["library_versions"]["numpy"] == np.__version__
    assert "torch" in run["library_versions"]
    assert run["saved_predictions"] is None


def test_save_masks_roundtrip_and_reject_existing_directory(inputs, tmp_path):
    weights, manifest, samples, calls = inputs
    destination = tmp_path / "predictions"
    report = evaluator.run_inference(weights, manifest, save_predictions=destination)
    assert set(p.name for p in destination.iterdir()) == {"explicit-0.png", "explicit-1.png"}
    for path in report["inference_run"]["saved_predictions"].values():
        assert np.array_equal(cv2.imread(path, 0), np.eye(2, dtype=np.uint8) * 255)
    before = len(calls)
    with pytest.raises(FileExistsError):
        evaluator.run_inference(weights, manifest, save_predictions=destination)
    assert len(calls) == before


@pytest.mark.parametrize("sample_id", ["../escape", "/absolute", "a/b", "a\\b", "CON", "nul.txt", "LPT1", "a.", "", "a:b"])
def test_unsafe_ids_fail_before_model(inputs, sample_id):
    weights, manifest, samples, calls = inputs
    samples[0]["sample_id"] = sample_id
    manifest.write_text(json.dumps({"samples": samples}))
    with pytest.raises(ValueError, match="unsafe sample_id"):
        evaluator.run_inference(weights, manifest)
    assert not calls


@pytest.mark.parametrize("duplicate", ["explicit-0", "EXPLICIT-0"])
def test_duplicate_ids_rejected(inputs, duplicate):
    weights, manifest, samples, calls = inputs
    samples[1]["sample_id"] = duplicate
    manifest.write_text(json.dumps({"samples": samples}))
    with pytest.raises(ValueError, match="duplicate or case-colliding"):
        evaluator.run_inference(weights, manifest)
    assert not calls


def test_legacy_predict_masks_rejects_duplicate_stems(inputs):
    weights, manifest, samples, calls = inputs
    with pytest.raises(ValueError, match="duplicate image stems"):
        evaluator.predict_masks(weights, [s["image"] for s in samples], .25)
    assert not calls
    result = evaluator.predict_masks(weights, [samples[0]["image"]], .25)
    assert list(result) == ["same"]
    assert result["same"].dtype == np.bool_


def test_missing_local_weights_never_loads_model(inputs):
    weights, manifest, samples, calls = inputs
    weights.unlink()
    with pytest.raises(ValueError, match="existing local file"):
        evaluator.run_inference(weights, manifest)
    assert not calls


@pytest.mark.parametrize("conf", [-.1, 1.1, float("nan"), float("inf")])
def test_invalid_confidence(inputs, conf):
    weights, manifest, samples, calls = inputs
    with pytest.raises(ValueError, match="confidence"):
        evaluator.run_inference(weights, manifest, conf)
    assert not calls


def test_cli_confidence_and_optional_saving(inputs, tmp_path):
    weights, manifest, samples, calls = inputs
    out, destination = tmp_path / "report.json", tmp_path / "saved"
    assert evaluator.main(["--weights", str(weights), "--manifest", str(manifest),
                           "--conf", ".61", "--out", str(out),
                           "--save-predictions", str(destination)]) == 0
    report = json.loads(out.read_text())
    assert report["inference_run"]["confidence"] == .61
    assert destination.is_dir()


def test_weights_changed_during_inference_is_rejected(inputs, monkeypatch):
    weights, manifest, samples, calls = inputs
    original = evaluator._predict_samples
    def mutate(*args):
        result = original(*args)
        weights.write_bytes(b"changed")
        return result
    monkeypatch.setattr(evaluator, "_predict_samples", mutate)
    with pytest.raises(ValueError, match="weights changed"):
        evaluator.run_inference(weights, manifest)
