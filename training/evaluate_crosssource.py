"""Score a trained distress model on the CRKWH100 cross-source test set.

Owned by the ML role (``docs/ML_ROLE.md`` section 1).

Runs a trained YOLO segmentation model over the CRKWH100 images, reuses the
*exact* mask logic from the manifest self-check so no conversion bug can creep
between the two paths, then writes per-sample metrics and the aggregate report.

Usage::

    python -m training.evaluate_crosssource \\
        --weights runs/roadsight/distress_yoloseg/weights/best.pt \\
        --manifest data/manifests/crkhw100_test.json \\
        --out reports/ml/crosssource_r1.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from eval.distress_eval import score_raster_manifest


def load_manifest(manifest_path: Path) -> dict:
    return json.loads(Path(manifest_path).read_text(encoding="utf-8"))


def read_mask(path: Path) -> np.ndarray:
    mask = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if mask is None:
        raise ValueError(f"could not decode {path}")
    if mask.ndim == 3:
        mask = mask[..., 0]
    return mask


def predict_masks(weights: Path, image_paths: list[Path], conf: float):
    """Run a YOLO segmentation model and return per-image boolean masks."""
    from ultralytics import YOLO

    model = YOLO(str(weights))
    predictions = {}
    for image_path in image_paths:
        result = model.predict(
            source=str(image_path),
            conf=conf,
            retina_masks=True,
            verbose=False,
        )[0]
        height, width = result.orig_shape[:2]
        combined = np.zeros((height, width), dtype=bool)
        masks = getattr(result, "masks", None)
        if masks is not None:
            # retina_masks supplies original-resolution raster masks. Preserve
            # holes and thin branches rather than filling exterior polygons.
            raster = masks.data.cpu().numpy()
            if raster.ndim != 3 or raster.shape[1:] != (height, width):
                raise ValueError(f"unexpected model mask shape {raster.shape}")
            combined = np.any(raster > 0.5, axis=0)
        predictions[image_path.stem] = combined
    return predictions


def score(manifest: dict, predictions: dict[str, np.ndarray]) -> dict:
    """Pixel metrics plus per-sample area statistics, in raster space."""
    return score_raster_manifest(manifest, predictions)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--out", default="reports/ml/crosssource_eval.json")
    args = parser.parse_args(argv)

    manifest = load_manifest(Path(args.manifest))
    images = [Path(s["image"]) for s in manifest["samples"]]
    missing_images = [str(p) for p in images if not Path(p).exists()]
    if missing_images:
        raise SystemExit(f"missing images: {missing_images[:3]}")

    predictions = predict_masks(Path(args.weights), images, args.conf)
    report = score(manifest, predictions)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "samples"}, indent=2))
    print(f"per-sample rows: {len(report['samples'])}  ->  {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
