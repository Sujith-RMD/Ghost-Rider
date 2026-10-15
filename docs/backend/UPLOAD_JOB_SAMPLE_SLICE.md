# Upload → Job → Sample Slice

**Owner:** Backend & AWS AI
**Status:** Implemented and tested (local/S3-less path proven; live S3 smoke test pending)
**Last Updated:** 16 October 2026
**Reference:** `docs/final_plan.md` §11.4, `docs/backend/CONTRACT_STATUS.md`

This document records the acceptance-critical slice: a new file is uploaded
privately, validated, processed **exactly once despite retries**, stored with full
versions and honest evidence, and returned through the API without fabricated
fields.

## Proven flow

| Step | Call | Result |
|------|------|--------|
| 1. Allocate | `POST /v1/uploads` | `upload_id`, `object_key`, short-lived **PUT** `upload_url` (S3) or `/v1/uploads/{id}/local` |
| 2. Transfer | `PUT` to `upload_url` | Object stored privately; local path returns `size_bytes` + `sha256` |
| 3. Finalize | `POST /v1/uploads/{id}/finalize` | Object verified; frame metadata persisted; durable job created (`received → validated → queued`); returns `job_id` |
| 4. Process | worker (inline thread or `python -m backend.worker`) | Claims the job atomically, stores one sample, marks job `succeeded`, links `result_sample_id` |
| 5. Read | `GET /v1/jobs/{id}` then `GET /v1/samples/{id}` | Terminal job state + linked sample with versions, provenance and nulls for unmeasured physics |

`uploads/` is served read-only at `/uploads` for the local fallback; with S3
configured the client uploads directly to the bucket with a private presigned PUT
and the backend only `HEAD`s the object at finalize.

## Job lifecycle and durability

```
received → validated → queued → processing → succeeded / partial / failed
```

- **Transition history** is appended to `job_events` (status, detail, timestamp),
  so the reason for every state is durable.
- **Idempotency** is enforced on `(session_id, frame_index, model_version)` via the
  `processed_frames` table with an `INSERT OR IGNORE` marker written in the same
  transaction as the sample. A retry can never double-store a result.
- **Leases / retry recovery**: a claimed job gets a `lease_expires_at`. If the
  worker crashes mid-job, the lease expires and the job becomes claimable again.
  Attempts are capped (`GHOST_RIDER_JOB_MAX_ATTEMPTS`, default 3); beyond that the
  job is failed with `attempt_limit_exceeded`.
- **Atomic writes**: the processed-frame marker, sample row and session counter
  update commit together or not at all.

## Honest results

The worker's analysis step (`worker.run_upload_inference` / `run_inference`) is the
single ML integration seam. Until the ML AI delivers a packaged artifact it returns
a **typed stub** whose physical measurements are all `null`:

- `geometry_valid = false`, `observed_area = null`, `metrics = null`, `score = null`,
  `quality = null`
- Provenance that *is* known is preserved: `captured_at`, GPS (with accuracy and a
  `simulated` flag), `image_path`/`image_url`, `model_version`/`feature_version`/
  `scoring_version`.

An uncalibrated frame never gains physical units, and absent GPS never becomes a
fabricated position.

## How to run

```powershell
# from the repository root, using the project venv
.venv\Scripts\python.exe -m pytest tests/backend -q      # 46 tests
```

The API starts an **inline worker thread** by default (single-host prototype) and
processes finalized jobs automatically. For the deployed two-process layout:

```powershell
$env:GHOST_RIDER_INLINE_WORKER = "false"                 # API process: no inline worker
$env:PYTHONPATH = "D:\PROJECTS\Ghost-Rider"
.venv\Scripts\python.exe -m backend.worker --poll 1.0    # separate worker process
```

### Relevant environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `GHOST_RIDER_INLINE_WORKER` | `true` | Run the worker inside the API process |
| `GHOST_RIDER_JOB_MAX_ATTEMPTS` | `3` | Attempt cap before a job is failed |
| `GHOST_RIDER_JOB_LEASE_SECONDS` | `300` | Processing lease before a stuck job is reclaimable |
| `MAX_UPLOAD_MB` | `25` | Local streaming upload cap |
| `GHOST_RIDER_MODEL_VERSION` / `_FEATURE_VERSION` / `_SCORING_VERSION` | `stub*` | Versions recorded on results |

## Tests

- `tests/backend/test_upload_job_sample_slice.py`
  - `test_upload_job_sample_slice` — full allocate → PUT → finalize → process → read
  - `test_job_processing_is_idempotent` — a second attempt creates no second sample
  - `test_process_frame_stores_single_sample` — live/replay frame idempotency
  - `test_finalize_without_object_is_rejected` — `object_not_found`
  - `test_upload_rejects_non_image_bytes` — `invalid_image`

## Not yet done (external dependencies)

- **Live S3 smoke test**: private PUT presign → `HEAD` → finalize. Requires AWS
  credentials in the environment (the S3 PUT presign code path is implemented but
  has only been exercised against the local fallback).
- **Real ML artifact** in `run_upload_inference` (ML owner delivers the interface).
- **Live camera transport** feeding the same engine with an explicit `live` mode.
