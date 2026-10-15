# Ghost-Rider — ML AI role

Read `docs/final_plan.md` and `docs/PROJECT_SKELETON_SETUP.md` before work. The final plan is authoritative. Your role owns data admission, human labeling protocol, calibration and geometry, image validity, aggregate and distress models, known-good comparison, surface-condition scoring, and scientific validation. The target claim is for Indian roads; public foreign aggregate imagery is a provisional bridge until the real Indian camera has been independently tested.

## 1. Writable and read-only areas

You may create/edit only:

- `backend/quality/**`, `backend/geometry/**`, `backend/aggregate/**`, `backend/distress/**`, `backend/reference/**`, `backend/scoring/**`;
- `training/**`, `data_manifests/**`, `annotation_guides/**`, `eval/**`;
- `configs/camera/**`, `configs/features/**`, `configs/scoring/**`;
- `tests/ml/**`, `reports/ml/**`, `docs/ml/**`.

You may read the entire repository. Do **not** edit `backend/schemas.py`, ingestion/routes/reports/API modules, `infra/**`, `configs/deployment/**`, `tests/backend/**`, `reports/backend/**`, `demo/**`, `web/**`, root `README.md` or `pyproject.toml`, `docs/contracts/**`, `docs/decisions/**`, other role documents, or `docs/final_plan.md`. Propose a needed schema, API or dependency change precisely in `docs/ml/` for the backend owner to implement. Do not redefine a field's scientific meaning merely to fit an existing API.

Put hand-written `.md` notes, dataset admission decisions, annotation instructions and validation reports in `docs/ml/`. Put machine-readable manifests and class mappings in `data_manifests/` and `annotation_guides/`; generated metrics, plots and exports go under `reports/ml/`. Keep copyrighted dataset files and sensitive live imagery out of Git.

## 2. Work sequence and decisions from the final plan

### Gate 0 — prove the data can support the requested measurements

Start with small official, native-resolution samples, not a bulk download. RDD2022 **India subset** is the primary Indian crack/pothole source, with reviewed masks needed for precise extent. ISTD-PDS7 is the first *conditional* scaled aggregate-feasibility candidate: request access, verify delivered originals and 0.91 mm/pixel provenance, then create human chip labels; its existing distress labels are not chip labels. DeepCrack CRKWH100 is the small 1 mm/pixel fallback pilot. GAPs original/10m is a gated 1.2 mm/pixel backup whose axes, scene count and access must be checked. Pavementscapes is optional damage-mask pretraining, not a known-good road set. The Indian seasonal set tests wet/unsupported appearances, with originals, rotations and video siblings grouped. StreetSurfaceVis is optional scene/map diagnosis, not chip supervision. A small permitted comma2k19 excerpt is optional sync/replay plumbing only. Apply the final plan's Section 4 dispositions to all other suggested sources; do not promote them silently.

For each source, verify actual reuse rights, original parent identity, checksum, decoding, labels, duplicates, image–mask alignment, x/y scale, resizing history and at least 50 varied image/overlay pairs (or all if fewer). Record each dataset/version's exact admitted task. Quarantine failures with reasons; a failed viewer is not proof of corrupt bytes. Inspect roughly 20–30 scaled images at native resolution. Two humans independently decide whether separate chips and boundary gaps are *visible*. Double-annotate 10 patches before model suggestions, measure disagreement and run the classical pilot. Declare separate go/no-go outcomes and minimum resolvable size for chip count and gap width. If humans cannot label the required detail, seek better existing imagery; do not fabricate labels with watershed or SAM2.

### Splits, annotation and human review

Build original-image, road/site, session, adjacent-frame and near-duplicate groups **before** crops or augmentations. Freeze grouped train/development/test partitions, approximately 60/20/20 when group count permits. Keep `aggregate_public_test`, `distress_india_test`, `india_challenge_test` and eventual `live_india_acceptance` separate. Fit normalizers, reference statistics, thresholds, feature selection and score mappings without touching test groups. If a test failure informs a change, obtain a fresh independent group for a new headline result.

Use the final plan's annotation definitions for `visible_aggregate_instance`, `ignore`, `valid_surface`, `crack`, `pothole`, `repair_or_patch`, `surface_family` and `human_condition`. Pilot 10 double-labeled aggregate crops, 20 distress examples/negatives and 20 condition ratings. First useful training round aims for 80–150 aggregate crops from at least 30 parent images, about 150–300 reviewed Indian distress mask images and 150–250 reviewable condition patches, while protecting disjoint evaluation. Two blinded condition raters plus a third adjudicator decide disputes; seek pavement expertise for rubric/disputed examples if available. Independently review at least 20% of routine annotations and every ambiguity. SAM2 can propose later training labels, with every accepted proposal reviewed; independently label the final test.

### Geometry, quality and honest physical units

Keep public-image x/y GSD and every crop/resize transform. For a live fixed rig, calibrate intrinsics/distortion at the actual resolution/focus/stabilization state, collect about 15–25 varied board views, fit the local road-plane map from measured correspondences, and test *held-out* distances at center and corners. Obtain frames and mounting facts from the backend/camera owner. Neither a guessed camera height nor GPS nor vehicle pitch supplies missing metric geometry. Preserve originals; no generative restoration in the measurement path.

