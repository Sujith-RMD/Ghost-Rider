"""Tests for the image-quality validity gate.

Owned by the ML role (`docs/ML_ROLE.md` section 1, `backend/quality/`).

Final plan section 7.2 requires rejecting or suppressing affected metrics for
decode failure, absent scale, excessive blur, clipping/glare, invalid surface,
changed zoom/crop, unstable plane and inadequate source resolution. Section 7.2
also warns that one universal Laplacian threshold can mistake smooth good asphalt
for blur - so these tests check the *wiring and the units*, never that a threshold
is scientifically calibrated. The policy carries an explicit
`thresholds_calibrated` flag, and the tests assert it stays false while no camera
rig exists (task C11 is blocked on hardware).

These tests are arithmetic and status logic on synthetic images. They establish
nothing about real road imagery.
"""

from __future__ import annotations

import numpy as np
import pytest

from backend.quality import (
    QUALITY_STATUSES,
    REASON_CODES,
    QualityPolicy,
    classify_quality,
    image_metrics,
)


def _textured(height: int = 320, width: int = 320, seed: int = 0) -> np.ndarray:
    """A deterministic noise image: sharp, mid-range, unclipped.

    Default size is above the policy's 256 px source minimum so these cases
    exercise sharpness and clipping rather than resolution.
    """
    rng = np.random.default_rng(seed)
    return rng.integers(60, 200, size=(height, width), dtype=np.uint8)


def _flat(value: int = 128, height: int = 320, width: int = 320) -> np.ndarray:
    return np.full((height, width), value, dtype=np.uint8)


# --------------------------------------------------------------- metric plumbing


def test_metrics_report_size_channels_and_sharpness():
    metrics = image_metrics(_textured())
    assert metrics["decode_ok"] is True
    assert metrics["width"] == 320
    assert metrics["height"] == 320
    assert metrics["channels"] == 1
    assert metrics["laplacian_variance"] > 0.0
    assert metrics["dynamic_range"] > 40


def test_metrics_accept_a_colour_image_and_report_three_channels():
    metrics = image_metrics(np.repeat(_textured(64, 64)[:, :, None], 3, axis=2))
    assert metrics["channels"] == 3
    assert metrics["decode_ok"] is True


def test_metrics_of_a_none_image_report_a_decode_failure_not_an_exception():
    # Final plan section 6.1 item 2: record failures rather than silently skipping.
    metrics = image_metrics(None)
    assert metrics["decode_ok"] is False
    assert metrics["laplacian_variance"] is None


def test_metrics_of_an_empty_image_report_a_decode_failure():
    assert image_metrics(np.zeros((0, 0), dtype=np.uint8))["decode_ok"] is False


# ------------------------------------------------------------------ status logic


def test_a_sharp_clean_image_is_accepted():
    report = classify_quality(_textured())
    assert report.status == "accepted"
    assert report.reason_codes == ()


def test_missing_image_is_rejected_for_decode_failure():
    report = classify_quality(None)
    assert report.status == "rejected"
    assert REASON_CODES["decode_failed"] in report.reason_codes


def test_a_flat_image_is_rejected_as_insufficiently_sharp():
    # A constant image has zero Laplacian variance; nothing is measurable in it.
    report = classify_quality(_flat())
    assert report.status == "rejected"
    assert REASON_CODES["insufficient_sharpness"] in report.reason_codes


def test_a_glare_clipped_image_is_rejected_and_the_code_says_which_end():
    bright = _textured()
    bright[:100, :] = 255  # half the frame blown out
    report = classify_quality(bright)
    assert report.status == "rejected"
    assert REASON_CODES["clipped_highlights"] in report.reason_codes
    assert REASON_CODES["clipped_shadows"] not in report.reason_codes

    dark = _textured()
    dark[:100, :] = 0
    report_dark = classify_quality(dark)
    assert REASON_CODES["clipped_shadows"] in report_dark.reason_codes


def test_an_image_below_the_declared_source_resolution_is_rejected():
    # final plan section 7.2: reject metrics when the source resolution is inadequate.
    report = classify_quality(_textured(64, 64), QualityPolicy(min_source_px=256))
    assert report.status == "rejected"
    assert REASON_CODES["inadequate_source_resolution"] in report.reason_codes


def test_a_missing_scale_limits_the_result_but_is_not_an_image_defect():
    # A perfectly good image with no scale is still not metric evidence. The status
    # must say so, and it must be distinguishable from a broken image.
    report = classify_quality(_textured(), has_scale=False)
    assert report.status == "limited"
    assert REASON_CODES["scale_missing"] in report.reason_codes
    assert report.is_metric_evidence is False


def test_scaled_and_valid_is_metric_evidence():
    report = classify_quality(_textured(), has_scale=True)
    assert report.is_metric_evidence is True


def test_low_dynamic_range_limits_rather_than_rejects():
    # Sharp edges but only 8 grey levels of range. Compressing the noise fixture
    # instead would have blurred it, which would exercise a different reason code.
    dull = np.full((320, 320), 120, dtype=np.uint8)
    dull[::4, :] = 128
    report = classify_quality(dull)
    assert report.status == "limited"
    assert REASON_CODES["low_dynamic_range"] in report.reason_codes
    assert REASON_CODES["insufficient_sharpness"] not in report.reason_codes


def test_unsupported_channel_count_is_rejected():
    report = classify_quality(np.zeros((32, 32, 7), dtype=np.uint8))
    assert report.status == "rejected"
    assert REASON_CODES["unsupported_channels"] in report.reason_codes


def test_several_reasons_are_all_reported_not_just_the_first():
    broken = np.zeros((32, 32), dtype=np.uint8)
    report = classify_quality(broken, QualityPolicy(min_source_px=256))
    assert report.status == "rejected"
    assert len(report.reason_codes) >= 2
    assert REASON_CODES["decode_failed"] not in report.reason_codes  # it did decode


def test_every_reported_status_and_reason_is_from_the_declared_vocabulary():
    for report in (
        classify_quality(None),
        classify_quality(_flat()),
        classify_quality(_textured()),
        classify_quality(_textured(), has_scale=False),
    ):
        assert report.status in QUALITY_STATUSES
        for code in report.reason_codes:
            assert code in set(REASON_CODES.values())


# ------------------------------------------------------- honesty of the thresholds


def test_thresholds_are_declared_uncalibrated_while_no_rig_exists():
    # Task C11 (per-rig threshold calibration) is blocked on camera access. A policy
    # must not be able to claim calibration it does not have by default.
    policy = QualityPolicy()
    assert policy.thresholds_calibrated is False
    report = classify_quality(_textured(), policy=policy)
    assert report.thresholds_calibrated is False


def test_the_report_carries_its_policy_version_and_metrics():
    report = classify_quality(_textured())
    described = report.describe()
    assert described["policy_version"] == QualityPolicy().policy_version
    assert described["status"] in QUALITY_STATUSES
    assert described["metrics"]["laplacian_variance"] is not None
    assert described["thresholds_calibrated"] is False


def test_invalid_policy_values_are_rejected_at_construction():
    with pytest.raises(ValueError):
        QualityPolicy(min_source_px=0)
    with pytest.raises(ValueError):
        QualityPolicy(clip_fraction_reject=1.5)
    with pytest.raises(ValueError):
        QualityPolicy(min_laplacian_variance=-1.0)
