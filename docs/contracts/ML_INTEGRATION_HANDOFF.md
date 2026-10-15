# RoadSight AI: ML integration handoff (Phase 1 proposal)

Status: **proposed for ML owner review**, 16 October 2026. The implemented transport and Pydantic shapes are described below; scientific validity, calibration, distress, reference, and scoring are **not** approved by this document. `docs/final_plan.md` remains the product authority.

## Current entry point and lifecycle

The backend worker calls `backend.analysis.decode_image(path)`, then `backend.analysis.measure_frame(image, metadata)`, then `backend.analysis.build_segment_result(...)`. The ML owner owns `backend/quality/`, `backend/geometry/`, `backend/aggregate/`, `backend/distress/`, `backend/reference/`, and `backend/scoring/`; the backend owner owns this adapter, durable job/storage flow, Pydantic schemas, and API. Keep this boundary: do not make API routes import model internals.

For a still image: `POST /v1/uploads` allocates an object key and local or presigned PUT URL; PUT sends image bytes; `POST /v1/uploads/{id}/finalize` verifies object presence/size and creates a durable job; `GET /v1/jobs/{id}` polls it; `GET /v1/samples/{sample_id}` returns `SegmentResult`. S3-only objects are now fetched through the worker and decoded from private temporary storage; no public local copy is needed. A missing or undecodable object fails without a sample. A decoded image with no score yields a **partial** job and a sample with `score=null`; only an implemented numeric score can currently yield `succeeded`.

## Input contract

`FrameMetadata` (in `backend/schemas.py`) is optional and includes `gps`, `imu`, optional verified `grade`, `captured_at`, `monotonic_capture_time_ns`, `device_id`, `camera_profile_id`, `source_mode`, `frame_index`, and `telemetry_hash`. Upload time is not capture time. Preserve GPS accuracy and `simulated` flag. A profile ID alone does **not** prove calibration; `backend.analysis.resolve_scale` currently returns `PlanarScale.unscaled` for every input.

The image passed to `measure_frame` is decoded by OpenCV. Source bytes must be bounded by `MAX_UPLOAD_MB` (default 25 MiB); image decode failure is an invalid input, not an all-zero feature vector. The current quality gate may reject a frame, in which case metrics are absent.

## Output mapping and null semantics

The adapter returns a dictionary containing `quality`, `observed_area`, `metrics`, `geometry_valid`, and `limitations`. `build_segment_result` maps that into `SegmentResult` with sample/route ID, image provenance, capture/GPS/grade fields, evidence URLs, and `model_version`, `feature_version`, `scoring_version`. The stored `/v1/samples/{id}` response is the API contract; `backend/schemas.py` is the source of field names and types.

| Field | Current meaning | Required before a validated claim |
|---|---|---|
| `quality.status`, `quality.reasons` | Accepted, limited, or rejected image gate plus reason codes | ML owner confirms operating thresholds for the actual Indian camera and lighting. |
| `geometry_valid`, `observed_area.*_m2` | False and null physical area while scale is uncalibrated | Calibration profile and bounded scale uncertainty, valid road ROI, and independent geometry check. |
| `metrics.chip_count`, `aggregate_coverage` | Exploratory visible instance/coverage output where quality permits | Human-reviewed labels and transfer check on Indian road imagery; report minimum resolvable size and avoid treating unlabeled/no-instance as true zero. |
| `metrics.chip_density_per_m2`, `*diameter_mm`, `gap_*_mm` | Null without valid scale | Geometry, qualified instances/gaps, and stated estimator version. |
| `metrics.pothole_*`, `crack_*`, `texture_deviation` | Null unless their actual module ran and passed its domain gate | ML owner supplies masks/reference and validation. Missing distress is not zero distress. |
| `reference`, `score` | Null today | Human-reviewed known-good reference, held-out calibration, explicit unsupported/partial-input policy, and versioned score mapping. |
| `evidence` / overlays | Null unless a real artifact exists | Persist immutable object key, renderable private URL, and alignment to the source image. |

Use `null` for missing/unsupported/unmeasured, `0` only for a measured absence. Never infer millimetres or square metres from GPS or image pixels alone. Do not label an unvalidated score Good/Bad. Do not turn a quality-limited/unsupported frame into a confident score. Store model/config/reference version and data provenance with every result.

## Required ML owner decisions before API/UI promotion

1. Confirm the `quality` status and reason-code taxonomy, including which `limited` outputs may be displayed and when `rejected` forbids all metrics.
2. Confirm source scale provenance, minimum resolvable chip size, valid ROI/ignore mask, and uncertainty rule. A camera profile string without a verified calibration must remain unscaled.
3. Confirm chip boundary/count/density definitions, handling of partial border instances, and whether current experimental aggregate output may appear in the UI with an explicit qualifier. Preserve human review for ambiguous Indian surfaces.
4. Supply a group-disjoint evaluation report and versioned model artifacts for distress, reference, and score; state the route/site/camera split and performance on Indian imagery. If a required branch is missing, `score=null` remains the contract.
5. Provide the exact overlay format/coordinate transform and a model error taxonomy. Backend will map external failures to `failed` or `partial` without fabricating measurements.

## Integration acceptance checks

- Decodable local and S3-only uploads produce the same class of evidence; wrong/missing/oversized/undecodable objects do not produce a successful job.
- Quality rejection, unknown scale, missing ML stack, and missing score retain honest nulls and explicit status; retry/idempotency creates at most one sample for `(session, frame_index, model_version)`.
- Known synthetic geometry verifies area and density arithmetic; independent reviewed images verify real-world detection. Synthetic tests are not evidence of road accuracy.
- The frontend uses `GET /v1/jobs/{id}` and `GET /v1/samples/{id}` without computing scores itself, and marks `partial`, `failed`, simulated GPS, and uncalibrated metrics visibly.
- A final real-camera Indian road run and external AWS/Google Maps smoke test remain separate gates; replay does not satisfy live capture.
