"""Additive distress summaries; only explicit group IDs define resampling units."""
from __future__ import annotations

import numpy as np

MIN_BOOTSTRAP_GROUPS = 10
BOOTSTRAP_REPLICATES = 1000
BOOTSTRAP_SEED = 0


def mask_row(sample_id, pred, gt, group_id=None):
    if gt.ndim != 2 or gt.size == 0 or pred.ndim != 2 or pred.size == 0:
        raise ValueError(f"sample {sample_id} masks must be non-empty 2D arrays")
    tp = int(np.count_nonzero(pred & gt))
    fp = int(np.count_nonzero(pred & ~gt))
    fn = int(np.count_nonzero(~pred & gt))
    tn = int(gt.size - tp - fp - fn)
    return dict(sample_id=sample_id, group_id=group_id, tp=tp, fp=fp, fn=fn, tn=tn)


def _ratio(n, d):
    return float(n / d) if d else None


def summarize(rows):
    tp, fp, fn, tn = (sum(r[k] for r in rows) for k in ("tp", "fp", "fn", "tn"))
    positive = [r for r in rows if r["tp"] + r["fn"] > 0]
    negative = [r for r in rows if r["tp"] + r["fn"] == 0]
    alarms = sum(r["fp"] > 0 for r in negative)
    misses = sum(r["tp"] + r["fp"] == 0 for r in positive)
    zero_overlap = sum(r["tp"] == 0 for r in positive)
    macro = {}
    for name, numerator, denominator in (
        ("pixel_iou_mean", lambda r: r["tp"], lambda r: r["tp"] + r["fp"] + r["fn"]),
        ("pixel_precision_mean", lambda r: r["tp"], lambda r: r["tp"] + r["fp"]),
        ("pixel_recall_mean", lambda r: r["tp"], lambda r: r["tp"] + r["fn"]),
        ("dice_mean", lambda r: 2 * r["tp"], lambda r: 2 * r["tp"] + r["fp"] + r["fn"]),
    ):
        macro[name] = float(np.mean([
            numerator(r) / denominator(r) if denominator(r) else 1.0 for r in rows
        ])) if rows else None
    return {
        **macro,
        "n_scored": len(rows), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "pixel_iou_micro": _ratio(tp, tp + fp + fn),
        "pixel_precision_micro": _ratio(tp, tp + fp),
        "pixel_recall_micro": _ratio(tp, tp + fn),
        "dice_micro": _ratio(2 * tp, 2 * tp + fp + fn),
        "dice_positive_mean": float(np.mean([
            2 * r["tp"] / (2 * r["tp"] + r["fp"] + r["fn"])
            for r in positive])) if positive else None,
        "n_positive_frames": len(positive), "n_negative_frames": len(negative),
        "n_false_alarm_frames": alarms, "n_missed_positive_frames": misses,
        "negative_frame_false_alarm_rate": _ratio(alarms, len(negative)),
        "missed_positive_frame_rate": _ratio(misses, len(positive)),
        "n_zero_overlap_positive_frames": zero_overlap,
        "zero_overlap_positive_frame_rate": _ratio(zero_overlap, len(positive)),
        "zero_overlap_convention": "GT-positive frames with TP=0 / all GT-positive frames; includes empty and spatially disjoint predictions, unlike the no-foreground missed_positive_frame_rate",
    }


def reporting_metrics(rows):
    result = summarize(rows)
    groups = {}
    missing = []
    for row in rows:
        group = row.get("group_id")
        if not isinstance(group, str) or not group.strip():
            missing.append(row["sample_id"])
        else:
            groups.setdefault(group, []).append(row)
    result["groups"] = {g: summarize(groups[g]) for g in sorted(groups)}
    result["n_groups"] = len(groups)
    result["missing_group_ids"] = missing
    result["group_metadata_complete"] = not missing
    metrics = ("pixel_iou_micro", "pixel_precision_micro", "pixel_recall_micro",
               "dice_micro", "dice_positive_mean", "negative_frame_false_alarm_rate",
               "missed_positive_frame_rate", "zero_overlap_positive_frame_rate")
    intervals = {}
    ordered = [groups[g] for g in sorted(groups)]
    for metric in metrics:
        support = sum(summarize(group)[metric] is not None for group in ordered)
        reason = ("missing_group_metadata" if missing else
                  "insufficient_supporting_groups" if support < MIN_BOOTSTRAP_GROUPS else None)
        entry = {"low": None, "high": None, "supporting_groups": support, "reason": reason}
        if reason is None:
            rng = np.random.default_rng(BOOTSTRAP_SEED)
            values = []
            for _ in range(BOOTSTRAP_REPLICATES):
                draw = rng.integers(0, len(ordered), size=len(ordered))
                value = summarize([r for i in draw for r in ordered[int(i)]])[metric]
                if value is not None:
                    values.append(value)
            if len(values) == BOOTSTRAP_REPLICATES:
                entry["low"], entry["high"] = map(float, np.percentile(values, [2.5, 97.5]))
            else:
                entry["reason"] = "undefined_bootstrap_replicates"
        intervals[metric] = entry
    result["group_bootstrap"] = {
        "confidence_level": 0.95, "replicates": BOOTSTRAP_REPLICATES,
        "seed": BOOTSTRAP_SEED, "minimum_supporting_groups": MIN_BOOTSTRAP_GROUPS,
        "method": "percentile; resample explicit groups with replacement, retain all member frames",
        "caveat": "group_id must identify independent parent/site units; independence is not inferred or verified",
        "intervals": intervals,
    }
    result["additional_metric_convention"] = (
        "Micro ratios use pooled pixel counts; undefined denominators are null. "
        "Positive-only Dice includes GT-positive frames only. False alarms are any "
        "predicted foreground on GT-negative frames / GT-negative frames; missed "
        "positive frames have no predicted foreground / GT-positive frames (not spatial misses)."
    )
    return result
