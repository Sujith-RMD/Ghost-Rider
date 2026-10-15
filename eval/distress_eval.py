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
    if not files and gt_dir is None:
        raise ValueError(f"no .txt label files found in {labels_dir}")

    if gt_dir is not None and not Path(gt_dir).is_dir():
        raise NotADirectoryError(gt_dir)
    gt_files = _label_files(Path(gt_dir)) if gt_dir is not None else []
    if gt_dir is not None and not gt_files:
        raise ValueError(f"no .txt ground-truth files found in {gt_dir}")
    gt_map = {p.name: p for p in gt_files}
    prediction_names = {p.name for p in files}
    unpredicted = sorted(set(gt_map) - prediction_names)
    # YOLO commonly omits label files for images with no detections. Include
    # these as empty predictions rather than dropping all missed positives.
    files = sorted(set(files) | {labels_dir / name for name in unpredicted})

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
        masks = rasterize_label_file(shape, path, class_filter={0}) if path.exists() else {}
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

        if gt.any():
            instance_ious.append(
                _best_overlap_iou(_instances(prediction), _instances(gt))
            )

    unlabelled.extend(unpredicted)

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


def evaluate_manifest(
    manifest_path: str | Path,
    predictions: dict[str, np.ndarray],
) -> dict:
    """Score a directory of predicted raster masks against a raster GT manifest.

    ``predictions`` maps ``sample_id`` to a boolean mask. Works in raster space
    so a thin crack is never re-encoded as a polygon (which measurably
    over-fills by 2.41x). Returns pixel metrics plus per-sample areas, because
    defect extent is what the quality index eventually consumes.

    ``manifest_path`` is written by ``training.prepare_crkhw100_test.py``.
    """
    data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    return score_raster_manifest(data, predictions, manifest_name=str(manifest_path))


def score_raster_manifest(data: dict, predictions: dict[str, np.ndarray],
                          manifest_name: str | None = None) -> dict:
    """Score complete raster predictions; missing inference is not background."""
    samples = data.get("samples", [])
    ids = [s["sample_id"] for s in samples]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate sample_id in manifest")
    missing_ids = sorted(set(ids) - predictions.keys())
    if missing_ids:
        raise ValueError(f"missing predictions: {missing_ids}")
    scale_note = data.get("negative_note", "")

    pixel_ious: list[float] = []
    precisions: list[float] = []
    recalls: list[float] = []
    dices: list[float] = []
    extents_gt: list[float] = []
    extents_pred: list[float] = []
    missing: list[str] = []
    rows: list[dict] = []
    n_negatives = 0

    for sample in samples:
        sample_id = sample["sample_id"]
        gt = _read_raster_mask(sample["gt_mask"])
        pred = np.asarray(predictions[sample_id])
        if pred.dtype != np.bool_:
            raise ValueError(f"prediction {sample_id} must be a boolean mask")
        if pred.shape != gt.shape:
            raise ValueError(
                f"prediction {sample_id} shape {pred.shape} != GT shape {gt.shape}"
            )

        inter = int(np.count_nonzero(pred & gt))
        union = int(np.count_nonzero(pred | gt))
        pixel_ious.append(inter / union if union else 1.0)
        pred_px = int(np.count_nonzero(pred))
        gt_px = int(np.count_nonzero(gt))
        precisions.append(inter / pred_px if pred_px else 1.0)
        recalls.append(inter / gt_px if gt_px else 1.0)
        dices.append(
            2.0 * inter / (pred_px + gt_px) if (pred_px + gt_px) else 1.0
        )
        extents_gt.append(gt_px / gt.size)
        extents_pred.append(pred_px / pred.size)
        n_negatives += int(gt_px == 0)
        rows.append({
            "sample_id": sample_id, "gt_pixels": gt_px, "pred_pixels": pred_px,
            "gt_fraction": gt_px / gt.size, "pred_fraction": pred_px / pred.size,
            "pixel_iou": pixel_ious[-1], "precision": precisions[-1],
            "recall": recalls[-1], "dice": dices[-1],
        })

    return {
        "manifest": manifest_name,
        "role": data.get("role"),
        "n_scored": len(pixel_ious),
        "n_missing_predictions": len(missing),
        "missing": missing,
        "pixel_iou_mean": _safe_mean(pixel_ious),
        "pixel_precision_mean": _safe_mean(precisions),
        "pixel_recall_mean": _safe_mean(recalls),
        "dice_mean": _safe_mean(dices),
        "dice_p10": float(np.percentile(dices, 10)) if dices else None,
        "dice_p90": float(np.percentile(dices, 90)) if dices else None,
        "samples": rows,
        "extent_gt_mean": _safe_mean(extents_gt),
        "extent_pred_mean": _safe_mean(extents_pred),
        "extent_ratio_pred_over_gt": (
            _safe_mean(extents_pred) / _safe_mean(extents_gt)
            if extents_gt and _safe_mean(extents_gt)
            else None
        ),
        "scale_note": data.get("scale_note"),
        "negative_caveat": scale_note,
        "false_alarm_measurable": n_negatives > 0,
        "n_negatives_scored": n_negatives,
        "metric_convention": "Per-image macro means; empty precision/recall denominator scores 1; both-empty IoU/Dice score 1",
        "caveat": scale_note,
    }


def _read_raster_mask(path: str | Path) -> np.ndarray:
    mask = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if mask is None:
        raise ValueError(f"could not decode mask {path}")
    if mask.ndim == 3:
        mask = mask[..., 0]
    return mask > 127


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", default=None, help="directory of predicted .txt labels")
    parser.add_argument("--images", default=None, help="directory of paired images")
    parser.add_argument("--gt", default=None, help="directory of ground-truth .txt labels")
    parser.add_argument(
        "--manifest",
        default=None,
        help="raster GT manifest from training.prepare_crkhw100_test.py",
    )
    parser.add_argument(
        "--pred-masks",
        default=None,
        help="directory of predicted raster masks, named <sample_id>.<ext>",
    )
    parser.add_argument("--out", default=None, help="write the JSON report here")
    args = parser.parse_args(argv)

    if not args.labels and not args.manifest:
        parser.error("give either --labels (YOLO format) or --manifest (raster GT)")

    if args.manifest:
        if not args.pred_masks:
            parser.error("--manifest requires --pred-masks")
        pred_dir = Path(args.pred_masks)
        predictions = {}
        for path in sorted(pred_dir.iterdir()):
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".tif"}:
                predictions[path.stem] = _read_raster_mask(path)
        payload = evaluate_manifest(args.manifest, predictions)
    else:
        payload = evaluate(args.labels, args.images, args.gt).describe()

    text = json.dumps(payload, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
