# Implementation Batch 1 status

**Updated:** 16 October 2026
**Branch:** `batch1-engineering-reliability`
**Scope:** reliability fixes and evidence readiness; no training, deployment, AWS calls, or merge.

## Verified in this workspace

- The route aggregator no longer invents 5 m/frame or substitutes `(0, 0)` for absent GPS. Unknown distance stays `null`; gaps/poor-accuracy fixes do not create false measured segments. Regression coverage includes missing, mixed and inaccurate GPS, duplicate points, an explicit distance override, and valid GPS routes.
- Default CORS is restricted to local desktop origins (5173 and 4173); an explicit deployment allow-list remains supported. Public `/uploads` serving remains enabled for local development and is disabled by the EC2 deployment environment unless explicitly configured. S3 objects continue to use presigned access.
- A real India RDD image (`India_000000.jpg`, 720×720) completed the existing `backend.analysis.measure_frame` adapter at source resolution. Result: quality `limited` because scale is missing, no calibrated geometry or physical units, no ground truth and no road-quality score. Its 116 watershed regions are **exploratory candidates only**, not verified aggregate count. Local JSON evidence is in ignored `.runtime/batch1-real-image-adapter.json`; the dataset image was not copied.
- Dated AWS smoke records and unresolved conflict markers were reconciled. S3 lifecycle, S3 upload, and Bedrock statuses are explicitly historical (16 Oct 2026); current cloud state was not queried.
- Two-person annotation can use the existing native-resolution browser tool and `ANNOTATION_GUIDE.md`; ambiguous aggregate boundaries belong in `ignore`. Chip/gap ground truth and inter-annotator agreement remain unavailable until scale and independent human labels are verified. Existing evaluation supports ignore-mask and instance metrics, but no admitted real chip labels exist, so real-road accuracy metrics remain unavailable.

## Verification

| Check | Result |
|---|---|
| Backend focused: route, security defaults, analysis adapter | 22 passed |
| ML suite | 686 passed, 1 skipped; 8 expected provisional-annotation warnings |
| Frontend unit tests | 33 passed; React Router upgrade notices only |
| Frontend typecheck | Passed |
| Frontend production build | Passed |
| `git diff --check` | Passed |
| Backend full suite | Not completed in this Windows sandbox: Starlette `TestClient` stalls creating an asyncio Proactor self-pipe/socketpair at `tests/backend/test_live_reports_integration.py:9`. The captured stack reaches `socket.accept` / `_fallback_socketpair`; this is local-loopback sandbox restriction, not evidence of SQLite locking or worker failure. Focused non-loopback backend tests pass. |

## Still open in Batch 1

- **A/E:** real intermediate stage maps (flattening, normalized response, Otsu, morphology, distance, markers, watershed boundaries) are not yet emitted or shown in the assessment/sample UI. The UI must label stages unavailable until genuine pipeline artifacts are supplied.
- **B:** no double-annotated real-road chip set, no real-road F1/count/split-merge report, and no calibrated gap/physical-scale evaluation.
- **D:** complete backend integration suite needs an environment permitting local loopback sockets; live camera, AWS state, credentials, and deployments were not tested.
- **Data:** India RDD 2022 provides India road distress boxes and negatives, not aggregate instance masks or physical scale. Do not use its dev split as a final independent test. Other crack/texture datasets remain purpose-limited per `docs/ml/DATA_ADMISSION.md`; none justifies chip-scale claims or retraining in this batch.

## Dataset/model decision for this batch

Do not train or promote a learned model. Keep the existing classical OpenCV/scikit-image watershed path as an explicitly exploratory baseline. Use India RDD images only for a clearly labeled end-to-end software demonstration or the admitted distress-detection task; its boxes are not chip masks. Use only a human-reviewed, rights-cleared, group-separated image set for future real-image evaluation. Freeze parent/road/session grouping before splitting; keep all crops, adjacent frames and derivatives in one split. Exclude unreadable/duplicate/ambiguous regions from metrics rather than treating them as clean negatives. Physical size, gap width and count per area stay unavailable until delivered-file scale is verified.

## Handoff boundary

Changes are on the isolated branch. No cloud action, model training, force-push or merge was performed. The remaining A/E integration is a real acceptance dependency; this status document is not a claim that Batch 1 is complete.
