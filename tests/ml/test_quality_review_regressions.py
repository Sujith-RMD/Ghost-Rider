"""Regression checks for quality evidence preprocessing, not rig calibration."""

import numpy as np
import pytest

from backend.quality import QualityPolicy, classify_quality, image_metrics


def test_alpha_does_not_hide_clipping_or_change_brightness():
    colour = np.zeros((320, 320, 3), dtype=np.uint8)
    rgba = np.concatenate([colour, np.full((320, 320, 1), 255, dtype=np.uint8)], axis=2)
    rgb_metrics = image_metrics(colour)
    rgba_metrics = image_metrics(rgba)
    for key in ("mean_intensity", "clipped_low_fraction", "laplacian_variance"):
        assert rgba_metrics[key] == rgb_metrics[key]
    assert "clipped_shadows" in classify_quality(rgba).reason_codes


def test_equivalent_integer_bit_depths_have_equivalent_quality():
    image = np.random.default_rng(42).integers(60, 200, (320, 320), dtype=np.uint8)
    eight = image_metrics(image)
    sixteen = image_metrics(image.astype(np.uint16) * 257)
    for key in ("laplacian_variance", "dynamic_range", "mean_intensity"):
        assert sixteen[key] == pytest.approx(eight[key])
    assert classify_quality(image).status == classify_quality(image.astype(np.uint16) * 257).status


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_nonfinite_image_is_rejected_without_nan_report(value):
    image = np.full((320, 320), value)
    report = classify_quality(image)
    assert report.status == "rejected"
    assert report.reason_codes == ("decode_failed",)
    assert report.metrics["laplacian_variance"] is None


@pytest.mark.parametrize("value", [np.nan, np.inf])
def test_nonfinite_sharpness_threshold_is_not_a_valid_policy(value):
    with pytest.raises(ValueError):
        QualityPolicy(min_laplacian_variance=value)
