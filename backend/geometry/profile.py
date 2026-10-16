"""Fail-closed capture/profile gate for a future camera adapter.

This is not a calibration estimator or a frame/road-plane stability check.
Adapters must report actual capture settings, not requested defaults. Focus is
an exact, locked focus-state identifier (including lens/enclosure configuration);
zoom includes optical and digital zoom. Dynamic/unknown settings use ``None``.
Crop is a normalized sensor rectangle (left, top, width, height); explicitly use
(0, 0, 1, 1) for no capture crop. This is distinct from downstream image cropping,
which continues to preserve scale under :meth:`PlanarScale.cropped`.

A recheck creates a new immutable validation/profile; compatibility never
silently rescales or promotes an old calibration. Evidence is supplied by the
caller: this module cannot authenticate a physical calibration report.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
from math import isfinite

from .scale import PlanarScale


class ProfileReason(str, Enum):
    PROFILE_MISSING = "profile_missing"
    CAPTURE_UNKNOWN = "capture_unknown"
    PROFILE_SIGNATURE_UNKNOWN = "profile_signature_unknown"
    DEVICE_CHANGED = "device_changed"
    RESOLUTION_CHANGED = "resolution_changed"
    FOCUS_CHANGED = "focus_changed"
    ZOOM_CHANGED = "zoom_changed"
    CROP_CHANGED = "crop_changed"
    STABILIZATION_CHANGED = "stabilization_changed"
    MOUNT_CHANGED = "mount_changed"
    VALIDATION_MISSING = "validation_missing"
    VALIDATION_FAILED = "validation_failed"
    VALIDATION_PROVENANCE_MISSING = "validation_provenance_missing"
    VALIDATION_SIGNATURE_MISMATCH = "validation_signature_mismatch"
    VALIDATION_SCALE_MISMATCH = "validation_scale_mismatch"
    SCALE_UNAVAILABLE = "scale_unavailable"
    SCALE_PROVENANCE_MISSING = "scale_provenance_missing"


def _known_text(value: object) -> bool:
    return isinstance(value, str) and value.strip().lower() not in ("", "unknown", "unvalidated")


def _number(value: object) -> bool:
    return type(value) in (int, float) and isfinite(value)


@dataclass(frozen=True)
class CaptureSignature:
    """Exact capture geometry identity; ``None`` means unknown, never a wildcard.

    Mount ID must change after remounting or geometry changes. Stabilization
    identifies the verified mode/state; ``"off"`` is known, ``None`` is not.
    All members are immutable scalars/tuples; mutable input is rejected.
    """

    device_id: str | None = None
    resolution: tuple[int, int] | None = None
    focus: str | None = None
    zoom: float | None = None
    crop: tuple[float, float, float, float] | None = None
    stabilization: str | None = None
    mount_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("device_id", "focus", "stabilization", "mount_id"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{name} must be a string or None")
        if self.resolution is not None:
            if (type(self.resolution) is not tuple or len(self.resolution) != 2
                    or any(type(v) is not int or v <= 0 for v in self.resolution)):
                raise ValueError("resolution must be a positive integer (width, height) tuple")
        if self.zoom is not None and (not _number(self.zoom) or self.zoom <= 0):
            raise ValueError("zoom must be finite and positive or None")
        if self.crop is not None:
            if (type(self.crop) is not tuple or len(self.crop) != 4
                    or not all(_number(v) for v in self.crop)):
                raise ValueError("crop must be a finite normalized rectangle tuple")
            x, y, width, height = self.crop
            if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 1 or y + height > 1:
                raise ValueError("crop must lie within the normalized sensor bounds")

    @property
    def unknown_fields(self) -> tuple[str, ...]:
        return tuple(
            field.name for field in fields(self)
            if getattr(self, field.name) is None
            or (isinstance(getattr(self, field.name), str)
                and not _known_text(getattr(self, field.name)))
        )


@dataclass(frozen=True)
class CalibrationValidation:
    """Caller-supplied held-out physical validation, bound to signature and scale.

    IDs identify the calibration artifact and recheck report. Provenance must
    identify the independent distance checks, their acceptance criteria and
    outcome (including center/corners as applicable); no universal threshold is
    invented here. ``checked_at`` is a report timestamp, not an expiry policy.
    Missing evidence is representable, but cannot authorize metric use.
    """

    signature: CaptureSignature
    scale: PlanarScale
    calibration_id: str | None = None
    validation_id: str | None = None
    checked_at: str | None = None
    provenance: str | None = None
    passed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.signature, CaptureSignature):
            raise TypeError("signature must be a CaptureSignature")
        if not isinstance(self.scale, PlanarScale):
            raise TypeError("scale must be a PlanarScale")
        if type(self.passed) is not bool:
            raise TypeError("passed must be a bool")
        for name in ("calibration_id", "validation_id", "checked_at", "provenance"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{name} must be a string or None")


@dataclass(frozen=True)
class CameraProfile:
    signature: CaptureSignature
    scale: PlanarScale
    validation: CalibrationValidation | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.signature, CaptureSignature):
            raise TypeError("signature must be a CaptureSignature")
        if not isinstance(self.scale, PlanarScale):
            raise TypeError("scale must be a PlanarScale")
        if self.validation is not None and not isinstance(self.validation, CalibrationValidation):
            raise TypeError("validation must be a CalibrationValidation or None")

    def evaluate(self, current: CaptureSignature | None) -> ProfileCompatibility:
        return evaluate_capture(self, current)

    def require_scale(self, current: CaptureSignature | None) -> PlanarScale:
        """Enforce compatibility before passing the scale into metric code."""
        result = self.evaluate(current)
        if result.scale is None:
            raise IncompatibleProfileError(result)
        return result.scale


@dataclass(frozen=True)
class ProfileCompatibility:
    reasons: tuple[ProfileReason, ...]
    scale: PlanarScale | None

    @property
    def compatible(self) -> bool:
        return not self.reasons


class IncompatibleProfileError(ValueError):
    def __init__(self, result: ProfileCompatibility) -> None:
        self.result = result
        super().__init__(", ".join(reason.value for reason in result.reasons))


_CHANGE_REASONS = (
    ProfileReason.DEVICE_CHANGED, ProfileReason.RESOLUTION_CHANGED,
    ProfileReason.FOCUS_CHANGED, ProfileReason.ZOOM_CHANGED,
    ProfileReason.CROP_CHANGED, ProfileReason.STABILIZATION_CHANGED,
    ProfileReason.MOUNT_CHANGED,
)


def evaluate_capture(
    profile: CameraProfile | None, current: CaptureSignature | None,
) -> ProfileCompatibility:
    """Return all applicable reasons in stable order and no scale on failure.

    This is a stateless check of the supplied current capture. The adapter must
    call it for each capture and retire profiles after an observed rig change;
    it cannot detect unreported changes or a change-and-return between calls.
    """
    if profile is not None and not isinstance(profile, CameraProfile):
        raise TypeError("profile must be a CameraProfile or None")
    if current is not None and not isinstance(current, CaptureSignature):
        raise TypeError("current must be a CaptureSignature or None")
    reasons = []
    if profile is None:
        reasons.append(ProfileReason.PROFILE_MISSING)
    if current is None or current.unknown_fields:
        reasons.append(ProfileReason.CAPTURE_UNKNOWN)
    if profile is None:
        return ProfileCompatibility(tuple(reasons), None)
    if profile.signature.unknown_fields:
        reasons.append(ProfileReason.PROFILE_SIGNATURE_UNKNOWN)
    if current is not None:
        for field, reason in zip(fields(CaptureSignature), _CHANGE_REASONS):
            old, new = getattr(profile.signature, field.name), getattr(current, field.name)
            if field.name not in profile.signature.unknown_fields and field.name not in current.unknown_fields and old != new:
                reasons.append(reason)
    validation = profile.validation
    if validation is None:
        reasons.append(ProfileReason.VALIDATION_MISSING)
    else:
        if not validation.passed:
            reasons.append(ProfileReason.VALIDATION_FAILED)
        if not all(_known_text(getattr(validation, name)) for name in (
            "calibration_id", "validation_id", "checked_at", "provenance",
        )):
            reasons.append(ProfileReason.VALIDATION_PROVENANCE_MISSING)
        if validation.signature != profile.signature:
            reasons.append(ProfileReason.VALIDATION_SIGNATURE_MISMATCH)
        if validation.scale != profile.scale:
            reasons.append(ProfileReason.VALIDATION_SCALE_MISMATCH)
    if not profile.scale.is_scaled:
        reasons.append(ProfileReason.SCALE_UNAVAILABLE)
    if not _known_text(profile.scale.provenance):
        reasons.append(ProfileReason.SCALE_PROVENANCE_MISSING)
    return ProfileCompatibility(tuple(reasons), None if reasons else profile.scale)
