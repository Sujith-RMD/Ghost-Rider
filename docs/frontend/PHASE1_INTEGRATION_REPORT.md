# Phase 1 frontend–backend integration report

**Baseline:** GitHub `main` was `602c35481fe1bac4953c4aa006c0ce0b5c6656c4` when work began on 16 October 2026. Teammates advanced it to `15b73dbd396a0e2758f76684bd08136af6fff4f1` during implementation; the integration branch was rebased onto that latest head without conflicts. Work is on `phase1-frontend-backend-integration`; it has not been merged into `main`.

## Merge audit and patch comparison

The baseline already contained the Phase 1 backend S3 and partial-result fixes, the 1.0.0 OpenAPI document, and newer ML tiling/distress work. Production frontend `AssessPage` was still disabled; `virtual:roadsight-data` still selected `api/disconnected.ts` for the normal build. The older `frontend-owner-phase1.patch` passed `git apply --check` on the latest baseline. All five file hunks were applied with `--ignore-space-change`; there were no content conflicts. Its line-ending whitespace warnings were mechanical. The patch was then adapted for generated contract types, image validation, same-tab resume, bounded requests, real sample detail, health, and browser-discovered defects. `backend-phase1.patch` was not reapplied.

## Connected scope

- **Assess:** JPEG/PNG selection and native preview; 25 MB client gate; real `POST /v1/uploads`, byte `PUT` to the returned destination, `POST /finalize`, job polling, and stored sample fetch. Upload and processing failures stay separate. A synchronous submission guard prevents duplicate jobs from rapid clicks. Only the job ID is retained in `sessionStorage` for reload within the same tab; the result is fetched again from the backend.
- **Evidence:** backend image quality and reason codes, real stored original, score status, geometry validity, exploratory count, and unavailable density are displayed without synthesizing a score or physical units. A sample link reopens the stored result independently of the Assess page.
- **System:** `GET /v1/health` displays service statuses and compares server version with pinned OpenAPI version. External Maps, camera, and physical calibration remain labeled unverified.
- **Backend media correction:** local media URLs now preserve the path relative to a custom media root; sample reads reconstruct a current local URL or fresh S3 presigned URL from the persisted source. Previously the browser received `/uploads/browser-road-test.jpg` and got 404 for a nested private upload.
- **Job truth:** a future numeric score alone no longer marks a rejected, limited, or review result `succeeded`; accepted quality and a final Good/Bad score are also required. This is job-state semantics only, not a change to scientific scoring.

Generated TypeScript types come from `docs/contracts/openapi.v1.json` via `npm run contract:generate -- ../docs/contracts/openapi.v1.json 1.0.0`. A fresh FastAPI OpenAPI document was compared with the checked-in document: paths, component schemas, and version match.

## Verification

| Check | Result |
|---|---|
| Backend: `.venv/Scripts/python -m pytest tests/backend -q --tb=short` with `TEMP` and `TMP` set to a writable workspace folder and local loopback allowed | **70 passed**, one Starlette deprecation warning, 6.79 seconds. The earlier stall was the Windows sandbox blocking Python's event-loop socket, not an application test failure. |
| Frontend: `npm run typecheck`, `npm test`, `npm run lint` | Passed; 25 tests |
| Frontend: `VITE_API_BASE_URL=http://127.0.0.1:8000/ npm run build` | Passed; normal production bundle |
| Frontend: `npm run build:demo` | Passed before final source changes; fixture bundle remains separate |
| Existing Playwright fixture browser suite | Chrome reached all five test names but the runner stalled before a final summary in this Windows environment; the run was interrupted. Earlier bundled Chromium attempts failed immediately at launch. Real browser integration was verified through the Codex in-app browser instead. |

The real browser test used a **newly generated synthetic 800 × 600 JPEG**, not Indian-road evidence. The normal production build at `127.0.0.1:4173` called FastAPI at `127.0.0.1:8000`. Backend logs confirmed OPTIONS/POST upload allocation, OPTIONS/PUT bytes, OPTIONS/POST finalization, repeated `GET /jobs`, `GET /samples`, and an HTTP 200 for the nested original image. Job `566e417a-4d6c-4003-ad2e-dc4237b37b9f` produced stored sample `224bf433-f91c-49b4-92af-00971a2452e0`. The UI showed `partial`, quality `limited` with `scale_missing`, score unavailable, uncalibrated physical scale, exploratory count 216, and density unavailable. Reloading Assess restored the authoritative result; opening sample detail fetched it independently. The System page displayed API healthy, contract 1.0.0 matched, database ok, S3/Bedrock not configured, model not loaded, worker ready. These values establish transport and persistence, **not** validated aggregate measurement accuracy.

## Remaining issues and screen status

| Priority | Finding | Owner |
|---|---|---|
| P0 | No real live Indian road camera access or calibrated target imagery. The live requirement cannot be accepted yet. | Backend/AWS + team |
| P0 | Aggregate instance outputs are exploratory; no reviewed Indian chip truth, physical calibration, validated score, or known-good reference artifact is available. | ML |
| P1 | Local `/uploads` media is served by a static mount without per-user authorization. A deployed multi-user service needs protected media access before storing private field imagery. | Backend/AWS |
| P1 | Full browser fixture E2E suite did not run in this sandbox; run on a teammate machine or CI with Chromium. Explicit network-interruption and S3 browser cases remain unverified. | Frontend + Backend/AWS |
| P2 | Assess supports the latest job in one tab; there is no production sample list/session index yet. | Frontend + Backend/AWS |
| P2 | Real AWS S3/Bedrock, Maps with real GPS, and deployed CORS/key restrictions are unverified. | Backend/AWS + Frontend |

Production screen classification: **Assess, stored sample detail, and System are real backend-connected.** The general Samples list, Sessions, Live/replay, Route map, and Reports remain UI present but disconnected in production. Their demo versions are fixtures only. Maps additionally awaits a restricted key and real GPS; Live awaits physical camera access; reports await the route/session and Bedrock integration. No production screen silently falls back to fixtures.

## Next owner tasks

- **ML:** follow `docs/contracts/ML_INTEGRATION_HANDOFF.md`; deliver callable, versioned adapter with reviewed quality/scale/aggregate/distress fields, explicit null reasons, and independent Indian validation. Preserve the score as null until the scoring and reference gates pass.
- **Backend/AWS:** obtain real camera access, connect frame ingestion, protect local media or deploy private S3 access, verify S3 and Bedrock on AWS, and expose list/session records for the remaining screens. Keep grade provenance separate from surface score.
- **Frontend:** run full desktop browser suite in CI or an unrestricted Chrome environment; connect the general Samples list and then session/route/report screens as their authoritative endpoints become ready. Verify actual Maps/GPS and camera states without simulated coordinates.
