"""Inclination (road grade) — a formal requirement kept separate from surface.

Owned by the ML role (``docs/ML_ROLE.md`` section 1, ``backend/geometry/`` is
ML-writable). Authority: ``docs/final_plan.md`` section 10 and ML_ROLE section 2
("Keep inclination separate from surface SQI").

Why this module exists at all: inclination is a **formal brief requirement**, not
an optional extra (final plan section 10). It stays a formal requirement until it
is either measured or **explicitly exempted by the judge**. It must never be
silently dropped, and it must never be folded into the surface-quality number — a
steep but smooth road is a *good surface* on a steep grade, and the two facts
have to survive independently in the record.

The honesty rules are built into the types rather than left to a caller:

* **``null`` is not ``0``.** ``0.0`` percent grade is a *measured flat* road. An
  unmeasured grade is ``None`` (``validity`` carries the reason). Confusing the
  two would turn "we did not measure the slope" into "the road is flat".
* **Longitudinal grade is not crossfall.** They are different measurements with
  different consequences, so they live in different fields and one may be present
  without the other.
* **Pitch-as-slope and Google elevation are rejected as fine-scale grade truth**
  (task G4). A phone's pitch is camera pitch, not road grade; a public elevation
  API is a coarse regional trend, not a local road slope. Both are refused at the
  boundary by :class:`GradeSource`, so nothing downstream can mistake them for a
  calibrated measurement.
* **Sensor-assisted paths are conditional** (task G3): an automatic camera/IMU
  grade is only admissible after synchronised alignment and independent
  validation. Until that validation exists the source may be constructed but the
  ``is_calibrated`` flag stays ``False`` and the value is not ``valid``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import atan, degrees, isfinite, tan, radians

__all__ = [
    "GradeSource",
    "GradeValidity",
    "GradeMeasurement",
    "grade_percent_from_degrees",
    "grade_degrees_from_percent",
]


class GradeSource(str, Enum):
    """Where a grade value came from, and therefore whether it may be trusted.

    The vocabulary is fixed by final plan section 10 and ML_ROLE section 2. The
    two refused sources are present *so that they can be refused explicitly* with
    a clear reason, rather than silently accepted or silently dropped.
    """

    INCLINOMETER = "inclinometer"
    """A calibrated inclinometer or phone level on a rigid straightedge — the
    first supported path (task G2): human-verified, zero-offset and repeatability
    validated, longitudinal grade distinguished from crossfall."""

    RIG_IMU = "rig_imu"
    """An automatic camera/IMU rig path. Conditional (task G3): admissible only
    after synchronised alignment and independent validation. ``is_calibrated``
    records whether that validation has happened."""

    SURVEY = "survey"
    """An engineering survey / known-control measurement."""

    REFERENCE_SURFACE = "reference_surface"
    """Grade measured off a physically measured reference plane in frame."""

    PHONE_PITCH = "phone_pitch"
    """**REFUSED** as grade truth (task G4). The phone reports device pitch, which
    mixes camera mounting angle with road slope. Building a ``GradeMeasurement``
    with this source raises."""

    GOOGLE_ELEVATION = "google_elevation"
    """**REFUSED** as fine-scale grade truth (task G4). A public elevation model
    is a coarse regional trend, far coarser than a single road segment."""

    UNKNOWN = "unknown"
    """No source could be established. Produces an invalid measurement, never a
    number."""

    @property
    def is_admissible(self) -> bool:
        """True for sources that may ever yield a valid grade."""
        return self not in (GradeSource.PHONE_PITCH, GradeSource.GOOGLE_ELEVATION)


class GradeValidity(str, Enum):
    """Why a grade is or is not usable. Travels with every measurement."""

    VALID = "valid"
    UNMEASURED = "unmeasured"
    UNCALIBRATED_SENSOR = "uncalibrated_sensor"



@dataclass(frozen=True)
class GradeMeasurement:
    """One road-grade observation.

    ``grade_percent`` and ``grade_deg`` are two representations of the same
    longitudinal slope; build with :meth:`from_percent` or :meth:`from_degrees`
    so they are always consistent. Crossfall is stored separately and optional.

    A measurement is only ``valid`` when it came from an admissible source, was
    actually measured, and (for a sensor path) has been independently validated.
    Everything else carries ``None`` values plus a :class:`GradeValidity` reason —
    never a fabricated ``0``.
    """

    grade_percent: float | None
    grade_deg: float | None
    crossfall_percent: float | None
    source: GradeSource
    validity: GradeValidity
    uncertainty_percent: float | None
    capture_time: str | None
    is_calibrated: bool
    notes: str | None

    @classmethod
    def from_percent(
        cls,
        percent: float | None,
        *,
        source: GradeSource,
        crossfall_percent: float | None = None,
        uncertainty_percent: float | None = None,
        capture_time: str | None = None,
        is_calibrated: bool = False,
        notes: str | None = None,
    ) -> "GradeMeasurement":
        """Build from a longitudinal grade in percent (rise/run x 100)."""
        return cls._build(
            percent,
            source=source,
            crossfall_percent=crossfall_percent,
            uncertainty_percent=uncertainty_percent,
            capture_time=capture_time,
            is_calibrated=is_calibrated,
            notes=notes,
        )

    @classmethod
    def from_degrees(
        cls,
        degrees_value: float | None,
        *,
        source: GradeSource,
        crossfall_percent: float | None = None,
        uncertainty_percent: float | None = None,
        capture_time: str | None = None,
        is_calibrated: bool = False,
        notes: str | None = None,
    ) -> "GradeMeasurement":
        """Build from a longitudinal grade in degrees of inclination."""
        percent = (
            None if degrees_value is None else grade_percent_from_degrees(degrees_value)
        )
        return cls._build(
            percent,
            source=source,
            crossfall_percent=crossfall_percent,
            uncertainty_percent=uncertainty_percent,
            capture_time=capture_time,
            is_calibrated=is_calibrated,
            notes=notes,
        )

    @classmethod
    def unmeasured(
        cls,
        *,
        source: GradeSource = GradeSource.UNKNOWN,
        notes: str | None = None,
    ) -> "GradeMeasurement":
        """An explicit "we did not measure the slope" record.

        Values are ``None``, never ``0`` — the flat-road case is a *measured*
        ``0.0``; this is the no-evidence case.
        """
        if not isinstance(source, GradeSource):
            raise TypeError("source must be a GradeSource")
        return cls(
            grade_percent=None,
            grade_deg=None,
            crossfall_percent=None,
            source=source,
            validity=GradeValidity.UNMEASURED,
            uncertainty_percent=None,
            capture_time=None,
            is_calibrated=False,
            notes=notes,
        )

    @classmethod
    def _build(
        cls,
        percent: float | None,
        *,
        source: GradeSource,
        crossfall_percent: float | None,
        uncertainty_percent: float | None,
        capture_time: str | None,
        is_calibrated: bool,
        notes: str | None,
    ) -> "GradeMeasurement":
        if not isinstance(source, GradeSource):
            raise TypeError("source must be a GradeSource")

        # Refused sources (G4) are rejected at the boundary, loudly.
        if not source.is_admissible:
            raise ValueError(
                f"{source.value!r} is not admissible as fine-scale grade truth "
                "(final plan section 10, task G4); use a calibrated inclinometer, "
                "survey or validated rig source instead"
            )

        if percent is None:
            return cls.unmeasured(source=source, notes=notes)

        value = float(percent)
        if not isfinite(value):
            raise ValueError("grade percent must be finite")

        # A sensor path is not valid until independently validated (G3).
        validity = (
            GradeValidity.UNCALIBRATED_SENSOR
            if (source is GradeSource.RIG_IMU and not is_calibrated)
            else GradeValidity.VALID
        )

        return cls(
            grade_percent=value,
            grade_deg=grade_degrees_from_percent(value),
            crossfall_percent=(
                None if crossfall_percent is None else float(crossfall_percent)
            ),
            source=source,
            validity=validity,
            uncertainty_percent=(
                None if uncertainty_percent is None else float(uncertainty_percent)
            ),
            capture_time=capture_time,
            is_calibrated=bool(is_calibrated),
            notes=notes,
        )

    @property
    def is_valid(self) -> bool:
        """A grade may only be cited downstream when this is ``True``."""
        return self.validity is GradeValidity.VALID

    @property
    def has_value(self) -> bool:
        """True when a numeric grade is present, regardless of admissibility."""
        return self.grade_percent is not None

    def describe(self) -> dict:
        """JSON-serializable block for the assessment record."""
        return {
            "grade_percent": self.grade_percent,
            "grade_deg": self.grade_deg,
            "crossfall_percent": self.crossfall_percent,
            "grade_source": self.source.value,
            "validity": self.validity.value,
            "is_valid": self.is_valid,
            "uncertainty_percent": self.uncertainty_percent,
            "capture_time": self.capture_time,
            "is_calibrated": self.is_calibrated,
            "notes": self.notes,
        }


# ------------------------------------------------------- unit conversions


def grade_percent_from_degrees(deg: float) -> float:
    """Inclination in percent from an angle in degrees: ``tan(theta) x 100``."""
    value = float(deg)
    if not isfinite(value):
        raise ValueError("degrees must be finite")
    return tan(radians(value)) * 100.0


def grade_degrees_from_percent(percent: float) -> float:
    """Inclination angle in degrees from a percent grade: ``atan(p/100)``."""
    value = float(percent)
    if not isfinite(value):
        raise ValueError("percent must be finite")
    return degrees(atan(value / 100.0))

