"""Tests for the inclination (road grade) schema — task G1.

Owned by the ML role (`docs/ML_ROLE.md` section 1, ``backend/geometry/``).

Inclination is a **formal brief requirement** (final plan section 10) that must be
kept separate from surface condition, and it stays required until measured or
explicitly exempted by the judge. These tests pin the honesty rules the schema
enforces, not any claim about a real road's slope:

* ``null`` is not ``0`` — an unmeasured grade is ``None`` with a reason, a flat
  road is a measured ``0.0``.
* Longitudinal grade and crossfall are distinct; one can exist without the other.
* ``phone_pitch`` and ``google_elevation`` are **refused** as fine-scale grade
  truth (task G4) — constructing with them raises.
* A ``rig_imu`` grade is not ``valid`` until independently validated (task G3).

These are arithmetic and status-logic checks on synthetic values. They establish
nothing about live-camera inclination.
"""

from __future__ import annotations

import pytest

from backend.geometry import (
    GradeMeasurement,
    GradeSource,
    GradeValidity,
    grade_degrees_from_percent,
    grade_percent_from_degrees,
)


# --------------------------------------------------------------- conversions


def test_percent_and_degrees_round_trip():
    for pct in (-4.0, -1.0, 0.0, 1.0, 5.0, 12.5):
        deg = grade_degrees_from_percent(pct)
        assert grade_percent_from_degrees(deg) == pytest.approx(pct, abs=1e-9)


def test_zero_grade_is_flat():
    assert grade_degrees_from_percent(0.0) == 0.0
    assert grade_percent_from_degrees(0.0) == 0.0


def test_known_value_5_percent():
    # tan(atan(0.05)) = 0.05 -> 5%. Degrees should be ~2.862 degrees.
    assert grade_degrees_from_percent(5.0) == pytest.approx(2.862, abs=0.001)


def test_conversions_reject_nan():
    with pytest.raises(ValueError):
        grade_percent_from_degrees(float("nan"))
    with pytest.raises(ValueError):
        grade_degrees_from_percent(float("inf"))


# ------------------------------------------------- building a valid measurement


def test_from_percent_populates_both_representations():
    g = GradeMeasurement.from_percent(5.0, source=GradeSource.INCLINOMETER)
    assert g.grade_percent == 5.0
    assert g.grade_deg == pytest.approx(2.862, abs=0.001)
    assert g.is_valid is True
    assert g.validity is GradeValidity.VALID
    assert g.has_value is True


def test_from_degrees_is_consistent_with_percent():
    g = GradeMeasurement.from_degrees(2.8624, source=GradeSource.SURVEY)
    assert g.grade_percent == pytest.approx(5.0, abs=0.01)
    assert g.grade_deg == pytest.approx(2.8624, abs=1e-3)


def test_measured_flat_road_is_zero_not_null():
    # The flat-road case is a *measured* 0.0, and it is valid.
    g = GradeMeasurement.from_percent(0.0, source=GradeSource.INCLINOMETER)
    assert g.grade_percent == 0.0
    assert g.has_value is True
    assert g.is_valid is True


def test_uncertainty_and_capture_time_are_recorded():
    g = GradeMeasurement.from_percent(
        3.0,
        source=GradeSource.INCLINOMETER,
        uncertainty_percent=0.2,
        capture_time="2026-10-16T10:00:00Z",
    )
    assert g.uncertainty_percent == 0.2
    assert g.capture_time == "2026-10-16T10:00:00Z"
    assert g.describe()["uncertainty_percent"] == 0.2


# --------------------------------------------------- longitudinal vs crossfall


def test_crossfall_is_independent_of_longitudinal_grade():
    # A road can have longitudinal grade with zero crossfall (a crowned road
    # drained to one side), or crossfall on a flat longitudinal grade.
    g = GradeMeasurement.from_percent(
        4.0, source=GradeSource.INCLINOMETER, crossfall_percent=-1.5
    )
    assert g.grade_percent == 4.0
    assert g.crossfall_percent == -1.5

    flat = GradeMeasurement.from_percent(
        0.0, source=GradeSource.INCLINOMETER, crossfall_percent=2.0
    )
    assert flat.grade_percent == 0.0
    assert flat.crossfall_percent == 2.0


