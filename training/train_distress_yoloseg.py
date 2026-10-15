"""YOLO segmentation baseline for the distress engine (task tracker **E8**).

Owned by the ML role (``docs/ML_ROLE.md`` section 1).

This is the **fast, working baseline**, not the plan-compliant challenger. Final
plan section 8.1 names a small U-Net with a ResNet18 encoder for E8; YOLO
segmentation is used here first because Crack-Seg already ships YOLO polygons, so
no format conversion is needed and the whole thing runs in minutes on a free
Colab T4. A U-Net challenger should be compared against this baseline and kept
only if it beats it on unseen parents (final plan 8.1).

Why polygons are acceptable here but not for CRKWH100: Crack-Seg's ground truth
was authored as polygons, so no re-encoding happens. Converting a *raster* crack
mask to a polygon measurably over-fills by 2.41x, which is why CRKWH100 stays in
raster space (see ``training/prepare_crkhw100_test.py``).

Usage (local or Colab)::

    python -m training.train_distress_yoloseg \\
        --data data/external/crack-seg \\
        --epochs 60 --imgsz 416 --batch 16 --device 0

    # CPU-only laptop, sanity check that the pipeline runs:
    python -m training.train_distress_yoloseg --data <path> --epochs 2 --device cpu --model yolov8n-seg.pt
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

EPOCHS_DEFAULT = 60
MODEL_DEFAULT = "yolov8n-seg.pt"
DATA_YAML_NAME = "roadsight_distress.yaml"


def build_data_yaml(data_root: Path, out_dir: Path) -> Path:
    """Write a YOLO data yaml keeping train, development and test separate.

    These exported splits do not by themselves establish parent-group isolation.
    CRKWH100 is an additional foreign diagnostic, not a replacement for India.
    """
    import yaml  # ultralytics dependency

    images_dir = data_root / "images"
    train_dir = images_dir / "train"
    val_dir = images_dir / "val"
    for required in (train_dir, val_dir):
        if not required.is_dir():
            raise NotADirectoryError(f"expected {required}")

    out_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = out_dir / DATA_YAML_NAME
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "path": str(data_root.resolve()),
                "train": "images/train",
                "val": "images/val",
                "test": "images/test",
                "names": {0: "crack"},
                "nc": 1,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return yaml_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, help="crack-seg dataset root")
    parser.add_argument("--model", default=MODEL_DEFAULT)
    parser.add_argument("--epochs", type=int, default=EPOCHS_DEFAULT)
    parser.add_argument("--imgsz", type=int, default=416)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", default="0", help="0, cpu, or mps")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--project", default="runs/roadsight")
    parser.add_argument("--name", default="distress_yoloseg")
    args = parser.parse_args(argv)

    try:
        from ultralytics import YOLO
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "ultralytics is not installed. In Colab: pip install ultralytics"
        ) from exc

    data_root = Path(args.data)
    yaml_path = build_data_yaml(data_root, Path("data/manifests"))

    model = YOLO(args.model)
    results = model.train(
        data=str(yaml_path),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        seed=args.seed,
        workers=args.workers,
        project=args.project,
        name=args.name,
        exist_ok=False,
        # Determinism and modest augmentation only: any transform that changes
        # geometry changes the metric meaning of a mask (final plan 8.3).
        deterministic=True,
        fliplr=0.5,
        flipud=0.0,
        degrees=0.0,
        scale=0.2,
        mosaic=0.0,
    )

    save_dir = Path(results.save_dir) if hasattr(results, "save_dir") else None
    summary = {
        "model": args.model,
        "data_yaml": str(yaml_path),
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "batch": args.batch,
        "device": args.device,
        "seed": args.seed,
        "save_dir": str(save_dir) if save_dir else None,
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "note": (
            "Trained on Crack-Seg train; val used for checkpoint selection. "
            "Group isolation requires a separate lineage audit. Evaluate on the cross-source "
            "CRKWH100 set with eval/distress_eval.py --manifest. That set "
            "carries no negative images: pixel precision/recall and overlap "
            "are measurable, but intact-image false-alarm rate is not."
        ),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
