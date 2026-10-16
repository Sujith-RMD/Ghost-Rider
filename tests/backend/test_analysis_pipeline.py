"""Tests for the real ML analysis wiring (backend/analysis.py + worker seam).

Verifies the pipeline the worker now runs end-to-end:
- decode (Windows-path safe), quality gate, unscaled measurement;
- honest null-vs-zero semantics: counts/ratios are real without calibration,
  every mm/m²/count-per-m² value is ``None`` until a scale exists;
- rejected quality frames carry reason codes but no metric evidence;
- the worker's ``run_inference`` returns these real measurements.

Synthetic images come from the ML team's own generator
(``eval.aggregate_eval.make_synthetic_case``), so ground-truth instance counts
are known.
"""

import json

import numpy as np
import pytest

from backend import analysis
from backend.ingestion.queue import QueueItem
from backend.schemas import FrameMetadata, QualityStatus
from backend.worker import MODEL_VERSION, run_inference


@pytest.fixture(scope="module")
def synthetic_case():
    from eval.aggregate_eval import make_synthetic_case

    return make_synthetic_case(seed=0)


# --------------------------------------------------------------------------- #
# Scale honesty
# --------------------------------------------------------------------------- #

def test_resolve_scale_is_unscaled_without_calibration_store():
    scale = analysis.resolve_scale(None)
    assert scale.is_scaled is False
    assert scale.source.value == "unscaled"

    metadata = FrameMetadata(camera_profile_id="cam-a")
    scale = analysis.resolve_scale(metadata)
    assert scale.is_scaled is False
    assert "cam-a" in scale.provenance  # provenance kept for future migration


# --------------------------------------------------------------------------- #
# Real measurement on a synthetic image
# --------------------------------------------------------------------------- #

def test_measure_frame_produces_real_counts_and_honest_nulls(synthetic_case):
    image = synthetic_case["image"]
    outcome = analysis.measure_frame(image)

    quality = outcome["quality"]
    assert quality is not None
    # Uncalibrated frames are at most "limited", never silently accepted.
    assert quality.status in (QualityStatus.ACCEPTED, QualityStatus.LIMITED)
    assert "scale_missing" in quality.reasons

    metrics = outcome["metrics"]
    assert metrics is not None, "measurements must exist for an acceptable frame"
    # Dimensionless evidence is real and matches the generator's ground truth.
    assert metrics.chip_count == synthetic_case["n_gt"]
    assert metrics.aggregate_coverage is not None
    assert 0.0 < metrics.aggregate_coverage <= 1.0

    # Uncalibrated input must NOT gain physical units.
    assert outcome["geometry_valid"] is False
    assert metrics.chip_density_per_m2 is None
    assert metrics.median_chip_diameter_mm is None
    assert metrics.min_chip_diameter_mm is None
    assert metrics.gap_median_mm is None
    assert metrics.gap_iqr_mm is None
    assert metrics.gap_p90_mm is None

    area = outcome["observed_area"]
    assert area is not None
    assert area.observed_area_m2 is None
    assert area.eligible_area_m2 is None
    assert area.scale_source == "unscaled"
    assert area.scale_uncertainty is None

    # Limitations are recorded, not hidden.
    assert any("valid_surface_mask" in item for item in outcome["limitations"])


def test_measure_frame_records_scale_limitation(synthetic_case):
    outcome = analysis.measure_frame(synthetic_case["image"])
    assert any("unscaled" in item for item in outcome["limitations"])


def test_manual_surface_roi_excludes_outside_instances_from_metrics(monkeypatch):
    from backend.aggregate.measurement import measure_surface

    labels = np.zeros((320, 320), dtype=np.int32)
    labels[45:75, 35:65] = 1
    labels[45:75, 245:275] = 2
    image = np.random.default_rng(4).integers(30, 220, (320, 320, 3), dtype=np.uint8)
    roi = np.zeros((320, 320), dtype=bool)
    roi[:, :160] = True

    def measure_with_roi(_image, valid_surface_mask, scale, tiling=None, distress_mask=None):
        result = measure_surface(
            labels, valid_surface_mask, scale, labels=labels, distress_mask=distress_mask
        )
        return result, labels

    monkeypatch.setattr(analysis, "measure_tiled", measure_with_roi)
    outcome = analysis.measure_frame(image, valid_surface_mask=roi)

    assert outcome["metrics"].chip_count == 1
    assert "manual_surface_roi_applied" in outcome["limitations"]


