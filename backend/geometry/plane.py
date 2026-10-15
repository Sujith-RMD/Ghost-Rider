"""Road-plane geometry: homography, projection and local metric scale.

Owned by the ML role (see ``docs/ML_ROLE.md`` section 1).

Implements the planar mapping described in final plan section 7.1: for an
undistorted image with world-to-camera pose ``[R|t]`` and a local road plane at
``Z = 0``, the plane-to-image homography is ``H = K [r1 r2 t]``. Inverting and
normalizing ``H`` lets areas and lengths be measured *on the plane* rather than
in the image.

Deliberate limitations (kept explicit so they cannot be forgotten):

* A flat-plane mapping yields *projected* dimensions only. Pothole walls, water
  depth and volumetric loss remain unmeasured.
* A camera attitude relative to gravity does not by itself give the changing
  camera-to-road-plane relationship.
* Local scale varies across an oblique view, so a single mm/pixel value is only
  valid for a small footprint. Use :func:`local_scale` instead of assuming one.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt

import numpy as np

__all__ = [
    "LocalScale",
    "as_homography",
    "plane_homography",
    "normalize_homography",
    "invert_homography",
    "apply_homography",
    "local_scale",
    "polygon_area",
    "project_points_to_plane",
]


@dataclass(frozen=True)
class LocalScale:
    """Local metric scale (mm per image pixel) at one image point.

    ``min``/``max`` are the singular values of the local Jacobian, i.e. the
    smallest and largest mm-per-pixel the mapping produces in any direction.
    ``mean`` is the equal-area scale ``sqrt(min * max)``.
    """

    min_mm_per_px: float
    max_mm_per_px: float
    mean_mm_per_px: float
    anisotropy: float

    def describe(self) -> dict:
        return {
            "min_mm_per_px": self.min_mm_per_px,
            "max_mm_per_px": self.max_mm_per_px,
            "mean_mm_per_px": self.mean_mm_per_px,
            "anisotropy": self.anisotropy,
        }


def as_homography(h: np.ndarray) -> np.ndarray:
    """Validate and return a normalized 3x3 homography as float64."""
    array = np.asarray(h, dtype=np.float64)
    if array.shape != (3, 3):
        raise ValueError(f"homography must be 3x3, got shape {array.shape}")
    if not np.all(np.isfinite(array)):
        raise ValueError("homography contains non-finite values")
    if abs(float(np.linalg.det(array))) < 1e-12:
        raise ValueError("homography is singular and cannot be inverted")
    return normalize_homography(array)


def normalize_homography(h: np.ndarray) -> np.ndarray:
    """Normalize so that ``H[2, 2] == 1`` (up to float precision)."""
    array = np.asarray(h, dtype=np.float64)
    if array.shape != (3, 3):
        raise ValueError(f"homography must be 3x3, got shape {array.shape}")
    scale = float(array[2, 2])
    if abs(scale) < 1e-12:
        raise ValueError("cannot normalize a homography with H[2, 2] == 0")
    return array / scale


def plane_homography(k: np.ndarray, r: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Plane-to-image homography ``H = K [r1 r2 t]``.

    Parameters
    ----------
    k:
        3x3 camera intrinsic matrix.
    r:
        3x3 world-to-camera rotation matrix (orthonormal).
    t:
        Translation from the world/plane frame origin to the camera, in the
        camera frame. Any unit system may be used consistently.
    """
    k = np.asarray(k, dtype=np.float64)
    r = np.asarray(r, dtype=np.float64)
    t = np.asarray(t, dtype=np.float64).reshape(-1)
    if k.shape != (3, 3):
        raise ValueError(f"K must be 3x3, got shape {k.shape}")
    if r.shape != (3, 3):
        raise ValueError(f"R must be 3x3, got shape {r.shape}")
    if t.shape != (3,):
        raise ValueError(f"t must have 3 elements, got shape {t.shape}")
    if not (np.all(np.isfinite(k)) and np.all(np.isfinite(r)) and np.all(np.isfinite(t))):
        raise ValueError("camera parameters contain non-finite values")
    h = k @ np.column_stack((r[:, 0], r[:, 1], t))
    return as_homography(h)


