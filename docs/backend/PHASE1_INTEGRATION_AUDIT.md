# RoadSight Phase 1 integration audit — 16 October 2026

**Implementation update:** The audit below records the original baseline. The isolated `phase1-integration` worktree now fixes I-01 and the upload portion of I-03: S3-only bytes are read through a bounded private temporary file, missing/undecodable uploads fail, and analysed but unscored samples receive `partial`. S3 and local finalize enforce the configured size cap; live multipart reads are bounded. `docs/contracts/openapi.v1.json` is a generated snapshot of the running `1.0.0` API, and `docs/contracts/ML_INTEGRATION_HANDOFF.md` proposes the ML boundary. Backend verification after these changes: **62 passed, one Starlette/httpx deprecation warning**. This does not close I-02 (frontend owner integration), scientific ML gates, actual camera, live AWS, or Google Maps.

The frontend owner patch is a separate review artifact. It connects the production Assess route to allocate → PUT → finalize → poll → sample, resumes a saved job after reload, and displays `partial` with nulls distinct from measured zero. It was tested in an isolated copy of the current `web/` tree: TypeScript passed, production build passed, 24 frontend tests passed. A local Chrome smoke run against the actual patched FastAPI service successfully uploaded and analysed a new JPEG, displayed the persisted partial sample, and resumed it after reload. The original teammate-owned `web/` tree was not modified. The frontend owner must review/apply the patch before calling the integrated team branch complete.

Scope: read-only audit of the local Ghost-Rider checkout. No ML code or scientific definitions were changed. This is not a completion claim for Phase 1.

## Baseline and test evidence

- Local branch name: `main`; `git log -1` reports `6c84ddb5f40e1a0f1151da7986c02fa41869b8b9` (`feat(backend): wire real ML pipeline into worker, failure tests, AWS runbook`). `git diff --name-only` shows existing frontend and frontend-document changes. `git status` fails with `fatal: this operation must be run in a work tree` against this OneDrive reparse-point checkout, so the complete dirty-tree inventory and remote parity are **not verified**. `git ls-remote origin` was blocked by local Git credential/MSYS startup errors; remote HEAD is **not verified**. Do not overwrite existing frontend work.
- Backend: an isolated Python 3.12 dependency target in the Codex workspace ran `pytest tests/backend -q --basetemp <workspace temp>` with `GHOST_RIDER_DISABLE_DOTENV=1` and `GHOST_RIDER_INLINE_WORKER=false`: **60 passed, one Starlette/httpx deprecation warning**. The first run had 57 passed/3 setup errors solely because pytest could not write its default sandbox temp directory; the rerun above removed that environment error. No live AWS call was made during this audit.
- Frontend: `npm run typecheck` passed; `npm test` passed **22/22**; `npm run build` passed. These are separate service checks, not a connected browser/upload test.
- There is no committed OpenAPI JSON in `docs/contracts/`. The v1 FastAPI app generates OpenAPI at runtime. The published `docs/contracts/endpoints.md` and frontend's `CONTRACT_QUESTIONS.md` do not yet close the browser integration contract.

## What exists

| Area | Observed status | Evidence and limit |
|---|---|---|
| v1 FastAPI and SQLite | Implemented, locally tested | `backend/api/server.py`, `backend/api/v1.py`, `backend/queues.py`; backend tests start the app and exercise local upload/job/sample. |
| Local image upload and durable job | Implemented, locally tested | `backend/api/v1.py:143-378`, `backend/worker.py:246-459`; 60 backend tests include upload, invalid bytes, idempotency, lease recovery, failure. |
| ML quality and aggregate path | Implemented, limited | `backend/analysis.py` calls ML-owned quality/geometry/aggregate modules. The current checkout is **ahead of the pasted brief's “ML code not pushed” assumption**. Scale is intentionally uncalibrated; scoring/reference/distress remain absent. Public-source chip validity and Indian transfer are unproven per `docs/ml/TASKS.md`. |
| S3 | Service smoke test reported in team notes, app-level worker path unverified | `docs/backend/AWS_SMOKE_TEST.md` reports a prior private PUT/HEAD/GET in `ap-southeast-2`; this audit made no cloud call. The worker cannot read S3-only bytes (issue I-01). |
| Bedrock | Prior service call documented; reporting path tested locally | `docs/backend/AWS_SMOKE_TEST.md` reports live Converse; `tests/backend/test_bedrock_reports.py` checks local behavior. No cloud call in this audit. |
| Frontend | Builds and tests, real service disconnected | `web/vite.config.ts:18-25` selects fixtures for development/demo and `web/src/api/disconnected.ts` for production. `web/src/features/assess/AssessPage.tsx:130-143` disables Analyse. |
| Google Maps | Component exists, real key/GPS not tested | `web/src/features/route-map/GoogleRouteMap.tsx`; simulated fixture is labeled. No verified Maps browser key, marker or real route in this audit. |
| Live camera | HTTP frame endpoint exists; camera transport unverified | `backend/api/v1.py:432-503`; no actual road camera is available. A replay cannot pass the live gate. |

## Confirmed issues and repair order

