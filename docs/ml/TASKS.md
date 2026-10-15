# ML role — task tracker

Derived **only** from `docs/ML_ROLE.md` and `docs/final_plan.md`. Every task cites
its source section so it can be re-checked, and nothing here invents a requirement.

Status legend:

- ~~struck through~~ = **achieved and verified** (evidence in `docs/ml/changelog.md`)
- `[~]` = **partial** — started, not complete
- `[ ]` = **open**
- `[!]` = **blocked** — needs the user, hardware, or access

Last updated: 2026-10-16. Current gate: **Gate 0 (incomplete)** — Phase 1 of the
plan's phase table (final plan §14).

---

## A. Gate 0 — prove the data can support the requested measurements

Source: ML_ROLE §2 "Gate 0", final plan §5.1, §4.2, §4.3, §6.1.

### A1. Acquisition and provenance

- ~~A1.1 Obtain a scale-documented source's native-resolution samples~~ — **CRKWH100 obtained**: 100 PNGs, all 512×512, from a 25.30 MiB zip, extracted to `data/external/deepcrack/CRKWH100/images/`. Evidence: `reports/ml/crkhw100_audit.json`.
- ~~A1.2 Archive checksum, byte size and access terms recorded~~ — CRKWH100 `e6da26f7…42889b`, 26,533,247 bytes. Crack-Seg `814b566d…efecdc`, 96,089,865 bytes.
- ~~A1.3 Reusable dataset admission audit tooling~~ — `eval/dataset_audit.py`, runnable as `python -m eval.dataset_audit`.
- ~~A1.4 Decode every image; record failures rather than silently skipping~~ — CRKWH100 100/100 decoded, 0 failures; Crack-Seg 4,029/4,029, 0 failures. *ML_ROLE §2: "a failed viewer is not proof of corrupt bytes."*
- ~~A1.5 Duplicate ancestry and split-leakage checks~~ — Crack-Seg: 1,549 parents, 0 spanning splits, 1 within-test exact duplicate, 18 dHash candidates all rejected by correlation. CRKWH100: no splits shipped, 0 exact duplicates.
- `[!]` **A1.6 Verify the CRKWH100 1 mm/pixel claim survives into the delivered files.** All 100 files are exactly **512×512**, which is not obviously a raw line-array frame. **Crop (scale preserved) vs resize (scale destroyed) is undetermined.** Until this is resolved, `scale_source` for CRKWH100 must stay `unverified` and no mm value may be published. *ML_ROLE §2: "verify delivered originals and 0.91 mm/pixel provenance"; final plan §6.1 item 7 says no blanket mm/px value is copied across versions.*
- ~~A1.7 Resolve the DeepCrack licence~~ — **RESOLVED 2026-10-15.** Permission granted directly by the originating author (Dr. Qin Zou, supervising professor). `rights_status=granted_by_author` written to `crkhw100_audit.json`. Scope: solo academic project, non-commercial, no redistribution, attribution required. The CC BY 4.0 mirror claim is moot. **Rights only — the A1.6 scale question is unaffected.**
- `[!]` **A1.8 Obtain RDD2022 India subset** — the plan's **PRIMARY Indian distress source**. 47,420 images total across six countries; India subset required. Ships bounding boxes; precise segmentation needs manual masks on selected subset. *final_plan §4.2: "Primary Indian distress source."* **BLOCKING: every Indian distress claim.** Link: https://github.com/sekilab/RoadDamageDetector
- `[!]` **A1.9 Request ISTD-PDS7 access** — the **ONLY public candidate for scaled aggregate feasibility**. 18,527 images documented at 0.91 mm/pixel. Access by request via https://www.mdpi.com/2072-4292/15/7/1750. Existing labels are distress, not chips; human chip annotations required. *final_plan §4.2: "First public-data candidate for scaled aggregate feasibility."* **BLOCKING: if A1.6 resolves against CRKWH100, this becomes the entire chip task.**
- `[ ]` A1.10 Request **GAPs original images** access (1.2 mm/px backup, academic access form required) — not requested. The 10m release has only 20 large images with few independent scenes. *final_plan §4.2: "Backup scaled imagery."* Link: https://www.tu-ilmenau.de/universitaet/fakultaeten/fakultaet-informatik-und-automatisierung/profil/institute-und-fachgebiete/institut-fuer-technische-informatik-und-ingenieurinformatik/fachgebiet-neuroinformatik-und-kognitive-robotik/data-sets-code/german-asphalt-pavement-distress-dataset-gaps
- `[!]` **A1.11 Obtain Indian seasonal paved/unpaved dataset** — **Indian robustness/challenge set** for wet appearance and unsupported surfaces. 4,242 Nashik/Mumbai originals plus rotated versions and video; group siblings, start from originals. *final_plan §4.2: "Indian robustness/challenge set."* **BLOCKING: wet/unsupported-surface validation.** Link: https://data.mendeley.com/datasets/tj2m7zz4rg/2
- `[ ]` A1.12 Obtain **Pavementscapes** — optional distress-mask pretraining (4,000 images, 6 damage categories, grayscale, claimed 1-2 mm GSD unverified). *final_plan §4.2: "Preferred optional distress-mask pretraining source."* Optional. Link: https://github.com/tongzheng1992/Pavementscapes
- `[ ]` A1.13 CRKWH100 crack GT (separate OneDrive link https://1drv.ms/f/s!AittnGm6vRKLglyfiCw_C6BDeFsP) — not downloaded; only needed for crack masks, not chip work. Optional backup.

### A2. Human visibility decisions — **cannot be done by the agent**

Source: ML_ROLE §2 "Two humans independently decide…", final plan §5.1 steps 2, 4, 6.

- ~~A2.1 Contact sheet of native-resolution tiles~~ — `reports/ml/crkhw100_contact_sheet.png` (20 native 256 px centre-crops, **pixel-only `10 px` bar** - no mm bar, because the 1 mm/px claim is unverified; never resized, sampled evenly across the set). A second, fillable artifact now exists for A2.3: `reports/ml/crkhw100_annotation_patches.png` (10 numbered native 256 px patches, no model overlay) with `annotation_guides/aggregate_patch_annotation_template.csv` (20 prefilled rows, coordinates included, judgements blank).
- `[!]` **A2.2 Two people independently judge at native resolution whether separate chips are distinguishable and adjacent boundary gaps are locatable.** Not done. Zooming must not merely magnify ambiguity.
- `[!]` **A2.3 Double-annotate 10 small patches with no model suggestions, and measure the disagreement floor.** Not done.
- `[!]` **A2.4 Declare separate go/no-go for chip count and for gap width, plus the minimum resolvable size for each.** Not done — depends on A2.2/A2.3.
- `[ ]` A2.5 Inspect ~20–30 scaled images at native resolution (superset of A2.2's sample).

### A3. Classical pilot on real data

Source: final plan §5.1 step 5, §8.1.

- ~~A3.1 Run the classical segmentation pilot on admitted real imagery~~ — done on 12 CRKWH100 images at the claimed 1 mm/px.
- `[~]` **A3.2 Tune the classical baseline for real imagery.** *(updated 2026-10-16: two genuine baseline defects were found by measurement and fixed — the 3x3 morphological close was bridging the visible binder joint between touching chips (903 of 1,380 joint pixels flipped back, 59 chip components collapsed to 21), and greedy NMS marker seeding fragmented flat distance plateaus (a uniform 20x120 region returned 26 fragments). Touching-scenario instance F1 went 0.148 -> 0.877 on held-out-validated settings. Real-image tuning is still blocked on labels and verified scale, so this stays partial.)* Original note: The synthetic-tuned config **fails to transfer**: it returns ~2,150 instances/image (polarity `brighter`) and ~3,742 (polarity `darker`) with a 3.91–5.53 mm median "diameter" and up to 0.54 coverage. Real chip counts are hundreds per m², not thousands, and 3.91 mm is far too small for road aggregate. Cause: marker density (`marker_min_distance_px`, `min_marker_radius_px`) and the foreground threshold are tuned to clean synthetic disks. **No result from this pilot may be reported as a chip measurement.**
- `[ ]` A3.3 Compare model error against the human disagreement floor (A2.3). Blocked on A2.3.
- `[ ]` A3.4 Inspect split/merge errors specifically, not just total count, because opposing errors can cancel.

---

## B. Splits, annotation and human review

Source: ML_ROLE §2 "Splits, annotation and human review", final plan §6.2, §6.3.

- ~~B1. Prohibit crops/augmentations before grouping~~ — no split or crop has been produced yet, so nothing has violated this.
- ~~B2. Record that Crack-Seg's shipped split honoured parent boundaries~~ — 0 of 1,549 parents span splits (audited).
- `[ ]` B1 Build original-image / road / session / adjacent-frame / near-duplicate groups **before** any crop.
- `[ ]` B2 Freeze grouped train/development/test partitions (~60/20/20 by group when group count permits).
- ~~B3 Adjacent-frame check for CRKWH100~~ — tested: consecutive-image correlation median **+0.020** vs random-pair control **+0.006** → **no adjacency**, these are independent frames, not contiguous crops. *(Corrects the assumption that sequential filenames 1000–1099 imply one scan.)*
- `[ ]` B4 Keep `aggregate_public_test`, `distress_india_test`, `india_challenge_test` and eventual `live_india_acceptance` **separate** manifests.
- `[ ]` B5 Fit normalizers, reference statistics, thresholds, feature selection and score mappings **without touching test groups**.
- `[ ]` B6 If a test failure informs a change, obtain a **fresh independent group** for a new headline result.
- `[ ]` B7 Write the annotation guide for `visible_aggregate_instance`, `ignore`, `valid_surface`, `crack`, `pothole`, `repair_or_patch`, `surface_family`, `human_condition` (ML_ROLE's exact label set).
- `[ ]` B8 Pilot: 10 double-labelled aggregate crops, 20 distress examples/negatives, 20 condition ratings.
- `[ ]` B9 First useful training round: **80–150 aggregate crops from ≥ 30 distinct parent images**, ~150–300 Indian distress mask images, 150–250 reviewable condition patches.
- `[ ]` B10 Two blinded condition raters plus a third adjudicator; seek pavement expertise for the rubric. *(Pending D3: the judge's exact definitions of "chip boundary width" and "roughness".)*
- `[ ]` B11 Independently review ≥ 20% of routine annotations and every ambiguous case.
- `[ ]` B12 SAM2 only as a *proposal* tool **after** the unaided pilot, with every accepted proposal reviewed; test set labelled independently.

---

## C. Geometry, quality gates and honest physical units

Source: ML_ROLE §2 "Geometry, quality and honest physical units", final plan §7.1–§7.4.

- ~~C1 Planar scale with explicit `scale_source` lineage (`source_calibrated` / `rig_calibrated` / `reference_measured` / `unscaled`)~~ — `backend/geometry/scale.py`.
- ~~C2 Plan area formula `valid_pixels × sx × sy / 1e6`~~ — implemented and unit-tested.
- ~~C3 Crop preserves scale; resize changes scale, and the lineage is recorded~~ — implemented and unit-tested.
- ~~C4 Area-uncertainty propagation (relative linear error doubles in area)~~ — implemented and unit-tested.
- ~~C5 Plane homography `H = K[r1 r2 t]` and image↔plane mapping~~ — `backend/geometry/plane.py`, round-trip tested.
- ~~C6 Local mm/px from the Jacobian singular values, so no single global mm/px is assumed for an oblique view~~ — implemented and unit-tested.
- ~~C7 No metric value is ever fabricated: unscaled imagery yields `null`, never `0`, and a measured empty region yields `0.0`~~ — asserted directly in tests.
- `[!]` C8 **Live rig calibration**: intrinsics/distortion at the actual resolution/focus/stabilization state, ~15–25 varied board views, local road-plane fit from measured correspondences, tested on *held-out* distances at centre and corners. Blocked: no camera. *(final plan §5.2: "No camera access means live functionality is blocked.")*
- `[!]` C9 Obtain frames and mounting facts from the backend/camera owner.
- `[~]` C10 Implement independent validity/status reasons — **implemented and tested 2026-10-16** (`backend/quality/validity.py`, `eval/quality_gate.py`, 18 tests, `quality-v1`): decode failure, unsupported channels, inadequate source resolution, insufficient sharpness, clipped highlights, clipped shadows, low dynamic range and missing scale, each producing `accepted`/`limited`/`rejected` plus reason codes. **Still missing, deliberately not faked:** surface-domain (unsupported material) and plane-stability reasons need surface labels and a calibrated rig respectively, and feature-completeness needs the reference/scoring slice to exist.
- `[!]` C11 Calibrate rejection thresholds from accepted/rejected examples **per rig** *(2026-10-16: the policy exists and is exercised, and every report carries `thresholds_calibrated: false`; on the 100 CRKWH100 frames these provisional thresholds rejected 0, so the gate has not yet been shown to bind on real data. Blocked on the rig.)* Original note: — explicitly **not** one universal blur cutoff.
- `[ ]` C12 A camera change or altered zoom/crop must invalidate the old profile until rechecked — enforce in code.
- `[ ]` C13 Record the supported minimum particle diameter and minimum gap width.
- `[ ]` C14 Test stationary first, then controlled slow motion. FPS cannot compensate for exposure blur.
- `[ ]` C15 Error reporting must separate **annotation agreement using source scale** from held-out **physical** live-camera error.

---

## D. Features

Source: final plan §7.3 (the only features in scope).

- ~~D1 Count density with eligible area and visible minimum size~~ — implemented, unit-tested, with null-vs-zero behaviour.
- ~~D2 2D equivalent diameter, explicitly *not* sieve size or internal gradation~~ — implemented, documented as projected appearance.
- ~~D3 Aggregate union coverage (union, never a sum that double-counts)~~ — implemented and unit-tested.
- ~~D4 Gap median/IQR/p90 plus valid sample count from a documented medial-axis method requiring opposing boundaries on distinct instances~~ — implemented and unit-tested.
- ~~D5 Interior counting ROI with a context margin; count by centroid inside the ROI; flag border-touching instances~~ — implemented and unit-tested.
- ~~D6 Denominator safeguard: observed, texture-eligible, ignored and distress areas recorded separately~~ — implemented and unit-tested.
- ~~D7 Fixed-scale texture proxies (GLCM contrast/homogeneity, gradient energy, LBP summary at fixed physical offsets)~~ - **implemented and verified 2026-10-16.** `texture_statistics()` in `backend/aggregate/features.py`, exported from the package. GLCM contrast/homogeneity/energy/correlation at configurable physical mm offsets, mean squared Sobel gradient energy in 1/mm^2, LBP uniformity fraction at a physical radius. Unscaled imagery returns all-`None` with a limitation rather than a fabricated number. 20 tests in `tests/ml/test_measurement_core.py`. **Two documented caveats:** a 3x3 Sobel is a null operator at the checkerboard/Nyquist frequency, so a near-pixel-scale surface can read as low gradient energy; and a physical offset must quantise to a whole pixel count, so the effective offset set depends on the declared scale.
- ~~D8 Crack skeleton length and defect mask area - not implemented (needs the distress engine)~~ - **implemented 2026-10-16.** ``backend/distress/features.py`` with ``crack_skeleton_length_m``, ``defect_extent_fraction``, ``distress_metrics``, ``rasterize_polygon``, ``rasterize_label_file``. Skeleton length sums *step* distances (diagonal = sqrt(2)) so diagonal cracks are not under-reported by 29%. 20 tests in ``tests/ml/test_distress_features.py`` including an analytic ground-truth check.
- ~~D9 Merge tile-boundary instances and count each particle once - designed, not implemented (no tiling yet)~~ - **implemented 2026-10-16** (see E6). Verified exact-count on disks centred exactly on tile boundaries across 5 tile configs; a deliberately broken no-merge variant double counts 7 to 20, proving the test has teeth.
- `[ ]` D10 Changing the minimum measurable diameter must require a new reference version — enforce in code.
- `[!]` D11 **Validate D4 against human endpoint annotations.** Currently unvalidated; the method provably misses a genuine narrow gap inside one merged instance rather than guessing.

---

## E. Models and training

Source: ML_ROLE §2 "Models, reference and score", final plan §8.

- ~~E1 Classical OpenCV/scikit-image marker-watershed baseline exists and is available~~ — `backend/aggregate/segmentation.py`. Kept as the fallback if a learned model cannot beat it on unseen parents.
- ~~E2 A real defect found and fixed rather than hidden~~ — the background-flood bias (293 px² vs 441 px² true, a 34% size bias); switched to the negated distance transform.
- `[~]` E3 **Retune the classical baseline on real imagery** *(updated 2026-10-16: the baseline is now correct on synthetic geometry with a visible boundary and its real-image behaviour is characterised in unit-free terms — at `min_instance_area_px=0` it still reports ~2,900 instances at 3.57 px median diameter on a 512x512 CRKWH100 image, which is texture noise rather than chips. Choosing a real minimum size needs verified scale (A1.6) and human labels (A2.3).)* Original note: (see A3.2). Until then the baseline is only proven on synthetic geometry.
- `[ ]` E4 Small U-Net with a pretrained ResNet18 encoder predicting interior/boundary/background with an ignore mask; instances reconstructed by validated watershed postprocessing.
- `[ ]` E5 Train from human instance labels converted to interior/boundary targets; derive the final mask from foreground support, **not shrunken interiors alone** (otherwise the measured gap widens artificially).
- ~~E6 Measure geometry at original metric resolution, tiles ~512x512 with overlap, instance IDs merged at tile boundaries~~ - **implemented and verified 2026-10-16.** ``backend/aggregate/tiling.py`` with ``segment_tiled()``, ``measure_tiled()``, ``tile_windows()``. Union-find merge of boundary-straddling fragments, guarded by a minimum-overlap-fraction rule. 10 tests in ``tests/ml/test_tiling.py``. **Known requirement:** the watershed config must set ``min_instance_area_px`` above the noise size, or tiling fragments pure noise into thousands of specks (see changelog).
- `[ ]` E7 One Mask R-CNN alternative **only** if repeated merging persists despite sound labels.
- `[ ]` E8 Separate U-Net/ResNet18 weights for broad crack + pothole masks; fine-tune on reviewed Indian masks.
- `[ ]` E9 Retain foreign mask pretraining **only** if Indian development results improve.
- `[ ]` E10 YOLO box detector **only** as temporary localization when masks are unavailable; boxes cannot supply precise defect area.
- `[ ]` E11 Ravelling/bleeding/polishing stay human-reviewed appearance flags until evidence supports automation.
- ~~E12 No dedicated speed-breaker model~~ — correctly out of scope; agreed, nothing built.
- `[ ]` E13 Colab recipe: locked versions, frozen encoder then gradual unfreezing, AdamW, mixed precision, resumable checkpoints, saved manifests and random states.
- `[ ]` E14 Track three curves: training loss, group-held-out segmentation/count performance, and acceptance/rejection rates.
- `[ ]` E15 Diagnostic runbook for leakage, underfitting, domain shift (final plan §8.4 table) applied when the first real results exist.

---

## F. Known-good reference and the score

Source: ML_ROLE §2 "Models, reference and score", final plan §9.

- `[ ]` F1 Reviewed known-good reference from supported surfaces, starting with **5–8 stable features** (not dozens of correlated descriptors).
- `[ ]` F2 Robust medians/scales fitted on training good groups; compare simple normalized-deviation vs shrinkage Mahalanobis; prefer the simpler reference when independent groups are few.
- `[ ]` F3 Keep domain support **separate from severity**, so a damaged *supported* asphalt patch is not discarded as an unfamiliar material.
- `[ ]` F4 PatchCore/anomalib **only** after F1–F2 work; memory bank must contain training-good images only. Optional.
- `[ ]` F5 Score from texture deviation `T` and observed distress burden `D`, with at most one distribution term.
- `[ ]` F6 Compare a transparent fixed rule against a small regularized, preferably monotone human-rated model; calibrate on grouped development predictions.
- `[ ]` F7 `SQI = 100 × (1 − P_bad)` **only** if probability calibration is supported; otherwise ship a **provisional reference-deviation index** with a review label and say so.
- `[ ]` F8 Derive Good/Bad thresholds from development tradeoffs. **Never** copy the 70/40 bands or invent weights.
- `[ ]` F9 Missing mandatory evidence ⇒ `score = null` unless a separately evaluated partial-input rule exists.
- `[ ]` F10 Keep confidence components and severe-defect inspection flags separate; version reference, model, feature and score definitions together.

---

## G. Inclination (a formal requirement)

Source: ML_ROLE §2 "Keep inclination separate", final plan §10.

- `[ ]` G1 Grade schema with `grade_percent`, `grade_deg`, `source`, `uncertainty`, `capture_time`, `validity`, kept separate from surface condition.
- `[ ]` G2 First supported path: human-verified supporting measurement (calibrated inclinometer/phone level on a rigid straightedge), zero-offset and repeatability validated, longitudinal grade distinguished from crossfall.
- `[!]` G3 Automatic camera/IMU path — conditional on synchronized alignment and independent validation. Blocked: no hardware.
- ~~G4 Reject pitch-as-slope and Google elevation as fine-scale grade truth~~ — agreed and recorded; nothing built on them.
- `[!]` G5 Inclination stays a formal requirement until measured or **explicitly exempted by the judge**. Pending D3/judge.

---

## H. Handoff to backend and frontend

Source: ML_ROLE §3, final plan §11.4, §11.5.

- `[ ]` H1 Write the feature/unit/null-behaviour **specification** under `docs/ml/` (definitions currently live only in code).
- `[ ]` H2 Propose the scientific record fields, units, null reasons, provenance and version identifiers under `docs/ml/` for the backend to publish as the Pydantic/OpenAPI contract.
- `[ ]` H3 Supply a callable inference adapter for `quality → geometry → aggregate/distress → reference → score` with a deterministic result/status shape.
- `[ ]` H4 Supply reviewed visual overlays and metric examples with source and uncertainty for frontend interpretation.
- `[ ]` H5 Raise any interface or requirement conflict in `docs/ml/` and ask the owning role to change the owned file.
- `[ ]` H6 Populate `configs/camera/`, `configs/features/`, `configs/scoring/` — all three still empty. Measurement config currently exists only as code dataclasses.

---

## I. Completion evidence

Source: ML_ROLE §4, final plan §13.1–§13.4.

- ~~I1 Gate 0 data admission decision document~~ — `docs/ml/DATA_ADMISSION.md` exists, Crack-Seg decision complete.
- ~~I2 Provenance register and checksum/licence inventory~~ — `data_manifests/crack_seg_ultralytics_2025-08-21.json` plus the admission doc.
- `[~]` I3 Gate 0 output set: admission document ✓, contact sheet ✓, original-source manifests ✓, reviewed annotation set ✗, supported feature-size range ✗, chips/gaps go/no-go ✗.
- ~~I4 Minimal software tests worth keeping (coordinate-transform direction/units, resizing scale updates, polygon area, density denominator, border counting, ignored-pixel handling, null-vs-zero, policy versions)~~ — **154 tests**, all passing (113 at the session start, 136 after the segmentation slice, 154 after the quality gate; see `docs/ml/changelog.md` 2026-10-16).
- `[ ]` I5 Annotation guide and independent review records.
- `[ ]` I6 Frozen split manifests including original/duplicate lineage.
- `[ ]` I7 Camera feasibility and calibration report with the actual operating envelope.
- `[ ]` I8 Feature specification (minimum resolvable sizes, denominator rules, null behaviour).
- `[ ]` I9 Model cards with data ancestry, seeds, weight/config hashes and failure examples.
- `[ ]` I10 Reference/scoring specification with the development procedure and final thresholds.
- `[ ]` I11 Validation report separating foreign development, public Indian evaluation and live Indian acceptance.
- `[ ]` I12 Group-held-out **public aggregate** results and **Indian distress** results.
- `[ ]` I13 Human score agreement/calibration, or an explicitly provisional index.
- `[!]` I14 **Independent Indian live-camera acceptance** once access exists.
- `[ ]` I15 Report count/gap errors and intervals **by independent parent/site**, plus rejection/unknown coverage.
- ~~I16 Eval harness in `eval/` for per-task and India/live acceptance metrics~~ — `eval/aggregate_eval.py`: pixel precision/recall/F1/IoU/Dice, greedy instance matching at an IoU threshold, signed/absolute/relative count error, a synthetic fixture with exact labels in three boundary scenarios, a held-out parameter sweep (`--sweep-markers`, train seeds 0-7 reported against held-out 5000-5007), real-image descriptive diagnostics and a determinism check. **India/live acceptance metrics remain open** — no Indian or live data has been obtained. **Distress harness added 2026-10-16:** ``eval/distress_eval.py`` (``python -m eval.distress_eval --labels <dir> [--gt <dir>]``) scores any directory of YOLO segmentation polygons - pixel IoU, precision, recall, Dice, best-overlap instance IoU, extent distribution. GT-vs-GT self-check returns 1.0 on every metric. Run on the real Crack-Seg test split: 112 images, extent mean 1.98%, median 1.64%, p90 3.88%, max 5.82%.

**Explicitly not a completion claim:** foreign public-image performance alone does
**not** complete the India claim or the live requirement (ML_ROLE §4).

---

## J. Working agreements and hygiene

Source: user instruction, ML_ROLE §1.

- ~~J1 `docs/ml/changelog.md` created and updated after every change/run/decision~~ — maintained; 8 entries.
- ~~J2 Stay inside the ML-owned writable areas~~ — verified repeatedly; `data/` needed and received explicit user approval (D9).
- ~~J3 Test after each feature; do not proceed until it runs~~ — followed for the measurement core (92 passing) and again for the 2026-10-16 segmentation and fixture changes (8 tests observed failing before implementation; 154 passing after the quality gate).
- ~~J4 Delete temporary scripts once they have served their purpose~~ — diagnostic and probe scripts deleted after use.
- ~~J5 Consolidated tests from 6 files to 2 to avoid file sprawl~~ — done.
- ~~J6 TDD order (red → green) was violated in slice 1~~ — recorded rather than retroactively fixed. **Followed from the 2026-10-16 slice onward:** the 8 new tests for the fixture scenarios, the minimum-area filter and the hole-fill limit were observed failing (`TypeError: WatershedConfig.__init__() got an unexpected keyword argument 'min_instance_area_px'`) before the implementation existed. One recorded deviation: `select_annotation_patches` had its test and implementation written in the same edit, so no red state was observed for that single function.
- `[ ]` J7 Unit-test the `eval/dataset_audit.py` helpers (currently exercised only on real archives, so not regression-protected).
- `[ ]` J8 Confirm whether the locally implemented `skeletonize_2d` is preferred over adding the absent `scikit-image` (D6).

---

## Blocked on the user right now

**Resolved 2026-10-15:** D8 (DeepCrack licence) — granted by the originating author. Removed from this list; remaining rows renumbered.

| # | What | Why it blocks |
|---|---|---|
| 1 | **A1.8** — RDD2022 India subset | PRIMARY Indian distress source; blocks every Indian distress claim |
| 2 | **A1.9** — ISTD-PDS7 access request | ONLY public scaled aggregate candidate at 0.91 mm/px; if A1.6 fails, this is the entire chip task |
| 3 | **A1.11** — Indian seasonal dataset | Indian robustness/wet-surface validation |
| 4 | **A1.6** — crop vs resize of CRKWH100 512×512 | Decides whether any mm value exists for CRKWH100 (fallback pilot) |
| 5 | **A2.2/A2.3** — two humans inspect contact sheet and double-label 10 patches | The only path to a chips/gaps go/no-go. Open `reports/ml/crkhw100_annotation_patches.png` and `reports/ml/crkhw100_contact_sheet.png`, fill `annotation_guides/aggregate_patch_annotation_template.csv` |
| 6 | **D3** — judge's exact meaning of "chip boundary width" and "roughness" | Feature definitions stay provisional until confirmed |
| 7 | **C8** — camera access | Blocks live requirement and live calibration; replay cannot substitute |
| 8 | **D4** — approve ML-side dependencies | `segmentation-models-pytorch` and `scikit-image` absent; needed when Gate 0 clears |
