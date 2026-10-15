# Ghost-Rider Contract Status

**Owner:** Backend & AWS AI  
**Last Updated:** 16 October 2026

## Published Contracts

### ✅ Complete (upload → job → sample slice proven end-to-end)

| Contract | Location | Version | Status |
|----------|----------|---------|--------|
| Pydantic Schemas | `backend/schemas.py` | 1.1.0 | Published (provisional — pending ML confirm) |
| API Endpoints Spec | `docs/contracts/endpoints.md` | 1.1.0 | Published |
| v1 uploads (+ bounded local PUT) | `backend/api/v1.py` | 1.1.0 | Implemented + tested |
| v1 jobs (durable lifecycle + events) | `backend/api/v1.py`, `backend/worker.py` | 1.1.0 | Implemented + tested |
| v1 samples | `backend/api/v1.py` | 1.1.0 | Implemented + tested |
| Worker (live frames + durable jobs) | `backend/worker.py` | 1.2.0 | Implemented — **real** quality→measure pipeline via `backend/analysis.py`; scoring pending |
| Health Endpoint | `backend/app/health.py`, `/v1/health` | 1.1.0 | Implemented |

### 🔄 In Progress

| Contract | Location | Notes |
|----------|----------|-------|
| v1 sessions/frames (live) | `backend/api/v1.py` | Endpoints implemented; real camera transport pending hardware |
| v1 segments (50 m bins) | `backend/api/v1.py`, `backend/routes/` | Binning + coverage-truth implemented; real GPS data pending |
| Bedrock reports | `backend/reports/` | Live Bedrock **verified** (`apac.amazon.nova-micro-v1:0`) |
| Distress / scoring / reference | `backend/distress/`, `scoring/`, `reference/` | Empty ML packages — `score`/`reference`/`evidence` stay **null** (not fabricated) |

### 📋 Planned / pending external

| Item | Priority | Dependency |
|------|----------|------------|
| S3 private upload smoke test | High | ✅ **PASS** — bucket created in `ap-southeast-2` (SCP is region-scoped); full round-trip verified (`docs/backend/AWS_SMOKE_TEST.md` Run 2) |
| Bedrock Converse smoke test | High | ✅ Verified live in `ap-southeast-2` (`apac.amazon.nova-micro-v1:0`) |
| Google Maps data contract render | Medium | Frontend |
| Real ML artifact wired into worker | High | 🔄 Aggregate + quality **wired live** (`backend/analysis.py`); distress path wired (crack-mask metrics + canonical features); runtime distress **detection** and scoring modules still empty (ML AI) |
| S3 lifecycle policy (raw-frame expiry) | Low | ✅ **Live** — rule `ghost-rider-expire-raw-uploads` applied (expire `uploads/` after 7 d + abort incomplete multiparts); IAM permission granted by the account owner |
| Canonical record persistence | Medium | ✅ **Done** — `canonical_json` column + additive migration; `GET /v1/samples/{id}` returns the §11.5 record (real sha256, geometry, feature list; absent when nothing was measured) |
| Live camera transport test | High | Camera-access track (hardware) |

## Version History

### v1.3.0 (2026-10-16)
- **Merged with the frontend team's integration** (`14f196f`, `9ec7999`): S3
  uploads are fetched via presigned download into a private temp dir during
  analysis, and jobs complete as **`partial`** (not `succeeded`) whenever no
  SQI score exists yet — truthful while the scoring module is undelivered;
  canonical provenance (sha256) is captured before the temp dir is removed and
  `original_uri` is the S3 object key.
- **Tiled measurement**: `measure_frame` now uses the ML team's
  `measure_tiled` (native-resolution tiles, boundary-safe instance merge) —
  verified: 120 instances on a 1024×768 synthetic frame counted exactly once;
  small frames unchanged (regression-tested).
- **Canonical sample records persisted**: `samples.canonical_json` column +
  additive migration; sample-id allocated before inference so the canonical
  identity matches the stored row; `GET /v1/samples/{id}` returns the
  final-plan §11.5 record (real sha256/URI, geometry, camera, feature list);
  the record is **absent** when nothing was measured (never fabricated).
- **Distress path wired**: crack-mask measurements translate into
  `crack_skeleton_length_m` / `crack_total_area_m2` plus canonical feature rows
  (density, extent); unscaled frames stay `null`. Runtime crack detection
  still awaits the ML model artifact.
- 66/66 backend tests pass.
- Lifecycle rule artifact: `infra/s3-lifecycle.json` (apply command in the
  runbook) — still IAM-blocked for this user.

### v1.2.0 (2026-10-16)
- **Real ML pipeline wired into the worker** (replaces the typed stub):
  `backend/analysis.py` decodes (Windows-path safe) → quality gate
  (`backend.quality`) → unscaled `PlanarScale` → aggregate measurement
  (`backend.aggregate.measure_surface`) → contract translation. Counts/ratios
  are real; every mm/m²/count-per-m² value stays `null` without calibration.
  Verified against the ML team's synthetic generator: chip count 60/60 on all
  seeds; `MODEL_VERSION=measure-v1`, `FEATURE_VERSION=quality-v1`
  (version-pinned idempotency keeps old stub rows intact).
- **CPU latency measured** (512×512): median 1.8 s/frame, ≈0.6 fps single-core
  — recorded in `docs/backend/AWS_RUNBOOK.md` §5 (GPU decision deferred to ML
  owner per final plan).
- **Failure/recovery tests**: crashed-worker lease reclaim, active-lease
  protection, attempt-limit failure with reason code, analysis-stack crash →
  job fails with no fabricated sample, S3 degradation to local URLs.
