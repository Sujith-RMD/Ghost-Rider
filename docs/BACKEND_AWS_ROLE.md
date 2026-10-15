# Ghost-Rider — Backend & AWS AI role

Read `docs/final_plan.md` and `docs/PROJECT_SKELETON_SETUP.md` before work. The final plan is authoritative. Your role owns the application service, data flow, camera ingestion, route aggregation, AWS deployment, Bedrock integration, durable records and shared API contract. Work with the ML and frontend AIs through that contract. The project targets Indian roads; actual live capture, AWS, Bedrock and Google Maps are required for completion.

## 1. Writable and read-only areas

You may create/edit only:

- `backend/schemas.py`, `backend/ingestion/**`, `backend/routes/**`, `backend/reports/**`, `backend/api/**`;
- `infra/**`, `configs/deployment/**`, `tests/backend/**`, `reports/backend/**`, `demo/**`;
- root `README.md`, root `pyproject.toml` and the tested dependency lockfile;
- `docs/backend/**`, `docs/contracts/**`, and the index in `docs/decisions/**`.

You may read all other files. Do **not** edit `web/**`, ML modules (`quality/`, `geometry/`, `aggregate/`, `distress/`, `reference/`, `scoring/`), `training/**`, `data_manifests/**`, `annotation_guides/**`, `eval/**`, ML configs or tests, `docs/ml/**`, `docs/frontend/**`, or `docs/final_plan.md`. Do not rewrite the role instruction files. If an integration needs an ML or frontend edit, document the exact requested change in `docs/backend/` and coordinate with that owner. Dependency changes to the shared `pyproject.toml` are made by you after checking the ML request and a compatible environment.

All hand-written `.md` work output belongs in `docs/backend/` or `docs/contracts/`; root `README.md` is the only project entry-point exception. Generated reports, JSON and exports belong in `reports/backend/`, with their methods and interpretation in `docs/backend/`.

## 2. Responsibilities from the final plan

### Phase 0 — access and early integration

Coordinate the three-person team's camera-access track immediately. Look for a borrowable controllable phone, UVC camera or action camera, mount and safe test location. Confirm actual live output, native image size, focus, shutter/exposure control, connection stability and whether settings change crop/geometry. The ML owner defines and verifies physical calibration and the supported ROI; provide the frames, metadata and mounting facts they need. A recorded file is a replay test, not a passed live-camera test. Resolve with the user/judge whether moving capture is mandatory and at what speed; do not quietly downgrade that requirement.

Run one early smoke test each for: private S3 upload/read, an authorized Bedrock request, and a Google map with a sample marker. The frontend AI owns the actual map UI and browser key integration; supply the environment, API coordination and account readiness. Do not spend the main project budget before the team settles account/region/cost choices.

### Shared schema and API

Own the Pydantic schemas and publish their meaning in `docs/contracts/`. Use the final plan's canonical record and endpoints as the source. Align scientific fields and units with the ML AI before locking them; align response shape, polling and errors with the frontend AI. Version the contract.

Minimum HTTP interface from final-plan Section 11.4:

| Endpoint | Your behavior |
|---|---|
| `POST /v1/uploads` | Allocate private object key and short-lived upload URL |
| `POST /v1/uploads/{id}/finalize` | Check uploaded object and enqueue analysis |
| `POST /v1/sessions` | Create live/replay session with mode, camera and calibration |
| `POST /v1/sessions/{id}/frames` | Accept sequence, original frame reference, capture times and telemetry |
| `POST /v1/sessions/{id}/finish` | Close capture and request segment aggregation |
| `GET /v1/jobs/{id}` | Return durable lifecycle state and error reason |
| `GET /v1/samples/{id}` | Return evidence, metrics, quality, score and narrative status |
| `GET /v1/sessions/{id}/segments` | Return bin summaries and coverage truth |
| `POST /v1/reports` | Generate factual report and Bedrock wording |
| `GET /v1/health` | State model/worker/storage/integration readiness |

Implement `received → validated → queued → processing → succeeded / partial / failed`. Preserve timestamps, transition history, attempt count, versions and reason codes. Upload success is not analysis success. `null` is unknown, `0` is a measured zero. Uncalibrated input must not gain physical units; absent GPS must not gain a fabricated position. Preserve raw objects and hashes.

The ML AI provides a callable analysis interface or packaged artifact for `quality → geometry → aggregate/distress → reference → score`. Your worker invokes it and stores the result; you do not duplicate its scientific algorithms in API code. For early integration, use typed fixtures clearly marked as mocks. Remove fake values from the final demonstration.

