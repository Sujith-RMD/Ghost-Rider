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
| Worker (live frames + durable jobs) | `backend/worker.py` | 1.1.0 | Implemented (typed stub analysis) |
| Health Endpoint | `backend/app/health.py`, `/v1/health` | 1.1.0 | Implemented |

### 🔄 In Progress

| Contract | Location | Notes |
|----------|----------|-------|
| v1 sessions/frames (live) | `backend/api/v1.py` | Endpoints implemented; real camera transport pending hardware |
| v1 segments (50 m bins) | `backend/api/v1.py`, `backend/routes/` | Binning + coverage-truth implemented; real GPS data pending |
| Bedrock reports | `backend/reports/` | Live Bedrock **verified** (`apac.amazon.nova-micro-v1:0`) |

### 📋 Planned / pending external

| Item | Priority | Dependency |
|------|----------|------------|
| S3 private upload smoke test | High | ✅ **PASS** — bucket created in `ap-southeast-2` (SCP is region-scoped); full round-trip verified (`docs/backend/AWS_SMOKE_TEST.md` Run 2) |
| Bedrock Converse smoke test | High | ✅ Verified live in `ap-southeast-2` (`apac.amazon.nova-micro-v1:0`) |
| Google Maps data contract render | Medium | Frontend |
| Real ML artifact wired into worker | High | ML AI delivers packaged interface |
| S3 lifecycle policy (raw-frame expiry) | Low | `s3:PutLifecycleConfiguration` denied by IAM policy — admin-applied, optional |

## Version History

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
