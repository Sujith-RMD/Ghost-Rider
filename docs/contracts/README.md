# Ghost-Rider API Contracts

This directory contains the versioned API contract documentation for the Ghost-Rider backend.

**Owner:** Backend & AWS AI  
**Purpose:** Define the Pydantic/OpenAPI contract that ML and Frontend consume

## Versioning

Contracts are versioned. The current version is defined in `backend/schemas.py`.

Breaking changes require:
1. A new version number
2. Documentation of the change in this file
3. Coordination with ML and Frontend roles
4. A transition period where both versions are supported

## Schema Conventions

- `null` means not measured/unknown
- `0` means measured absence
- Units are always explicit (meters, mm, m², etc.)
- Missing GPS cannot become an Indian map coordinate
- Missing scale cannot become mm, cm², or count/m²
- All scientific fields are defined by ML role in docs/ml/

## Available Contracts

### Core Models (backend/schemas.py)

- **GPSData** - GPS fix with accuracy and simulated flag
- **IMUData** - Device orientation (pitch/roll/yaw)
- **FrameMetadata** - Frame-level metadata including source mode
- **AreaResult** - Road area measurements with scale info
- **QualityResult** - Image quality assessment with reasons
- **MetricResult** - Single measured metric with validity
- **AggregatedMetrics** - Aggregate and distress measurements
- **DistressEvidence** - Visual evidence references (masks, overlays)
- **ReferenceComparison** - Known-good reference comparison
- **ScoreResult** - Surface condition score with status
- **SegmentResult** - Full analysis for one segment
- **JobState** - Durable job lifecycle state
- **SessionState** - Live/replay session state
- **SegmentSummary** - 50m bin summary for maps
- **ReportContent** - Structured report content
- **ReportResult** - Generated report with Bedrock status

### API Endpoints

See `docs/contracts/endpoints.md` for the full endpoint specification.

## Cross-Role Coordination

1. **ML → Backend**: Propose scientific field definitions in `docs/ml/`
2. **Backend → ML**: Confirm field implementation in schemas.py
3. **Backend → Frontend**: Publish OpenAPI spec at `/docs`
4. **Frontend → Backend**: Request field/UX changes in `docs/frontend/`

Never silently change field meanings. Version and coordinate.

## Status Values

Quality: `accepted`, `limited`, `rejected`
Score: `Good`, `Bad`, `review`, `unknown`
Job: `received`, `validated`, `queued`, `processing`, `succeeded`, `partial`, `failed`
Source mode: `upload`, `live`, `replay`
Narrative: `generated`, `fallback`, `not_requested`

## Null vs Zero

This is critical for correct UI display:

```python
# CORRECT: Show "not measured" or "unknown"
score.value = null  # UI shows "Not scored"

# CORRECT: Show "0 defects detected"
score.value = 0     # UI shows "0" or "No defects"
```

The frontend must distinguish these cases. The backend never converts null to 0.

## Changelog

### v1.1.0 (2026-10-16)
Additive, non-breaking changes that complete the upload → job → sample slice:

- **New endpoint** `PUT /v1/uploads/{id}/local` — bounded streaming upload used
  when S3 is not configured; validates size and image magic header.
- **Changed** `POST /v1/uploads` — now returns a short-lived S3 **PUT** presigned
  URL (previously a GET presign was returned, which could not be used to upload).
- **Changed** `POST /v1/uploads/{id}/finalize` — persists frame metadata onto the
  job, records `received → validated → queued` in the new `job_events` table, and
  reports `object_not_found` / `conflict` error codes.
- **Additive field** `JobState.result_sample_id` — the sample produced once the
  job succeeds (`null` until then).
- **New table** `job_events` (transition history) and `processed_frames`
  (worker idempotency on `(session_id, frame_index, model_version)`).

No existing field changed meaning. ML units and the null-vs-zero policy are
unchanged.

### v1.2.0 (2026-10-16)
Additive, non-breaking India distress localization evidence on stored samples:

- `SegmentResult.distress_detection` reports detector status, checkpoint SHA-256,
  model version, image dimensions, inference time, confidence threshold, class
  names, and bounding boxes in original-image pixel coordinates.
- Detection evidence is persisted with each sample. Missing weights and inference
  failures are explicit; no generic pretrained model is substituted.
- The field is optional. Existing quality metrics and scores are unchanged; boxes
  do not establish physical size, area, roughness, or Good/Bad road quality.

The v1.1.0 upload/job lifecycle additions remain unchanged.