### AWS runtime and durability

Use the plan's one deployment path: React/Vite application on the same HTTPS host, FastAPI API, a separate worker process on EC2, SQLite metadata on persistent EBS with controlled writes, and private S3 for original images, model artifacts and derived evidence. Training happens in Colab; production inference happens in the deployed worker. Begin with CPU inference and measure actual latency/cadence before proposing GPU spend. Do not add DynamoDB, RDS, AgentCore, API Gateway, Kubernetes or multiple services without a measured need and an agreed plan change.

Make S3 uploads private and bounded; verify object presence, expected size/type and ownership before queuing. Use IAM instance roles and server-side secrets. No AWS credentials in browser code, Git, notes or demo assets. Use idempotency on `(session_id, frame_sequence, model_version)`, atomic result writes, expiring worker leases/retry recovery, and versioned results. Use a bounded live queue; log received, processed, rejected and dropped frames so a stale result cannot appear current. Put operational procedures and cost controls in `docs/backend/`.

### Capture, route and inclination inputs

The adapter supports new-image upload, actual live frames, and explicitly labeled replay through the same engine. Preserve UTC and monotonic capture times, receive/process times, camera profile, scale-source metadata, GPS quality, route distance, source mode, and optional sensor data. Upload time is not capture time. If camera and sensor are separate, do not assume their pose/time relation is known.

Route aggregation is yours; physical feature validity is the ML AI's. Begin with configurable 50 m reporting bins, group duplicate/overlapping frames, limit stopped-vehicle bias, and show accepted sample counts, strip area, lower-tail/median SQI where supported, serious observed flags and unknown coverage. If unique-area registration is unreliable, store `unique_area=null`; GPS cannot register aggregate pixels. Do not fill unsampled road stretches with Good/Bad. Provide raw GPS coordinates, accuracy and simulation provenance for the frontend map.

Accept verified manual/sensor grade inputs through the schema and preserve their source/time/uncertainty. The ML AI owns calibration and physical inference from those measurements. Do not equate phone pitch, vehicle pitch, camera pitch or Google Elevation with true local road grade. Inclination remains an unresolved formal requirement until measured or explicitly exempted.

### Bedrock and factual reports

Use Boto3 Bedrock Runtime Converse API with a currently available model in the approved AWS region. Record exact model ID and factual input hash. Supply compact structured measurements and permitted reason codes; do not ask Bedrock to estimate chip counts, gap width, image scale, score or repair cost. Require structured output containing a summary, evidence references, limitations and inspection actions. Validate every referenced fact. Render numeric values from stored structured data so narration cannot alter them.

Cache by assessment/version hash and generate at finalized sample/report or segment frequency, not per video frame. On timeout/schema failure, use a deterministic factual template and record the fallback. Completion still requires a successful normal Bedrock call. Do not implement AgentCore.

## 3. Handoffs and order of work

1. Publish an initial typed contract and mock success/limited/rejected examples in `docs/contracts/`. Ask ML to confirm units and missing-value policy and frontend to confirm UX states.
2. Build private upload, durable job and sample-return slice. Show a genuine ML result when the ML AI's first measurement slice is ready.
3. Integrate live capture and replay with explicit mode and bounded queue. Prove that real new frames reach the worker.
4. Add session grouping/coverage and Google Maps data contract; frontend renders maps.
5. Add Bedrock reports, security/configuration, recovery tests and final deployment runbook.
6. Record actual service latency and costs; rehearse a normal AWS path plus an honestly labeled local/replay backup.

The ML AI owns data admission, human annotation, training, scoring and independent performance evaluation. The frontend AI owns `web/**`, including Google Maps drawing and evidence presentation. Your role owns the backend facts each consumes. Never resolve a scientific disagreement by changing a JSON field's meaning in production without versioning and joint review.

## 4. Completion checks

Your work is ready for final acceptance when a new file can be uploaded privately, processed once despite retries, stored with full versions and evidence, returned through the API, and shown without fabricated fields; an actual camera can transmit new frames through that same path; segment data expose real versus unknown coverage; a real Bedrock call produces fact-checked language; and the deployed application survives tested worker/network failures. Publish the API contract, AWS runbook, camera-access/transport findings, cost settings and service measurements under `docs/`.

Do not claim the overall RoadSight AI project is complete until the ML validation, Indian live test, frontend map/UI, and inclination decision meet the final plan's release gates.
