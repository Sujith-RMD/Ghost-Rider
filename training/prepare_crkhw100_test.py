"""Build the CRKWH100 cross-source distress test set, kept in RASTER space.

Owned by the ML role.

Why no polygon conversion
-------------------------
An earlier version of this script converted the BMP ground-truth masks into YOLO
segmentation polygons. Measured against the originals it was **wrong by 2.41x**
(total polygon pixels 225,881 against 93,711 real crack pixels; mean IoU 0.34).

The cause is structural, not a tuning problem. A crack is a thin branched curve.
``cv2.findContours(..., RETR_EXTERNAL)`` traces only the outer contour of the whole
network, and ``fillPoly`` then fills the entire interior of that outer contour -
branches, holes and all - turning a 3-px-wide crack into a solid blob. No
contour mode or simplification epsilon fixes this, because the information simply
is not representable as a coarse polygon.

So the test set stays as raster masks and evaluation happens in raster space,
where the ground truth is exact. This is also what final plan 4.3 means by
distinguishing *actual-width masks* from centreline labels: the mask IS the
ground truth, and re-encoding it is a lossy step that must not be performed.

Usage::

    python -m training.prepare_crkhw100_test \\
        --images data/external/deepcrack/CRKWH100/images \\
        --gt data/external/CRKWH100_gt/CRKWH100_gt \\
        --out data/manifests/crkhw100_test.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp"}
MASK_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mask_stats(path: Path) -> dict:
    mask = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if mask is None:
        raise ValueError(f"could not decode mask {path}")
    if mask.ndim == 3:
        mask = mask[..., 0]
    binary = mask > 127
    return {
        "shape": list(mask.shape),
        "unique_values": sorted(int(v) for v in np.unique(mask)[:4]),
        "crack_pixels": int(binary.sum()),
        "crack_fraction": float(binary.mean()),
    }


def build(images_dir: Path, gt_dir: Path, out_path: Path) -> dict:
    images = sorted(p for p in images_dir.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    gts = {p.stem: p for p in gt_dir.iterdir() if p.suffix.lower() in MASK_SUFFIXES}
    if not images:
        raise ValueError(f"no images found in {images_dir}")
    if not gts:
        raise ValueError(f"no ground-truth masks found in {gt_dir}")

    samples = []
    unmatched = []
    for image_path in images:
        gt_path = gts.get(image_path.stem)
        if gt_path is None:
            unmatched.append(image_path.name)
            continue
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"could not decode image {image_path}")
        stats = _mask_stats(gt_path)
        if list(image.shape[:2]) != stats["shape"]:
            raise ValueError(f"image/mask shape mismatch: {image_path} and {gt_path}")
        samples.append(
            {
                "sample_id": image_path.stem,
                "image": str(image_path),
                "gt_mask": str(gt_path),
                "image_shape": list(image.shape[:2]),
                "mask_shape": stats["shape"],
                "scale": None,
                "scale_note": (
                    "CRKWH100 1 mm/px is the publisher's claim and is UNVERIFIED "
                    "(A1.6: crop-vs-resize undetermined, author unreachable). "
                    "All metrics are in pixels."
                ),
                "source": "DeepCrack CRKWH100 (stored BMP masks, unmodified)",
                "crack_pixels": stats["crack_pixels"],
                "crack_fraction": stats["crack_fraction"],
                "image_sha256": _sha256(image_path),
                "gt_sha256": _sha256(gt_path),
            }
        )

    if unmatched:
        raise ValueError(f"images without ground truth: {unmatched}")
    ids = [s["sample_id"] for s in samples]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate image stems")
    positives = sum(1 for s in samples if s["crack_pixels"] > 0)
    manifest = {
        "manifest_version": 1,
        "dataset": "crkhw100_crosssource_test",
        "role": (
            "Held-out CROSS-SOURCE distress test. Different sensor, resolution "
            "(512x512 vs Crack-Seg 416x416) and geography from the training "
            "source. Not an Indian test and not a substitute for live capture."
        ),
        "raster_space": True,
        "polygon_conversion_attempted": (
            "Rejected. Measured 2.41x area over-fill (mean IoU 0.34) because "
            "thin branched cracks cannot be represented as coarse polygons. "
            "Ground truth kept exact in raster space."
        ),
        "n_samples": len(samples),
        "n_positives": positives,
        "n_negatives": len(samples) - positives,
        "negative_note": (
            f"Matched masks contain {len(samples) - positives} negative images. "
            "Pixel precision is measurable on positive images; intact-image "
            "false-alarm rate requires representative negative images. "
            "Cross-source independence requires a training-source lineage audit."
        ),
        "images_dir": str(images_dir),
        "gt_dir": str(gt_dir),
        "samples": samples,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {
        "manifest": str(out_path),
        "n_samples": len(samples),
        "n_positives": positives,
        "n_negatives": len(samples) - positives,
        "unmatched_images": unmatched,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", required=True)
    parser.add_argument("--gt", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    summary = build(Path(args.images), Path(args.gt), Path(args.out))
    for key, value in summary.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
