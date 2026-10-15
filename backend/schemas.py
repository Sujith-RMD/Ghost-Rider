"""Shared Pydantic schemas for the Ghost-Rider backend.

These schemas define the public API contract between backend, ML, and frontend.
All models use `extra="forbid"` to reject unexpected fields and strictly adhere
to null-vs-zero semantics:
- `null` (None) represents unmeasured, unknown, or uncalibrated values.
- `0` represents a measured zero quantity (e.g. 0 defects detected).

Ownership: Backend & AWS AI
Reference: docs/contracts/README.md, docs/final_plan.md (Sections 11.4, 11.5)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #

class QualityStatus(str, Enum):
    """Image quality assessment status."""

    ACCEPTED = "accepted"
    LIMITED = "limited"
    REJECTED = "rejected"


class ScoreStatus(str, Enum):
    """Surface condition scoring status."""

    GOOD = "Good"
    BAD = "Bad"
    REVIEW = "review"
    UNKNOWN = "unknown"


class JobStatus(str, Enum):
    """Analysis job lifecycle states."""

    RECEIVED = "received"
    VALIDATED = "validated"
    QUEUED = "queued"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class SourceMode(str, Enum):
    """How the image was acquired."""

    UPLOAD = "upload"
    LIVE = "live"
    REPLAY = "replay"


class NarrativeStatus(str, Enum):
    """Bedrock narrative generation status."""

    GENERATED = "generated"
    FALLBACK = "fallback"
    NOT_REQUESTED = "not_requested"


# --------------------------------------------------------------------------- #
# GPS, IMU, and Inclination sensor data
# --------------------------------------------------------------------------- #

class GPSData(BaseModel):
    """GPS fix attached to a frame."""

    model_config = ConfigDict(extra="forbid")

    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in degrees")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude in degrees")
    speed_mps: Optional[float] = Field(default=None, ge=0.0, description="Speed in meters per second (null if unknown)")
    heading_deg: Optional[float] = Field(default=None, ge=-360.0, le=360.0, description="Heading in degrees (null if unknown)")
    accuracy_m: Optional[float] = Field(default=None, ge=0.0, description="Horizontal accuracy in meters (null if unknown)")
    simulated: bool = Field(default=False, description="True if GPS is simulated, not real hardware GPS")


class IMUData(BaseModel):
    """Device orientation captured with the frame."""

    model_config = ConfigDict(extra="forbid")

    pitch_deg: float = Field(default=0.0, ge=-90.0, le=90.0, description="Pitch in degrees")
    roll_deg: float = Field(default=0.0, ge=-180.0, le=180.0, description="Roll in degrees")
    yaw_deg: Optional[float] = Field(default=None, ge=-360.0, le=360.0, description="Yaw in degrees (null if unknown)")
    accel_z: Optional[float] = Field(default=None, description="Vertical acceleration (null if unknown)")


class GradeMeasurement(BaseModel):
    """Verified road inclination / grade measurement."""

    model_config = ConfigDict(extra="forbid")

    grade_percent: Optional[float] = Field(
        default=None,
        description="Longitudinal road grade in percent: 100 * tan(angle). Null if unmeasured."
    )
    grade_deg: Optional[float] = Field(
        default=None,
        ge=-90.0,
        le=90.0,
        description="Longitudinal grade in degrees. Null if unmeasured."
    )
    source: str = Field(
        ...,
        description="Source provenance: manual_sensor, calibrated_inclinometer, stationary_camera_imu"
    )
    uncertainty_deg: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Estimated uncertainty in degrees (null if unknown)"
    )
    captured_at: Optional[str] = Field(
        default=None,
        description="ISO 8601 capture timestamp of the sensor measurement"
    )
    valid: bool = Field(
        default=True,
        description="Whether this grade reading is considered valid under current mounting"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Clarifications: e.g. longitudinal vs crossfall, straightedge verification"
    )


# --------------------------------------------------------------------------- #
# Frame metadata
# --------------------------------------------------------------------------- #

class FrameMetadata(BaseModel):
    """Metadata for a single frame."""

    model_config = ConfigDict(extra="forbid")

    gps: Optional[GPSData] = Field(default=None, description="GPS fix if available")
    imu: IMUData = Field(default_factory=IMUData, description="IMU orientation data")
    grade: Optional[GradeMeasurement] = Field(default=None, description="Supporting road grade measurement")
    captured_at: Optional[str] = Field(default=None, description="ISO 8601 capture timestamp (UTC)")
    monotonic_capture_time_ns: Optional[int] = Field(default=None, description="Monotonic clock timestamp in nanoseconds")
    device_id: Optional[str] = Field(default=None, description="Camera or device identifier")
    camera_profile_id: Optional[str] = Field(default=None, description="Camera calibration profile identifier")
    source_mode: SourceMode = Field(default=SourceMode.UPLOAD, description="How this frame was acquired")
    frame_index: Optional[int] = Field(default=None, description="Sequence number for live or replay")
    telemetry_hash: Optional[str] = Field(default=None, description="SHA256 hash of raw telemetry payload")


# --------------------------------------------------------------------------- #
# Analysis results: Geometry, Quality, Metrics, Evidence, Scoring
# --------------------------------------------------------------------------- #

class AreaResult(BaseModel):
    """Road area measurements."""

    model_config = ConfigDict(extra="forbid")

    observed_area_m2: Optional[float] = Field(default=None, ge=0.0, description="Total observed road area (null if scale unknown)")
    eligible_area_m2: Optional[float] = Field(default=None, ge=0.0, description="Texture-eligible area (null if scale unknown)")
    ignored_area_m2: Optional[float] = Field(default=None, ge=0.0, description="Ignored area (null if scale unknown)")
    distress_area_m2: Optional[float] = Field(default=None, ge=0.0, description="Distress area (null if scale unknown)")
    scale_source: Optional[str] = Field(default=None, description="Scale source: rig_calibrated, source_calibrated, unscaled")
    scale_uncertainty: Optional[float] = Field(default=None, ge=0.0, description="Relative scale uncertainty ratio (null if unknown)")


class QualityResult(BaseModel):
    """Image quality assessment."""

    model_config = ConfigDict(extra="forbid")

    status: QualityStatus = Field(..., description="Overall quality status: accepted, limited, rejected")
    reasons: List[str] = Field(default_factory=list, description="Reason codes: e.g. blur_laplacian, glare, uncalibrated_scale")
    min_source_resolution: Optional[int] = Field(default=None, description="Minimum detectable feature size in pixels")
    sharpness_score: Optional[float] = Field(default=None, ge=0.0, description="Sharpness metric value (null if uncomputed)")
    glare_present: bool = Field(default=False, description="Whether glare or clipping was detected")
    ignored_fraction: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Fraction of frame masked as ignore")


class MetricResult(BaseModel):
    """Single measured metric with validity information."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Metric identifier, e.g. chip_count_density, median_chip_diameter")
    value: Optional[float] = Field(default=None, description="Measured value (null = unknown, 0 = measured absence)")
    unit: str = Field(..., description="Unit of measurement: mm, m2, count/m2, unitless")
    valid: bool = Field(default=True, description="Whether the measurement is valid")
    estimator_version: Optional[str] = Field(default=None, description="Version of estimator that produced this")
    notes: Optional[str] = Field(default=None, description="Human-readable notes about this metric")


