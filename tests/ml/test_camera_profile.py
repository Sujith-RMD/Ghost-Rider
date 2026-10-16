"""Synthetic contract tests, not evidence of real camera calibration."""

from dataclasses import FrozenInstanceError, fields, replace

import pytest

from backend.geometry.profile import (
    CalibrationValidation,
    CameraProfile,
    CaptureSignature,
    IncompatibleProfileError,
    ProfileReason as R,
    evaluate_capture,
)
from backend.geometry.scale import PlanarScale, ScaleSource


@pytest.fixture
def signature():
    return CaptureSignature(
        device_id="test-device/lens-1", resolution=(1920, 1080),
        focus="locked:position-42/enclosure-A", zoom=1.0,
        crop=(0.0, 0.0, 1.0, 1.0), stabilization="off", mount_id="test-mount-v1",
    )


@pytest.fixture
def profile(signature):
    scale = PlanarScale.calibrated(
        0.5, 0.6, ScaleSource.RIG_CALIBRATED,
        "synthetic fixture only: measured target", 0.01, 0.02,
    )
    validation = CalibrationValidation(
        signature, scale, calibration_id="synthetic-calibration-1",
        validation_id="synthetic-recheck-1", checked_at="2026-10-16T12:00:00Z",
        provenance="synthetic held-out center/corner distances; fixture criteria passed",
        passed=True,
    )
    return CameraProfile(signature, scale, validation)


def assert_blocked(profile, current, *reasons):
    result = evaluate_capture(profile, current)
    assert not result.compatible
    assert result.scale is None
    assert result.reasons == reasons
    if profile is not None:
        with pytest.raises(IncompatibleProfileError) as exc:
            profile.require_scale(current)
        assert exc.value.result == result
        assert all(reason.value in str(exc.value) for reason in reasons)


def test_exact_validated_capture_reuses_scale_without_guessing(profile, signature):
    result = profile.evaluate(signature)
    assert result.compatible
    assert result.reasons == ()
    assert result.scale is profile.scale
    assert profile.require_scale(signature) is profile.scale
    assert result.scale.sx_mm_per_px == 0.5
    assert result.scale.sy_mm_per_px == 0.6
    assert result.scale.rel_uncertainty_x == 0.01


CHANGES = [
    ("device_id", "other-device", R.DEVICE_CHANGED),
    ("resolution", (1280, 720), R.RESOLUTION_CHANGED),
    ("focus", "locked:position-43/enclosure-A", R.FOCUS_CHANGED),
    ("zoom", 1.01, R.ZOOM_CHANGED),
    ("crop", (0.1, 0.0, 0.9, 1.0), R.CROP_CHANGED),
    ("stabilization", "enabled:state-1", R.STABILIZATION_CHANGED),
    ("mount_id", "remounted-v2", R.MOUNT_CHANGED),
]


@pytest.mark.parametrize("name,value,reason", CHANGES)
def test_each_changed_capture_state_blocks_old_profile(profile, signature, name, value, reason):
    assert_blocked(profile, replace(signature, **{name: value}), reason)


@pytest.mark.parametrize("name,value,reason", CHANGES)
def test_editing_profile_signature_without_recheck_does_not_revalidate(
    profile, signature, name, value, reason,
):
    changed = replace(signature, **{name: value})
    assert_blocked(replace(profile, signature=changed), changed, R.VALIDATION_SIGNATURE_MISMATCH)
    # Only explicit evidence for the changed signature authorizes its use.
    rechecked = replace(
        profile, signature=changed,
        validation=replace(profile.validation, signature=changed, validation_id="new-recheck"),
    )
    assert rechecked.require_scale(changed) is profile.scale
    assert profile.signature == signature


@pytest.mark.parametrize("name", [f.name for f in fields(CaptureSignature)])
def test_unknown_current_field_is_not_a_wildcard(profile, signature, name):
    assert_blocked(profile, replace(signature, **{name: None}), R.CAPTURE_UNKNOWN)


@pytest.mark.parametrize("name", [f.name for f in fields(CaptureSignature)])
def test_matching_unknown_profile_and_current_never_pass(profile, signature, name):
    unknown = replace(signature, **{name: None})
    candidate = replace(profile, signature=unknown,
                        validation=replace(profile.validation, signature=unknown))
    assert_blocked(candidate, unknown, R.CAPTURE_UNKNOWN, R.PROFILE_SIGNATURE_UNKNOWN)


@pytest.mark.parametrize("name", ["device_id", "focus", "stabilization", "mount_id"])
@pytest.mark.parametrize("value", ["", "  ", "unknown", " Unvalidated "])
def test_unknown_text_fails_closed(profile, signature, name, value):
    assert_blocked(profile, replace(signature, **{name: value}), R.CAPTURE_UNKNOWN)


