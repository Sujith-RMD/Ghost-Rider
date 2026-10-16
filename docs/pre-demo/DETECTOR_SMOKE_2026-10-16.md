# India detector integration smoke test — 16 October 2026

## Scope and baseline

Tested `feature/india-distress-detector-integration` starting at `518fd64` against `main` at `b1feb6e`. No retraining was performed. Local checkpoint `models/india_rdd2022_yolov8n/best.pt` is 6,527,786 bytes and has SHA-256 `ff477bb3aaeb3559bf8f3c040acf55ab3b468b520c21fb8d6bc1fa9d03204881`; it remains ignored by Git. The running FastAPI app's generated OpenAPI equals `docs/contracts/openapi.v1.json` exactly (`info.version: 1.2.0`, 16 paths), and the frontend's generated types and pinned version use 1.2.0.

The test used an actual loopback FastAPI server, an isolated SQLite database and local upload directory, and the built Vite frontend. The browser used the production build, including a 1920×1080 Chrome run. No FastAPI TestClient was used. API and browser source was the same public RDD India imagery used for the model's development evaluation, so this is an integration test, **not** an independent accuracy estimate.

## Real HTTP path and detector evidence

| Case | Upload / local PUT / finalize | Job and stored sample | Detector result | Report |
| --- | --- | --- | --- | --- |
| RDD `India_000024.jpg` | 200 / 200 / 200 | job `82c93dcb-55a1-493a-9d86-752044b2d056`, sample `1e7d1cbb-6fa1-458a-9d60-1a1b8a392876`; GET 200, reload GET 200 | `success`; one `alligator crack`, confidence 0.6418, original 720×720 box `[1.70, 503.93, 660.32, 698.69]`; inference 2,194 ms; persisted model hash matches checkpoint | POST 200, GET 200, report `e3f95c88-85f3-47cb-95b1-f363f4793981` |
| RDD `India_000022.jpg`, empty label file | 200 / 200 / 200 | job `5709d1bd-bad6-486a-822f-2b6f7db63807`, sample `e2b0aa23-864d-4837-a520-33d787808eb5`; GET 200, reload GET 200 | `success`, zero detections, same model hash; inference 82 ms. Zero boxes does not establish a defect-free road. | POST 200, GET 200, report `234fbff6-5a7a-4292-98b4-ffad69b82c91` |
| Missing configured checkpoint | 200 / 200 / 200 | job `cf77162f-39eb-4b9e-aca9-0fa03b629461`, sample `0abe0b4f-6f21-4169-b52e-6492cf679a12`; GET 200, reload GET 200 | `unavailable`, reason `weights_not_found`, zero boxes, no fabricated model provenance. A nonexistent path was configured temporarily; the real weight was untouched. | POST 200, GET 200, report `8ae24ae8-97c8-468c-bfc7-55d3f84264d3` |

All three jobs finished `partial`, correctly withholding physical scale and road score. The positive and empty original image bytes served from local object storage matched their uploaded source SHA-256; image GET was 200. The detector result and class map survived sample reload. The map contains seven classes: alligator crack, block crack, longitudinal crack, other corruption, pothole, repair and transverse crack. The frontend shows original-image boxes, labels, confidence, checkpoint hash prefix and inference time. A separate desktop browser upload produced job `fd7f5738-bb04-4870-81a4-169c7d968d10`, sample `bd749952-b197-463f-822e-69050552c535`; its measured upload, PUT, finalize and sample GET times were 2,067 ms, 16 ms, 2,025 ms and 2,044 ms. After image load, the natural image and SVG viewBox were both 720×720 and their displayed rectangles matched exactly at 1920×1080. See `reports/smoke-20261016/` for the HTTP logs, timings, geometry and screenshots.

## AWS, Bedrock and factual report

Existing `backend/.env` credentials were loaded into a separate local process without printing or modifying them. STS succeeded in `ap-southeast-2` (account suffix `4441`); existing bucket `ghost-rider-road-storage` returned head 200. A bounded 49-byte S3 object had PUT 200, GET 200 with matching SHA-256, then DELETE 204. A minimal Bedrock Converse call to `apac.amazon.nova-micro-v1:0` returned 200 in 1,300 ms. No infrastructure was provisioned.

The actual RoadSight `/v1/reports` route was then called for the stored positive sample with narrative enabled. Bedrock responded, but early wording made unsupported pothole or absence claims. Validation now rejects unsupported crack/pothole claims, numeric prose, references outside the stored sample and absence claims that contradict other evidence. The final route returned HTTP 200 in 1,958 ms, report `78f5acfa-6535-4ca2-b6c8-3ae355627b77`, using the factual template (`narrative_status: fallback`). This is a successful safe degradation of the Bedrock report flow, not a claim that Bedrock generated an accepted narrative. The persisted report references only the stored sample.

## Classical stages and campus transfer

`eval.processing_evidence` still produces the original-preserving stage manifest and images. On the forward-looking positive RDD image, its full-frame watershed stage found 248 **unverified candidate regions**; visual review showed boundaries on sky, vegetation and a vehicle. These are not YOLO distress detections or a valid aggregate count. The dashboard labels watershed candidates separately, and the offline stage artifact is at `.runtime/smoke-20261016/processing/India_000024/candidate_boundaries.png`. Do not use this full-frame count for chip density, width, depth or score.

No campus smartphone originals or MP4 frames were found in the inspected project `datasets` and `demo` locations, so campus accuracy, missed detections, wrong boxes and processing times cannot yet be measured. `docs/pre-demo/CAMPUS_CAPTURE_RUNBOOK.md` gives a ready-to-run local JPEG and MP4-frame import, checksum preflight, review log and ROI procedure. RDD's forward-looking imagery differs from downward-facing phone imagery; a human-reviewed campus set is required before any transfer claim.

## Verification and deployment

- Python ML/backend tests: 26 passed using `--basetemp=.runtime/pytest-detector-final` (the sandbox's default Windows temp was unwritable).
- Frontend tests: 35 passed; production TypeScript/Vite build passed.
- OpenAPI runtime vs checked-in snapshot: exact match, v1.2.0.
- No calibrated physical measurements or road-quality score were inferred from boxes.

To install elsewhere, place the exact `best.pt` at `models/india_rdd2022_yolov8n/best.pt`, verify the SHA-256 above, install the project's Python and frontend dependencies, and start FastAPI plus the built frontend as in the campus runbook. Set the frontend API base URL at build time and set the backend `CORS_ORIGINS` to the exact browser origin if the preview port differs. Deploy the weight through a private artifact channel, never Git; if absent, the app stores an explicit `weights_not_found` result. Keep raw datasets, campus captures and credentials out of the repository.
