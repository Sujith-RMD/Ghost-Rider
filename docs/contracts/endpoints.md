# Ghost-Rider API Endpoints

**Version:** 1.2.0
**Format:** OpenAPI 3.0 compatible
**Base URL:** `/v1`

See `backend/schemas.py` for detailed model definitions.

## Authentication

None required for local development. Production deployments use AWS IAM or JWT tokens.

## Endpoints

### Live and report integration additions (2026-10-16)

- `GET /v1/sessions/{id}` returns `SessionState`, including lifecycle `status`
  (`live` or `finished`) and nullable `latest_sample_id`. Counters and capture /
  processing timestamps come from the stored session. Unknown sessions return 404.
- `POST /v1/sessions/{id}/frames` requires multipart camera bytes and metadata;
  finished sessions return 409. The browser waits for its outstanding frame before
  sending another and captures at most once every five seconds.
- `POST /v1/reports` requires an existing sample or a job with a stored sample.
  Unknown assessments return 404; unfinished jobs return 409. Supplied measurement
  fields are ignored. Report persistence failure returns 503.
- `GET /v1/reports/{id}` returns the saved `ReportResult`, or 404 if absent.

The published OpenAPI snapshot and frontend generated types include these changes.

### Uploads

#### POST /v1/uploads

Allocate a private object key and short-lived upload URL.

**Request:**
```json
{
  "filename": "road_frame.jpg",
  "content_type": "image/jpeg",
  "expected_size": 2048576
}
```

**Response (201 Created):**
```json
{
  "upload_id": "uuid-here",
  "upload_url": "/uploads/route-id/frame.jpg",
  "object_key": "uploads/route-id/frame.jpg",
  "expires_at": "2026-10-15T12:00:00Z",
  "status": "ready"
}
```

**Behavior:**
- Returns a short-lived presigned S3 **PUT** URL when AWS is configured (content type is bound into the signature when supplied)
- Returns the bounded local upload endpoint (`/v1/uploads/{id}/local`) otherwise
- URL expires in 1 hour (configurable via `PRESIGNED_URL_TTL`)

---

#### PUT /v1/uploads/{id}/local

Bounded streaming upload used when S3 is not configured (and for the local/replay
demonstration path). Used when `POST /v1/uploads` returns a `/v1/uploads/{id}/local`
upload URL.

**Request:** raw image bytes (`Content-Type: image/jpeg` etc.)

**Response (200 OK):**
```json
{
  "upload_id": "uuid-here",
  "status": "uploaded",
  "object_key": "uploads/upload-uuid/frame.jpg",
  "size_bytes": 2048576,
  "sha256": "9f2c...64-hex...",
  "uploaded_at": "2026-10-16T09:15:00+00:00"
}
```

**Behavior:**
- Streams to disk under the media root; enforces `MAX_UPLOAD_MB` (default 25) and aborts oversized uploads with `upload_too_large`
- Validates the image magic header; rejects non-images with `invalid_image`
- Empty bodies are rejected with `empty_upload`
- Only `ready`/`uploaded` slots accept bytes; other states return `409 conflict`

---

#### POST /v1/uploads/{id}/finalize

Check uploaded object and enqueue analysis.

**Request:**
```json
{
  "metadata": {
    "gps": {"lat": 12.9716, "lon": 77.5946, "accuracy_m": 5.0},
    "imu": {"pitch_deg": 0.0, "roll_deg": 0.0},
    "captured_at": "2026-10-15T10:30:00Z",
    "source_mode": "upload"
  }
}
```

**Response (202 Accepted):**
```json
{
  "upload_id": "uuid-here",
  "status": "queued",
  "job_id": "job-uuid",
  "message": "Analysis queued"
}
```

**Behavior:**
- Validates the object exists and is non-empty (local: file under the media root; S3: `HEAD` with `ContentLength > 0`)
- Persists the supplied frame metadata (GPS/IMU/capture time) on the job for the worker
- Creates a durable job and records the `received → validated → queued` transition history in `job_events`
- Returns `400 object_not_found` when the object is missing; `409 conflict` when the slot was already finalized
- **Upload success ≠ analysis success**: the job is only `succeeded` after the worker stores a sample

After finalize, poll `GET /v1/jobs/{id}` until it is terminal, then read the linked
sample via `result_sample_id` (`GET /v1/samples/{id}`).

---

### Sessions

#### POST /v1/sessions

Create a live/replay session.

**Request:**
```json
{
  "mode": "live",
  "camera_id": "camera-001",
  "calibration_id": "cal-2026-10"
}
```

**Response (201 Created):**
```json
{
  "session_id": "session-uuid",
  "mode": "live",
  "camera_id": "camera-001",
  "calibration_id": "cal-2026-10",
  "created_at": "2026-10-15T10:00:00Z",
  "frame_count": 0,
  "processed_count": 0,
  "rejected_count": 0,
  "dropped_count": 0
}
```