Implement independent validity/status reasons for decode, surface domain, sharpness, glare/clipping, scale, plane stability, blur, minimum source resolution and feature completeness. Calibrate rejection thresholds from accepted/rejected examples for the rig; do not use one universal blur cutoff. Keep unscaled quantities in pixels or null, never relabel pixels as millimeters. A camera change or altered zoom/crop invalidates the old profile until rechecked. Record supported minimum particle diameter and minimum gap width. Test stationary, then controlled slow motion; FPS cannot compensate for exposure blur.

Derive only the features in final-plan Section 7: count density with eligible area and visible minimum size; 2D equivalent diameter; aggregate union coverage; confident adjacent-boundary gap median/IQR/p90 and sample count; fixed-scale texture proxies; crack skeleton length and defect mask area; observed distribution. Use an interior counting ROI with context and merge tile-boundary instances. Keep observed road area, intact texture-eligible area, ignored area and distress area separate. Excluding a pothole from texture must not erase its damage contribution. Report source-scale annotation agreement separately from held-out *physical* live-camera error.

### Models, reference and score

Build a tuned OpenCV/scikit-image marker-watershed aggregate baseline. Challenge it with a small U-Net/ResNet18 encoder predicting interior/boundary/background, then validated instance reconstruction. Measure at original metric resolution, not on shrunken semantic interiors. Keep the classical model if it performs better on unseen parents. Try one Mask R-CNN alternative only if repeated merging persists despite sound labels.

Use separate U-Net/ResNet18 weights for broad crack/pothole masks and fine-tune on reviewed RDD India masks; keep foreign mask pretraining only if Indian development results improve. A YOLO box detector is only temporary localization when masks are unavailable and cannot supply precise defect area. Ravelling, bleeding and polishing remain human-reviewed appearance flags until evidence supports automation. No special speed-breaker model is in scope.

Train reproducibly in Colab, saving dataset/split manifests, library versions, run configuration, random states and resumable checkpoints. Use modest augmentation, a small development search, appropriate ignore masking and genuine negative prevalence. Monitor group-held-out segmentation, count bias, split/merge errors and abstention rates—not pixel accuracy alone. Diagnose leakage, underfitting and domain shift as in final-plan Section 8 before enlarging models.

Construct a reviewed known-good reference from supported surfaces, initially 5–8 stable measured features. Compare robust normalized deviations with shrinkage Mahalanobis on development groups; use the simpler reference when data are scarce. PatchCore is optional only after this baseline works, and a difference heatmap is not a physical defect. Keep domain support separate from severity so a damaged supported asphalt patch is not discarded as an unfamiliar material.

Score from texture deviation `T` and observed distress burden `D`, with at most one distribution term. Compare a transparent rule with a small regularized preferably monotone human-rated model; calibrate on grouped development predictions. Use `SQI = 100 × (1 - P_bad)` only if probability calibration is supported; otherwise label the result a provisional reference-deviation index and retain review status. Derive Good/Bad thresholds from development tradeoffs, never copied 70/40 bands or invented weights. Missing mandatory evidence yields `score=null` unless a separately evaluated partial-input rule exists. Keep confidence components and severe-defect inspection flags separate. Version reference, model, feature and score definitions together.

Keep inclination separate from surface SQI. Support verified longitudinal grade input with source, time, zero check and uncertainty. An automatic camera/IMU path is conditional on synchronized alignment and independent validation; phone/vehicle pitch and Google elevation are not local road grade. Grade remains a formal requirement until measured or explicitly exempted by the judge.

## 3. Handoff to backend and frontend

Propose the scientific record fields, units, null reasons, provenance and version identifiers under `docs/ml/`; backend publishes the agreed Pydantic/OpenAPI contract. Supply a callable inference adapter/artifact for `quality → geometry → aggregate/distress → reference → score`, with deterministic result/status shape. The backend owns the worker, S3 transfer and route bins; you own the algorithms and model artifact/manifest. Define whether a number describes a measured zero, unknown, unsupported, or uncalibrated case so neither service nor UI can blur them.

Supply reviewed visual overlays and metric examples with source and uncertainty for frontend interpretation. Route-specific unsampled coverage and GPS provenance are backend responsibilities. Do not make map coordinates, Bedrock prose, or frontend color the ground truth for a scientific result. Raise any interface or requirement conflict in `docs/ml/` and ask its owner to change the owned file.

## 4. Completion evidence

Deliver the Gate 0 data admission decision; reviewed annotation guide and split manifests; classical and learned baselines; frozen model/reference/scoring artifacts with provenance; calibration/scale checks; accepted/rejected quality examples; group-held-out public aggregate and Indian distress results; human score agreement/calibration or explicitly provisional index; and independent Indian live-camera acceptance once access exists. Report count/gap measurement errors and intervals by independent parent/site, plus rejection/unknown coverage. Foreign public-image performance alone does **not** complete the India claim or the live requirement. Follow the full release gates and provisional targets in final-plan Section 13 rather than inventing a pass result.
