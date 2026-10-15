"""Physical planar scale for pavement imagery.

Owned by the ML role (see ``docs/ML_ROLE.md`` section 1).

Design rules taken from ``docs/final_plan.md``:

* ``null`` is not ``0``. An unscaled image has *no* metric area; it must never be
  relabelled as millimetres or square metres (final plan section 2, section 7.4).
* Cropping preserves scale; resizing changes it (final plan section 7.1). The
  lineage is tracked explicitly instead of copying one blanket mm/pixel value
  across dataset versions (final plan section 6.1 item 7).
* A relative linear-scale error approximately doubles in area, so uncertainty is
  propagated rather than dropped (final plan section 7.4).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite, pi, sqrt

__all__ = [
    "ScaleSource",
    "PlanarScale",
    "equivalent_diameter_mm",
    "UnscaledError",
]


class UnscaledError(ValueError):
    """Raised when a metric value is demanded from unscaled imagery."""


class ScaleSource(str, Enum):
    """Where a physical scale came from.

    These values are the vocabulary fixed by final plan section 6.1 item 7.
    """

    SOURCE_CALIBRATED = "source_calibrated"
    """Documented by the dataset author or supplying instrument."""

    RIG_CALIBRATED = "rig_calibrated"
    """Produced by our own calibration of a specific camera rig profile."""

    REFERENCE_MEASURED = "reference_measured"
    """Derived from a physically measured target visible in the frame."""

    UNSCALED = "unscaled"
    """No verified scale. Metric quantities are unavailable, not zero."""

    @property
    def is_metric(self) -> bool:
        return self is not ScaleSource.UNSCALED


@dataclass(frozen=True)
class PlanarScale:
    """Millimetres of road surface per pixel, per image axis.

    ``sx_mm_per_px``/``sy_mm_per_px`` are ``None`` exactly when the source is
    :attr:`ScaleSource.UNSCALED`. Build instances with :meth:`calibrated` or
    :meth:`unscaled` rather than the raw constructor.
    """

    sx_mm_per_px: float | None
    sy_mm_per_px: float | None
    source: ScaleSource
    provenance: str
    rel_uncertainty_x: float | None = None
    rel_uncertainty_y: float | None = None

    # ------------------------------------------------------------------ build

    def __post_init__(self) -> None:
        if not isinstance(self.source, ScaleSource):
            raise TypeError("source must be a ScaleSource")
        if self.source is ScaleSource.UNSCALED:
            if self.sx_mm_per_px is not None or self.sy_mm_per_px is not None:
                raise ValueError(
                    "unscaled imagery must not carry a mm/pixel value; "
                    "use PlanarScale.calibrated(...) when a verified scale exists"
                )
        else:
            for name, value in (
                ("sx_mm_per_px", self.sx_mm_per_px),
                ("sy_mm_per_px", self.sy_mm_per_px),
            ):
                if value is None or not isfinite(float(value)) or float(value) <= 0.0:
                    raise ValueError(
                        f"{name} must be a finite positive number for a calibrated scale"
                    )
        for name, value in (
            ("rel_uncertainty_x", self.rel_uncertainty_x),
            ("rel_uncertainty_y", self.rel_uncertainty_y),
        ):
            if value is not None and (not isfinite(float(value)) or float(value) < 0.0):
                raise ValueError(f"{name} must be a finite non-negative number or None")
        if not isinstance(self.provenance, str):
            raise TypeError("provenance must be a string")

    @classmethod
    def calibrated(
        cls,
        sx_mm_per_px: float,
        sy_mm_per_px: float,
        source: ScaleSource,
        provenance: str,
        rel_uncertainty_x: float | None = None,
        rel_uncertainty_y: float | None = None,
    ) -> "PlanarScale":
        """Create a scaled instance. ``source`` must not be ``UNSCALED``."""
        if source is ScaleSource.UNSCALED:
            raise ValueError(
                "use PlanarScale.unscaled(...) when no verified scale exists"
            )
        return cls(
            sx_mm_per_px=float(sx_mm_per_px),
            sy_mm_per_px=float(sy_mm_per_px),
            source=source,
            provenance=provenance,
            rel_uncertainty_x=rel_uncertainty_x,
            rel_uncertainty_y=rel_uncertainty_y,
        )

    @classmethod
    def unscaled(cls, provenance: str = "") -> "PlanarScale":
        """Create the explicit no-scale state (metric outputs become ``None``)."""
        return cls(
            sx_mm_per_px=None,
            sy_mm_per_px=None,
            source=ScaleSource.UNSCALED,
            provenance=provenance,
        )

    # ------------------------------------------------------------- properties

    @property
    def is_scaled(self) -> bool:
        return self.source.is_metric

    @property
    def equivalent_mm_per_px(self) -> float | None:
        """Equal-area isotropic scale: ``sqrt(sx * sy)``.

        Valid for area-derived equivalent diameters, not directional lengths.
        Gap lengths must transform their x/y displacements separately.
        ``None`` when unscaled.
        """
        if not self.is_scaled:
            return None
        return sqrt(float(self.sx_mm_per_px) * float(self.sy_mm_per_px))

    @property
    def pixel_area_mm2(self) -> float | None:
        """Physical area of one pixel in mm^2, or ``None`` when unscaled."""
        if not self.is_scaled:
            return None
        return float(self.sx_mm_per_px) * float(self.sy_mm_per_px)

    # -------------------------------------------------------------- geometry

    def area_m2(self, pixel_count: float) -> float | None:
        """Physical area of ``pixel_count`` pixels.

        Implements ``valid_pixels x sx x sy / 1_000_000`` from final plan
        section 7.1. Returns ``None`` when unscaled, and ``0.0`` only for a
        genuinely measured empty region.
        """
        if pixel_count is None:
            raise TypeError("pixel_count must be a number, not None")
        pixel_count = float(pixel_count)
        if not isfinite(pixel_count) or pixel_count < 0.0:
            raise ValueError("pixel_count must be a finite non-negative number")
        pixel_area = self.pixel_area_mm2
        if pixel_area is None:
            return None
        return pixel_count * pixel_area / 1_000_000.0

    def require_scaled(self) -> "PlanarScale":
        """Raise :class:`UnscaledError` unless a verified scale exists.

        For code paths that must not silently continue without metric geometry.
        """
        if not self.is_scaled:
            raise UnscaledError(
                f"metric geometry requested from unscaled imagery (provenance={self.provenance!r})"
            )
        return self

    def cropped(self) -> "PlanarScale":
        """Cropping preserves scale, so the scale is unchanged (final plan 7.1)."""
        return self

    def resized(self, fx: float, fy: float) -> "PlanarScale":
        """Scale lineage through a resize by factors ``fx``/``fy``.

        ``fx`` is ``new_width / old_width``. Down-sampling by two halves the pixel
        count per axis, so mm/pixel doubles. Resizing unscaled imagery stays
        unscaled.
        """
        for name, value in (("fx", fx), ("fy", fy)):
            if value is None or not isfinite(float(value)) or float(value) <= 0.0:
                raise ValueError(f"{name} must be a finite positive number")
        if not self.is_scaled:
            return PlanarScale.unscaled(
                provenance=f"{self.provenance} [resized x{float(fx):g}, x{float(fy):g}]".strip()
            )
        return PlanarScale.calibrated(
            sx_mm_per_px=float(self.sx_mm_per_px) / float(fx),
            sy_mm_per_px=float(self.sy_mm_per_px) / float(fy),
            source=self.source,
            provenance=f"{self.provenance} [resized x{float(fx):g}, x{float(fy):g}]".strip(),
            rel_uncertainty_x=self.rel_uncertainty_x,
            rel_uncertainty_y=self.rel_uncertainty_y,
        )

    def relative_area_uncertainty(self) -> float | None:
        """First-order relative uncertainty of an area.

        Area is a product of two independent linear scales, so relative
        variances add: ``sqrt(rx^2 + ry^2)``. ``None`` when either input is
        unknown or the scale is unscaled.
        """
        if not self.is_scaled:
            return None
        if self.rel_uncertainty_x is None or self.rel_uncertainty_y is None:
            return None
        rx = float(self.rel_uncertainty_x)
        ry = float(self.rel_uncertainty_y)
        return sqrt(rx * rx + ry * ry)

    # ------------------------------------------------------------- provenance

    def describe(self) -> dict:
        """JSON-serializable provenance block for the assessment record."""
        return {
            "scale_source": self.source.value,
            "sx_mm_per_px": self.sx_mm_per_px,
            "sy_mm_per_px": self.sy_mm_per_px,
            "equivalent_mm_per_px": self.equivalent_mm_per_px,
            "rel_uncertainty_x": self.rel_uncertainty_x,
            "rel_uncertainty_y": self.rel_uncertainty_y,
            "relative_area_uncertainty": self.relative_area_uncertainty(),
            "scale_provenance": self.provenance,
        }


def equivalent_diameter_mm(projected_area_mm2: float) -> float:
    """Equivalent diameter ``sqrt(4 * A / pi)`` of a 2D projected area.

    This is the exposed 2D appearance of a particle, not its sieve size or
    internal gradation (final plan section 7.3).
    """
    if projected_area_mm2 is None:
        raise TypeError("projected_area_mm2 must be a number, not None")
    area = float(projected_area_mm2)
    if not isfinite(area) or area < 0.0:
        raise ValueError("projected_area_mm2 must be a finite non-negative number")
    return sqrt(4.0 * area / pi)