class AggregatedMetrics(BaseModel):
    """Aggregate and distress measurements for a segment."""

    model_config = ConfigDict(extra="forbid")

    chip_count: Optional[int] = Field(default=None, ge=0, description="Visible aggregate instance count (null if uncalibrated/unmeasured)")
    chip_density_per_m2: Optional[float] = Field(default=None, ge=0.0, description="Chip count density (null if area unknown)")
    min_chip_diameter_mm: Optional[float] = Field(default=None, ge=0.0, description="Minimum resolvable chip diameter (null if uncalibrated)")
    median_chip_diameter_mm: Optional[float] = Field(default=None, ge=0.0, description="Median chip diameter (null if uncalibrated)")
    chip_size_distribution: Optional[Dict[str, float]] = Field(default=None, description="Size distribution buckets")
    aggregate_coverage: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Aggregate union coverage ratio (null if unmeasured)")
    crack_skeleton_length_m: Optional[float] = Field(default=None, ge=0.0, description="Crack skeleton length (null if unmeasured/uncalibrated)")
    pothole_count: Optional[int] = Field(default=None, ge=0, description="Pothole instance count (null if unmeasured)")
    pothole_total_area_m2: Optional[float] = Field(default=None, ge=0.0, description="Total pothole area (null if uncalibrated)")
    crack_total_area_m2: Optional[float] = Field(default=None, ge=0.0, description="Total crack area (null if uncalibrated)")
    gap_median_mm: Optional[float] = Field(default=None, ge=0.0, description="Adjacent-boundary gap median (null if uncalibrated)")
    gap_iqr_mm: Optional[float] = Field(default=None, ge=0.0, description="Gap interquartile range (null if uncalibrated)")
    gap_p90_mm: Optional[float] = Field(default=None, ge=0.0, description="Gap 90th percentile (null if uncalibrated)")
    gap_sample_count: Optional[int] = Field(default=None, ge=0, description="Number of qualifying gap sites measured")
    texture_deviation: Optional[float] = Field(default=None, description="Texture deviation T from known-good reference")