# --------------------------------------------------------------------------- #
# Quality gate: rejected frames carry no measurements
# --------------------------------------------------------------------------- #

def test_blank_image_is_rejected_without_measurements():
    blank = np.full((256, 256, 3), 127, dtype=np.uint8)
    outcome = analysis.measure_frame(blank)

    assert outcome["quality"].status == QualityStatus.REJECTED
    assert outcome["quality"].reasons  # reason codes present
    assert outcome["metrics"] is None
    assert outcome["observed_area"] is None
    assert "quality_rejected" in outcome["limitations"]


def test_small_image_is_rejected_for_resolution():
    tiny = np.full((64, 64, 3), 200, dtype=np.uint8)
    outcome = analysis.measure_frame(tiny)

    assert outcome["quality"].status == QualityStatus.REJECTED
    assert "inadequate_source_resolution" in outcome["quality"].reasons
    assert outcome["metrics"] is None


# --------------------------------------------------------------------------- #
# Decoding
# --------------------------------------------------------------------------- #

def test_decode_image_roundtrip_and_failures(tmp_path, synthetic_case):
    import cv2

    good = tmp_path / "frame.png"
    assert cv2.imwrite(str(good), synthetic_case["image"])
    decoded = analysis.decode_image(good)
    assert decoded is not None and decoded.shape[0] >= 1

    assert analysis.decode_image(tmp_path / "missing.png") is None
    assert analysis.decode_image(None) is None

    garbage = tmp_path / "garbage.png"
    garbage.write_bytes(b"not an image at all")
    assert analysis.decode_image(garbage) is None


# --------------------------------------------------------------------------- #
# SegmentResult composition
# --------------------------------------------------------------------------- #

def test_build_segment_result_is_all_unknown_without_measurement():
    result = analysis.build_segment_result(
        segment_id=3,
        route_id="sess-1",
        metadata=None,
        image_path=None,
        image_url=None,
        raw_url=None,
        model_version="measure-v1",
        feature_version="quality-v1",
        scoring_version="not-implemented",
        measured=None,
    )
    assert result.quality is None
    assert result.metrics is None
    assert result.observed_area is None
    assert result.geometry_valid is False
    assert result.model_version == "measure-v1"
    assert result.error is None  # absence of an image is not an analysis error


# --------------------------------------------------------------------------- #
# Worker seam: run_inference runs the real pipeline
# --------------------------------------------------------------------------- #

def _make_queue_item(image_path, session_id="sess-test", frame_index=1):
    return QueueItem(
        session_id=session_id,
        frame_index=frame_index,
        source_mode="upload",
        filename="frame.png",
        received_at="2026-10-16T00:00:00+00:00",
        monotonic_received_ns=0,
        image_path=str(image_path),
        metadata_json=None,
    )


def test_worker_run_inference_returns_real_measurements(tmp_path, synthetic_case):
    import cv2

    path = tmp_path / "frame.png"
    assert cv2.imwrite(str(path), synthetic_case["image"])

    result = run_inference(_make_queue_item(path))

    assert result is not None
    assert result.quality is not None
    assert result.quality.status in (QualityStatus.ACCEPTED, QualityStatus.LIMITED)
    assert result.metrics is not None
    assert result.metrics.chip_count == synthetic_case["n_gt"]
    # Honest unknowns for everything needing a scale.
    assert result.metrics.chip_density_per_m2 is None
    assert result.geometry_valid is False
    assert result.model_version == MODEL_VERSION


def test_worker_run_inference_without_image_is_unknown(tmp_path):
    result = run_inference(_make_queue_item(tmp_path / "missing.png"))
    assert result is not None
    assert result.quality is None
    assert result.metrics is None
    assert result.model_version == MODEL_VERSION
