"""Write real, reproducible image-processing artifacts from the production adapter.

Run: ``python -m eval.processing_evidence --image road.jpg --output-dir evidence``.
The candidate segmentation remains exploratory; this command does not evaluate
accuracy, establish ROI, or calibrate physical scale.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import cv2
import numpy as np

from backend import analysis
from backend.aggregate.tiling import image_flatten_sigma
from backend.quality.validity import classify_quality


def _view(array: np.ndarray) -> tuple[np.ndarray, str]:
    value = np.asarray(array)
    if value.dtype == np.uint8:
        return value, "native 8-bit pipeline output"
    finite = value[np.isfinite(value)]
    if finite.size == 0 or float(finite.max()) <= float(finite.min()):
        return np.zeros(value.shape, dtype=np.uint8), "display-only min/max normalization"
    lo, hi = np.percentile(finite, [0.5, 99.5])
    if hi <= lo:
        lo, hi = float(finite.min()), float(finite.max())
    scaled = np.clip((value.astype(np.float32) - lo) * (255.0 / (hi - lo)), 0, 255)
    return scaled.astype(np.uint8), "display-only 0.5/99.5 percentile normalization"


def _color_labels(labels: np.ndarray) -> np.ndarray:
    maximum = int(labels.max()) if labels.size else 0
    scaled = (labels.astype(np.float32) * (255.0 / maximum)).astype(np.uint8) if maximum else np.zeros(labels.shape, np.uint8)
    colored = cv2.applyColorMap(scaled, cv2.COLORMAP_TURBO)
    colored[labels == 0] = 0
    return colored


def _boundaries(labels: np.ndarray) -> np.ndarray:
    boundary = np.zeros(labels.shape, dtype=bool)
    boundary[:-1] |= (labels[:-1] != labels[1:]) & ((labels[:-1] > 0) | (labels[1:] > 0))
    boundary[:, :-1] |= (labels[:, :-1] != labels[:, 1:]) & ((labels[:, :-1] > 0) | (labels[:, 1:] > 0))
    return boundary


def build_bundle(image_path: str | Path, output_dir: str | Path, roi_mask_path: str | Path | None = None) -> dict:
    source = Path(image_path)
    target = Path(output_dir)
    if not source.is_file():
        raise FileNotFoundError(source)
    image = analysis.decode_image(source)
    if image is None:
        raise ValueError(f"could not decode image: {source.name}")
    target.mkdir(parents=True, exist_ok=True)
    original_name = f"original{source.suffix.lower()}"
    shutil.copyfile(source, target / original_name)

    roi_mask = None
    if roi_mask_path is not None:
        roi_mask = cv2.imread(str(roi_mask_path), cv2.IMREAD_GRAYSCALE)
        if roi_mask is None or roi_mask.shape != image.shape[:2]:
            raise ValueError("ROI mask must decode and match the source image dimensions")
        roi_mask = roi_mask > 0
    outcome = analysis.measure_frame(
        image, include_processing_stages=True, valid_surface_mask=roi_mask
    )
    arrays = outcome.get("processing_stages")
    stages_available = bool(arrays and "candidate_labels" in arrays)
    labels = arrays["candidate_labels"] if stages_available else None
    metrics = outcome.get("metrics")
    quality = classify_quality(image, has_scale=False).describe()
    config = analysis.MeasurementConfig()
    watershed = config.watershed
    tiling = analysis.DEFAULT_TILING
    parameters = {
        "illumination_flattened": {"input": "source image", "sigma_px": image_flatten_sigma(image.shape[:2], watershed), "operation": "gray - GaussianBlur(gray, sigma)"},
        "contrast_normalized": {"input": "illumination_flattened", "polarity": watershed.polarity, "low_percentile": watershed.norm_lo_percentile, "high_percentile": watershed.norm_hi_percentile},
        "otsu_binary": {"input": "contrast_normalized", "threshold": "Otsu global threshold"},
        "morphology_foreground": {"input": "otsu_binary", "opening_kernel_px": watershed.noise_kernel_px, "enclosed_hole_fill_max_area_px": watershed.hole_fill_max_area_px},
        "distance_transform": {"input": "morphology_foreground", "metric": "L2", "mask_size_px": 5},
        "markers": {"input": "distance_transform", "method": watershed.marker_method, "h_max_fraction": watershed.marker_h_max_fraction, "minimum_peak_distance_px": watershed.marker_min_distance_px},
        "candidate_instances": {"input": "foreground + markers + distance_transform", "tile_px": tiling.tile_px if tiling else None, "overlap_px": tiling.overlap_px if tiling else None, "stitch_rule": "shared-pixel overlap"},
        "candidate_boundaries": {"input": "candidate_instances labels + source image", "boundary_color_bgr": [0, 0, 255]},
    }

    stage_info = {
        "illumination_flattened": ("Signed image minus a Gaussian blur; tile sigma is pinned to whole-image scale.", "Suppresses broad illumination gradients while retaining local texture.", "Shadow edges and texture at the flattening scale can be removed; signed values are display-normalized only."),
        "contrast_normalized": ("Robust percentile mapping to uint8 using configured 0.5/99.5 percentiles.", "Provides a stable 8-bit response for thresholding.", "Percentile clipping can suppress rare extremes; it is not a physical reflectance measure."),
        "otsu_binary": ("Otsu global threshold on the normalized flattened response.", "Creates candidate foreground without hand-picked per-image threshold.", "Mixed materials, shadows and texture can be confused with aggregate."),
        "morphology_foreground": ("Configured elliptical morphological opening, then fill only small enclosed holes.", "Removes tiny specks while avoiding a closing operation that can bridge visible gaps.", "Small real particles may be removed; filled holes are not observed material boundaries."),
        "distance_transform": ("OpenCV L2 distance transform with mask size 5 on the cleaned foreground.", "Encodes distance from each candidate pixel to background for marker/watershed splitting.", "Depends on the thresholded foreground and is measured in pixels only."),
        "markers": ("Configured relative H-maxima marker selection on each tile (or configured NMS alternative).", "Seeds candidate regions for marker-controlled watershed.", "Invisible boundaries cannot be recovered; marker count is not human-verified chip count."),
        "candidate_instances": ("The production tile watershed labels after overlap stitching and compact relabeling.", "Shows the analyzer's actual exploratory instance candidates.", "Candidates are not verified exposed aggregates or validated measurements."),
        "candidate_boundaries": ("Pixel-neighbour label transitions overlaid on the unchanged original.", "Lets a reviewer inspect where candidate labels meet in source coordinates.", "A boundary is a model output, not physical truth."),
    }
    stages = {}
    for name, (reason, effect, limitation) in stage_info.items():
        if not stages_available:
            stages[name] = {
                "file": None,
                "algorithm": name.replace("_", " "),
                "parameters": parameters[name],
                "status": "unavailable",
                "unavailable_reason": "quality_gate_rejected_before_segmentation",
                "reason": reason,
                "effect": effect,
                "limitation": limitation,
                "physical_validation": False,
                "native_coordinate_space": True,
            }
            continue
        if name == "candidate_instances":
            view = _color_labels(labels)
            filename = "candidate_instances.png"
            transform = "deterministic display colors; underlying IDs are in candidate_labels.npy"
        elif name == "candidate_boundaries":
            view = image[..., :3].copy() if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            view[_boundaries(labels)] = (0, 0, 255)
            filename = "candidate_boundaries.png"
            transform = "red overlay on unchanged source pixels"
        elif name == "markers":
            view = _color_labels(arrays[name])
            filename = "markers.png"
            transform = "deterministic display colors; marker IDs are tile-local"
        else:
            view, transform = _view(arrays[name])
            filename = f"{name}.png"
        if not cv2.imwrite(str(target / filename), view):
            raise OSError(f"could not write {filename}")
        stages[name] = {
            "file": filename,
            "algorithm": name.replace("_", " "),
            "parameters": parameters[name],
            "status": "available",
            "reason": reason,
            "effect": effect,
            "limitation": limitation,
            "display_transform": transform,
            "physical_validation": False,
            "native_coordinate_space": True,
        }

    if labels is not None:
        np.save(target / "candidate_labels.npy", labels, allow_pickle=False)
    manifest = {
        "format": "roadsight-processing-evidence/1",
        "source_name": source.name,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "original_file": original_name,
        "width_px": int(image.shape[1]),
        "height_px": int(image.shape[0]),
        "quality": quality,
        "brightness_mean_gray": quality["metrics"].get("mean_intensity"),
        "contrast_dynamic_range_p99_minus_p1": quality["metrics"].get("dynamic_range"),
        "sharpness_laplacian_variance": quality["metrics"].get("laplacian_variance"),
        "quality_thresholds_calibrated": quality["thresholds_calibrated"],
        "roi": {"available": roi_mask is not None, "source_name": Path(roi_mask_path).name if roi_mask_path else None, "source_sha256": hashlib.sha256(Path(roi_mask_path).read_bytes()).hexdigest() if roi_mask_path else None, "reason": "Human-drawn binary road mask; used for downstream measurements. No automatic road-plane detector is implemented." if roi_mask is not None else "The current analyzer uses a full-frame surface mask; no road-plane/ROI detector is implemented."},
        "calibration": {"status": "uncalibrated", "physical_validation": False, "physical_units_available": False},
        "candidate_count": {"count": metrics.chip_count if metrics else None, "verified": False, "meaning": "Unverified watershed candidates whose reported count is restricted to the supplied ROI." if roi_mask is not None else "Exploratory watershed candidate regions; not ground-truth aggregate count." if labels is not None else "Unavailable because the quality gate rejected this image."},
        "reported_pixel_metrics": metrics.model_dump(mode="json") if metrics else None,
        "limitations": list(outcome.get("limitations", [])) + ["No road ROI detector.", "No physical scale or human aggregate labels.", "No road-quality score.", "Candidate instances require human verification."],
        "processing_configuration": {"watershed": watershed.__dict__, "tiling": tiling.__dict__ if tiling else None},
        "stages": stages,
        "candidate_label_file": "candidate_labels.npy" if labels is not None else None,
        "ground_truth_available": False,
        "accuracy_claimed": False,
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the real analyzer and export its image-processing evidence.")
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--roi-mask", type=Path, help="Optional human-drawn binary mask (nonzero pixels are road); dimensions must match --image")
    args = parser.parse_args()
    manifest = build_bundle(args.image, args.output_dir, args.roi_mask)
    print(json.dumps({"output_dir": str(args.output_dir), "candidate_count": manifest["candidate_count"], "quality": manifest["quality"]["status"], "physical_units_available": False}, indent=2))


if __name__ == "__main__":
    main()