**Behavior:**
- Creates session with explicit mode
- Associates camera and calibration profile
- Tracks frame counts for live/replay distinction

---

#### POST /v1/sessions/{id}/frames

Accept a frame sequence.

**Request (multipart):**
- `frame`: Image file (required)
- `metadata`: JSON with GPS, IMU, timestamps

**Response (200 OK):**
```json
{
  "session_id": "session-uuid",
  "frame_index": 42,
  "captured_at": "2026-10-15T10:30:00.000Z",
  "processed_at": "2026-10-15T10:30:01.500Z",
  "status": "received"
}
```

**Behavior:**
- Accepts frame with original reference
- Stores capture times (UTC and monotonic)
- Validates metadata format
- Handles replay vs live differently
- Rate limits to bounded queue

---

#### POST /v1/sessions/{id}/finish

Close capture and request segment aggregation.

**Request:**
```json
{
  "final_timestamp": "2026-10-15T10:45:00Z"
}
```

**Response (200 OK):**
```json
{
  "session_id": "session-uuid",
  "status": "finished",
  "total_frames": 1500,
  "processed_frames": 1485,
  "rejected_frames": 15,
  "aggregation_job_id": "job-uuid"
}
```

**Behavior:**
- Closes the capture session
- Triggers segment aggregation
- Returns aggregation job ID

---

### Jobs

#### GET /v1/jobs/{id}

Return durable lifecycle state.

**Response (200 OK):**
```json
{
  "job_id": "job-uuid",
  "status": "processing",
  "error_reason": null,
  "attempt_count": 1,
  "started_at": "2026-10-15T10:30:01Z",
  "completed_at": null,
  "updated_at": "2026-10-15T10:30:05Z",
  "versions": {
    "model": "stub-0.0.0",
    "feature": "stub",
    "scoring": "stub"
  },
  "result_sample_id": null
}
```

`result_sample_id` is `null` until the job succeeds, then holds the id of the
stored sample (`GET /v1/samples/{result_sample_id}`).

**Job Status Values:**
- `received` - Job created, waiting validation
- `validated` - Input validated, waiting queue
- `queued` - In processing queue
- `processing` - Currently being processed
- `succeeded` - Completed successfully
- `partial` - Completed with partial results
- `failed` - Failed with error

**Behavior:**
- Immutable state transitions
- Preserves attempt count and timestamps
- Returns error reason on failure

---

### Samples

#### GET /v1/samples/{id}

Return evidence, metrics, quality, score and narrative status.

**Response (200 OK):**
```json
{
  "sample_id": "sample-uuid",
  "segment_id": 42,
  "route_id": "route-uuid",
  "image_url": "/uploads/route-id/frame.jpg",
  "mask_url": "/uploads/route-id/mask_frame.jpg",
  "overlay_url": "/uploads/route-id/overlay_frame.jpg",

  "quality": {
    "status": "accepted",
    "reasons": ["sharp", "proper_exposure"],
    "min_source_resolution": 1920
  },

  "geometry_valid": true,
  "observed_area": {
    "observed_area_m2": 12.5,
    "eligible_area_m2": 10.2,
    "ignored_area_m2": 0.5,
    "distress_area_m2": 1.8,
    "scale_source": "camera_calibration",
    "scale_uncertainty": 0.02
  },

  "metrics": {
    "chip_count": 23,
    "chip_density_per_m2": 1.84,
    "min_chip_diameter_mm": 2.5,
    "median_chip_diameter_mm": 8.3,
    "aggregate_coverage": 0.15,
    "crack_skeleton_length_m": 0.42,
    "pothole_count": 2,
    "pothole_total_area_m2": 0.8,
    "crack_total_area_m2": 0.9,
    "gap_median_mm": 15.2,
    "gap_sample_count": 12
  },

  "score": {
    "value": 65,
    "status": "review",
    "reference_version": "0.2.0",
    "policy_version": "0.2.0",
    "texture_term": 0.12,
    "distress_term": 0.28,
    "severe_defect_flag": true,
    "reasons": ["moderate_distress", "severe_defect_present"]
  },

  "reference": {
    "reference_version": "0.2.0",
    "feature_count": 6,
    "deviation_robust": 1.8,
    "supported_surface": true
  },

  "model_version": "yolov8n-0.1.0",
  "feature_version": "0.1.0",
  "scoring_version": "0.2.0",
  "created_at": "2026-10-15T10:35:00Z"
}
```

**Null vs Zero Semantics:**
- `null` = not measured/unknown (show "Not measured" in UI)
- `0` = measured absence (show "0" or "None detected")
- Missing GPS → no map coordinates
- Missing scale → no physical units

