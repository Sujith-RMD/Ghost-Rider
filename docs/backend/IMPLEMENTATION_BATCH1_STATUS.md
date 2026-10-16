# Implementation Batch 1 status

**Updated:** 16 October 2026
**Branch:** `batch1-engineering-reliability`
**Scope:** reliability fixes and evidence readiness; no training, deployment, AWS calls, or merge.

## Verified in this workspace

- The route aggregator no longer invents 5 m/frame or substitutes `(0, 0)` for absent GPS. Unknown distance stays `null`; gaps/poor-accuracy fixes do not create false measured segments. Regression coverage includes missing, mixed and inaccurate GPS, duplicate points, an explicit distance override, and valid GPS routes.
- Default CORS is restricted to local desktop origins (5173 and 4173); an explicit deployment allow-list remains supported. Public `/uploads` serving remains enabled for local development and is disabled by the EC2 deployment environment unless explicitly configured. S3 objects continue to use presigned access.
- A real India RDD image (`India_000000.jpg`, 720×720) completed the existing `backend.analysis.measure_frame` adapter at source resolution. The new `python -m eval.processing_evidence` command writes the original pixels, current intermediate maps, candidate label IDs and a parameter/limitation manifest. The source was not copied into Git. On this image the segmentation map has 176 candidate regions and the downstream measurement reports 116 after filters; both are unvalidated. The candidates include obvious non-road scene regions (sky, trees, vehicles and wires), demonstrating why the missing ROI detector blocks accuracy claims. Quality is limited due to missing scale; there is no calibrated geometry, physical unit, ground truth or road-quality score.
- Dated AWS smoke records and unresolved conflict markers were reconciled. S3 lifecycle, S3 upload, and Bedrock statuses are explicitly historical (16 Oct 2026); current cloud state was not queried.
- Two-person annotation can use the existing native-resolution browser tool and `ANNOTATION_GUIDE.md`; ambiguous aggregate boundaries belong in `ignore`. The guide now gives an independent two-rater pilot and third-person adjudication. Chip/gap ground truth and inter-annotator agreement remain unavailable until scale and independent human labels are verified. Existing evaluation supports ignore-mask and instance metrics, but annotation-manifest import into a real-image evaluator is not implemented. No admitted real chip labels exist, so real-road accuracy metrics remain unavailable.

## Verification

| Check | Result |
|---|---|
| Backend focused: route, security defaults, analysis adapter | 22 passed |
| Broader backend no-loopback subset | 31 passed, 2 sample API tests deselected because they require blocked `TestClient` socket setup |
| Processing-evidence adapter/bundle and tiling regression tests | 14 passed |
| ML suite | 690 passed, 1 skipped; 8 expected provisional-annotation warnings |
| Frontend unit tests | 33 passed; React Router upgrade notices only |
| Frontend typecheck | Passed |
| Frontend production build | Passed |
| `git diff --check` | Passed |
| Backend full suite | Not completed in this Windows sandbox: Starlette `TestClient` stalls creating an asyncio Proactor self-pipe/socketpair at `tests/backend/test_live_reports_integration.py:9`. The captured stack reaches `socket.accept` / `_fallback_socketpair`; this is local-loopback sandbox restriction, not evidence of SQLite locking or worker failure. Focused non-loopback backend tests pass. |

## Still open in Batch 1

- **A:** the CLI emits real intermediate maps and a manifest; image-level accuracy metrics and aggregate correctness remain unavailable. The Indian road-scene example visibly confirms the no-ROI failure mode.
- **E:** the assessment/sample UI does not yet persist or show these maps. They are inspectable only from the local CLI evidence folder; no fixture masks were added to production.
- **B:** no double-annotated real-road chip set, no real-road F1/count/split-merge report, and no calibrated gap/physical-scale evaluation.
- **D:** complete backend integration suite needs an environment permitting local loopback sockets; live camera, AWS state, credentials, and deployments were not tested.
- **Data:** India RDD 2022 provides India road distress boxes and negatives, not aggregate instance masks or physical scale. Do not use its dev split as a final independent test. Other crack/texture datasets remain purpose-limited per `docs/ml/DATA_ADMISSION.md`; none justifies chip-scale claims or retraining in this batch.

## Dataset/model decision for this batch

Do not train or promote a learned model. Keep the existing classical OpenCV/scikit-image watershed path as an explicitly exploratory baseline. Use India RDD images only for a clearly labeled end-to-end software demonstration or the admitted distress-detection task; its boxes are not chip masks. Use only a human-reviewed, rights-cleared, group-separated image set for future real-image evaluation. Freeze parent/road/session grouping before splitting; keep all crops, adjacent frames and derivatives in one split. Exclude unreadable/duplicate/ambiguous regions from metrics rather than treating them as clean negatives. Physical size, gap width and count per area stay unavailable until delivered-file scale is verified.

## Handoff boundary

Changes are on the isolated branch. No cloud action, model training, force-push or merge was performed. The remaining A/E integration is a real acceptance dependency; this status document is not a claim that Batch 1 is complete.