def test_crossfall_defaults_to_none():
    g = GradeMeasurement.from_percent(3.0, source=GradeSource.INCLINOMETER)
    assert g.crossfall_percent is None


# ---------------------------------------------- refused sources (task G4)


def test_phone_pitch_is_refused():
    # Task G4: a phone reports device pitch, not road grade. Constructing with
    # it must raise so nothing downstream can mistake it for a measurement.
    with pytest.raises(ValueError, match="not admissible"):
        GradeMeasurement.from_percent(3.0, source=GradeSource.PHONE_PITCH)


def test_google_elevation_is_refused():
    # Task G4: a public elevation model is a coarse regional trend, not a local
    # road slope. It too is refused at the boundary.
    with pytest.raises(ValueError, match="not admissible"):
        GradeMeasurement.from_percent(3.0, source=GradeSource.GOOGLE_ELEVATION)


def test_refused_sources_are_marked_not_admissible():
    assert GradeSource.PHONE_PITCH.is_admissible is False
    assert GradeSource.GOOGLE_ELEVATION.is_admissible is False
    assert GradeSource.INCLINOMETER.is_admissible is True
    assert GradeSource.RIG_IMU.is_admissible is True
    assert GradeSource.SURVEY.is_admissible is True


# --------------------------------------- unmeasured: null is not zero


def test_unmeasured_grade_is_null_not_zero():
    g = GradeMeasurement.unmeasured()
    # None, not 0.0 — the crucial honesty distinction.
    assert g.grade_percent is None
    assert g.grade_deg is None
    assert g.has_value is False
    assert g.is_valid is False
    assert g.validity is GradeValidity.UNMEASURED


def test_building_with_none_percent_yields_unmeasured():
    g = GradeMeasurement.from_percent(None, source=GradeSource.INCLINOMETER)
    assert g.grade_percent is None
    assert g.is_valid is False
    assert g.validity is GradeValidity.UNMEASURED


def test_unknown_source_produces_invalid_not_a_number():
    g = GradeMeasurement.unmeasured(source=GradeSource.UNKNOWN)
    assert g.validity is GradeValidity.UNMEASURED
    assert g.grade_percent is None


# ---------------------------------------------- uncalibrated sensor (G3)


def test_rig_imu_without_validation_is_uncalibrated():
    # Task G3: an automatic camera/IMU grade is conditional on independent
    # validation. Until that happens the value may be present but is NOT valid.
    g = GradeMeasurement.from_percent(2.0, source=GradeSource.RIG_IMU)
    assert g.grade_percent == 2.0          # value present
    assert g.is_calibrated is False
    assert g.is_valid is False
    assert g.validity is GradeValidity.UNCALIBRATED_SENSOR


def test_rig_imu_with_validation_is_valid():
    g = GradeMeasurement.from_percent(2.0, source=GradeSource.RIG_IMU, is_calibrated=True)
    assert g.is_calibrated is True
    assert g.is_valid is True
    assert g.validity is GradeValidity.VALID


def test_inclinometer_is_valid_without_extra_flag():
    # The human-verified straightedge path (G2) is the first supported path and
    # does not carry the sensor-validation gate.
    g = GradeMeasurement.from_percent(1.5, source=GradeSource.INCLINOMETER)
    assert g.is_valid is True


# ---------------------------------------------------------- describe() block


def test_describe_is_json_serializable_and_complete():
    import json

    g = GradeMeasurement.from_percent(
        4.0, source=GradeSource.SURVEY, crossfall_percent=-1.0
    )
    block = g.describe()
    # Must survive a JSON round-trip for the assessment record handed to backend.
    assert json.loads(json.dumps(block)) == block
    assert block["grade_percent"] == 4.0
    assert block["grade_source"] == "survey"
    assert block["is_valid"] is True
    assert "grade_deg" in block
    assert "crossfall_percent" in block
    assert "validity" in block

