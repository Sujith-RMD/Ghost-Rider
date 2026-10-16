# Pre-demo sprint status

## Scope and current state

This branch adds a manually supplied pavement region-of-interest (ROI) to the image-processing evidence path, so an operator can exclude non-road pixels in an oblique frame. ROI application is recorded in the evidence manifest and is passed through to downstream pixel-space measurements. It does not establish physical scale, defect ground truth, or a validated road-quality score. See [CAMPUS_CAPTURE_RUNBOOK.md](CAMPUS_CAPTURE_RUNBOOK.md) for the local demo procedure.

## Checks completed

- Backend and ML test suites: 720 tests passed, including analysis, worker recovery, security defaults, schemas, S3 upload-worker, and evidence processing.
- Frontend: 33 tests passed; typecheck and production build passed.
- Local API round-trip: health, upload, job, stored sample/image, and report retrieval worked for an India RDD image. Bedrock narrative was unavailable in this local test and the deterministic factual fallback was used.
- AWS: safe smoke checks passed for the configured account, S3 object round-trip and cleanup, and Bedrock Converse with Nova Micro.
- Campus video tooling: FFmpeg is installed; runbook commands and limitations are recorded.

## Dataset and model evidence

- Primary India localization dataset: RDD2022 India-only YOLO repackaging, 7,706 images (6,165 train / 1,541 development), bounding boxes only, CC BY-SA 4.0 with third-party repackaging recorded. The split is random-held-out; road/session independence is not established. Its shipped test split is unlabelled and excluded.
- Crack-Seg remains a conditional, internal-only crack mask dataset because provenance/license terms are not clear enough for redistribution or India-performance claims. Other crack datasets are not admitted for training until provenance and rights are resolved.
- A one-epoch CPU smoke run on 123 training images completed and inference ran. Its development metrics were effectively zero (mAP50 0.000024), so the checkpoint is rejected for product integration and must not be presented as a capable RoadSight model.
- The local RTX 3050 currently has a CPU-only PyTorch installation. The signed-in Colab T4 runtime is now connected, and approval to transfer the public RDD subset was received. A 442 MB archive containing the India train/dev images, labels, and YAML is prepared locally; the browser upload control requires the user to select it, so no dataset files have been sent yet. Do not upload private campus imagery.

## Claims and limits for the demo

Show processing and evidence artifacts, not validated physical measurements. The current analyzer can produce exploratory pixel-space candidates. Do not claim chip count per square metre, crack width in millimetres, roughness, depth, calibrated inclination, route distance, or a validated Good/Bad score. Human review is required for capture suitability, ROI masks, labels, calibration, and any quality interpretation. Preserve original frames and source/timestamp metadata; reject blurred, wet, shadowed, or incorrectly masked examples.

## Not completed

- GPU training and a usable Indian detector checkpoint: waiting for the approved dataset archive to be selected in Colab; current smoke checkpoint fails the quality bar.
- Live camera capture: requires an actual camera device and operator-run capture; no camera was available to this automated session.
- Independent road/session-held-out evaluation and physical scale validation: the available labels and metadata do not support these claims.