def test_missing_profile_or_current(profile, signature):
    assert_blocked(None, signature, R.PROFILE_MISSING)
    assert_blocked(None, None, R.PROFILE_MISSING, R.CAPTURE_UNKNOWN)
    assert_blocked(profile, None, R.CAPTURE_UNKNOWN)


def test_all_changes_are_reported_in_stable_order(profile, signature):
    changed = replace(signature, **{name: value for name, value, _ in CHANGES})
    assert_blocked(profile, changed, *(reason for _, _, reason in CHANGES))


def test_unvalidated_and_failed_profiles(profile, signature):
    assert_blocked(replace(profile, validation=None), signature, R.VALIDATION_MISSING)
    failed = replace(profile.validation, passed=False)
    assert_blocked(replace(profile, validation=failed), signature, R.VALIDATION_FAILED)


@pytest.mark.parametrize("name", ["calibration_id", "validation_id", "checked_at", "provenance"])
@pytest.mark.parametrize("value", [None, "", "  ", "unknown", "unvalidated"])
def test_validation_requires_all_provenance(profile, signature, name, value):
    validation = replace(profile.validation, **{name: value})
    assert_blocked(replace(profile, validation=validation), signature, R.VALIDATION_PROVENANCE_MISSING)


def test_swapping_scale_requires_revalidation(profile, signature):
    changed_scale = replace(profile.scale, sx_mm_per_px=0.25)
    assert_blocked(replace(profile, scale=changed_scale), signature, R.VALIDATION_SCALE_MISMATCH)


@pytest.mark.parametrize("provenance", ["", " ", "unknown"])
def test_scale_provenance_is_required_even_with_validation(profile, signature, provenance):
    scale = replace(profile.scale, provenance=provenance)
    candidate = replace(profile, scale=scale, validation=replace(profile.validation, scale=scale))
    assert_blocked(candidate, signature, R.SCALE_PROVENANCE_MISSING)


def test_no_validation_flag_can_invent_metric_scale(profile, signature):
    scale = PlanarScale.unscaled("synthetic: no physical geometry available")
    candidate = replace(profile, scale=scale, validation=replace(profile.validation, scale=scale))
    assert_blocked(candidate, signature, R.SCALE_UNAVAILABLE)
    assert scale.area_m2(100) is None


def test_capture_crop_gate_does_not_change_downstream_crop_semantics(profile, signature):
    assert profile.scale.cropped() is profile.scale
    assert_blocked(profile, replace(signature, crop=(0.0, 0.0, 0.5, 1.0)), R.CROP_CHANGED)


def test_multiple_missing_evidence_paths_are_not_short_circuited(signature):
    candidate = CameraProfile(CaptureSignature(), PlanarScale.unscaled())
    assert_blocked(candidate, None, R.CAPTURE_UNKNOWN, R.PROFILE_SIGNATURE_UNKNOWN,
                   R.VALIDATION_MISSING, R.SCALE_UNAVAILABLE, R.SCALE_PROVENANCE_MISSING)


@pytest.mark.parametrize("name,value", [
    ("resolution", [1920, 1080]), ("resolution", (True, 1080)),
    ("resolution", (0, 1080)), ("resolution", (1920,)),
    ("zoom", 0), ("zoom", -1), ("zoom", float("nan")),
    ("zoom", float("inf")), ("zoom", True), ("zoom", "1"),
    ("crop", [0, 0, 1, 1]), ("crop", (0, 0, 1)),
    ("crop", (0, 0, float("nan"), 1)), ("crop", (-0.1, 0, 1, 1)),
    ("crop", (0.1, 0, 1, 1)), ("crop", (0, 0, 0, 1)),
    ("crop", (0, 0, 1, 1.1)), ("crop", (False, 0, 1, 1)),
])
def test_malformed_geometry_rejected(signature, name, value):
    with pytest.raises(ValueError):
        replace(signature, **{name: value})


@pytest.mark.parametrize("name", ["device_id", "focus", "stabilization", "mount_id"])
def test_mutable_or_wrong_text_rejected(signature, name):
    with pytest.raises(TypeError):
        replace(signature, **{name: []})


def test_records_are_immutable(profile, signature):
    for record, name, value in (
        (signature, "zoom", 2.0), (profile, "validation", None),
        (profile.validation, "passed", False),
        (profile.evaluate(signature), "scale", None),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(record, name, value)


@pytest.mark.parametrize("operation", [
    lambda p, s: CameraProfile(None, p.scale),
    lambda p, s: CameraProfile(s, None),
    lambda p, s: CameraProfile(s, p.scale, {}),
    lambda p, s: replace(p.validation, signature=None),
    lambda p, s: replace(p.validation, scale=None),
    lambda p, s: replace(p.validation, passed="true"),
    lambda p, s: replace(p.validation, provenance=[]),
    lambda p, s: evaluate_capture({}, s),
    lambda p, s: evaluate_capture(p, {}),
])
def test_wrong_api_types_cannot_bypass_gate(profile, signature, operation):
    with pytest.raises(TypeError):
        operation(profile, signature)
