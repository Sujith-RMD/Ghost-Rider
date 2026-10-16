"""India distress detection baseline (task tracker E10 / I12).

Owned by the ML role (``docs/ML_ROLE.md`` section 1).

This is the second of two deliberately separate distress models. The split is not
accidental:

| | Crack-Seg model | This model |
|---|---|---|
| Source | foreign | **India** |
| Label | polygons (precise area) | **boxes only** |
| Resolution | 416x416 close-up | 720x720 dashcam-style oblique |
| Feeds | defect-area measurement | the **India claim** |

Final plan 4.2 is explicit that RDD2022 "ships bounding boxes; precise segmentation
needs manual masks", and that "freeze an Indian test subset before annotation-driven
training". Both are honoured here: the box format is kept as boxes, and the split was
frozen by ``training.prepare_india_distress.py`` before any model saw it.

Box-to-mask conversion was measured at 2.41x area over-fill and rejected, so that
step is not performed.

Usage (Colab)::

    python -m training.train_india_detection --data-root data/external/rdd2022_india
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

MODEL_DEFAULT = "yolov8n.pt"
CLASS_NAMES = [
    "alligator crack",
    "block crack",
    "longitudinal crack",
    "other corruption",
    "pothole",
    "repair",
    "transverse crack",
]


def write_yolo_labels(data_root: Path, out_dir: Path, records: list[dict]) -> Path:
    """Write YOLO detection labels for the frozen train/dev split.

    Negative images get an **empty** label file, which is how YOLO represents an
    image with no objects. Deleting them instead would silently destroy the
    negative class, and negatives are the entire reason this dataset matters.
    """
    import yaml

    for split in ("train", "dev"):
        (out_dir / "labels" / split).mkdir(parents=True, exist_ok=True)
        (out_dir / "images" / split).mkdir(parents=True, exist_ok=True)

    src_images = data_root / "images"
    for record in records:
        split = record["split"]
        height = float(record["height"])
        width = float(record["width"])
        lines = []
        for box in record["boxes"]:
            if box["class_title"] not in CLASS_NAMES:
                continue
            class_id = CLASS_NAMES.index(box["class_title"])
            x_c = (box["x_min"] + box["x_max"]) / 2.0 / width
            y_c = (box["y_min"] + box["y_max"]) / 2.0 / height
            w = (box["x_max"] - box["x_min"]) / width
            h = (box["y_max"] - box["y_min"]) / height
            # Clamp: a box touching the edge can round slightly outside.
            x_c = min(max(x_c, 0.0), 1.0)
            y_c = min(max(y_c, 0.0), 1.0)
            w = min(max(w, 0.0), 1.0)
            h = min(max(h, 0.0), 1.0)
            lines.append(
                "%d %.10f %.10f %.10f %.10f" % (class_id, x_c, y_c, w, h)
            )
        (out_dir / "labels" / split / (record["sample_id"] + ".txt")).write_text(
            "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
        )
        image = src_images / (record["sample_id"] + ".jpg")
        if image.exists():
            target = out_dir / "images" / split / image.name
            if not target.exists():
                target.write_bytes(image.read_bytes())

    yaml_path = out_dir / "rdd2022_india.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "path": str(out_dir.resolve()),
                "train": "images/train",
                "val": "images/dev",
                "test": "images/dev",
                "names": {i: n for i, n in enumerate(CLASS_NAMES)},
                "nc": len(CLASS_NAMES),
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return yaml_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", default="data/external/rdd2022_india")
    parser.add_argument("--work-dir", default="data/external/rdd2022_india_yolo")
    parser.add_argument("--model", default=MODEL_DEFAULT)
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--imgsz", type=int, default=720)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--device", default="0")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--project", default="runs/roadsight")
    parser.add_argument("--name", default="india_detection")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args(argv)

    data_root = Path(args.data_root)
    manifest_path = data_root / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(
            f"manifest not found at {manifest_path}; run "
            "python -m training.prepare_india_distress first"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = manifest["records"]

    work_dir = Path(args.work_dir)
    yaml_path = write_yolo_labels(data_root, work_dir, records)
    print("wrote", yaml_path)

    if args.prepare_only:
        print(json.dumps({
            "yaml": str(yaml_path),
            "n_train": sum(1 for r in records if r["split"] == "train"),
            "n_dev": sum(1 for r in records if r["split"] == "dev"),
            "n_negative": sum(1 for r in records if r["is_negative"]),
        }, indent=2))
        return 0

    try:
        from ultralytics import YOLO
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("ultralytics is not installed. In Colab: pip install ultralytics") from exc

    model = YOLO(args.model)
    results = model.train(
        data=str(yaml_path),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        seed=args.seed,
        project=args.project,
        name=args.name,
        exist_ok=True,
        deterministic=True,
        fliplr=0.5,
        flipud=0.0,
        degrees=0.0,
        scale=0.2,
        mosaic=0.0,
    )

    summary = {
        "model": args.model,
        "yaml": str(yaml_path),
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "seed": args.seed,
        "save_dir": str(getattr(results, "save_dir", "")),
        "n_train": sum(1 for r in records if r["split"] == "train"),
        "n_dev": sum(1 for r in records if r["split"] == "dev"),
        "n_negatives": manifest["n_negatives"],
        "negative_rate": manifest["negative_rate"],
        "note": (
            "Boxes only: this is localisation, not area measurement. Validate with "
            "eval/distress_eval.py on the dev split; report mAP50 and the "
            "false-positive rate on the 51% negative images, which is the first "
            "time this project can measure it at all."
        ),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