| ID | Priority | Evidence | Correction, owner and verification |
|---|---|---|---|
| I-01 | P0 | `backend/api/v1.py:318-341` accepts S3 `HEAD`; `backend/worker.py:383-395` looks only for a local file, then builds a result even when no bytes were read. | Backend: stream/download the exact verified object to bounded private working storage, or fail the job with an explicit storage reason. Test S3-only upload with a controlled S3 fake: no local file exists; worker reads the uploaded bytes and produces a linked sample; missing object fails without a success record. |
| I-02 | P0 | `web/vite.config.ts:18-25`, `web/src/api/disconnected.ts:2-11`, `web/src/app/App.tsx:39-44`, `web/src/features/assess/AssessPage.tsx:130-143`. Production workspace throws before the Assess screen and the upload button is disabled. | Frontend owner: pin generated v1 types and connect the existing allocate → PUT → finalize → poll → sample flow. Preserve the mock-only demo bundle. Browser test against the actual local API: success/partial/failed, invalid image, reload/resume by job ID. |
| I-03 | P0 | `backend/analysis.py:153-198` can return all unknown on missing stack, decode failure or processing error; `backend/worker.py:316-335,395-408` and `process_upload_job` can still persist `succeeded`. | Backend: make availability explicit. `succeeded` means supported analysis completed; use `partial` for accepted but incomplete evidence, or `failed` for unreadable/dependency errors, with stable reason codes. Test missing ML imports, undecodable S3 object and analysis exception without invented metrics. ML owner confirms the scientific meaning of partial output. |
| I-04 | P1 | `backend/api/v1.py:451-461` reads an entire live multipart frame into memory before bounding it. | Backend: apply the same byte cap to frame ingestion as local still upload, with a typed rejection. Test oversized frame without growing a full request buffer. |
| I-05 | P1 | `backend/api/v1.py:324-327` checks only S3 size `>0`; `UploadRequest.expected_size` is not persisted or checked. | Backend: enforce configured maximum and expected size/content type as available, verify decodable bytes before treating finalize as validated. Test oversized and mismatched S3 object. |
| I-06 | P1 | `backend/api/v1.py:809` health reads legacy `backend.pipeline.model_status()`, while v1 worker uses `backend.analysis`. | Backend: report actual v1 quality/aggregate readiness and worker mode, separating configured from probed AWS services. Test ML import unavailable and worker disabled. |
| I-07 | P1 | `backend/api/server.py:81`, `backend/api/v1.py:820` claim version `1.0.0`, while `docs/backend/CONTRACT_STATUS.md` calls the upload contract `1.1.0` and worker `1.2.0`. | Backend: publish one actual OpenAPI `info.version`, save a reviewable contract snapshot in `docs/contracts/`, and let frontend pin that version. Check generated TypeScript against the published snapshot. |
| I-08 | P1 | `backend/api/server.py:101` mounts local uploads as public static files; `backend/app/config.py:132` defaults CORS to `*` with credentials. | Backend: decide prototype access policy; prevent private evidence exposure on the deployed host, set explicit allowed origins, document auth boundary. Verify anonymous requests cannot read protected captures where protection is required. |
| I-09 | P1 | Legacy `backend/main.py` and `backend/pipeline.py` coexist with v1 `backend/api/server.py`; `backend/api/v1.py:809` still consults legacy model readiness. | Backend: use one documented ASGI entrypoint (`backend.api.server:app`), stop presenting legacy scores as v1 readiness, and mark legacy endpoints as non-authoritative. No rewrite needed. |
| I-10 | P2 | `docs/contracts/endpoints.md` includes example values that are not a frozen runtime schema; frontend `web/src/api/display.ts` explicitly calls its types presentation-only. | Backend publishes exact requests/responses, error envelopes, null reasons, PUT headers and expiry. Frontend maps those to display types without score logic. Contract test asserts the sample OpenAPI path/schema. |

The local upload test does **not** prove S3-backed inference. The current image-quality and particle output is experimental: `docs/ml/TASKS.md` says source-scale and independent human labels are outstanding. A numeric `chip_count` from the current baseline must not be promoted as validated Indian road measurement.

## Proposed smallest integration design (awaiting review)

Reuse `/v1/uploads`, local/S3 PUT, finalize, jobs and samples. Correct S3 byte resolution and job truth in the backend. Publish a pinned v1 OpenAPI snapshot plus a proposed `docs/contracts/ML_INTEGRATION_HANDOFF.md`; keep scientific field definitions marked pending ML confirmation. Connect the existing Assess screen to the real API with persisted job ID and explicit partial/unavailable states. Show the actual uploaded image and supported fields, keeping uncalibrated physical units and score null. Keep fixture mode visibly separate. Test the whole local path in a browser and S3 behavior with a fake before any live cloud retry.

The first connected UI slice is still upload → job → one sample. Route, reports and live camera remain honest readiness surfaces until their real service/hardware inputs exist. Do not add another queue, database, model or frontend framework.

## Verification gate still outstanding

| Gate | Current result |
|---|---|
| Backend starts | pass (FastAPI test client in backend suite) |
| Frontend builds | pass |
| Frontend communicates with backend | fail (production adapter disconnected) |
| Genuine local image upload | pass (backend test client) |
| S3-backed analysis | fail by code path; not live-tested here |
| Jobs persist / failure handling | pass for tested local cases; incomplete availability semantics |
| Real ML scoring / calibrated chip metrics | blocked by ML data and camera gates |
| Google Maps with real data | not tested; key/GPS unavailable in this audit |
| Live camera | blocked by hardware access |
| Bedrock normal path | prior documented smoke result; not tested here |

## Ownership and external checks

Backend owns `backend/schemas.py`, `backend/analysis.py`, `backend/worker.py`, `backend/api/`, `tests/backend/`, and `docs/contracts/`. Frontend owner owns `web/` and `docs/frontend/`. The ML owner must confirm units, minimum resolvable feature size, quality/partial reason taxonomy and acceptable display of exploratory counts. No ML-owned file should change in this phase. The existing frontend has uncommitted/untracked work, so any frontend integration should be applied only in a coordinated isolated change. No paid cloud resource, bucket policy or live deployment was changed by this audit.
