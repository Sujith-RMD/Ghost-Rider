"""Optional RDD2022 India YOLOv8n localization adapter."""

from __future__ import annotations

import hashlib
import logging
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Tuple

from ..app.config import get_settings
from ..schemas import DistressDetection, DistressDetectionEvidence

logger = logging.getLogger("ghost_rider.distress.inference")
MODEL_VERSION = "rdd2022-india-yolov8n"
IMAGE_SIZE = 736
CONFIDENCE_THRESHOLD = 0.25


def _weights_path() -> Path:
    return get_settings().distress_model_path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as checkpoint:
        for block in iter(lambda: checkpoint.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@lru_cache(maxsize=1)
def _load_model(path: str) -> Tuple[Any, str]:
    from ultralytics import YOLO

    weights = Path(path)
    return YOLO(str(weights), task="detect"), _sha256(weights)


def _device() -> Any:
    try:
        import torch

        return 0 if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def detect_distress(image: Any) -> DistressDetectionEvidence:
    """Run the verified detector once for a frame; never replace it with COCO."""
    height, width = (int(image.shape[0]), int(image.shape[1]))
    weights = _weights_path()
    base = {
        "image_width": width,
        "image_height": height,
        "confidence_threshold": CONFIDENCE_THRESHOLD,
    }
    if not weights.is_file() or weights.stat().st_size == 0:
        return DistressDetectionEvidence(
            status="unavailable", reason="weights_not_found", **base
        )

    try:
        model, model_hash = _load_model(str(weights))
        started = time.perf_counter()
        result = model.predict(
            source=image,
            imgsz=IMAGE_SIZE,
            conf=CONFIDENCE_THRESHOLD,
            device=_device(),
            verbose=False,
        )[0]
        inference_ms = (time.perf_counter() - started) * 1000
        names: Dict[int, str] = {int(key): str(value) for key, value in model.names.items()}
        detections = []
        boxes = result.boxes
        if boxes is not None:
            coordinates = boxes.xyxy.detach().cpu().tolist()
            class_ids = boxes.cls.detach().cpu().tolist()
            confidences = boxes.conf.detach().cpu().tolist()
            for coords, raw_class_id, raw_confidence in zip(coordinates, class_ids, confidences):
                class_id = int(raw_class_id)
                if class_id not in names:
                    continue
                x1, y1, x2, y2 = coords
                bbox = [
                    max(0.0, min(float(width), float(x1))),
                    max(0.0, min(float(height), float(y1))),
                    max(0.0, min(float(width), float(x2))),
                    max(0.0, min(float(height), float(y2))),
                ]
                detections.append(DistressDetection(
                    class_id=class_id,
                    class_name=names[class_id],
                    confidence=float(raw_confidence),
                    bbox_xyxy=bbox,
                ))
        return DistressDetectionEvidence(
            status="success",
            model_version=MODEL_VERSION,
            model_sha256=model_hash,
            class_names=names,
            inference_ms=inference_ms,
            detections=detections,
            **base,
        )
    except Exception as exc:
        logger.warning("Distress detector unavailable (%s: %s)", type(exc).__name__, exc)
        return DistressDetectionEvidence(
            status="error",
            reason="inference_failed",
            model_version=MODEL_VERSION,
            **base,
        )
