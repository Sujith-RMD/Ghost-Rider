"""Ghost-Rider computer-vision, homography-physics and scoring engine.

Pipeline overview
-----------------
1. :func:`load_model` lazily loads a YOLOv8 segmentation checkpoint
   (``yolov8n-seg.pt`` by default, overridable with ``YOLO_SEG_WEIGHTS``).
2. :func:`estimate_homography_scale` builds a true ground-plane homography from
   the camera mounting height, the device pitch/roll and the camera field of
   view, then returns the average square-metres-per-pixel over the visible road
   band (far rows cover more ground than near rows, so a single flat constant is
   physically wrong).
3. :func:`process_image` runs segmentation inference, sums the defect mask
   pixels, converts them to physical area with that scale, paints a
   semi-transparent red defect overlay with ``cv2.addWeighted`` and writes
   ``mask_<filename>.jpg`` next to the source image.
4. :func:`run_full_pipeline` aggregates every image of a route into 10 m
   segments, computes the Road Condition Index, applies the pothole hard
   override, uploads raw + overlay artefacts to S3 and asks Bedrock for repair
   recommendations.

Configuration is read through :mod:`app.config` (pydantic-settings); the older
environment variable names keep working as aliases.

Environment variables
---------------------
``YOLO_WEIGHTS_PATH`` (alias ``YOLO_SEG_WEIGHTS``)  Segmentation checkpoint.
``YOLO_CONF`` / ``YOLO_IOU`` / ``YOLO_IMGSZ``   Inference thresholds.
``CAMERA_HEIGHT_M``       Mounting height above the road (default 1.3).
``CAMERA_HFOV_DEG``       Horizontal field of view (default 70).
``CAMERA_MOUNT_PITCH_DEG`` Nominal downward mounting angle of the camera.
                          ``imu.pitch_deg`` is treated as the *deviation* from that
                          nominal angle: the homography/physics use
                          ``mount + deviation`` while the RCI penalty uses the
                          deviation alone (set to 0 to treat pitch_deg as the
                          absolute tilt, which reproduces the literal formula).
``CAMERA_IMAGE_SIZE``     Fallback ``WxH`` when the image shape is unknown.
``PIXEL_AREA_CALIBRATION`` Multiplier applied to the computed m2/pixel (field calibration).
``MIN_MASK_PIXELS``       Masks smaller than this are discarded as noise.
``YOLO_DEFECT_CLASS_MAP`` Explicit ``class_name=pothole`` / ``=crack`` overrides.
``YOLO_UNKNOWN_AS_DEFECT`` ``true`` (default) -> unknown classes are shape-classified.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np

try:
    from .bedrock_service import generate_road_recommendation
    from .s3_service import (
        BASE_DIR,
        UPLOADS_DIR,
        load_project_env,
        object_key_prefix,
        to_local_url,
        upload_file_to_s3,
    )
except ImportError:  # executed as a flat module (``uvicorn main:app`` inside backend/)
    from bedrock_service import generate_road_recommendation
    from s3_service import (
        BASE_DIR,
        UPLOADS_DIR,
        load_project_env,
        object_key_prefix,
        to_local_url,
        upload_file_to_s3,
    )

load_project_env()

try:  # flat layout
    from app.config import get_settings_safely
    from app.config import reload_settings as reload_configuration
except ImportError:  # package layout (``uvicorn backend.main:app``)
    from backend.app.config import get_settings_safely  # type: ignore[no-redef]
    from backend.app.config import reload_settings as reload_configuration  # type: ignore[no-redef]

try:
    from ultralytics import YOLO

    ULTRALYTICS_AVAILABLE = True
except Exception as _import_exc:  # pragma: no cover - optional dependency
    YOLO = None  # type: ignore[assignment]
    ULTRALYTICS_AVAILABLE = False

logger = logging.getLogger("ghost_rider.pipeline")


# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
_SETTINGS = get_settings_safely()


def _cfg(attribute: str, env_name: str, default: Any, caster: Any = float) -> Any:
    """Read one setting through ``app.config`` with an env/default fallback."""
    value = getattr(_SETTINGS, attribute, None) if _SETTINGS is not None else None
    if value in (None, ""):
        value = os.getenv(env_name)
    try:
        return caster(value)
    except (TypeError, ValueError):
        return default


def _resolve_weights_path() -> str:
    """Resolved segmentation checkpoint path (backend-relative when not absolute)."""
    if _SETTINGS is not None:
        return str(_SETTINGS.yolo_weights)
    return os.getenv("YOLO_SEG_WEIGHTS") or str(BASE_DIR / "yolov8n-seg.pt")


DEFAULT_WEIGHTS = _resolve_weights_path()
CONF_THRESHOLD = float(_cfg("YOLO_CONF", "YOLO_CONF", 0.25))
IOU_THRESHOLD = float(_cfg("YOLO_IOU", "YOLO_IOU", 0.45))
IMAGE_SIZE = int(_cfg("YOLO_IMGSZ", "YOLO_IMGSZ", 640, int))
CAMERA_HEIGHT_M = float(_cfg("CAMERA_HEIGHT_M", "CAMERA_HEIGHT_M", 1.3))
CAMERA_HFOV_DEG = float(_cfg("CAMERA_HFOV_DEG", "CAMERA_HFOV_DEG", 70.0))
CAMERA_MOUNT_PITCH_DEG = float(_cfg("CAMERA_MOUNT_PITCH_DEG", "CAMERA_MOUNT_PITCH_DEG", 25.0))
PIXEL_AREA_CALIBRATION = float(_cfg("PIXEL_AREA_CALIBRATION", "PIXEL_AREA_CALIBRATION", 1.0))
MIN_MASK_PIXELS = int(_cfg("MIN_MASK_PIXELS", "MIN_MASK_PIXELS", 50, int))
OVERLAY_ALPHA = float(_cfg("OVERLAY_ALPHA", "OVERLAY_ALPHA", 0.45))
MIN_PITCH_DEG = 2.0   # below this the ground-plane mapping degenerates (near-horizontal view)
MAX_PITCH_DEG = 89.0  # straight down
SEGMENT_LENGTH_M = float(_cfg("SEGMENT_LENGTH_M", "SEGMENT_LENGTH_M", 10.0))

# Mask overlay colour (BGR): the defect union is painted semi-transparent red.
OVERLAY_COLOR = (0, 0, 255)

_DEFAULT_IMAGE_SHAPE = (1080, 1920)  # (height, width)


def _parse_image_size_env() -> Tuple[int, int]:
    """Parse ``CAMERA_IMAGE_SIZE`` (``WxH``) into an ``(height, width)`` tuple."""
    configured = getattr(_SETTINGS, "CAMERA_IMAGE_SIZE", "") if _SETTINGS is not None else ""
    raw = str(configured or os.getenv("CAMERA_IMAGE_SIZE") or "").strip().lower().replace(" ", "")
    if "x" in raw:
        try:
            width, height = (int(part) for part in raw.split("x", 1))
            if width > 0 and height > 0:
                return height, width
        except (TypeError, ValueError):
            pass
    return _DEFAULT_IMAGE_SHAPE


DEFAULT_IMAGE_SHAPE = _parse_image_size_env()

# Class-name heuristics used to map model classes onto the two defect families.
POTHOLE_KEYWORDS = (
    "pothole", "pot_hole", "pot-hole", "hole", "pit", "blowout", "blow-out",
    "cavity", "depression", "rutting", "rut", "ravel", "road_damage",
)
CRACK_KEYWORDS = (
    "crack", "fissure", "joint", "seam", "sealant", "alligator", "crocodile",
    "transverse", "longitudinal", "linear", "spall", "edge_break",
)

# Classes that must never be counted as road-surface defects (COCO objects,
# scene furniture and the non-defect pavement classes of public datasets).
IGNORED_CLASSES = {
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
    "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
    "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
    "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier",
    "toothbrush", "road", "asphalt", "sidewalk", "pavement", "lane", "lane marking",
    "marking", "line", "kerb", "curb", "manhole", "shadow", "sky", "building", "wall",
    "tree", "vegetation", "grass", "plant", "pole", "sign", "vehicle", "water", "puddle",
    "speed bump", "crosswalk", "background",
}

# --------------------------------------------------------------------------- #
# Model management
# --------------------------------------------------------------------------- #
_model_lock = threading.Lock()
_model: Optional[Any] = None
_model_error: Optional[str] = None


def load_model(weights: Optional[str] = None) -> Optional[Any]:
    """Lazily load (and cache) the YOLO segmentation model.

    Returns ``None`` when ultralytics is missing or the checkpoint cannot be
    loaded/downloaded - the caller then reports a graceful per-image error
    instead of crashing the background task.
    """
    global _model, _model_error

    if _model is not None:
        return _model
    if not ULTRALYTICS_AVAILABLE:
        _model_error = "ultralytics is not installed"
        logger.error(_model_error)
        return None

    with _model_lock:
        if _model is not None:
            return _model

        candidates: List[str] = []
        for candidate in (weights or DEFAULT_WEIGHTS, str(BASE_DIR / "yolov8n-seg.pt"), "yolov8n-seg.pt"):
            if candidate and candidate not in candidates:
                candidates.append(candidate)

        for candidate in candidates:
            path = Path(candidate)
            if not path.is_absolute() and not path.exists():
                local = BASE_DIR / candidate
                path = local if local.exists() else path
            try:
                _model = YOLO(str(path)) if path.exists() else YOLO(candidate)
                _model_error = None
                logger.info("Loaded YOLO segmentation weights: %s", path if path.exists() else candidate)
                return _model
            except Exception as exc:
                logger.warning("Could not load YOLO weights '%s' (%s: %s).",
                               candidate, type(exc).__name__, exc)

        _model_error = "no loadable YOLO segmentation checkpoint found"
        logger.error(_model_error)
        return None


def model_status() -> dict:
    """Inspection helper for the health endpoint."""
    names = getattr(_model, "names", None)
    return {
        "ultralytics_installed": ULTRALYTICS_AVAILABLE,
        "loaded": _model is not None,
        "weights": DEFAULT_WEIGHTS,
        "classes": list(names.values()) if isinstance(names, dict) else None,
        "error": _model_error,
    }


# --------------------------------------------------------------------------- #
# Homography physics
# --------------------------------------------------------------------------- #
def _clamp_pitch(pitch_deg: float) -> float:
    try:
        pitch = float(pitch_deg)
    except (TypeError, ValueError):
        pitch = 0.0
    if not math.isfinite(pitch):
        pitch = 0.0
    return max(MIN_PITCH_DEG, min(abs(pitch) or MIN_PITCH_DEG, MAX_PITCH_DEG))


def ground_plane_homography(pitch_deg: float, roll_deg: float, camera_height_m: float = 1.3,
                            *, image_shape: Optional[Sequence[int]] = None,
                            hfov_deg: Optional[float] = None) -> np.ndarray:
    """Return the 3x3 homography mapping image pixels to ground-plane metres.

    Camera model
    ------------
    Pinhole camera mounted ``h`` metres above the road, optical axis tilted
    ``pitch`` degrees downwards and rolled by ``roll`` degrees.  In camera
    coordinates (x right, y down, z forward) a pixel ``(u, v)`` casts the ray
    ``(u - cx, v - cy, f)``.  Intersecting that ray with the ground plane
    ``Y = -h`` and expressing the hit point in vehicle coordinates (X lateral,
    Z forward along the road) gives a rational map that is exactly representable
    as a homography::

        X = (H00 u + H01 v + H02) / (H20 u + H21 v + H22)
        Z = (H10 u + H11 v + H12) / (H20 u + H21 v + H22)

    The denominator ``w`` is the depth term; ``w -> 0`` is the horizon, where
    ground-plane resolution becomes singular.
    """
    shape = tuple(image_shape) if image_shape else DEFAULT_IMAGE_SHAPE
    height_px, width_px = int(shape[0]), int(shape[1])
    if width_px <= 0 or height_px <= 0:
        height_px, width_px = DEFAULT_IMAGE_SHAPE

    height_m = float(camera_height_m) if camera_height_m else CAMERA_HEIGHT_M
    if not math.isfinite(height_m) or height_m <= 0:
        height_m = CAMERA_HEIGHT_M

    fov = float(hfov_deg) if hfov_deg else CAMERA_HFOV_DEG
    fov = max(10.0, min(fov, 150.0))

    theta = math.radians(_clamp_pitch(pitch_deg))
    try:
        phi = math.radians(float(roll_deg))
    except (TypeError, ValueError):
        phi = 0.0
    if not math.isfinite(phi):
        phi = 0.0

    f_px = (width_px / 2.0) / math.tan(math.radians(fov) / 2.0)
    cx = width_px / 2.0
    cy = height_px / 2.0

    cos_t, sin_t = math.cos(theta), math.sin(theta)
    cos_p, sin_p = math.cos(phi), math.sin(phi)

    return np.array(
        [
            [height_m * cos_p, height_m * sin_p, -height_m * (cos_p * cx + sin_p * cy)],
            [
                height_m * sin_t * sin_p,
                -height_m * sin_t * cos_p,
                height_m * (sin_t * cos_p * cy - sin_t * sin_p * cx + f_px * cos_t),
            ],
            [
                -cos_t * sin_p,
                cos_t * cos_p,
                cos_t * (sin_p * cx - cos_p * cy) + f_px * sin_t,
            ],
        ],
        dtype=np.float64,
    )


def pixel_to_ground(u: float, v: float, homography: np.ndarray) -> Optional[Tuple[float, float]]:
    """Map one pixel centre to ``(X, Z)`` metres on the ground plane.

    Returns ``None`` for singular points (at or above the horizon).
    """
    denominator = homography[2, 0] * u + homography[2, 1] * v + homography[2, 2]
    if abs(denominator) < 1e-9:
        return None
    x_m = (homography[0, 0] * u + homography[0, 1] * v + homography[0, 2]) / denominator
    z_m = (homography[1, 0] * u + homography[1, 1] * v + homography[1, 2]) / denominator
    if not (math.isfinite(x_m) and math.isfinite(z_m)):
        return None
    if z_m <= 0:  # behind the camera / above the horizon
        return None
    return x_m, z_m


def ground_area_per_pixel(u: float, v: float, homography: np.ndarray,
                          delta: float = 5e-2) -> Optional[float]:
    """Local ground area (m2) covered by a 1x1 pixel neighbourhood at ``(u, v)``.

    Computed as the absolute Jacobian determinant ``|d(X, Z) / d(u, v)|`` using a
    central finite difference, which is exact for this projective mapping.
    """
    if pixel_to_ground(u, v, homography) is None:
        return None
    plus_u = pixel_to_ground(u + delta, v, homography)
    minus_u = pixel_to_ground(u - delta, v, homography)
    plus_v = pixel_to_ground(u, v + delta, homography)
    minus_v = pixel_to_ground(u, v - delta, homography)
    if None in (plus_u, minus_u, plus_v, minus_v):
        return None

    d_x_du = (plus_u[0] - minus_u[0]) / (2 * delta)
    d_z_du = (plus_u[1] - minus_u[1]) / (2 * delta)
    d_x_dv = (plus_v[0] - minus_v[0]) / (2 * delta)
    d_z_dv = (plus_v[1] - minus_v[1]) / (2 * delta)

    area = abs(d_x_du * d_z_dv - d_x_dv * d_z_du)
    if not math.isfinite(area) or area <= 0:
        return None
    return area


def integrated_mask_area(mask_bool: np.ndarray, homography: np.ndarray) -> float:
    """Exact ground area of a mask: the local Jacobian integrated over its pixels.

    Unlike ``pixels * estimate_homography_scale(...)`` this evaluates the true
    pixel footprint at every mask pixel, so a defect near the image bottom (where
    one pixel covers far less ground than the ROI average) is not overestimated
    and one near the horizon is not underestimated.  Vectorised over the mask
    bounding box only, so the cost stays proportional to the defect size.
    """
    try:
        rows = np.flatnonzero(mask_bool.any(axis=1))
        cols = np.flatnonzero(mask_bool.any(axis=0))
        if rows.size == 0 or cols.size == 0:
            return 0.0
        row_start, row_end = int(rows[0]), int(rows[-1]) + 1
        col_start, col_end = int(cols[0]), int(cols[-1]) + 1
        subset = mask_bool[row_start:row_end, col_start:col_end]

        u = np.arange(col_start, col_end, dtype=np.float64)[None, :]
        v = np.arange(row_start, row_end, dtype=np.float64)[:, None]
        denominator = homography[2, 0] * u + homography[2, 1] * v + homography[2, 2]
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            numerator_x = homography[0, 0] * u + homography[0, 1] * v + homography[0, 2]
            numerator_z = homography[1, 0] * u + homography[1, 1] * v + homography[1, 2]
            z_m = numerator_z / denominator
            denominator_sq = denominator * denominator
            d_x_du = (homography[0, 0] * denominator - numerator_x * homography[2, 0]) / denominator_sq
            d_x_dv = (homography[0, 1] * denominator - numerator_x * homography[2, 1]) / denominator_sq
            d_z_du = (homography[1, 0] * denominator - numerator_z * homography[2, 0]) / denominator_sq
            d_z_dv = (homography[1, 1] * denominator - numerator_z * homography[2, 1]) / denominator_sq
            determinant = np.abs(d_x_du * d_z_dv - d_x_dv * d_z_du)

        valid = subset & np.isfinite(determinant) & (denominator > 0) & (z_m > 0)
        return float(determinant[valid].sum())
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Integrated mask area failed (%s: %s).", type(exc).__name__, exc)
        return 0.0


def estimate_homography_scale(pitch_deg: float, roll_deg: float, camera_height_m: float = 1.3,
                              *, image_shape: Optional[Sequence[int]] = None,
                              hfov_deg: Optional[float] = None,
                              roi: Optional[Tuple[float, float, float, float]] = None) -> float:
    """Average square-metres of road surface per pixel for the surveyed image.

    The value is the mean local Jacobian determinant of the ground-plane
    homography over the visible road band (default: the lower half of the frame,
    roughly 2 m to 12 m ahead of the vehicle, which is where a forward-facing
    camera can actually see surface defects - far rows cover far more ground per
    pixel than near rows, and this accounts for that).

    ``roll`` rotates the projection in the image plane; the homography honours
    it even though a pure rotation preserves the area Jacobian.

    Returns ``m2 / pixel`` clamped to a physically plausible band.  Never raises.
    """
    try:
        shape = tuple(image_shape) if image_shape else DEFAULT_IMAGE_SHAPE
        height_px, width_px = int(shape[0]), int(shape[1])
        if height_px <= 0 or width_px <= 0:
            height_px, width_px = DEFAULT_IMAGE_SHAPE
        homography = ground_plane_homography(
            pitch_deg, roll_deg, camera_height_m,
            image_shape=(height_px, width_px), hfov_deg=hfov_deg,
        )

        v0_frac, v1_frac, u0_frac, u1_frac = roi or (0.50, 0.96, 0.05, 0.95)
        rows = np.linspace(max(0.0, v0_frac) * height_px, min(1.0, v1_frac) * height_px, 16)
        cols = np.linspace(max(0.0, u0_frac) * width_px, min(1.0, u1_frac) * width_px, 16)

        samples: List[float] = []
        for v in rows:
            for u in cols:
                area = ground_area_per_pixel(float(u), float(v), homography)
                if area is not None:
                    samples.append(area)

        if samples:
            scale = float(np.mean(samples)) * PIXEL_AREA_CALIBRATION
        else:
            # Degenerate ROI (e.g. the whole band is above the horizon): use the
            # bottom-centre pixel, the closest and always-valid ground sample.
            fallback = ground_area_per_pixel(width_px / 2.0, height_px * 0.95, homography)
            if fallback is None:
                raise ValueError("degenerate ground-plane homography")
            scale = fallback * PIXEL_AREA_CALIBRATION

        if not math.isfinite(scale) or scale <= 0:
            raise ValueError(f"non-physical scale {scale!r}")

        clamp_min, clamp_max = 1e-8, 5e-2
        clamped = max(clamp_min, min(scale, clamp_max))
        if clamped != scale:
            logger.warning("Homography scale %.3e out of range; clamped to %.3e.", scale, clamped)
        return clamped
    except Exception as exc:
        logger.error("Homography scale computation failed (%s: %s); using heuristic fallback.",
                     type(exc).__name__, exc)
        # Last-resort heuristic: 1080p forward-looking camera at 1.3 m. Must not
        # raise even if pitch_deg is nonsense, this branch is the safety net.
        try:
            pitch_value = abs(float(pitch_deg))
        except (TypeError, ValueError):
            pitch_value = 0.0
        return 0.00015 * (1.0 + pitch_value / 100.0)


# --------------------------------------------------------------------------- #
# Defect classification
# --------------------------------------------------------------------------- #
def _class_overrides() -> Dict[str, str]:
    """Parse ``YOLO_DEFECT_CLASS_MAP`` (``"name=pothole,other=crack"``)."""
    overrides: Dict[str, str] = {}
    raw = (os.getenv("YOLO_DEFECT_CLASS_MAP") or "").strip()
    if not raw:
        return overrides
    for pair in raw.split(","):
        if "=" not in pair:
            continue
        name, kind = pair.split("=", 1)
        kind = kind.strip().lower()
        if name.strip() and kind in ("pothole", "crack"):
            overrides[name.strip().lower()] = kind
    return overrides


def classify_defect_shape(mask_bool: np.ndarray) -> Tuple[str, Dict[str, float]]:
    """Decide pothole vs crack from mask geometry when class names are useless.

    Potholes are compact blobs; cracks are elongated, thin and low-roundness.
    Rule: a mask is a **crack** when its minimum-area-rectangle aspect ratio is
    ``>= 2.5`` *or* its roundness ``4*pi*A/P^2`` is ``<= 0.45``, otherwise it is
    a **pothole**.
    """
    metrics: Dict[str, float] = {"roundness": 0.0, "aspect_ratio": 1.0, "solidity": 0.0, "area_px": 0.0}
    try:
        mask = np.ascontiguousarray(mask_bool.astype(np.uint8))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return "crack", metrics

        contour = max(contours, key=cv2.contourArea)
        area = float(cv2.contourArea(contour)) or float(mask.sum())
        if area <= 0:
            return "crack", metrics

        perimeter = float(cv2.arcLength(contour, True)) or 1.0
        roundness = float(4.0 * math.pi * area / (perimeter ** 2))
        (_, _), (rect_w, rect_h), _ = cv2.minAreaRect(contour)
        long_side = max(rect_w, rect_h)
        short_side = max(min(rect_w, rect_h), 1e-6)
        aspect_ratio = float(long_side / short_side)
        hull_area = float(cv2.contourArea(cv2.convexHull(contour))) or area
        solidity = float(area / hull_area)

        metrics.update(
            {
                "roundness": round(roundness, 4),
                "aspect_ratio": round(aspect_ratio, 3),
                "solidity": round(solidity, 4),
                "area_px": round(area, 1),
            }
        )
        kind = "crack" if (aspect_ratio >= 2.5 or roundness <= 0.45) else "pothole"
        return kind, metrics
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Shape classification failed (%s: %s); defaulting to crack.",
                     type(exc).__name__, exc)
        return "crack", metrics


def resolve_defect_kind(class_name: str, mask_bool: np.ndarray) -> Tuple[Optional[str], Dict[str, float]]:
    """Map a model class onto ``pothole`` / ``crack`` / ``None`` (ignore).

    Priority: explicit ``YOLO_DEFECT_CLASS_MAP`` override -> pothole keywords ->
    crack keywords -> known non-defect classes (ignored) -> shape classifier.
    """
    name = str(class_name or "").strip().lower()
    metrics: Dict[str, float] = {}

    override = _class_overrides().get(name)
    if override:
        _, metrics = classify_defect_shape(mask_bool)
        return override, metrics

    # A name matching both (e.g. "pothole_crack") counts as a pothole: the
    # stricter class wins because it triggers the hard status override.
    if any(keyword in name for keyword in POTHOLE_KEYWORDS):
        _, metrics = classify_defect_shape(mask_bool)
        return "pothole", metrics
    if any(keyword in name for keyword in CRACK_KEYWORDS):
        _, metrics = classify_defect_shape(mask_bool)
        return "crack", metrics
    if name in IGNORED_CLASSES:
        return None, metrics

    unknown_as_defect = (os.getenv("YOLO_UNKNOWN_AS_DEFECT", "true") or "true").strip().lower() not in (
        "0", "false", "no",
    )
    if not unknown_as_defect:
        return None, metrics
    return classify_defect_shape(mask_bool)


# --------------------------------------------------------------------------- #
# Image I/O helpers (unicode-safe on Windows)
# --------------------------------------------------------------------------- #
def _read_image(path: Path) -> Optional[np.ndarray]:
    try:
        buffer = np.fromfile(str(path), dtype=np.uint8)
        if buffer.size == 0:
            return None
        return cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    except Exception as exc:
        logger.error("Could not read image %s (%s: %s).", path, type(exc).__name__, exc)
        return None


def _write_image(path: Path, image: np.ndarray, quality: int = 92) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        suffix = path.suffix.lower()
        if suffix not in (".jpg", ".jpeg", ".png"):
            suffix = ".jpg"
            path = path.with_suffix(suffix)
        params = [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)] if suffix in (".jpg", ".jpeg") else []
        success, buffer = cv2.imencode(suffix, image, params)
        if not success:
            logger.error("cv2.imencode failed for %s.", path)
            return False
        buffer.tofile(str(path))
        return True
    except Exception as exc:
        logger.error("Could not write image %s (%s: %s).", path, type(exc).__name__, exc)
        return False


def _empty_result(image_path: Any, error: Optional[str] = None) -> Dict[str, Any]:
    """Same-shaped result used for every failure mode (never raises)."""
    path = Path(str(image_path)) if image_path else None
    local_url = to_local_url(image_path) if image_path else ""
    return {
        "image_path": str(image_path) if image_path else None,
        "filename": path.name if path else None,
        "mask_path": None,
        "mask_filename": None,
        "raw_url": local_url,
        "mask_url": "",
        "raw_local_url": local_url,
        "mask_local_url": "",
        "raw_object_key": None,
        "mask_object_key": None,
        "m2_per_pixel": 0.0,
        "defect_pixels": 0,
        "pothole_pixels": 0,
        "crack_pixels": 0,
        "pothole_area_m2": 0.0,
        "crack_area_m2": 0.0,
        "defect_area_m2": 0.0,
        "pothole_area_integrated_m2": 0.0,
        "crack_area_integrated_m2": 0.0,
        "defect_area_integrated_m2": 0.0,
        "has_defect": False,
        "has_pothole": False,
        "has_crack": False,
        "pothole_count": 0,
        "crack_count": 0,
        "detections": [],
        "image_height": None,
        "image_width": None,
        "class_mode": None,
        "error": error,
        "processing_ms": 0.0,
    }


def _normalise_names(names: Any) -> Dict[int, str]:
    """Coerce ``model.names`` (list or dict) into ``{class_id: class_name}``."""
    if isinstance(names, dict):
        return {int(key): str(value) for key, value in names.items()}
    if isinstance(names, (list, tuple)):
        return {index: str(value) for index, value in enumerate(names)}
    return {}


# --------------------------------------------------------------------------- #
# Single image processing
# --------------------------------------------------------------------------- #
def process_image(image_path: str, pitch_deg: float = 0.0, roll_deg: float = 0.0, *,
                  camera_height_m: Optional[float] = None, conf: Optional[float] = None,
                  iou: Optional[float] = None, imgsz: Optional[int] = None,
                  save_overlay: bool = True, output_path: Optional[str] = None,
                  model: Optional[Any] = None) -> Dict[str, Any]:
    """Segment one road photo and measure the physical defect area.

    Steps: load image -> YOLO segmentation -> per-mask pixel count -> convert to
    ``m2`` with the homography scale -> paint a semi-transparent red overlay with
    ``cv2.addWeighted`` -> write ``mask_<filename>.jpg`` next to the input.

    Returns a result dictionary with the same shape for success and failure; the
    ``error`` key is populated (and the areas stay zero) when anything fails.
    """
    started = time.perf_counter()
    result = _empty_result(image_path)

    try:
        path = Path(str(image_path))
        if not path.is_file():
            result["error"] = "image_not_found"
            logger.warning("Segmentation skipped, file not found: %s", image_path)
            return result

        image = _read_image(path)
        if image is None:
            result["error"] = "image_unreadable"
            return result

        height_px, width_px = image.shape[:2]
        result["image_height"] = int(height_px)
        result["image_width"] = int(width_px)

        detector = model or load_model()
        if detector is None:
            result["error"] = "model_unavailable"
            return result

        try:
            predictions = detector.predict(
                source=image,
                conf=conf if conf is not None else CONF_THRESHOLD,
                iou=iou if iou is not None else IOU_THRESHOLD,
                imgsz=imgsz if imgsz is not None else IMAGE_SIZE,
                verbose=False,
            )
        except AttributeError:  # older callables without .predict()
            predictions = detector(
                image,
                conf=conf if conf is not None else CONF_THRESHOLD,
                iou=iou if iou is not None else IOU_THRESHOLD,
                verbose=False,
            )

        if not predictions:
            result["error"] = "no_inference_result"
            return result
        prediction = predictions[0]

        names = _normalise_names(getattr(detector, "names", None) or getattr(prediction, "names", None))

        effective_height = camera_height_m if camera_height_m else CAMERA_HEIGHT_M
        m2_per_pixel = estimate_homography_scale(
            pitch_deg, roll_deg, effective_height, image_shape=(height_px, width_px),
        )
        homography = ground_plane_homography(
            pitch_deg, roll_deg, effective_height, image_shape=(height_px, width_px),
        )
        result["m2_per_pixel"] = round(float(m2_per_pixel), 12)

        mask_tensor = getattr(getattr(prediction, "masks", None), "data", None)
        boxes = getattr(prediction, "boxes", None)

        class_ids: List[int] = []
        confidences: List[float] = []
        if boxes is not None:
            try:
                class_ids = [int(value) for value in boxes.cls.tolist()]
            except Exception:
                class_ids = [int(value) for value in np.asarray(boxes.cls).ravel()]
            try:
                confidences = [float(value) for value in boxes.conf.tolist()]
            except Exception:
                confidences = [float(value) for value in np.asarray(boxes.conf).ravel()]

        masks_array = None
        if mask_tensor is not None:
            try:
                masks_array = mask_tensor.cpu().numpy()
            except AttributeError:
                masks_array = np.asarray(mask_tensor)

        union_mask = np.zeros((height_px, width_px), dtype=bool)
        detections: List[Dict[str, Any]] = []
        pothole_pixels = crack_pixels = 0
        pothole_area = crack_area = 0.0
        pothole_area_integrated = crack_area_integrated = 0.0
        pothole_count = crack_count = 0
        # "metadata" = the checkpoint exposes road-defect class names (fine-tuned
        # model); "geometry" = kinds were inferred from mask shape only.
        class_mode = "metadata"

        if masks_array is not None and len(masks_array) > 0:
            for index in range(len(masks_array)):
                raw_mask = np.asarray(masks_array[index])
                if raw_mask.ndim == 3:
                    raw_mask = raw_mask[0]
                if raw_mask.dtype != np.uint8:
                    raw_mask = (raw_mask > 0.5).astype(np.uint8)
                if raw_mask.shape != (height_px, width_px):
                    raw_mask = cv2.resize(raw_mask, (width_px, height_px),
                                          interpolation=cv2.INTER_NEAREST)
                mask_bool = raw_mask.astype(bool)

                pixels = int(np.count_nonzero(mask_bool))
                if pixels < MIN_MASK_PIXELS:
                    continue

                class_id = class_ids[index] if index < len(class_ids) else -1
                class_name = names.get(class_id, f"class_{class_id}")
                confidence = confidences[index] if index < len(confidences) else None

                kind, metrics = resolve_defect_kind(class_name, mask_bool)
                if kind is None:
                    continue
                if class_mode == "metadata":
                    lowered = class_name.lower()
                    if not (
                        any(keyword in lowered for keyword in POTHOLE_KEYWORDS)
                        or any(keyword in lowered for keyword in CRACK_KEYWORDS)
                        or lowered in _class_overrides()
                    ):
                        class_mode = "geometry"

                # Specification method: mask pixels x homography scale factor.
                area_m2 = float(pixels) * m2_per_pixel
                # Reference method: the same mask with the local pixel footprint
                # integrated exactly (perspective-correct, no ROI averaging bias).
                area_integrated_m2 = integrated_mask_area(mask_bool, homography)
                union_mask |= mask_bool
                if kind == "pothole":
                    pothole_pixels += pixels
                    pothole_area += area_m2
                    pothole_area_integrated += area_integrated_m2
                    pothole_count += 1
                else:
                    crack_pixels += pixels
                    crack_area += area_m2
                    crack_area_integrated += area_integrated_m2
                    crack_count += 1

                detections.append(
                    {
                        "class_id": class_id,
                        "class_name": class_name,
                        "kind": kind,
                        "confidence": None if confidence is None else round(confidence, 4),
                        "pixels": pixels,
                        "area_m2": round(area_m2, 4),
                        "area_integrated_m2": round(area_integrated_m2, 4),
                        "geometry": metrics,
                    }
                )

        defect_pixels = int(np.count_nonzero(union_mask))
        result.update(
            {
                "class_mode": class_mode if detections else None,
                "defect_pixels": defect_pixels,
                "pothole_pixels": pothole_pixels,
                "crack_pixels": crack_pixels,
                "pothole_area_m2": round(pothole_area, 4),
                "crack_area_m2": round(crack_area, 4),
                "defect_area_m2": round(pothole_area + crack_area, 4),
                "pothole_area_integrated_m2": round(pothole_area_integrated, 4),
                "crack_area_integrated_m2": round(crack_area_integrated, 4),
                "defect_area_integrated_m2": round(pothole_area_integrated + crack_area_integrated, 4),
                "has_defect": bool(detections),
                "has_pothole": pothole_count > 0,
                "has_crack": crack_count > 0,
                "pothole_count": pothole_count,
                "crack_count": crack_count,
                "detections": detections,
            }
        )

        if save_overlay and detections:
            overlay_target = (
                Path(output_path) if output_path else path.with_name(f"mask_{path.stem}.jpg")
            )
            if _draw_overlay(image, union_mask, detections, overlay_target):
                result["mask_path"] = str(overlay_target)
                result["mask_filename"] = overlay_target.name
                result["mask_local_url"] = to_local_url(overlay_target)
                result["mask_url"] = result["mask_local_url"]

        result["processing_ms"] = round((time.perf_counter() - started) * 1000.0, 2)
        logger.info(
            "Processed %s: %d pothole(s)/%d crack(s), %.4f m2 defect, %.3e m2/px in %.0f ms.",
            path.name, pothole_count, crack_count, result["defect_area_m2"], m2_per_pixel,
            result["processing_ms"],
        )
        return result
    except Exception as exc:
        logger.exception("Unhandled error while processing %s: %s", image_path, exc)
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["processing_ms"] = round((time.perf_counter() - started) * 1000.0, 2)
        return result


def _draw_overlay(image: np.ndarray, union_mask: np.ndarray, detections: List[Dict[str, Any]],
                  target: Path) -> bool:
    """Paint the semi-transparent red defect mask and annotate the frame."""
    try:
        colored = np.zeros_like(image)
        colored[union_mask] = OVERLAY_COLOR
        annotated = cv2.addWeighted(image, 1.0 - OVERLAY_ALPHA, colored, OVERLAY_ALPHA, 0.0)

        contour_source = union_mask.astype(np.uint8) * 255
        contours, _ = cv2.findContours(contour_source, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(annotated, contours, -1, (255, 255, 255), 1)

        total_pothole = sum(item["area_m2"] for item in detections if item["kind"] == "pothole")
        total_crack = sum(item["area_m2"] for item in detections if item["kind"] == "crack")
        canvas_height = annotated.shape[0]
        lines = [
            f"defects: {len(detections)}",
            f"potholes: {total_pothole:.3f} m2",
            f"cracks: {total_crack:.3f} m2",
        ]
        for offset, text in enumerate(lines):
            origin = (12, canvas_height - 48 + offset * 18)
            cv2.putText(annotated, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(annotated, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

        return _write_image(target, annotated)
    except Exception as exc:
        logger.error("Overlay rendering failed for %s (%s: %s).", target, type(exc).__name__, exc)
        return False


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def status_for_score(score: float) -> str:
    """Specification bands: Good >= 70, Fair 40..69, Bad < 40."""
    try:
        numeric = float(score)
    except (TypeError, ValueError):
        numeric = 0.0
    if numeric >= 70:
        return "Good"
    if numeric >= 40:
        return "Fair"
    return "Bad"


def compute_rci(pothole_area_m2: float = 0.0, crack_area_m2: float = 0.0,
                pitch_deg: float = 0.0) -> int:
    """Road Condition Index: ``100 - (150*A_pothole + 50*A_crack + 5*|pitch|)``."""
    def _num(value: Any) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0.0
        return numeric if math.isfinite(numeric) else 0.0

    score = 100.0 - (
        150.0 * max(_num(pothole_area_m2), 0.0)
        + 50.0 * max(_num(crack_area_m2), 0.0)
        + 5.0 * abs(_num(pitch_deg))
    )
    return int(max(0, min(100, round(score))))


def score_segment(pothole_area_m2: float, crack_area_m2: float, pitch_deg: float,
                  pothole_count: int = 0) -> Dict[str, Any]:
    """Score one 10 m segment and apply the pothole hard override."""
    score = compute_rci(pothole_area_m2, crack_area_m2, pitch_deg)
    base_status = status_for_score(score)
    force_bad = bool(pothole_count) or float(pothole_area_m2 or 0) > 0
    return {
        "score": score,
        "status": "Bad" if force_bad else base_status,
        "base_status": base_status,
        "status_override": force_bad,
        "override_reason": "pothole_detected" if force_bad else None,
    }


def build_50m_groups(segments: Sequence[Dict[str, Any]], group_size: int = 5,
                     segment_length_m: float = SEGMENT_LENGTH_M) -> List[Dict[str, Any]]:
    """Roll consecutive 10 m segments up into ~50 m reporting buckets."""
    groups: List[Dict[str, Any]] = []
    for start in range(0, len(segments), group_size):
        chunk = list(segments[start:start + group_size])
        if not chunk:
            continue
        scores = [float(item.get("score") or 0) for item in chunk]
        average = int(round(sum(scores) / len(scores))) if scores else 0
        statuses = [str(item.get("status") or "") for item in chunk]
        if "Bad" in statuses:
            group_status = "Bad"
        elif "Fair" in statuses:
            group_status = "Fair"
        else:
            group_status = "Good"
        worst = min(chunk, key=lambda item: float(item.get("score") or 0))
        start_m = start * segment_length_m
        end_m = (start + len(chunk)) * segment_length_m
        groups.append(
            {
                "group_id": len(groups) + 1,
                "segment_count": len(chunk),
                "segment_ids": [item.get("segment_id") for item in chunk],
                "start_m": round(start_m, 2),
                "end_m": round(end_m, 2),
                "distance_range": f"{int(start_m)}-{int(end_m)}m",
                "score": average,
                "status": group_status,
                "pothole_area_m2": round(sum(float(i.get("pothole_area_m2") or 0) for i in chunk), 4),
                "crack_area_m2": round(sum(float(i.get("crack_area_m2") or 0) for i in chunk), 4),
                "defect_area_m2": round(sum(float(i.get("defect_area_m2") or 0) for i in chunk), 4),
                "has_pothole": any(bool(i.get("has_pothole")) for i in chunk),
                "mask_urls": [i.get("mask_url") for i in chunk if i.get("mask_url")],
                "worst_segment_id": worst.get("segment_id"),
                "recommendation": worst.get("recommendation"),
            }
        )
    return groups


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #
def _coerce_metadata(raw: Any) -> Dict[str, Any]:
    """Accept a dict, a JSON string, or ``None`` for the per-image metadata."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError as exc:
            logger.warning("Ignoring malformed metadata JSON (%s).", exc)
    return {}