class DistressEvidence(BaseModel):
    """Distress segmentation evidence."""

    model_config = ConfigDict(extra="forbid")

    mask_url: Optional[str] = Field(default=None, description="URL to defect mask overlay")
    mask_local_path: Optional[str] = Field(default=None, description="Local disk path to mask overlay")
    crack_mask_url: Optional[str] = Field(default=None, description="URL to crack-specific mask")
    pothole_mask_url: Optional[str] = Field(default=None, description="URL to pothole-specific mask")
    overlay_url: Optional[str] = Field(default=None, description="URL to combined evidence overlay")


class ReferenceComparison(BaseModel):
    """Comparison against known-good reference."""

    model_config = ConfigDict(extra="forbid")

    reference_version: Optional[str] = Field(default=None, description="Version of the reference model used")
    feature_count: Optional[int] = Field(default=None, ge=0, description="Number of features compared")
    deviation_robust: Optional[float] = Field(default=None, description="Robust normalized deviation (null if uncomputed)")
    deviation_mahalanobis: Optional[float] = Field(default=None, description="Mahalanobis distance (null if uncomputed)")
    supported_surface: bool = Field(default=True, description="Whether the surface is in the supported domain")
    domain_support_covered: bool = Field(default=False, description="Whether domain support was explicitly checked")
    difference_heatmap_url: Optional[str] = Field(default=None, description="URL to difference heatmap (null if uncomputed)")


class ScoreResult(BaseModel):
    """Surface Quality Index (SQI) score."""

    model_config = ConfigDict(extra="forbid")

    value: Optional[int] = Field(default=None, ge=0, le=100, description="SQI value 0-100 (null = not scored/unknown)")
    status: ScoreStatus = Field(default=ScoreStatus.UNKNOWN, description="Good, Bad, review, unknown")
    reference_version: Optional[str] = Field(default=None, description="Version of reference used for scoring")
    policy_version: Optional[str] = Field(default=None, description="Version of scoring policy used")
    texture_term: Optional[float] = Field(default=None, description="Texture deviation component T")
    distress_term: Optional[float] = Field(default=None, description="Distress burden component D")
    distribution_term: Optional[float] = Field(default=None, description="Optional distribution term")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Empirically calibrated confidence")
    confidence_state: Optional[str] = Field(default=None, description="Descriptive confidence state: high, medium, low, uncalibrated")
    severe_defect_flag: bool = Field(default=False, description="Inspection priority flag for severe observed defect")
    reasons: List[str] = Field(default_factory=list, description="Scoring reason codes")
    partial_rule: Optional[str] = Field(default=None, description="Name of partial-input rule if applied")


