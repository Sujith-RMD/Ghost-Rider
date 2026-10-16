"""Grouped dimensional/count error reports; source agreement is not live calibration.

Run ``python -m eval.measurement_eval INPUT.json --out REPORT.json``.
Input contains evidence_type (annotation_source_scale, physical_live, synthetic),
metric (count, gap, length), unit (count, px, mm, m), and samples with sample_id,
group_id, truth, prediction (null if suppressed), and optional null_reason.
Group IDs must identify independent parent/site units; this tool cannot verify them.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

EVIDENCE_TYPES = ("annotation_source_scale", "physical_live", "synthetic")
UNITS = {"count": {"count"}, "gap": {"px", "mm", "m"}, "length": {"px", "mm", "m"}}


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return float(value)


def _summary(rows):
    available = [r for r in rows if r["prediction"] is not None]
    errors = np.asarray([r["prediction"] - r["truth"] for r in available], dtype=float)
    relative = np.asarray([abs(r["prediction"] - r["truth"]) / r["truth"]
                           for r in available if r["truth"] > 0], dtype=float)
    return {
        "n_total": len(rows), "n_scored": len(available),
        "n_suppressed": len(rows) - len(available),
        "scored_fraction": len(available) / len(rows) if rows else None,
        "suppressed_fraction": 1 - len(available) / len(rows) if rows else None,
        "bias": float(errors.mean()) if errors.size else None,
        "mae": float(np.abs(errors).mean()) if errors.size else None,
        "median_absolute_error": float(np.median(np.abs(errors))) if errors.size else None,
        "p95_absolute_error": float(np.percentile(np.abs(errors), 95)) if errors.size else None,
        "median_absolute_relative_error": float(np.median(relative)) if relative.size else None,
        "p95_absolute_relative_error": float(np.percentile(relative, 95)) if relative.size else None,
        "n_relative_scored": int(relative.size),
        "n_zero_truth_scored": sum(r["truth"] == 0 for r in available),
    }


def evaluate_measurements(data: dict, *, seed: int = 0, replicates: int = 1000) -> dict:
    """Report errors with cluster bootstrap, including all suppressed observations."""
    if data.get("evidence_type") not in EVIDENCE_TYPES:
        raise ValueError("explicit evidence_type is required")
    metric, unit = data.get("metric"), data.get("unit")
    if metric not in UNITS or unit not in UNITS[metric]:
        raise ValueError("incompatible metric/unit")
    if data["evidence_type"] == "physical_live" and unit == "px":
        raise ValueError("physical_live error requires physical units or counts")
    if type(seed) is not int or type(replicates) is not int or replicates < 100:
        raise ValueError("seed must be an integer and replicates >= 100")
    samples = data.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ValueError("samples must be a nonempty list")
    rows, ids, groups, reasons = [], set(), {}, {}
    for sample in samples:
        sid, group = sample.get("sample_id"), sample.get("group_id")
        if not isinstance(sid, str) or not sid.strip() or sid in ids:
            raise ValueError("sample_id must be unique and nonempty")
        ids.add(sid)
        if not isinstance(group, str) or not group.strip():
            raise ValueError(f"{sid}: explicit independent group_id required")
        truth = _number(sample.get("truth"), f"{sid}: truth")
        if "prediction" not in sample:
            raise ValueError(f"{sid}: prediction required (use null for suppression)")
        prediction = sample["prediction"]
        if prediction is None:
            reason = sample.get("null_reason")
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError(f"{sid}: suppression requires null_reason")
            reasons[reason] = reasons.get(reason, 0) + 1
        else:
            prediction = _number(prediction, f"{sid}: prediction")
        if metric == "count" and (not truth.is_integer() or prediction is not None and not prediction.is_integer()):
            raise ValueError("count measurements must be integers")
        row = dict(sample_id=sid, group_id=group, truth=truth, prediction=prediction)
        rows.append(row)
        groups.setdefault(group, []).append(row)
    summary = _summary(rows)
    per_group = {g: _summary(groups[g]) for g in sorted(groups)}
    interval_metrics = ("mae", "bias", "median_absolute_relative_error", "suppressed_fraction")
    intervals = {}
    ordered = [groups[g] for g in sorted(groups)]
    for name in interval_metrics:
        support = sum(per_group[g][name] is not None for g in per_group)
        entry = dict(low=None, high=None, supporting_groups=support,
                     reason="insufficient_supporting_groups" if support < 10 else None)
        if support >= 10:
            rng = np.random.default_rng(seed)
            values = [_summary([r for i in rng.integers(0, len(ordered), len(ordered))
                                for r in ordered[int(i)]])[name] for _ in range(replicates)]
            if all(v is not None for v in values):
                entry["low"], entry["high"] = map(float, np.percentile(values, [2.5, 97.5]))
            else:
                entry["reason"] = "undefined_bootstrap_replicates"
        intervals[name] = entry
    return {
        "report_version": "measurement-error-v1", "evidence_type": data["evidence_type"],
        "metric": metric, "unit": unit, "summary": summary, "n_groups": len(groups),
        "groups": per_group, "suppression_reasons": reasons,
        "group_bootstrap": {"confidence_level": .95, "seed": seed, "replicates": replicates,
                            "minimum_supporting_groups": 10, "intervals": intervals},
        "samples": rows,
        "limitations": ["Errors describe scored observations; suppression remains visible and is not imputed as zero.",
                        "Relative errors exclude zero truth; absolute errors retain those cases.",
                        "Bootstrap resamples explicit groups with all members, not individual crops. Group independence is caller-supplied, not verified.",
                        "Ten supporting groups is a reporting guard, not proof of sufficient sample size.",
                        "Source-scale annotation agreement and synthetic checks do not establish physical live-camera accuracy."],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    report = evaluate_measurements(json.loads(args.input.read_text(encoding="utf-8")), seed=args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("evidence_type", "metric", "unit", "summary", "n_groups")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