def _extract_angles(metadata: Dict[str, Any]) -> Tuple[float, float]:
    """Read pitch/roll from nested ``imu`` (or flat keys) with safe defaults."""
    imu = metadata.get("imu") if isinstance(metadata.get("imu"), dict) else {}

    def _num(*values: Any) -> float:
        for value in values:
            try:
                if value is None or isinstance(value, bool):
                    continue
                numeric = float(value)
                if math.isfinite(numeric):
                    return numeric
            except (TypeError, ValueError):
                continue
        return 0.0

    return (
        _num(imu.get("pitch_deg"), metadata.get("pitch_deg")),
        _num(imu.get("roll_deg"), metadata.get("roll_deg")),
    )


def _object_name_for(image_path: Any, route_id: Optional[str], kind: str) -> str:
    """Build the S3 object key for an artefact.

    Layout (prefixes come from ``S3_RAW_PREFIX`` / ``S3_MASK_PREFIX`` so the
    lifecycle rule applied by ``scripts/setup_aws_resources.py`` always matches):

    * raw frames    -> ``uploads/<route_id>/<filename>``    (expired after 7 days)
    * mask overlays -> ``masks/<route_id>/mask_<filename>`` (retained)
    """
    path = Path(str(image_path))
    relative = Path(path.name)
    try:
        relative = path.resolve().relative_to(UPLOADS_DIR)
    except Exception:
        pass
    parent = "" if relative.parent.as_posix() in (".", "") else relative.parent.as_posix()
    folder = (route_id or parent).strip("/")
    body = f"{folder}/{relative.name}" if folder else relative.name
    return f"{object_key_prefix(kind)}{body}"