- **AWS runbook published**: `docs/backend/AWS_RUNBOOK.md` (deploy, ops,
  failure playbook, cost controls, honest known gaps).
- `scipy>=1.10.0` added to `pyproject.toml` / `backend/requirements.txt`
  (imported by the ML modules; was undeclared).
- 60/60 backend tests pass.

### v1.1.2 (2026-10-16)
- **Region: `ap-southeast-2` throughout** — the org SCP `p-fakk0ucg` is
  region-scoped: `s3:CreateBucket` is denied outside `ap-southeast-2` (verified
  in `ap-south-1`) and allowed inside it. `Settings.AWS_REGION` default, deploy
  script, smoke test, docs and test fixtures moved from `ap-south-1`.
- **S3 bucket created**: `ghost-rider-road-storage` in `ap-southeast-2`, private
  (Block Public Access ON, SSE-S3).
- **Presigned-URL fix**: boto3 1.43.x presigns against the global
  `s3.amazonaws.com` host; S3 answers with `307 TemporaryRedirect`, which breaks
  the signed `host` header (`SignatureDoesNotMatch`). Fixed by pinning
  `AWS_S3_ENDPOINT_URL=https://s3.ap-southeast-2.amazonaws.com` (already honoured
  by `s3_service`). Smoke test now **PASS** end-to-end (PUT → HEAD → GET).
- Bedrock verified live in `ap-southeast-2` (a transient "account is currently
  being verified" block cleared within the session).
- Remaining AWS permission gaps (IAM-policy denies, optional): bucket
  management/lifecycle actions (`s3:PutLifecycleConfiguration`,
  `s3:ListAllMyBuckets`, ...).

### v1.1.1 (2026-10-16)
- Live AWS smoke test run (account `431223004441`, `ap-south-1`): **Bedrock verified**;
  bare `amazon.nova-micro-v1:0` rejected → added `backend/bedrock_models.py` and made
  `Settings`/`bedrock_service`/`reports` auto-promote bare Nova ids to the regional
  cross-region inference profile (`apac.`/`eu.`) — no-op in working regions.
- S3 blocked: Organizations SCP `p-fakk0ucg` denies `s3:CreateBucket` account-wide
  (console included) — bucket must be created by the org admin. See `docs/backend/AWS_SMOKE_TEST.md`.
- Tests made hermetic: `tests/backend/conftest.py` disables dotenv (`GHOST_RIDER_DISABLE_DOTENV=1`)
  and clears ambient AWS creds so a developer's `backend/.env` never reaches live AWS.
- 46/46 backend tests pass.

### v1.1.0 (2026-10-16)
- Completed and tested the upload → durable job → sample slice (see `docs/backend/UPLOAD_JOB_SAMPLE_SLICE.md`)
- Added `PUT /v1/uploads/{id}/local`; `POST /v1/uploads` now returns an S3 PUT presign
- Finalize persists frame metadata and records `received → validated → queued` in `job_events`
- Additive `JobState.result_sample_id`; new `job_events` and `processed_frames` tables
- Worker rewired onto the shared bounded ingestion queue with idempotent persistence
- 30/30 backend tests pass

### v1.0.0 (2026-10-15)
- Initial schema publication
- Core enums: QualityStatus, ScoreStatus, JobStatus, SourceMode, NarrativeStatus
- Core models: GPSData, IMUData, FrameMetadata, AreaResult, QualityResult
- Metric models: AggregatedMetrics, DistressEvidence, ReferenceComparison
- Scoring: ScoreResult with null/zero semantics
- Session models: JobState, SessionState
- Map models: SegmentSummary, SegmentList
- Report models: ReportContent, ReportResult
- Upload models: UploadRequest/Response, FinalizeRequest/Response
- Health models: HealthStatus, DeepHealthStatus

## Coordination Log

| Date | Change | ML Confirmed | Frontend Confirmed |
|------|--------|--------------|-------------------|
| 2026-10-15 | Initial schema publication | Pending | Pending |
| 2026-10-16 | Additive v1.1.0: local PUT, `result_sample_id`, job events (no field meaning changed) | Pending | Pending |

## Pending Decisions

| Decision | Owner | Status |
|----------|-------|--------|
| Exact Bedrock model ID | Backend + User | Waiting for AWS setup |
| Score threshold values | ML + Backend | Pending ML proposal |
| Camera calibration format | ML + Backend | Pending camera access |
| Session frame queue limits | Backend | Designing |
| Segment bin size (50m default) | Backend | Configured, adjustable |
| schemas.py acceptance as the ML-visible contract proposal | ML + Backend | Open — see below |

## ML Contract Proposal Status

`backend/schemas.py` is published as **backend's proposed v1 contract**, not as agreed science. Until ML confirms the following in `docs/ml/`, the sample/segment/score shapes in the v1 handlers are provisional and may be refined: unit conventions (mm, m², counts/m²), null vs zero meanings per field, minimum resolvable chip diameter / gap width, quality reason taxonomy, score status taxonomy, and whether any field is mandatory vs optional for a valid result. Frontend fixtures built from this schema must be labeled mock until that confirmation lands.

## Integration Notes

### With ML Role
- ML owns scientific field definitions in docs/ml/
- Backend publishes agreed fields in schemas.py
- Versions must be coordinated: model_version, feature_version, scoring_version
- Null/zero semantics are critical for ML results

### With Frontend Role
- Frontend consumes published OpenAPI at /docs
- Mock fixtures allowed until real contract stabilizes
- Health endpoint shape agreed
- Upload/session state machines need UX alignment

### Breaking Changes
Any breaking change requires:
1. New minor/major version
2. Documentation in this file
3. Coordination with ML and Frontend
4. Transition period for both consumers
