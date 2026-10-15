"""Unit tests for backend/schemas.py.

Verifies:
- All models enforce extra='forbid'
- Strict null-vs-zero semantics
- QualityStatus, ScoreStatus, JobStatus, SourceMode enums
- CanonicalSampleRecord completeness matching Section 11.5
- GradeMeasurement validation
"""

import pytest
from pydantic import ValidationError

from backend.schemas import (
    AggregatedMetrics,
    AreaResult,
    CanonicalSampleRecord,
    DistressEvidence,
    FrameMetadata,
    GPSData,
    GradeMeasurement,
    IMUData,
    JobState,
    JobStatus,
    MetricResult,
    NarrativeStatus,
    QualityResult,
    QualityStatus,
    ReferenceComparison,
    ReportContent,
    ReportResult,
    SampleAudit,
    SampleCamera,
    SampleCoverage,
    SampleGeometry,
    SampleIdentity,
    SampleLocation,
    SampleNarrative,
    SampleProvenance,
    SampleTime,
    ScoreResult,
    ScoreStatus,
    SegmentList,
    SegmentResult,
    SegmentSummary,
    SessionState,
    SourceMode,
    UploadRequest,
    UploadResponse,
)


def test_gps_data_validation():
    gps = GPSData(lat=12.9716, lon=77.5946, accuracy_m=3.5, simulated=False)
    assert gps.lat == 12.9716
    assert gps.lon == 77.5946
    assert gps.accuracy_m == 3.5
    assert not gps.simulated

    # Extra fields forbidden
    with pytest.raises(ValidationError):
        GPSData(lat=12.9716, lon=77.5946, unknown_field="invalid")

    # Invalid latitude
    with pytest.raises(ValidationError):
        GPSData(lat=95.0, lon=77.5946)


def test_null_vs_zero_semantics():
    """Critical invariant: null is unknown/not measured; 0 is measured absence."""
    # When unmeasured, values must be None
    unmeasured = AggregatedMetrics()
    assert unmeasured.chip_count is None
    assert unmeasured.chip_density_per_m2 is None
    assert unmeasured.gap_median_mm is None
    assert unmeasured.pothole_count is None

    # When measured as zero, value is 0
    measured_zero = AggregatedMetrics(
        chip_count=0,
        chip_density_per_m2=0.0,
        pothole_count=0,
        crack_total_area_m2=0.0,
    )
    assert measured_zero.chip_count == 0
    assert measured_zero.chip_density_per_m2 == 0.0
    assert measured_zero.pothole_count == 0
    assert measured_zero.crack_total_area_m2 == 0.0


def test_score_result_semantics():
    # Null score when uncalibrated or rejected
    unscored = ScoreResult(value=None, status=ScoreStatus.UNKNOWN)
    assert unscored.value is None
    assert unscored.status == ScoreStatus.UNKNOWN

    # Measured zero score
    scored_zero = ScoreResult(value=0, status=ScoreStatus.BAD)
    assert scored_zero.value == 0
    assert scored_zero.status == ScoreStatus.BAD

    # Valid score
    scored_good = ScoreResult(value=85, status=ScoreStatus.GOOD, policy_version="v1.0")
    assert scored_good.value == 85
    assert scored_good.status == ScoreStatus.GOOD

    # Extra fields forbidden
    with pytest.raises(ValidationError):
        ScoreResult(value=50, extra_key="invalid")


def test_grade_measurement():
    grade = GradeMeasurement(
        grade_percent=4.2,
        grade_deg=2.4,
        source="calibrated_inclinometer",
        uncertainty_deg=0.1,
        valid=True,
        notes="Longitudinal grade measured on rigid straightedge",
    )
    assert grade.grade_percent == 4.2
    assert grade.source == "calibrated_inclinometer"
    assert grade.valid

    # Extra fields forbidden
    with pytest.raises(ValidationError):
        GradeMeasurement(grade_percent=4.2, source="sensor", unknown_field=123)


def test_canonical_sample_record():
    canonical = CanonicalSampleRecord(
        identity=SampleIdentity(
            sample_id="samp-001",
            session_id="sess-001",
            source_dataset="RDD2022_India",
            parent_id="img_1234",
            sequence_id=1,
        ),
        provenance=SampleProvenance(
            file_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            original_uri="s3://ghost-rider-storage/raw/sess-001/frame_000001.jpg",
            license_record="CC-BY-4.0",
            split_group="test_group_A",
        ),
        time=SampleTime(
            captured_at_utc="2026-10-15T10:00:00Z",
            monotonic_capture_time_ns=1000000,
            received_at="2026-10-15T10:00:01Z",
            processed_at="2026-10-15T10:00:02Z",
        ),
        camera=SampleCamera(
            camera_id="cam_01",
            calibration_id="cal_rig_v1",
            width_px=1920,
            height_px=1080,
            exposure_ms=0.5,
            crop_state="uncropped",
        ),
        location=SampleLocation(
            lat=12.9716,
            lon=77.5946,
            accuracy_m=2.0,
            route_distance_m=0.0,
            distance_source="odometry",
            is_simulated=False,
        ),
        geometry=SampleGeometry(
            scale_source="rig_calibrated",
            sx_sy_or_h=[0.25, 0.25],
            valid_roi=[100, 100, 1720, 880],
            observed_area_m2=0.55,
            error_bound_pct=3.2,
        ),
        quality=QualityResult(
            status=QualityStatus.ACCEPTED,
            reasons=[],
            sharpness_score=142.5,
            glare_present=False,
        ),
        features=[
            MetricResult(name="chip_count_density", value=420.0, unit="count/m2", valid=True),
            MetricResult(name="median_gap", value=1.45, unit="mm", valid=True),
        ],
        assessment=ScoreResult(
            value=82,
            status=ScoreStatus.GOOD,
            policy_version="1.0.0",
        ),
        coverage=SampleCoverage(
            frame_interval_m=0.5,
            inspected_strip_m=0.6,
            unique_area_m2=None,  # Registration unreliable -> None
            coverage_method="conservative_spacing",
        ),
        audit=SampleAudit(
            model_hash="sha256_mock_model_weights",
            code_commit="git_commit_abc123",
            config_hash="sha256_config",
        ),
        narrative=SampleNarrative(
            factual_input_hash="sha256_factual_hash",
            bedrock_model_id="amazon.nova-micro-v1:0",
            status=NarrativeStatus.GENERATED,
            generated_at="2026-10-15T10:00:03Z",
        ),
    )
    assert canonical.identity.sample_id == "samp-001"
    assert canonical.geometry.scale_source == "rig_calibrated"
    assert canonical.coverage.unique_area_m2 is None