---

### Segments

#### GET /v1/sessions/{id}/segments

Return bin summaries and coverage truth.

**Response (200 OK):**
```json
{
  "route_id": "route-uuid",
  "segments": [
    {
      "segment_id": 1,
      "start_distance_m": 0.0,
      "end_distance_m": 50.0,
      "center_lat": 12.9716,
      "center_lon": 77.5946,
      "gps_accuracy_m": 5.0,
      "simulated": false,
      "sample_count": 30,
      "unique_area_m2": 8.5,
      "strip_area_m2": 12.0,
      "accepted_sample_count": 28,
      "median_score": 65,
      "lower_tail_score": 45,
      "serious_defect_observed": true,
      "unknown_coverage": false
    }
  ],
  "total_distance_m": 500.0,
  "coverage_percentage": 85.0,
  "unsampled_stretches": [
    {"start_m": 200.0, "end_m": 250.0}
  ]
}
```

**Behavior:**
- 50m reporting bins (configurable)
- Groups duplicate/overlapping frames
- GPS coordinates with accuracy
- Marks simulated vs real positions
- Shows unknown coverage explicitly
- Never fills gaps with Good/Bad

---

### Reports

#### POST /v1/reports

Generate factual report and Bedrock wording.

**Request:**
```json
{
  "assessment_id": "sample-uuid",
  "include_narrative": true
}
```

**Response (201 Created):**
```json
{
  "report_id": "report-uuid",
  "assessment_id": "sample-uuid",
  "content": {
    "summary": "Road segment shows moderate distress with 2 potholes detected...",
    "evidence_references": ["mask_frame.jpg", "overlay_frame.jpg"],
    "limitations": ["GPS accuracy 5m", "Single camera angle"],
    "inspection_actions": ["Inspect pothole at lat/lon", "Reassess after rain"],
    "narrative_status": "generated",
    "factual_template_used": false
  },
  "generated_at": "2026-10-15T10:36:00Z",
  "bedrock_model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
  "factual_input_hash": "sha256-abc123..."
}
```

**Behavior:**
- Uses Boto3 Bedrock Converse API
- Records exact model ID and input hash
- Caches by assessment hash
- Falls back to factual template on failure
- Validates all referenced facts
- Never asks Bedrock to estimate metrics

---

### Health

#### GET /v1/health

Service health check.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "version": "1.2.0",
  "services": {
    "database": {"status": "ok", "path": "/path/to/db"},
    "s3": {"status": "configured", "bucket": "ghost-rider-road-storage"},
    "bedrock": {"status": "configured", "model": "anthropic.claude-3-5-sonnet"},
    "model": {"status": "loaded", "name": "yolov8n"}
  }
}
```

---

#### GET /v1/health/deep

Detailed health with dependency probes.

**Query Parameters:**
- `probe`: `auto` (default) | `aws` | `none`

**Response (200 OK):**
```json
{
  "status": "healthy",
  "version": "1.2.0",
  "services": {
    "database": {"latency_ms": 0.5, "status": "ok"},
    "s3": {"bucket": "ghost-rider-road-storage", "region": "ap-southeast-2"},
    "bedrock": {"model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0"},
    "model": {"loaded": true, "type": "yolov8n"}
  },
  "probes": {
    "s3": {"head_bucket": "ok", "latency_ms": 150},
    "bedrock": {"converse_test": "ok", "latency_ms": 2000}
  },
  "probe_config": {
    "mode": "auto",
    "s3_timeout_ms": 5000,
    "bedrock_timeout_ms": 10000
  },
  "timestamp": "2026-10-15T10:30:00.000Z"
}
```

---

## Error Responses

All errors follow this format:

```json
{
  "detail": {
    "error": "error_code",
    "message": "Human-readable message",
    "fields": {}
  }
}
```

**Common Error Codes:**
- `invalid_metadata_json` - Metadata is not valid JSON
- `route_not_found` - Route ID doesn't exist
- `file_too_large` - Upload exceeds size limit
- `unsupported_media_type` - File is not a valid image
- `empty_upload` - Uploaded file is empty
- `no_images` - No images to process
- `already_processing` - Route already being processed
- `s3_unavailable` - S3 service unavailable
- `bedrock_unavailable` - Bedrock service unavailable

### India distress localization (v1.2.0)

`GET /v1/samples/{id}` may include `distress_detection`. Successful results carry
boxes as `[x1, y1, x2, y2]` in original-image pixels, confidence values, class
names, and the exact checkpoint hash. `unavailable` means weights are absent;
`error` means inference failed. A successful empty `detections` list means the
model returned no boxes at its configured confidence threshold, not proof that
no road defect exists. This evidence is localization only and does not alter
quality or score fields.
