"""Fixed trivial mask baselines, not trained-model or Indian acceptance results.

These baselines expose foreground prevalence and empty-mask metric conventions.
No threshold, model or preprocessing is fitted or selected using this report.
Run ``python -m eval.distress_baselines --manifest MANIFEST --out REPORT``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from eval.distress_eval import _read_raster_mask, score_raster_manifest


def evaluate_baselines(manifest_path: str | Path) -> dict:
    path = Path(manifest_path)
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    samples = data.get("samples", [])
    if not samples:
        raise ValueError("manifest requires samples")
    if len({s["sample_id"] for s in samples}) != len(samples):
        raise ValueError("duplicate sample_id in manifest")
    masks = {s["sample_id"]: _read_raster_mask(s["gt_mask"]) for s in samples}
    mask_hashes = {s["sample_id"]: hashlib.sha256(Path(s["gt_mask"]).read_bytes()).hexdigest()
                   for s in samples}
    for sample in samples:
        expected = sample.get("gt_sha256")
        if expected is not None and expected != mask_hashes[sample["sample_id"]]:
            raise ValueError(f"GT hash mismatch: {sample['sample_id']}")
    reports = {}
    for name, fill in (("always_background", False), ("always_foreground", True)):
        predictions = {sid: np.full(mask.shape, fill, dtype=bool) for sid, mask in masks.items()}
        reports[name] = score_raster_manifest(data, predictions, str(path))
    total = sum(mask.size for mask in masks.values())
    positive = sum(int(mask.sum()) for mask in masks.values())
    return {
        "purpose": "fixed_trivial_baseline_diagnostics", "trained_model_evaluated": False,
        "manifest": str(path), "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "gt_mask_sha256": mask_hashes,
        "n_samples": len(samples), "foreground_pixels": positive, "valid_pixels": total,
        "foreground_fraction_micro": positive / total if total else None,
        "baseline_reports": reports,
        "limitations": [
            "No predictions from a trained model, no fitting, and no threshold selection.",
            "Baseline results establish a comparison floor on the supplied labels, not useful road detection.",
            "All-foreground pixel recall of 1 is trivial and is not a model achievement.",
            "Always-background precision can be 1 under legacy empty-denominator conventions despite missed defects; read recall, positive-only Dice and pooled counts.",
            "Missing independent group metadata suppresses group intervals; dataset names or filename order do not prove independence.",
            "No verified physical units or Indian/live acceptance claim is made.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    report = evaluate_baselines(args.manifest)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"n_samples": report["n_samples"],
                      "foreground_fraction_micro": report["foreground_fraction_micro"],
                      "baselines": {name: {key: value[key] for key in
                          ("dice_micro", "dice_positive_mean", "pixel_recall_micro", "negative_frame_false_alarm_rate")}
                          for name, value in report["baseline_reports"].items()}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