# --------------------------------------------------------------------------- #
# Canonical Sample Record (Final Plan Section 11.5)
# --------------------------------------------------------------------------- #

class SampleIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sample_id: str = Field(..., description="Unique sample ID")
    session_id: Optional[str] = Field(default=None, description="Parent session ID")
    source_dataset: Optional[str] = Field(default=None, description="Dataset name and version if from benchmark")
    parent_id: Optional[str] = Field(default=None, description="Parent image ID")
    sequence_id: Optional[int] = Field(default=None, description="Sequence index in route")


class SampleProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_sha256: str = Field(..., description="SHA256 hash of original image file")
    original_uri: str = Field(..., description="Original URI or S3 object key")
    license_record: Optional[str] = Field(default=None, description="License terms or attribution")
    split_group: Optional[str] = Field(default=None, description="Evaluation split group (train, dev, test)")


class SampleTime(BaseModel):
    model_config = ConfigDict(extra="forbid")
    captured_at_utc: Optional[str] = Field(default=None, description="UTC capture timestamp (ISO 8601)")
    monotonic_capture_time_ns: Optional[int] = Field(default=None, description="Monotonic clock reading in nanoseconds")
    received_at: str = Field(..., description="UTC timestamp when server received the frame")
    processed_at: Optional[str] = Field(default=None, description="UTC timestamp when analysis completed")


class SampleCamera(BaseModel):
    model_config = ConfigDict(extra="forbid")
    camera_id: Optional[str] = Field(default=None, description="Camera hardware ID")
    calibration_id: Optional[str] = Field(default=None, description="Calibration profile ID")
    width_px: Optional[int] = Field(default=None, ge=1, description="Native frame width in pixels")
    height_px: Optional[int] = Field(default=None, ge=1, description="Native frame height in pixels")
    exposure_ms: Optional[float] = Field(default=None, ge=0.0, description="Exposure duration in milliseconds")
    crop_state: Optional[str] = Field(default=None, description="Crop or digital zoom description")


class SampleLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: Optional[float] = Field(default=None, ge=-90.0, le=90.0, description="Latitude (null if unlocated)")
    lon: Optional[float] = Field(default=None, ge=-180.0, le=180.0, description="Longitude (null if unlocated)")
    accuracy_m: Optional[float] = Field(default=None, ge=0.0, description="GPS accuracy radius in meters")
    route_distance_m: Optional[float] = Field(default=None, ge=0.0, description="Traveled distance along route")
    distance_source: Optional[str] = Field(default=None, description="Source of route distance: odometry, gps_polyline")
    is_simulated: bool = Field(default=False, description="True if simulated GPS coordinates")


class SampleGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scale_source: str = Field(..., description="Scale determination: rig_calibrated, source_calibrated, unscaled")
    sx_sy_or_h: Optional[List[float]] = Field(default=None, description="x/y scale factors (mm/px) or 3x3 homography matrix H")
    valid_roi: Optional[List[int]] = Field(default=None, description="Bounding box [x, y, w, h] of valid road ROI")
    observed_area_m2: Optional[float] = Field(default=None, ge=0.0, description="Total valid area inspected (null if uncalibrated)")
    error_bound_pct: Optional[float] = Field(default=None, ge=0.0, description="Scale error bound percentage")


class SampleCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frame_interval_m: Optional[float] = Field(default=None, ge=0.0, description="Distance spacing between consecutive frames")
    inspected_strip_m: Optional[float] = Field(default=None, ge=0.0, description="Transverse width of inspected pavement strip")
    unique_area_m2: Optional[float] = Field(default=None, ge=0.0, description="Unique pavement area (null if registration unreliable)")
    coverage_method: str = Field(default="conservative_spacing", description="Method used to estimate coverage")


class SampleAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_hash: Optional[str] = Field(default=None, description="Hash of ML model weights")
    code_commit: Optional[str] = Field(default=None, description="Git commit hash of running service")
    config_hash: Optional[str] = Field(default=None, description="Hash of active configuration")
    reviewer_corrections: Optional[Dict[str, Any]] = Field(default=None, description="Human reviewer audit annotations")


class SampleNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid")
    factual_input_hash: Optional[str] = Field(default=None, description="SHA256 hash of structured facts sent to Bedrock")
    bedrock_model_id: Optional[str] = Field(default=None, description="Exact AWS Bedrock model ID used")
    status: NarrativeStatus = Field(default=NarrativeStatus.NOT_REQUESTED, description="Narrative status")
    generated_at: Optional[str] = Field(default=None, description="UTC generation timestamp")


class CanonicalSampleRecord(BaseModel):
    """The canonical assessment record defined in Final Plan Section 11.5."""

    model_config = ConfigDict(extra="forbid")

    identity: SampleIdentity
    provenance: SampleProvenance
    time: SampleTime
    camera: SampleCamera
    location: SampleLocation
    geometry: SampleGeometry
    quality: QualityResult
    features: List[MetricResult] = Field(default_factory=list)
    assessment: ScoreResult
    coverage: SampleCoverage
    audit: SampleAudit
    narrative: SampleNarrative


# --------------------------------------------------------------------------- #
# Segment results (returned by GET /v1/samples/{id})
# --------------------------------------------------------------------------- #

class SegmentResult(BaseModel):
    """Full analysis result for one route segment or uploaded frame."""

    model_config = ConfigDict(extra="forbid")

    segment_id: int = Field(..., description="Segment identifier (1-based sequence or index)")
    route_id: Optional[str] = Field(default=None, description="Parent route or session identifier")
    sample_id: Optional[str] = Field(default=None, description="Unique sample identifier")
    image_path: Optional[str] = Field(default=None, description="Path to original image")
    image_url: Optional[str] = Field(default=None, description="URL to original image")
    mask_url: Optional[str] = Field(default=None, description="URL to mask overlay")
    raw_url: Optional[str] = Field(default=None, description="URL to raw uploaded image")
    captured_at: Optional[str] = Field(default=None, description="UTC capture timestamp")
    gps: Optional[GPSData] = Field(default=None, description="GPS fix if available")
    grade: Optional[GradeMeasurement] = Field(default=None, description="Supporting road grade measurement")

    # Geometry and quality
    geometry_valid: bool = Field(default=False, description="Whether geometry and scale are valid")
    observed_area: Optional[AreaResult] = Field(default=None, description="Area measurements (null if uncalibrated)")
    quality: Optional[QualityResult] = Field(default=None, description="Quality assessment")

    # Measurements and evidence
    metrics: Optional[AggregatedMetrics] = Field(default=None, description="Aggregate and distress metrics")
    evidence: Optional[DistressEvidence] = Field(default=None, description="Visual evidence references")

    # Scoring and reference
    score: Optional[ScoreResult] = Field(default=None, description="Surface condition score")
    reference: Optional[ReferenceComparison] = Field(default=None, description="Known-good comparison")

    # Model and version audit
    model_version: Optional[str] = Field(default=None, description="ML model version used")
    feature_version: Optional[str] = Field(default=None, description="Feature extraction version")
    scoring_version: Optional[str] = Field(default=None, description="Scoring version")

    # Metadata & canonical payload
    created_at: Optional[str] = Field(default=None, description="Analysis completion timestamp")
    error: Optional[str] = Field(default=None, description="Error message if analysis failed")
    canonical: Optional[CanonicalSampleRecord] = Field(default=None, description="Canonical record if available")


# --------------------------------------------------------------------------- #
# Job and session state
# --------------------------------------------------------------------------- #

class JobState(BaseModel):
    """Durable job lifecycle state."""

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(..., description="Unique job identifier")
    status: JobStatus = Field(..., description="Current job status: received -> validated -> queued -> processing -> succeeded/partial/failed")
    error_reason: Optional[str] = Field(default=None, description="Error description if failed")
    attempt_count: int = Field(default=0, ge=0, description="Number of processing attempts")
    started_at: Optional[str] = Field(default=None, description="When processing began")
    completed_at: Optional[str] = Field(default=None, description="When processing ended")
    updated_at: str = Field(..., description="Last state transition timestamp")
    versions: Dict[str, str] = Field(default_factory=dict, description="Model, feature, and scoring versions used")
    result_sample_id: Optional[str] = Field(
        default=None,
        description="Sample id produced when the job succeeded (null until then). Retrieve via GET /v1/samples/{id}.",
    )