def invert_homography(h: np.ndarray) -> np.ndarray:
    """Return ``inv(H)`` normalized, validating the input first."""
    return normalize_homography(np.linalg.inv(as_homography(h)))


def apply_homography(h: np.ndarray, points: np.ndarray) -> np.ndarray:
    """Map ``(N, 2)`` points through ``H``, returning ``(N, 2)`` float64.

    Points mapped to or behind the horizon are rejected rather than silently
    returned with a wrapped sign.
    """
    h = as_homography(h)
    pts = np.asarray(points, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise ValueError(f"points must have shape (N, 2), got {pts.shape}")
    if not np.all(np.isfinite(pts)):
        raise ValueError("points contain non-finite values")
    homogeneous = np.column_stack((pts, np.ones(len(pts))))
    mapped = (h @ homogeneous.T).T
    w = mapped[:, 2]
    if np.any(np.abs(w) < 1e-12):
        raise ValueError("point maps to the horizon; the homography is undefined there")
    return mapped[:, :2] / w[:, None]


def local_scale(
    h: np.ndarray,
    image_point: tuple[float, float],
    mm_per_plane_unit: float = 1_000.0,
) -> LocalScale:
    """Local metric scale of the plane-to-image homography at an image point.

    ``h`` maps plane coordinates to image pixels, so the Jacobian of the inverse
    map gives plane-units per pixel, converted to mm per pixel with
    ``mm_per_plane_unit`` (the default 1000 assumes the plane is expressed in
    metres).

    A single global mm/pixel cannot describe an oblique view; this is the honest
    per-location value.
    """
    if not isfinite(float(mm_per_plane_unit)) or float(mm_per_plane_unit) <= 0.0:
        raise ValueError("mm_per_plane_unit must be a finite positive number")
    m = invert_homography(h)
    u, v = float(image_point[0]), float(image_point[1])
    if not (isfinite(u) and isfinite(v)):
        raise ValueError("image_point must contain finite values")

    den = m[2, 0] * u + m[2, 1] * v + m[2, 2]
    if abs(den) < 1e-12:
        raise ValueError("image_point lies on the horizon of the homography")
    num_x = m[0, 0] * u + m[0, 1] * v + m[0, 2]
    num_y = m[1, 0] * u + m[1, 1] * v + m[1, 2]

    dx_du = (m[0, 0] * den - m[2, 0] * num_x) / (den * den)
    dx_dv = (m[0, 1] * den - m[2, 1] * num_x) / (den * den)
    dy_du = (m[1, 0] * den - m[2, 0] * num_y) / (den * den)
    dy_dv = (m[1, 1] * den - m[2, 1] * num_y) / (den * den)

    # Jacobian maps image pixels -> plane units; convert to mm per pixel.
    jacobian = np.array([[dx_du, dx_dv], [dy_du, dy_dv]], dtype=np.float64)
    jacobian = jacobian * float(mm_per_plane_unit)
    singular_values = np.linalg.svd(jacobian, compute_uv=False)
    lo = float(np.min(singular_values))
    hi = float(np.max(singular_values))
    return LocalScale(
        min_mm_per_px=lo,
        max_mm_per_px=hi,
        mean_mm_per_px=sqrt(max(lo * hi, 0.0)),
        anisotropy=(hi / lo) if lo > 0.0 else float("inf"),
    )


def polygon_area(points: np.ndarray) -> float:
    """Absolute area of a simple polygon by the shoelace formula.

    Units are those of the supplied coordinates (so project to the plane first
    if a metric area is required).
    """
    pts = np.asarray(points, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 2:
        raise ValueError(f"points must have shape (N, 2), got {pts.shape}")
    if len(pts) < 3:
        raise ValueError("a polygon needs at least 3 points")
    if not np.all(np.isfinite(pts)):
        raise ValueError("points contain non-finite values")
    x = pts[:, 0]
    y = pts[:, 1]
    return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def project_points_to_plane(h: np.ndarray, image_points: np.ndarray) -> np.ndarray:
    """Map image pixels to plane coordinates using ``inv(H)``."""
    return apply_homography(invert_homography(h), image_points)
