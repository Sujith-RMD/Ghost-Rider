"""Distress evaluation harness (task tracker **I16**).

Run a distress mask predictor against the Crack-Seg test split and report
pixel and instance metrics, or run the reference (ground-truth) masks to
establish the ceiling and the label distribution.

Usage::

    python -m eval.distress_eval --labels data/external/crack-seg/labels/test
    python -m eval.distress_eval --labels ./pred --gt data/external/crack-seg/labels/test

The harness works on **label files**, not images, so any predictor that emits
YOLO segmentation polygons can be scored by dropping them in a directory.
Ground truth is never rewritten.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path

import cv2
import numpy as np

from backend.distress.features import (
    DistressMetrics,
    distress_metrics,
    rasterize_label_file,
)
from backend.geometry import PlanarScale, ScaleSource

UNSCALED = PlanarScale.unscaled("crack-seg: 416x416 pre-export resize, GSD unknown")


@dataclass
class DistressReport:
    """Per-split distress metrics plus aggregate statistics."""

    n_images: int
    n_with_distress: int
    n_empty: int
    extent_mean: float | None
    extent_median: float | None
    extent_p90: float | None
    extent_max: float | None
    mask_pixel_mean: float | None
    skeleton_pixel_mean: float | None
    scale_note: str
    # filled only when ground truth is supplied
    pixel_iou_mean: float | None = None
    pixel_precision_mean: float | None = None
    pixel_recall_mean: float | None = None
    dice_mean: float | None = None
    instance_best_match_iou_mean: float | None = None
    unlabelled_gt_images: list[str] | None = None

    def describe(self) -> dict:
        return asdict(self)


def _image_shape(images_dir: Path, label_path: Path, fallback=(416, 416)):
    """Read the paired image to get the true rasterisation shape."""
    candidates = [
        images_dir / label_path.with_suffix(".jpg").name,
        images_dir / label_path.with_suffix(".png").name,
    ]
    for candidate in candidates:
        if candidate.exists():
            img = cv2.imread(str(candidate))
            if img is not None:
                return img.shape[:2]
    return fallback


def _label_files(labels_dir: Path) -> list[Path]:
    return sorted(labels_dir.glob("*.txt"))


def _mask_from(labels_dir: Path, images_dir: Path, path: Path) -> np.ndarray:
    shape = _image_shape(images_dir, path)
    masks = rasterize_label_file(shape, path, class_filter={0})
    return masks.get(0, np.zeros(shape, dtype=bool))


def _safe_mean(values: list[float]) -> float | None:
    if not values:
        return None
    return float(np.mean(values))


def evaluate(
    labels_dir: str | Path,
    images_dir: str | Path | None = None,
    gt_dir: str | Path | None = None,
) -> DistressReport:
    """Score a directory of YOLO segmentation labels against optional ground truth."""
    labels_dir = Path(labels_dir)
    if not labels_dir.is_dir():
        raise NotADirectoryError(labels_dir)

    # Label dirs are conventionally `<root>/labels/<split>` and images
    # `<root>/images/<split>`; only the images directory is needed for shape.
    if images_dir is not None:
        images_dir = Path(images_dir)
    elif labels_dir.parent.name == "labels":
        images_dir = labels_dir.parent.parent / "images" / labels_dir.name
    else:
        images_dir = labels_dir

    files = _label_files(labels_dir)
    if not files:
        raise ValueError(f"no .txt label files found in {labels_dir}")

    gt_files = _label_files(Path(gt_dir)) if gt_dir is not None else []
    gt_map = {p.name: p for p in gt_files}

    extents: list[float] = []
    mask_pixels: list[int] = []
    skeleton_pixels: list[int] = []
    ious: list[float] = []
    precisions: list[float] = []
    recalls: list[float] = []
    dices: list[float] = []
    instance_ious: list[float] = []
    unlabelled: list[str] = []

    for path in files:
        shape = _image_shape(images_dir, path)
        masks = rasterize_label_file(shape, path, class_filter={0})
        prediction = masks.get(0, np.zeros(shape, dtype=bool))
        record: DistressMetrics = distress_metrics(prediction, UNSCALED)
        if record.extent_fraction is not None:
            extents.append(record.extent_fraction)
        mask_pixels.append(record.mask_pixels)
        skeleton_pixels.append(record.skeleton_pixels)

        gt_path = gt_map.get(path.name)
        if gt_path is None:
            continue
        gt_masks = rasterize_label_file(shape, gt_path, class_filter={0})
        gt = gt_masks.get(0, np.zeros(shape, dtype=bool))
        if not gt.any() and prediction.any():
            # Prediction claims distress where none is labelled. That is a real
            # false positive, not a missing file.
            ious.append(0.0)
            precisions.append(0.0)
            recalls.append(0.0)
            dices.append(0.0)
            continue

        inter = int(np.count_nonzero(prediction & gt))
        union = int(np.count_nonzero(prediction | gt))
        iou = inter / union if union else 1.0
        ious.append(iou)
        precision = inter / int(np.count_nonzero(prediction)) if prediction.any() else 1.0
        recall = inter / int(np.count_nonzero(gt)) if gt.any() else 1.0
        precisions.append(precision)
        recalls.append(recall)
        gt_pixels = int(np.count_nonzero(gt))
        pred_pixels = int(np.count_nonzero(prediction))
        if (gt_pixels + pred_pixels) > 0:
            dices.append(2.0 * inter / (gt_pixels + pred_pixels))
        else:
            # Both empty: nothing to find, nothing falsely found.
            dices.append(1.0)

        if prediction.any() and gt.any():
            instance_ious.append(
                _best_overlap_iou(_instances(prediction), _instances(gt))
            )

    for name in gt_map:
        if name not in {p.name for p in files}:
            unlabelled.append(name)

    ext = np.asarray(extents) if extents else None
    return DistressReport(
        n_images=len(files),
        n_with_distress=int(np.count_nonzero([m > 0 for m in mask_pixels])),
        n_empty=sum(1 for m in mask_pixels if m == 0),
        extent_mean=_safe_mean(extents),
        extent_median=float(np.median(ext)) if ext is not None and ext.size else None,
        extent_p90=float(np.percentile(ext, 90)) if ext is not None and ext.size else None,
        extent_max=float(ext.max()) if ext is not None and ext.size else None,
        mask_pixel_mean=_safe_mean([float(v) for v in mask_pixels]),
        skeleton_pixel_mean=_safe_mean([float(v) for v in skeleton_pixels]),
        scale_note="unscaled: Crack-Seg is 416x416 with unknown resize history, so no metric length or area is reported",
        pixel_iou_mean=_safe_mean(ious),
        pixel_precision_mean=_safe_mean(precisions),
        pixel_recall_mean=_safe_mean(recalls),
        dice_mean=_safe_mean(dices),
        instance_best_match_iou_mean=_safe_mean(instance_ious),
        unlabelled_gt_images=unlabelled,
    )


def _instances(mask: np.ndarray) -> list[np.ndarray]:
    count, labels = cv2.connectedComponents(mask.astype(np.uint8), 8)
    return [labels == i for i in range(1, count)]


def _best_overlap_iou(pred: list[np.ndarray], gt: list[np.ndarray]) -> float:
    """IoU of each GT instance against its best-overlapping prediction, averaged."""
    scores: list[float] = []
    for target in gt:
        best = 0.0
        for candidate in pred:
            inter = np.count_nonzero(candidate & target)
            union = np.count_nonzero(candidate | target)
            if union:
                best = max(best, inter / union)
        scores.append(best)
    return _safe_mean(scores) or 0.0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", required=True, help="directory of predicted .txt labels")
    parser.add_argument("--images", default=None, help="directory of paired images")
    parser.add_argument("--gt", default=None, help="directory of ground-truth .txt labels")
    parser.add_argument("--out", default=None, help="write the JSON report here")
    args = parser.parse_args(argv)

    report = evaluate(args.labels, args.images, args.gt)
    payload = report.describe()
    text = json.dumps(payload, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