class SessionState(BaseModel):
    """Live/replay capture session state."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Unique session identifier")
    mode: SourceMode = Field(..., description="Capture mode: live, replay, upload")
    camera_id: Optional[str] = Field(default=None, description="Camera hardware ID")
    calibration_id: Optional[str] = Field(default=None, description="Calibration profile ID")
    created_at: str = Field(..., description="Session creation timestamp")
    frame_count: int = Field(default=0, ge=0, description="Frames received by API")
    processed_count: int = Field(default=0, ge=0, description="Frames processed by worker")
    rejected_count: int = Field(default=0, ge=0, description="Frames rejected by QC or format validation")
    dropped_count: int = Field(default=0, ge=0, description="Frames dropped due to bounded queue overflow")
    last_capture_at: Optional[str] = Field(default=None, description="Last frame capture timestamp")
    last_processed_at: Optional[str] = Field(default=None, description="Last frame processed timestamp")
    is_stale: bool = Field(default=False, description="Whether current result is stale")


# --------------------------------------------------------------------------- #
# Route segment summary (for Maps and 50m reporting bins)
# --------------------------------------------------------------------------- #

class SegmentSummary(BaseModel):
    """Summary for a configurable 50m reporting bin."""

    model_config = ConfigDict(extra="forbid")

    segment_id: int = Field(..., description="Reporting bin sequence identifier")
    start_distance_m: float = Field(..., ge=0.0, description="Start distance along route in meters")
    end_distance_m: float = Field(..., ge=0.0, description="End distance along route in meters")
    center_lat: Optional[float] = Field(default=None, ge=-90.0, le=90.0, description="Center GPS latitude (null if unlocated)")
    center_lon: Optional[float] = Field(default=None, ge=-180.0, le=180.0, description="Center GPS longitude (null if unlocated)")
    gps_accuracy_m: Optional[float] = Field(default=None, ge=0.0, description="GPS accuracy at center (null if unknown)")
    simulated: bool = Field(default=False, description="Whether position is simulated")
    sample_count: int = Field(default=0, ge=0, description="Number of frames received in this bin")
    accepted_sample_count: int = Field(default=0, ge=0, description="Frames that passed QC checks")
    unique_area_m2: Optional[float] = Field(default=None, ge=0.0, description="Unique road area covered (null if registration unreliable)")
    strip_area_m2: float = Field(default=0.0, ge=0.0, description="Total inspected strip area sampled")
    median_score: Optional[int] = Field(default=None, ge=0, le=100, description="Median SQI (null if not enough samples)")
    lower_tail_score: Optional[int] = Field(default=None, ge=0, le=100, description="Lower-tail SQI (p10/p25) (null if insufficient samples)")
    serious_defect_observed: bool = Field(default=False, description="Whether a severe defect flag was observed in this bin")
    unknown_coverage: bool = Field(default=False, description="Whether coverage is incomplete or unsampled")


class SegmentList(BaseModel):
    """List of segment summaries for a route."""

    model_config = ConfigDict(extra="forbid")

    route_id: str = Field(..., description="Route or session identifier")
    segments: List[SegmentSummary] = Field(default_factory=list, description="Reporting bin summaries")
    total_distance_m: float = Field(default=0.0, ge=0.0, description="Total route distance in meters")
    coverage_percentage: Optional[float] = Field(default=None, ge=0.0, le=100.0, description="Percentage of route covered (null if unknown)")
    unsampled_stretches: List[Dict[str, float]] = Field(default_factory=list, description="Unsampled distance ranges [{'start_m': ..., 'end_m': ...}]")


# --------------------------------------------------------------------------- #
# Reports & Bedrock narrative
# --------------------------------------------------------------------------- #

class ReportContent(BaseModel):
    """Structured report content containing verified facts and inspection actions."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(..., description="Human-readable factual summary")
    evidence_references: List[str] = Field(default_factory=list, description="References to evidence items (sample IDs, masks)")
    limitations: List[str] = Field(default_factory=list, description="Declared limitations (e.g. uncalibrated scale, partial route)")
    inspection_actions: List[str] = Field(default_factory=list, description="Recommended human inspection actions (never structural repair commands)")
    narrative_status: NarrativeStatus = Field(default=NarrativeStatus.NOT_REQUESTED, description="How narrative was produced: generated, fallback, not_requested")
    factual_template_used: bool = Field(default=False, description="True if deterministic fallback template was used")


