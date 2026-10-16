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
import hashlib
import platform
import re
import time
from importlib import metadata
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
    """Legacy stem-keyed API; ambiguous stems are rejected before inference."""
    paths = [Path(p) for p in image_paths]
    if len({p.stem for p in paths}) != len(paths):
        raise ValueError("duplicate image stems; use explicit sample_id mapping")
    return _predict_samples(weights, {p.stem: p for p in paths}, conf)[0]


def _predict_samples(weights, sample_images, conf):
    from ultralytics import YOLO

    if not np.isfinite(conf) or not 0 <= conf <= 1:
        raise ValueError("confidence must be finite and in [0, 1]")
    started = time.perf_counter()
    model = YOLO(str(weights))
    load_seconds = time.perf_counter() - started
    predictions = {}
    latencies = []
    for sample_id, image_path in sample_images.items():
        sample_started = time.perf_counter()
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
        predictions[sample_id] = combined
        wall_seconds = time.perf_counter() - sample_started
        speed = getattr(result, "speed", None) or {}
        inference_ms = speed.get("inference")
        if not isinstance(inference_ms, (int, float)) or not np.isfinite(inference_ms) or inference_ms < 0:
            inference_ms = None
        latencies.append({"sample_id": sample_id, "image": str(image_path),
                          "wall_seconds": wall_seconds,
                          "model_inference_seconds": inference_ms / 1000 if inference_ms is not None else None})
    return predictions, {
        "model_load_seconds": load_seconds,
        "elapsed_seconds": time.perf_counter() - started,
        "per_sample": latencies,
        "wall_p50_seconds": float(np.percentile([r["wall_seconds"] for r in latencies], 50)) if latencies else None,
        "wall_p95_seconds": float(np.percentile([r["wall_seconds"] for r in latencies], 95)) if latencies else None,
        "scope": "elapsed: model construction plus sequential prediction loop; excludes hashing, scoring and saving. Load: YOLO construction only. Per-sample wall: predict call (including image I/O, preprocessing, inference, postprocessing) plus CPU mask materialization. No warm-up excluded; first-call initialization included.",
        "model_only_scope": "model_inference_seconds is Ultralytics result.speed['inference'] in seconds, not wall time; null when unavailable. No extra GPU synchronization is imposed.",
    }


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _versions():
    versions = {"python": platform.python_version(), "numpy": np.__version__, "opencv": cv2.__version__}
    for name in ("ultralytics", "torch", "torchvision"):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def _validate_sample_id(sample_id):
    # Portable filenames, including Windows reserved device names and case folding.
    if (not isinstance(sample_id, str) or
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", sample_id) or
            sample_id.endswith(".") or
            sample_id.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}):
        raise ValueError(f"unsafe sample_id: {sample_id!r}")


def run_inference(weights, manifest_path, conf=0.25, save_predictions=None):
    """Run local weights with explicit manifest IDs and auditable provenance."""
    weights, manifest_path = Path(weights), Path(manifest_path)
    if not weights.is_file():
        raise ValueError(f"weights must be an existing local file (no downloads): {weights}")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    samples = manifest.get("samples", [])
    if not samples:
        raise ValueError("manifest must contain at least one sample")
    images = {}
    folded = set()
    for sample in samples:
        sample_id = sample["sample_id"]
        _validate_sample_id(sample_id)
        if sample_id.casefold() in folded:
            raise ValueError(f"duplicate or case-colliding sample_id: {sample_id}")
        folded.add(sample_id.casefold())
        image = Path(sample["image"])
        if not image.is_file():
            raise ValueError(f"missing image: {image}")
        images[sample_id] = image
    destination = Path(save_predictions) if save_predictions is not None else None
    if destination is not None and destination.exists():
        raise FileExistsError(f"prediction destination already exists: {destination}")
    weights_hash = _sha256(weights)
    predictions, timing = _predict_samples(weights, images, conf)
    if _sha256(weights) != weights_hash:
        raise ValueError("weights changed during inference")
    report = score(manifest, predictions)
    saved = None
    if destination is not None:
        # An exclusive directory also prevents races and partially overwriting prior runs.
        destination.mkdir(parents=True, exist_ok=False)
        saved = {}
        for sample_id, mask in predictions.items():
            path = destination / (sample_id + ".png")
            ok, encoded = cv2.imencode(".png", mask.astype(np.uint8) * 255)
            if not ok:
                raise ValueError(f"could not encode prediction {sample_id}")
            with path.open("xb") as stream:
                stream.write(encoded.tobytes())
            saved[sample_id] = str(path)
    report["inference_run"] = {
        "weights": str(weights), "weights_sha256": weights_hash,
        "manifest": str(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "confidence": conf, "library_versions": _versions(),
        "sample_images": {key: str(value) for key, value in images.items()},
        "path_convention": "image and GT paths are interpreted relative to process working directory, as in the legacy evaluator",
        "timing": timing, "saved_predictions": saved,
    }
    return report


def score(manifest: dict, predictions: dict[str, np.ndarray]) -> dict:
    """Pixel metrics plus per-sample area statistics, in raster space."""
    return score_raster_manifest(manifest, predictions)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--out", default="reports/ml/crosssource_eval.json")
    parser.add_argument("--save-predictions", help="new directory for sample-ID-named binary PNG masks; must not exist")
    args = parser.parse_args(argv)

    report = run_inference(args.weights, args.manifest, args.conf, args.save_predictions)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "samples"}, indent=2))
    print(f"per-sample rows: {len(report['samples'])}  ->  {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