def _publish_artifacts(image_path: Any, mask_path: Any, route_id: Optional[str]) -> Dict[str, Any]:
    """Upload the raw image and the mask overlay to S3 (local URL on failure)."""
    payload: Dict[str, Any] = {
        "raw_url": to_local_url(image_path) if image_path else "",
        "mask_url": to_local_url(mask_path) if mask_path else "",
        "raw_object_key": None,
        "mask_object_key": None,
    }
    if image_path:
        object_name = _object_name_for(image_path, route_id, "raw")
        payload["raw_url"] = upload_file_to_s3(str(image_path), object_name)
        payload["raw_object_key"] = object_name
    if mask_path:
        object_name = _object_name_for(mask_path, route_id, "masks")
        payload["mask_url"] = upload_file_to_s3(str(mask_path), object_name)
        payload["mask_object_key"] = object_name
    return payload


def run_full_pipeline(images_data: list, *, route_id: Optional[str] = None,
                      camera_height_m: Optional[float] = None,
                      segment_length_m: float = SEGMENT_LENGTH_M) -> Dict[str, Any]:
    """Process every uploaded image of a route and return the full assessment.

    For each image the function runs :func:`process_image`, applies the RCI
    formula, enforces the pothole hard override, publishes the raw image plus the
    ``mask_*.jpg`` overlay to S3 and requests a Bedrock recommendation.  Results
    are grouped into 10 m segments (one image == one segment) and rolled up into
    50 m buckets.

    Pitch handling: the metadata ``imu.pitch_deg`` is the *deviation* of the
    device from its nominal mount.  The ground-plane physics need the absolute
    tilt (``CAMERA_MOUNT_PITCH_DEG + deviation``) while the RCI penalty needs the
    deviation, because a 25 degree mounting angle feeding ``5*|pitch|`` would
    floor every segment at 0 regardless of its actual condition.  Setting
    ``CAMERA_MOUNT_PITCH_DEG=0`` reproduces the literal specification behaviour.

    This function never raises: individual image failures are captured in the
    segment's ``error`` field so a partly broken route still produces a report.
    """
    started = time.perf_counter()
    if not isinstance(images_data, (list, tuple)):
        logger.warning("run_full_pipeline expected a list, received %r.", type(images_data))
        images_data = []

    segments: List[Dict[str, Any]] = []
    failures = 0

    for index, item in enumerate(images_data):
        entry = item if isinstance(item, dict) else {"image_path": item}
        image_path = entry.get("image_path") or entry.get("path") or entry.get("file_path")
        metadata = _coerce_metadata(entry.get("metadata"))
        pitch_deg, roll_deg = _extract_angles(metadata)
        absolute_pitch_deg = pitch_deg + CAMERA_MOUNT_PITCH_DEG
        gps = metadata.get("gps") if isinstance(metadata.get("gps"), dict) else {}
        try:
            segment_id = int(entry.get("segment_id") or index + 1)
        except (TypeError, ValueError):
            segment_id = index + 1
        image_route_id = entry.get("route_id") or route_id

        logger.info("Segment %d/%d -> %s (pitch deviation=%.2f, absolute=%.2f, roll=%.2f)",
                    segment_id, len(images_data), image_path, pitch_deg,
                    absolute_pitch_deg, roll_deg)

        result = process_image(
            image_path, absolute_pitch_deg, roll_deg,
            camera_height_m=camera_height_m,
            output_path=entry.get("mask_output_path"),
            save_overlay=bool(entry.get("save_overlay", True)),
        )
        if result.get("error"):
            failures += 1

        scoring = score_segment(
            result.get("pothole_area_m2", 0.0),
            result.get("crack_area_m2", 0.0),
            pitch_deg,
            pothole_count=int(result.get("pothole_count") or 0),
        )

        artifacts = _publish_artifacts(result.get("image_path"), result.get("mask_path"), image_route_id)

        recommendation = generate_road_recommendation(
            {        "segment_id": segment_id,
        "score": scoring["score"],
        "status": scoring["status"],
        "pothole_area_m2": result.get("pothole_area_m2", 0.0),
        "crack_area_m2": result.get("crack_area_m2", 0.0),
        "pitch_deg": pitch_deg,
        "absolute_pitch_deg": absolute_pitch_deg,
        "roll_deg": roll_deg,
        "gps": gps,
    }
        )

        segments.append(
            {
                "segment_id": segment_id,
                "index": index,
                "distance_m": f"{int((segment_id - 1) * segment_length_m)}"
                              f"-{int(segment_id * segment_length_m)}m",
                "image_path": result.get("image_path"),
                "filename": result.get("filename"),
                "gps": gps,
                "pitch_deg": round(pitch_deg, 4),
                "absolute_pitch_deg": round(absolute_pitch_deg, 4),
                "roll_deg": round(roll_deg, 4),
                "score": scoring["score"],
                "status": scoring["status"],
                "base_status": scoring["base_status"],
                "status_override": scoring["status_override"],
                "override_reason": scoring["override_reason"],
                "defect_area_m2": result.get("defect_area_m2", 0.0),
                "pothole_area_m2": result.get("pothole_area_m2", 0.0),
                "crack_area_m2": result.get("crack_area_m2", 0.0),
                "defect_area_integrated_m2": result.get("defect_area_integrated_m2", 0.0),
                "pothole_area_integrated_m2": result.get("pothole_area_integrated_m2", 0.0),
                "crack_area_integrated_m2": result.get("crack_area_integrated_m2", 0.0),
                "pothole_count": result.get("pothole_count", 0),
                "crack_count": result.get("crack_count", 0),
                "has_pothole": result.get("has_pothole", False),
                "has_defect": result.get("has_defect", False),
                "m2_per_pixel": result.get("m2_per_pixel", 0.0),
                "raw_url": artifacts["raw_url"],
                "mask_url": artifacts["mask_url"],
                "raw_object_key": artifacts["raw_object_key"],
                "mask_object_key": artifacts["mask_object_key"],
                "mask_local_url": result.get("mask_local_url") or "",
                "mask_path": result.get("mask_path"),
                "detections": result.get("detections", []),
                "class_mode": result.get("class_mode"),
                "recommendation": recommendation,
                "processing_ms": result.get("processing_ms", 0.0),
                "error": result.get("error"),
            }
        )

    # ------------------------------------------------------------------ route
    total_pothole = round(sum(float(seg["pothole_area_m2"]) for seg in segments), 4)
    total_crack = round(sum(float(seg["crack_area_m2"]) for seg in segments), 4)
    total_pothole_integrated = round(sum(float(seg.get("pothole_area_integrated_m2") or 0) for seg in segments), 4)
    total_crack_integrated = round(sum(float(seg.get("crack_area_integrated_m2") or 0) for seg in segments), 4)
    scores = [int(seg["score"]) for seg in segments]
    overall_score = int(round(sum(scores) / len(scores))) if scores else 0
    overall_status = status_for_score(overall_score)
    route_pothole = any(bool(seg.get("has_pothole")) for seg in segments)
    if route_pothole:
        overall_status = "Bad"

    mean_pitch = (
        round(sum(abs(float(seg["pitch_deg"])) for seg in segments) / len(segments), 4)
        if segments else 0.0
    )

    overall_recommendation = generate_road_recommendation(
        {
            "segment_id": "route",
            "score": overall_score,
            "status": overall_status,
            "pothole_area_m2": total_pothole,
            "crack_area_m2": total_crack,
            "pitch_deg": mean_pitch,
        }
    )

    payload = {
        "route_id": route_id,
        "status": overall_status,
        "overall_score": overall_score,
        "overall_status": overall_status,
        "recommendation": overall_recommendation,
        "segment_length_m": segment_length_m,
        "segments": segments,
        "segments_50m": build_50m_groups(segments, segment_length_m=segment_length_m),
        "summary": {
            "total_segments": len(segments),
            "failed_segments": failures,
            "good_segments": sum(1 for seg in segments if seg["status"] == "Good"),
            "fair_segments": sum(1 for seg in segments if seg["status"] == "Fair"),
            "bad_segments": sum(1 for seg in segments if seg["status"] == "Bad"),
            "pothole_segments": sum(1 for seg in segments if seg.get("has_pothole")),
            "pothole_detected": route_pothole,
            "total_pothole_area_m2": total_pothole,
            "total_crack_area_m2": total_crack,
            "total_defect_area_m2": round(total_pothole + total_crack, 4),
            "total_pothole_area_integrated_m2": total_pothole_integrated,
            "total_crack_area_integrated_m2": total_crack_integrated,
            "total_defect_area_integrated_m2": round(total_pothole_integrated + total_crack_integrated, 4),
            "mean_abs_pitch_deg": mean_pitch,
            "camera_mount_pitch_deg": CAMERA_MOUNT_PITCH_DEG,
            "latency_ms": round((time.perf_counter() - started) * 1000.0, 2),
        },
    }
    logger.info(
        "Route %s processed: %d segment(s), overall RCI %d (%s), %.4f m2 defect, %.0f ms.",
        route_id or "<unsaved>", len(segments), overall_score, overall_status,
        payload["summary"]["total_defect_area_m2"], payload["summary"]["latency_ms"],
    )
    return payload


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    import sys

    logging.basicConfig(level=logging.INFO)
    listing: Iterable[str] = sys.argv[1:]
    print(json.dumps(run_full_pipeline([{"image_path": path, "route_id": "cli"} for path in listing]), indent=2))