class ReportResult(BaseModel):
    """Generated factual report with Bedrock narration metadata."""

    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(..., description="Unique report identifier")
    assessment_id: Optional[str] = Field(default=None, description="Assessment or session ID this report covers")
    content: ReportContent = Field(..., description="Structured report content")
    generated_at: str = Field(..., description="UTC generation timestamp")
    bedrock_model_id: Optional[str] = Field(default=None, description="Exact AWS Bedrock model ID used (null if fallback/none)")
    factual_input_hash: Optional[str] = Field(default=None, description="SHA256 hash of structured facts used for caching and validation")


# --------------------------------------------------------------------------- #
# Upload and finalize
# --------------------------------------------------------------------------- #

class UploadRequest(BaseModel):
    """Request to allocate a private upload slot."""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(..., description="Original filename")
    content_type: Optional[str] = Field(default=None, description="MIME type (e.g. image/jpeg, image/png)")
    expected_size: Optional[int] = Field(default=None, ge=1, le=52428800, description="Expected file size in bytes (max 50MB)")


class UploadResponse(BaseModel):
    """Response returned when an upload slot is allocated."""

    model_config = ConfigDict(extra="forbid")

    upload_id: str = Field(..., description="Unique upload identifier")
    upload_url: str = Field(..., description="Presigned S3 upload URL or local upload endpoint")
    object_key: str = Field(..., description="Private object key path")
    expires_at: Optional[str] = Field(default=None, description="Upload URL expiration timestamp (ISO 8601)")
    status: str = Field(default="ready", description="Upload slot status")


class FinalizeRequest(BaseModel):
    """Request to finalize an upload and enqueue analysis."""

    model_config = ConfigDict(extra="forbid")

    metadata: Optional[FrameMetadata] = Field(default=None, description="Frame metadata (GPS, IMU, grade, capture time)")
    source_mode: SourceMode = Field(default=SourceMode.UPLOAD, description="Source mode for this upload")


class FinalizeResponse(BaseModel):
    """Response returned after finalizing an upload."""

    model_config = ConfigDict(extra="forbid")

    upload_id: str = Field(..., description="Upload identifier")
    status: str = Field(default="queued", description="Processing status: queued")
    job_id: Optional[str] = Field(default=None, description="Associated job ID for polling lifecycle")
    message: Optional[str] = Field(default=None, description="Human-readable status message")


# --------------------------------------------------------------------------- #
# Health diagnostics
# --------------------------------------------------------------------------- #

class HealthStatus(BaseModel):
    """Basic service health status."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(default="healthy", description="Overall service status: healthy, degraded, unhealthy")
    version: str = Field(..., description="API version")
    services: Dict[str, Any] = Field(default_factory=dict, description="Sub-service statuses: database, s3, bedrock, model, worker")


class DeepHealthStatus(BaseModel):
    """Detailed health status with dependency probe results."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(default="healthy", description="Overall status")
    version: str = Field(..., description="API version")
    services: Dict[str, Any] = Field(default_factory=dict, description="Sub-service statuses")
    probes: Dict[str, Any] = Field(default_factory=dict, description="Live probe test outputs")
    probe_config: Dict[str, Any] = Field(default_factory=dict, description="Probe execution configuration")
    timestamp: str = Field(..., description="Health check execution timestamp")
