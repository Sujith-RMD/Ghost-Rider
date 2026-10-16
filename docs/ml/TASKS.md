# ML role — task tracker

Navigation: [Data admission and visibility evidence](DATA_ADMISSION.md) · [Changelog](changelog.md) · [User actions and blockers](#user-actions-and-blockers) · [Implementation review](#implementation-review)

## Summary

Gate 0 remains incomplete. Software foundations and synthetic tests exist, but verified delivered-image scale, independent human chip/gap labels, Indian mask/rights/grouping admission, the seasonal challenge data and camera access remain outstanding. RDD2022 India is now locally obtained and integrity-audited (9,665 decoded images); acquisition is not admission or accuracy. Foreign public imagery, synthetic metrics and evaluator self-checks do not establish Indian-road, live-camera or physical-measurement accuracy. No evidence-backed model-accuracy gain is claimed.

**State of play 2026-10-16.** The India distress localization baseline has been trained, locally installed, evaluated on sample imagery, and integrated as optional evidence in API v1.2.0. The aggregate measurement slice remains synthetic-only and Phase 0 camera acquisition has not begun. The binding constraint has moved from modelling to **labels and hardware**. Human annotation is not uniformly blocked: distress masks are achievable solo today (B13, A2.6), chip and gap annotation is not (A2.2, A2.3).

This document consolidates the task tracker, user decisions/actions and the 2026-10-16 implementation review. Task IDs and statuses are retained; historical run counts and claims below are snapshots, not current validation. The [implementation review](#implementation-review) supersedes historical greedy-matching, quality-v1 and source-independence claims: current quality policy is quality-v2, valid instance matching is no longer greedy, and ancestry must be confirmed before claiming cross-source independence. The final plan remains authoritative. Decision IDs such as D3/D4/D8 are distinct from similarly named feature task IDs.

Derived **only** from `docs/ML_ROLE.md` and `docs/final_plan.md`. Every task cites
its source section so it can be re-checked, and nothing here invents a requirement.

**Provenance of the task IDs.** The `A1.x` / `B` / `C` / `D7` / `E10` / `I16` / `J7`
numbering is **agent-derived for tracking**. It appears in neither `final_plan.md`
nor `ML_ROLE.md`; the final plan uses section numbers and prose, and ML_ROLE names
capabilities without IDs. Every task below still cites its upstream section, so the
*content* is checkable even though the labels are ours. Do not quote these IDs as if
they were plan identifiers.

**Ordering deviation from the plan, recorded 2026-10-16.** `final_plan.md` §14 places
Phase 2 ("one actual image → QC → metric ROI → classical masks/count/size/gaps →
versioned JSON") **before** Phase 4 ("frozen data and learned challenger ... Indian
distress mask subset"). Work so far has run the other way round: distress
segmentation, cross-source evaluation and the India detector are substantially done
while the **aggregate** measurement slice is still synthetic-only and blocked on
human labels. Both models are now trained-or-ready in the Colab runbook, which makes
Phase 2 the binding constraint on the whole project rather than Phase 4. Camera
acquisition is also a **Phase 0** item per §14 ("Camera acquisition and platform
smoke tests begin in Phase 0, not Phase 6") and has not been started.

**Consequence:** the highest-value remaining work is now A2.6/B13 (annotation, the
thing that unblocks everything) and C8 (camera access), not more distress modelling.

Status legend:

- ~~struck through~~ = **achieved and verified** (evidence in `docs/ml/changelog.md`)
- `[~]` = **partial** — started, not complete
- `[ ]` = **open**
- `[!]` = **blocked** — needs the user, hardware, or access

Last updated: 2026-10-16. Current gate: **Gate 0 (incomplete)** — Phase 1 of the
plan's phase table (final plan §14).

### Current usable evidence and next steps

- **Completed this implementation batch:** A1.8 (Indian archive acquisition/integrity inventory), C12 (standalone calibration-profile guard), C15 (evidence-type-safe error reporting), D10 (reference-definition guard), I16a (distress metric reporting), I16b (real-mask trivial comparison floor). These do not imply model or live acceptance.
- **Real-data reports:** RDD India has 7,706 train images/8,175 boxes and 1,959 unannotated test images, all decoded. CRKWH100 has 0.357479% foreground; trivial all-foreground pooled Dice is 0.007124 and all-background Dice is 0. No intact negatives means no false-alarm performance estimate. Reports are under `reports/ml/` and reproducible with [FEATURE_SPEC.md §9](FEATURE_SPEC.md#9-runnable-evaluation-and-provenance-tools).
- **Available software:** explicit-group split freezing; pooled/positive-only segmentation metrics and guarded intervals; count/gap/length bias/MAE/p95 with suppression coverage; local-weight inference hashes, optional raster outputs and scoped p50/p95 timing. No actual trained weights were available to run.
- **Next real unblockers, in priority order.** (1) **B13 + A2.6** — annotate distress masks and pass the self-consistency gate; solo-viable and unblocks Phase 2 and Phase 4. (2) **A14** — start camera acquisition and an AWS/Bedrock/Maps smoke test, both Phase 0 items per §14 that are currently absent. (3) **A3.5** — rebuild the Phase 2 measurement slice as a committed script, since the one-off accuracy script was deleted and nothing currently reproduces a real-image measurement. (4) **A1.9/A1.10** — request the scaled aggregate datasets, because without one of them the chip task has no scale at all. Do not convert boxes into precise area, and do not mark a training requirement done from evaluator tests.
- **Colab:** `training/COLAB_TRAINING.ipynb` + `training/COLAB_TRAINING.md` cover both distress models end to end — clone, Drive data, smoke test, real run, evaluation, and bring-the-results home. No data is committed to the repo, so Google Drive is the bridge. Start with the two-epoch smoke test; it costs two minutes and catches bad paths before a 60-epoch run wastes an hour.

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
- ~~A1.8 Obtain RDD2022 India subset~~ - **obtained and admitted 2026-10-16.** DatasetNinja repackaging of RDD2022, India-tagged only: **7,706 images** (720x720), 6,165 train / 1,541 dev frozen by seed 0 before any model ran. **8,175 bounding boxes** across 5 observed classes (pothole 3187, alligator crack 2021, longitudinal crack 1735, other corruption 1119, transverse crack 113; block crack and repair declared but unobserved in India). Licence CC BY-SA 4.0. Manifest `data/external/rdd2022_india/manifest.json`. **Key value: 3,934 negatives (51.1%) - the first intact-road imagery in the project.** RDD shipped test split is 100% unlabelled and was deliberately unused. Boxes only, so this feeds detection (E10), not area measurement.
- `[!]` A1.8a **Admit RDD India for training/evaluation:** verify original reuse rights (mirror declares CC BY-SA 4.0), review overlays/empty labels, resolve road/session/near-duplicate lineage, freeze grouped development/test, and obtain precise human masks. Test JSONs are unannotated, **not intact negatives**. No Indian accuracy claim is enabled by acquisition.
- `[!]` **A1.9 Request ISTD-PDS7 access** — the **ONLY public candidate for scaled aggregate feasibility**. 18,527 images documented at 0.91 mm/pixel. Access by request via https://www.mdpi.com/2072-4292/15/7/1750. Existing labels are distress, not chips; human chip annotations required. *final_plan §4.2: "First public-data candidate for scaled aggregate feasibility."* **BLOCKING: if A1.6 resolves against CRKWH100, this becomes the entire chip task.**
- `[ ]` A1.10 Request **GAPs original images** access (1.2 mm/px backup, academic access form required) — not requested. The 10m release has only 20 large images with few independent scenes. *final_plan §4.2: "Backup scaled imagery."* Link: https://www.tu-ilmenau.de/universitaet/fakultaeten/fakultaet-informatik-und-automatisierung/profil/institute-und-fachgebiete/institut-fuer-technische-informatik-und-ingenieurinformatik/fachgebiet-neuroinformatik-und-kognitive-robotik/data-sets-code/german-asphalt-pavement-distress-dataset-gaps
- `[!]` **A1.11 Obtain Indian seasonal paved/unpaved dataset** — **Indian robustness/challenge set** for wet appearance and unsupported surfaces. 4,242 Nashik/Mumbai originals plus rotated versions and video; group siblings, start from originals. *final_plan §4.2: "Indian robustness/challenge set."* **BLOCKING: wet/unsupported-surface validation.** Link: https://data.mendeley.com/datasets/tj2m7zz4rg/2
- `[ ]` A1.12 Obtain **Pavementscapes** — optional distress-mask pretraining (4,000 images, 6 damage categories, grayscale, claimed 1-2 mm GSD unverified). *final_plan §4.2: "Preferred optional distress-mask pretraining source."* Optional. Link: https://github.com/tongzheng1992/Pavementscapes
- ~~A1.13 CRKWH100 crack GT (separate OneDrive link)~~ - **obtained and admitted 2026-10-16.** 100 BMP masks at 512x512, binary (values 0/255), paired 1:1 with the images. Manifest: `data/manifests/crkhw100_test.json`. Admitted as a **held-out CROSS-SOURCE distress test** - different sensor, resolution and geography from Crack-Seg. `eval/distress_eval.py --manifest` scores it in raster space, GT-vs-GT self-check returns 1.0 on every metric. **Critical caveat: all 100 images carry crack GT, so this set supplies ZERO negatives.**

### A2. Human visibility decisions — **cannot be done by the agent**

Source: ML_ROLE §2 "Two humans independently decide…", final plan §5.1 steps 2, 4, 6.

- ~~A2.1 Contact sheet of native-resolution tiles~~ — `reports/ml/crkhw100_contact_sheet.png` (20 native 256 px centre-crops, **pixel-only `10 px` bar** - no mm bar, because the 1 mm/px claim is unverified; never resized, sampled evenly across the set). A second, fillable artifact now exists for A2.3: `reports/ml/crkhw100_annotation_patches.png` (10 numbered native 256 px patches, no model overlay) with `annotation_guides/aggregate_patch_annotation_template.csv` (20 prefilled rows, coordinates included, judgements blank).
- `[!]` **A2.2 Two people independently judge at native resolution whether separate chips are distinguishable and adjacent boundary gaps are locatable.** Not done. Zooming must not merely magnify ambiguity. **Blocked on a second human, not on skill.** One person cannot produce an inter-annotator number, so this is a structural blocker and must not be faked with a self-consistency figure.
- `[!]` **A2.3 Double-annotate 10 small patches with no model suggestions, and measure the disagreement floor.** Not done. **Blocked on two people.** Achievable substitutes are A2.6 (intra-annotator, clearly labelled as such) and A2.4a (one domain reviewer over the hardest patches). Neither is inter-annotator agreement.
- `[ ]` A2.6 **Solo intra-annotator self-consistency protocol.** *(2026-10-16: added, and achievable now by one person with no domain background.)* Annotate 20 images, wait ≥3 days, re-annotate the same 20 blind, measure agreement. Report as `intra_annotator_agreement` — **never** as `inter_annotator_agreement`. Its real output is diagnostic: images you disagree with yourself on are images you cannot reliably label and must go to `ignore`. Full protocol in `annotation_guides/ANNOTATION_GUIDE.md` §"If you have no domain expertise". Tooling: `annotation_guides/annotate.html`, verified by `node annotation_guides/verify_annotate.js`.
- `[ ]` A2.4a **One domain reviewer over the 20 hardest patches.** Lower bar than full double-annotation (A2.3) and still expert-checked. Candidate reviewers: the project's pavement-engineering contact, or an ISTD-PDS author (A1.9). Record the reviewer's identity and scope.
- `[!]` **A2.4 Declare separate go/no-go for chip count and for gap width, plus the minimum resolvable size for each.** Not done — depends on A2.2/A2.3.
- `[ ]` A2.5 Inspect ~20–30 scaled images at native resolution (superset of A2.2's sample).

### A3. Classical pilot on real data

Source: final plan §5.1 step 5, §8.1.

- ~~A3.1 Run the classical segmentation pilot on admitted real imagery~~ — done on 12 CRKWH100 images at the claimed 1 mm/px.
- `[~]` **A3.2 Tune the classical baseline for real imagery.** *(updated 2026-10-16: two genuine baseline defects were found by measurement and fixed — the 3x3 morphological close was bridging the visible binder joint between touching chips (903 of 1,380 joint pixels flipped back, 59 chip components collapsed to 21), and greedy NMS marker seeding fragmented flat distance plateaus (a uniform 20x120 region returned 26 fragments). Touching-scenario instance F1 went 0.148 -> 0.877 on held-out-validated settings. Real-image tuning is still blocked on labels and verified scale, so this stays partial.)* Original note: The synthetic-tuned config **fails to transfer**: it returns ~2,150 instances/image (polarity `brighter`) and ~3,742 (polarity `darker`) with a 3.91–5.53 mm median "diameter" and up to 0.54 coverage. Real chip counts are hundreds per m², not thousands, and 3.91 mm is far too small for road aggregate. Cause: marker density (`marker_min_distance_px`, `min_marker_radius_px`) and the foreground threshold are tuned to clean synthetic disks. **No result from this pilot may be reported as a chip measurement.**
- `[ ]` A3.3 Compare model error against the human disagreement floor (A2.3). Blocked on A2.3.
- `[ ]` A3.4 Inspect split/merge errors specifically, not just total count, because opposing errors can cancel.
- `[!]` **A3.5 Phase 2 measurement slice: one real image → QC → metric ROI → classical masks/count/size/gaps → versioned JSON.** *(2026-10-16: elevated to the binding constraint.)* This is the plan's own named critical deliverable — final_plan §14 Phase 2 — and it is **not done**. The aggregate engine exists (`backend/aggregate/{segmentation,features,measurement,tiling}.py`, `measure-v1` / `gap-medial-v1`) but has only been exercised on **synthetic** data and on the CRKWH100 classical pilot, which changelog records as "pathological oversegmentation, not real chip counts". The one-off accuracy script that produced real-image numbers was **deleted** as temporary ("four radius-12 disks each measured 441 px…"), so nothing in the repo reproduces a real-image measurement today; there is no `scripts/` directory. **Blocked on B13** (chip labels) and A1.6 (verified scale). Until a reproducible script exists, no count/size/gap figure may be published, and the aggregate requirement stays unaddressed however complete the distress branch becomes.
- `[!]` **A14 Acquire live camera access.** *(added 2026-10-16)* final_plan §14 is explicit: "Camera acquisition and platform smoke tests begin in **Phase 0**, not Phase 6. Phase 6 is integration/completion, not the first attempt to find hardware." §1 calls live access a "first-stage dependency" and §18 keeps it open. **Not started.** Nothing in this tracker currently asks anyone to go and get a camera, so the omission is silent. This blocks Phase 6, C8 and the entire live/local acceptance requirement (§2: "Actual live road-camera capture is required. Replay is backup only.").

---

## B. Splits, annotation and human review

Source: ML_ROLE §2 "Splits, annotation and human review", final plan §6.2, §6.3.

- ~~B1. Prohibit crops/augmentations before grouping~~ — no split or crop has been produced yet, so nothing has violated this.
- ~~B2. Record that Crack-Seg's shipped split honoured parent boundaries~~ — 0 of 1,549 parents span splits (audited).
- `[~]` B1 Build original-image / road / session / adjacent-frame / near-duplicate groups **before** any crop. **Tooling implemented and verified 2026-10-16:** `training/group_splits.py` builds connected groups from explicit source-scoped parent/site/road/session/sequence/duplicate IDs and reviewed cross-source links. Missing grouping evidence fails; filenames/correlation do not establish independence. Actual reviewed real-data grouping remains open (no local data).
- `[~]` B2 Freeze grouped train/development/test partitions (~60/20/20 by group when group count permits). **Software complete:** deterministic group allocation, frozen assignment preservation, cross-split leak detection, checksums, group/sample statistics and overwrite protection; 35 tests. Actual frozen admitted-data partitions remain open.
- ~~B3 Adjacent-frame check for CRKWH100~~ — tested: consecutive-image correlation median **+0.020** vs random-pair control **+0.006** → **no adjacency**, these are independent frames, not contiguous crops. *(Corrects the assumption that sequential filenames 1000–1099 imply one scan.)*
- `[~]` B4 Keep `aggregate_public_test`, `distress_india_test`, `india_challenge_test` and eventual `live_india_acceptance` **separate** manifests. `training/group_splits.py` emits separate role lists, additionally supports `foreign_crosssource_test`, and rejects connected groups spanning roles. Required real evaluation cohorts remain unavailable.
- `[ ]` B5 Fit normalizers, reference statistics, thresholds, feature selection and score mappings **without touching test groups**.
- `[ ]` B6 If a test failure informs a change, obtain a **fresh independent group** for a new headline result.
- ~~B7 Write the annotation guide for `visible_aggregate_instance`, `ignore`, `valid_surface`, `crack`, `pothole`, `repair_or_patch`, `surface_family`, `human_condition` (ML_ROLE's exact label set).~~ — **written 2026-10-16.** `annotation_guides/ANNOTATION_GUIDE.md` defines all eight labels, the ground rules (label from native pixels not a model; use `ignore` when unsure; **do not manufacture chip ground truth** on an unresolvable speckle field; group before splitting) and the aggregation/denominator notes. It is a *definitions* document, not a result: no double-labelled set exists yet, so the disagreement floor is unmeasured (B8/A2.3 still blocked on two humans).
- `[ ]` B8 Pilot: 10 double-labelled aggregate crops, 20 distress examples/negatives, 20 condition ratings.
- `[ ]` **B9 First useful training round.** *(updated 2026-10-16)* **The distress half is now achievable by one person with no domain background** and is the highest-value open task: ~150–300 Indian distress mask images (`crack`, `pothole`, `repair_or_patch`, plus `ignore` and `valid_surface`) drawn with `annotation_guides/annotate.html`. See B13. The aggregate half (80–150 aggregate crops from ≥30 distinct parent images) stays blocked on A2.2/A2.3.
- `[ ]` B13 **Distress annotation workflow (solo-viable).** *(added 2026-10-16)* Draw `crack`/`pothole`/`repair_or_patch` masks at the crack's real width on CRKWH100 or RDD India images, pass the A2.6 self-consistency gate, then scale to the B9 target. This is the tier that does **not** require domain expertise — crack/pothole/repair are visual categories, and RDD2022 itself was labelled by crowd workers. Use `ignore` freely. **Never** annotate `visible_aggregate_instance` or chip gaps: those are Tier 3, blocked on verified scale (A1.6) and domain judgement (A2.4a). *final_plan §6.3, §4.3.*
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
- ~~C12 A camera change or altered zoom/crop must invalidate the old profile until rechecked — enforce in code.~~ **Standalone gate implemented and verified 2026-10-16:** `backend/geometry/profile.py`, `CameraProfile.require_scale(current)`. Device/resolution/focus/zoom/capture-crop/stabilization/mount changes, unknown state or missing/failed/mismatched validation suppress scale. Explicit signature-and-scale-bound recheck required. Future adapter must call this per capture and retire profiles on reported changes; unreported physical changes cannot be detected. No rig calibration claimed.
- `[ ]` C13 Record the supported minimum particle diameter and minimum gap width.
- `[ ]` C14 Test stationary first, then controlled slow motion. FPS cannot compensate for exposure blur.
- ~~C15 Error reporting must separate **annotation agreement using source scale** from held-out **physical** live-camera error.~~ **Reporting contract verified 2026-10-16:** `eval/measurement_eval.py` requires explicit `annotation_source_scale`, `physical_live` or `synthetic` evidence; pixel measurements cannot claim physical-live validation. 17 focused tests. Actual physical error results remain blocked on C8.

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
- ~~D10 Changing the minimum measurable diameter must require a new reference version — enforce in code.~~ **Standalone gate implemented and verified 2026-10-16:** `backend/reference/compatibility.py` fingerprints immutable physical diameter/gap limits, method versions and scale domain; incompatible definitions fail and `revise_reference()` requires a different version for changed definitions. Must be used by the eventual fitted reference; no F1/F2 completion claimed.
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
- `[~]` E10 YOLO box detector **only** as temporary localization when masks are unavailable; boxes cannot supply precise defect area. **Colab baseline run completed 2026-10-16 and integrated as optional evidence in API v1.2.0:** pretrained YOLOv8n, 60 epochs on 6,165 RDD2022 India train images, evaluated on 1,541 frozen dev images (mAP50 0.337, mAP50-95 0.152). On 783 empty-label dev images, 95 (12.13%) produced at least one box at confidence 0.25; labels may omit real defects, so this is not a confirmed false-positive rate. Block crack/repair have zero India examples; transverse crack has 23 dev boxes. Localization only; not approved for physical measurement or road-quality scoring.
- `[ ]` E11 Ravelling/bleeding/polishing stay human-reviewed appearance flags until evidence supports automation.
- ~~E12 No dedicated speed-breaker model~~ — correctly out of scope; agreed, nothing built.
- `[~]` E13 Colab recipe: locked versions, frozen encoder then gradual unfreezing, AdamW, mixed precision, resumable checkpoints, saved manifests and random states. **Inference provenance tooling verified 2026-10-16:** weight/manifest hashes, confidence, actual library versions, sample-ID mapping, optional original-resolution saved masks and overwrite guards. This does not complete the planned U-Net training/resume/environment-lock recipe. Existing Colab instructions preserved.
- `[~]` E14 Track three curves: training loss, group-held-out segmentation/count performance, and acceptance/rejection rates. **Metric reporting implemented:** pooled/macro/positive-only distress metrics, frame-error denominators, explicit-group summaries/guarded intervals, dimensional suppression coverage and inference p50/p95 timing. Training curves and actual image-quality acceptance/rejection evidence still require real runs; frame false-alarm rates are not quality rejection rates.
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

- ~~G1 Grade schema with `grade_percent`, `grade_deg`, `source`, `uncertainty`, `capture_time`, `validity`, kept separate from surface condition.~~ — **implemented 2026-10-16.** `backend/geometry/grade.py` (`GradeMeasurement`, `GradeSource`, `GradeValidity`), exported from `backend/geometry/`. Longitudinal grade is a distinct field from crossfall; `phone_pitch`/`google_elevation` are refused at the boundary; a `rig_imu` value is `uncalibrated_sensor` (not `valid`) until independently validated. `null` (unmeasured) is kept strictly distinct from a measured `0.0` (flat). 20 tests in `tests/ml/test_grade.py`.
- `[ ]` G2 First supported path: human-verified supporting measurement (calibrated inclinometer/phone level on a rigid straightedge), zero-offset and repeatability validated, longitudinal grade distinguished from crossfall.
- `[!]` G3 Automatic camera/IMU path — conditional on synchronized alignment and independent validation. Blocked: no hardware.
- ~~G4 Reject pitch-as-slope and Google elevation as fine-scale grade truth~~ — agreed and recorded; nothing built on them.
- `[!]` G5 Inclination stays a formal requirement until measured or **explicitly exempted by the judge**. Pending D3/judge.

---

## H. Handoff to backend and frontend

Source: ML_ROLE §3, final plan §11.4, §11.5.

- ~~H1 Write the feature/unit/null-behaviour **specification** under `docs/ml/` (definitions currently live only in code).~~ — **written 2026-10-16.** `docs/ml/FEATURE_SPEC.md` §1–§7: every geometry/grade/aggregate/gap/texture/distress/quality field with its unit, when it is `null`, and when it is a real `0.0`, plus the `null`-is-not-`0` rule and the scale-source vocabulary.
- ~~H2 Propose the scientific record fields, units, null reasons, provenance and version identifiers under `docs/ml/` for the backend to publish as the Pydantic/OpenAPI contract.~~ — **proposed 2026-10-16.** `docs/ml/FEATURE_SPEC.md` §8 lists the version identifiers to carry together (`measure-v1`, `agg-classical-v3`, `gap-medial-v2`, `texture-proxy-v1`, `quality-v2`, scale/grade source) and proposes the `{value, unit, scale_source, null_reason?, limitation?}` record shape with a short `null_reason` code set. Backend owns the actual schema (`docs/contracts/`).
- `[ ]` H3 Supply a callable inference adapter for `quality → geometry → aggregate/distress → reference → score` with a deterministic result/status shape.
- `[ ]` H4 Supply reviewed visual overlays and metric examples with source and uncertainty for frontend interpretation.
- `[ ]` H5 Raise any interface or requirement conflict in `docs/ml/` and ask the owning role to change the owned file.
- ~~H6 Populate `configs/camera/`, `configs/features/`, `configs/scoring/` — all three still empty. Measurement config currently exists only as code dataclasses.~~ — **populated 2026-10-16.** `configs/features/aggregate.json` mirrors the `MeasurementConfig`/`WatershedConfig`/texture defaults exactly; `configs/camera/rig_template.json` mirrors `QualityPolicy` and carries `thresholds_calibrated: false` with the rig fields left `null` (no camera, task C8); `configs/scoring/scoring.json` is an honest **not-implemented** skeleton — all weights/thresholds `null`, SQI disabled, `score=null` policy — so no invented 70/40 band exists (tasks F7–F9). `tests/ml/test_configs.py` (13 tests) round-trips the features JSON against the live dataclasses and asserts the scoring/camera honesty flags, so a fabricated number would fail a test.

---

## I. Completion evidence

Source: ML_ROLE §4, final plan §13.1–§13.4.

- ~~I1 Gate 0 data admission decision document~~ — `docs/ml/DATA_ADMISSION.md` exists, Crack-Seg decision complete.
- ~~I2 Provenance register and checksum/licence inventory~~ — `data_manifests/crack_seg_ultralytics_2025-08-21.json` plus the admission doc.
- `[~]` I3 Gate 0 output set: admission document ✓, contact sheet ✓, original-source manifests ✓, reviewed annotation set ✗, supported feature-size range ✗, chips/gaps go/no-go ✗.
- ~~I4 Minimal software tests worth keeping (coordinate-transform direction/units, resizing scale updates, polygon area, density denominator, border counting, ignored-pixel handling, null-vs-zero, policy versions)~~ — **154 tests**, all passing (113 at the session start, 136 after the segmentation slice, 154 after the quality gate; see `docs/ml/changelog.md` 2026-10-16).
- `[ ]` I5 Annotation guide and independent review records.
- `[~]` I6 Frozen split manifests including original/duplicate lineage. Builder/validator complete (`training/group_splits.py`), but no real-data frozen manifest generated and no independence claim.
- `[ ]` I7 Camera feasibility and calibration report with the actual operating envelope.
- `[ ]` I8 Feature specification (minimum resolvable sizes, denominator rules, null behaviour).
- `[ ]` I9 Model cards with data ancestry, seeds, weight/config hashes and failure examples.
- `[ ]` I10 Reference/scoring specification with the development procedure and final thresholds.
- `[ ]` I11 Validation report separating foreign development, public Indian evaluation and live Indian acceptance.
- `[ ]` I12 Group-held-out **public aggregate** results and **Indian distress** results.
- `[ ]` I13 Human score agreement/calibration, or an explicitly provisional index.
- `[!]` I14 **Independent Indian live-camera acceptance** once access exists.
- `[~]` I15 Report count/gap errors and intervals **by independent parent/site**, plus rejection/unknown coverage. **Reporting software verified:** `eval/measurement_eval.py` reports per-group MAE/bias, median/p95 absolute/relative errors, zero-truth denominators, suppression reasons/fractions, and group-bootstrap intervals only with ≥10 supporting explicit groups. `reports/ml/measurement_metric_checks.json` is synthetic software validation only. Real human count/gap/physical error measurements remain open.
- ~~I16b Fixed real-mask baseline floor~~ — `eval/distress_baselines.py` evaluated all 100 CRKWH100 raster GT masks and verified stored hashes: foreground 0.357479%; always-background pooled Dice 0, always-foreground pooled Dice 0.007124. Report `reports/ml/crkhw100_trivial_baselines.json`. No negative frames, hence false-alarm rate unknown; no trained model evaluated or test thresholds tuned.
- ~~I16a Defensible distress metric-reporting software~~ — **verified 2026-10-16:** `eval/distress_eval.py` and `eval/group_metrics.py` expose pooled TP/FP/FN/TN and micro IoU/precision/recall/Dice, GT-positive-only Dice, negative-frame false-alarm and positive-frame miss denominators, explicit group results and guarded 95% group-bootstrap intervals. Empty manifests fail. `reports/ml/distress_metric_checks.json` is deterministic synthetic software validation, not road accuracy. Existing macro metrics retained for compatibility.
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
- ~~J7 Unit-test the `eval/dataset_audit.py` helpers~~ - **closed 2026-10-16.** `tests/ml/test_dataset_audit.py`, 26 passing tests covering polygon parsing (valid, multi-class, empty-as-valid-negative, unparsable, too-few-points, out-of-range), stroke-width measurement (fat rectangle vs collapsed centreline, degenerate skips), dHash determinism, and the label-geometry classification. The audit helpers are now regression-protected.
- ~~J8 Confirm whether the locally implemented `skeletonize_2d` is preferred over adding the absent `scikit-image` (D6)~~ - **resolved 2026-10-16.** `scikit-image` 0.26.0 is now present and `test_skeletonize_matches_scikit_image_exactly` cross-validates the local implementation exactly, and passes. Decision: **keep the local implementation** as the production path; scikit-image is the cross-validation oracle in tests only. A runtime dependency for an already-validated function costs more than it gains.

---

## User actions and blockers

Owned by the ML role (`docs/ML_ROLE.md` §1). These require human judgement, access, licensing decisions, hardware or authority over files outside ML ownership. The priority table below governs ordering. D8 is resolved; rights do not resolve scale or the two-person review.

The 2026-10-16 update supplied the fillable numbered 10-patch sheet and CSV template; human review can proceed without another agent artifact. Dependency versions and absence claims in the original request are historical: J8 records scikit-image 0.26.0 as present, retained only as a test oracle; the local skeletonizer remains the production path. Approval/ownership for the learned challenger dependency remains open.

### 1. `A1.6` — Is the CRKWH100 512×512 a crop or a resize? **BLOCKING EVERYTHING METRIC**

**Why it blocks:** all 100 delivered images are exactly 512×512. The DeepCrack
repo claims a 1 mm/pixel ground sampling distance. A **crop preserves scale**; a
**resize destroys it**. I cannot tell which happened from the files.

- If it is a crop → the scale may be usable and every metric measurement (count/m²,
  chip diameter in mm, gap width in mm) becomes possible.
- If it is a resize → there is **no mm/px at all** for this source, and all metric
  output must stay `null` forever. Gate 0's chip/gap feasibility question would
  then rest entirely on ISTD-PDS7 (item 8).

**What I need you to do — any one of these:**

1. Tell me how you produced the OneDrive zip (was it the raw author files, or did
   something re-export them at 512×512?).
2. Ask the DeepCrack author, Dr. Qin Zou (`qzou@whu.edu.cn`, listed in the repo
   README), what the original CRKWH100 frame dimensions are and whether the
   distributed files were resized.
3. Point me at the original paper's dataset table if you can access it, and I will
   extract the stated native resolution myself.

**After you answer:** I will either propagate the verified scale through the files
and publish metric features, or mark this source `unscaled` permanently and
re-scope the chip task. Either way I stop hedging.

---

### 2. `D8` - The DeepCrack licence - **RESOLVED 2026-10-15**

**Status: closed. No action needed from you.**

The question existed because the repository states no licence at all - GitHub's
`license` field is `null`, the README "Copy Right" section is the single sentence
*"This dataset was collected for academic research"*, and a third-party mirror
labels the same data CC BY 4.0. None of that resolved cleanly from public
information.

**Resolution: permission granted by the dataset's originating author.** Dr. Qin
Zou, who produced CRKWH100, is the supervising professor on this solo project and
has granted permission directly. This is the strongest available provenance -
stronger than any repository licence, and it settles the mirror discrepancy
entirely, since permission from the owner overrides whatever a third party claims.

#### Recorded

| Field | Value |
|---|---|
| `rights_status` | `granted_by_author` |
| Basis | Direct permission from the originating author / supervisor |
| Scope | Solo academic project: manual annotation of exposed aggregate, texture-measurement development and validation, non-commercial |
| Redistribution | Not granted unless stated otherwise - **do not redistribute the images** |
| Attribution | Required; see `attribution_text` in the audit JSON |
| Written into | `reports/ml/crkhw100_audit.json` under `rights` |
| Written proof | `AUTHOR_GRANT_PENDING_FILE` - save the grant (email/letter) here when convenient |

#### What this does **not** resolve

1. **A1.6 stays open.** Author permission settles *rights*, not *scale*. Whether
   the delivered 512x512 files are crops or resizes is still undetermined, so
   `scale_source` remains `unverified` and **no mm value from CRKWH100 may be
   published yet**. Being able to ask the author directly is a genuine advantage:
   this is now a short question to your own supervisor rather than an open risk.
2. **Gate 0's two-human review still needs two people.** That is a separate
   requirement from licensing and remains outstanding.

Note: Crack-Seg remains scoped *internal use only, no redistribution* by your
earlier decision, so that one was already closed.

---
### 3. `A2.2` + `A2.3` — The human visibility review **BLOCKING THE GATE 0 VERDICT**

**Why it blocks:** final plan §5.1 requires *two people, independently, at native
resolution* to decide whether separate chips and boundary gaps are *visible*, and
then to double-label 10 patches with **no model suggestions**. No script can do
this, and I will not generate pseudo-labels and call the requirement met.

**Open this file:**

```
reports/ml/crkhw100_contact_sheet.png
```
20 native-resolution 256 px crops (never resized). The scale bar is drawn in
**pixels only (10 px)** — there is deliberately **no mm bar**, because the
1 mm/px figure is the publisher's claim only and is not verified for this
delivery (see A1.6, crop-vs-resize undetermined). The caption strip states this.
Judge chip visibility on what you can see, not on any assumed physical scale.

**Then answer three questions per patch:**

1. Can you distinguish **separate chips** (individual exposed aggregate particles)?
2. Can you locate the **boundary gap** between two adjacent chips?
3. Does zooming in **resolve** the ambiguity, or merely **magnify** it?

**Then, to double-label 10 patches, use the two fillable files:**

```
reports/ml/crkhw100_annotation_patches.png                  10 numbered native 256 px patches
annotation_guides/aggregate_patch_annotation_template.csv   one row per patch per annotator
```

The patches are native crops, never resized, and carry **no model overlay** -
final plan section 6.3 requires the unaided pilot to come before any model
proposal. Both annotators label the **same** patches (the placement is seeded and
reproducible), each working alone and without seeing the other's rows.

Per patch, fill in:

- `chip_visible` — `yes` / `no` / `unsure`
- `chip_count` — your count of separate chips you can actually see
- `gap_visible` — `yes` / `no` / `unsure`
- `gap_endpoint_a_xy`, `gap_endpoint_b_xy` — this patch's `x,y` pixel coordinates
  of the first clear gap (the sheet gives each patch its `top`/`left` origin, so
  patch-local coordinates are fine as long as you say so in `notes`)
- `zoom_effect` — `resolves` or `magnifies`
- `notes` — anything ambiguous, including "cannot separate these at all"

That gives me the human disagreement floor, which is what the model error gets
compared against.

**If the answer is "no, chips are not distinguishable":** that is a valid and
useful result. It means the chip-count requirement needs better imagery, and Gate 0
returns a `no-go` for chips. I need that answer rather than silence.

---

### 4. `D3` — The judge's exact definitions

**Why it blocks:** `TASKS.md` marks the chip-boundary-width and roughness feature
definitions provisional until the judge confirms them (final plan §18).

**What I need:** ask the judge/team liaison:

1. Does **"chip boundary width"** mean the visible gap between adjacent chips, the
   binder film thickness, or the width of every dark region? These are different
   measurements and only the first is measurable from RGB.
2. Does **"roughness"** mean a physical depth/texture metric, or an image-derived
   texture proxy? The plan forbids claiming physical MTD/MPD from ordinary RGB.
3. Is **moving capture** mandatory, and at what minimum speed? A stationary live
   feed proves ingestion, not moving inspection.
4. Is **sensor-assisted inclination** (a calibrated phone level on a straightedge)
   acceptable, or is continuous automatic slope measurement required?

**After you answer:** I finalise the feature specification (`H1`) and stop carrying
provisional definitions.

---

### 5. `C8` — Camera access

**Why it blocks:** the live requirement cannot be met by replay, and live
calibration (intrinsics, distortion, road-plane mapping) needs the actual device.
Final plan §5.2: *"No camera access means live functionality is blocked."*

**What I need:** one camera, computer connectivity, a rigid mount, a measured
target (a physically measured checkerboard), and a safe test location — via the
college robotics/CV/civil lab, a faculty project, a controllable phone, or a loan.

**Do not buy a specific model yet.** I will test a sample feed first and report
native dimensions, focus, working distance, field of view, exposure control, live
output and stability before anything is purchased.

---

### 6. `D4` — Approve ML-side dependencies

**Why it blocks:** the learned aggregate challenger needs
`segmentation-models-pytorch`; the original request also recorded `scikit-image` as absent (worked around it
with a local `skeletonize_2d`, decision `D6`; later resolved in J8).

**Historical environment snapshot (see J8 and the section introduction for the later scikit-image resolution):** numpy 2.4.3, opencv 5.0.0, scipy 1.17.0, scikit-learn 1.8.0,
torch 2.14.0+**cpu**, pytest 9.0.2, Python 3.14.0.

**What I need:** approve the dependencies **and** who adds them.
`backend/requirements.txt` and `pyproject.toml` are **not mine to edit**, so either
you change them or you tell me to write a proposal in `docs/ml/` for the backend
owner.

---

### 7. RDD2022 India subset — **OBTAINED; ADMISSION STILL CRITICAL**

**Current update:** archive obtained and all Indian images decoded; A1.8 is complete. Remaining actions are rights verification, human overlay/negative review, grouped splits and actual-width masks (A1.8a). The acquisition instructions below are historical provenance pointers, not a request to download the 14 GB archive again. Test annotations are empty/unpublished and cannot support false-alarm measurement.

**Priority:** HIGHEST after A1.6 — blocks every Indian distress claim

**Why it matters:** The final_plan §4.2 explicitly designates this as the **primary
Indian distress source**. Every distress-engine claim about Indian roads depends on
this dataset. Without it, we have no Indian validation data at all.

**What it is:**
- Part of RDD2022 full release: 47,420 images across 6 countries
- India subset contains images with longitudinal/transverse/alligator cracks and potholes
- Ships with bounding boxes (YOLO format)
- Precise segmentation requires manually adding masks to selected subset
- Paper: https://arxiv.org/abs/2209.08538
- Official repo: https://github.com/sekilab/RoadDamageDetector

**What I need:**
1. Open the RDD2022 repository and download the **India subset only**
2. Place files at `data/external/rdd2022_india/`
3. Report the actual size and image count you received

**Important notes:**
- Audit actual class IDs and splits; do not combine RDD2020/2022 without checking
- Freeze an Indian test subset before any annotation-driven training
- Boxes are not pixel masks — we'll need to manually segment a selected subset

---

### 8. ISTD-PDS7 — **ONLY PUBLIC SCALED AGGREGATE CANDIDATE (CRITICAL)**

**Priority:** HIGHEST — if A1.6 resolves against CRKWH100, this becomes the entire chip task

**Why it matters:** The final_plan §4.2 designates this as the **first public-data
candidate for scaled aggregate feasibility**. It has 18,527 images documented at
**0.91 mm/pixel** — the only public source with verified scale that could answer the
chip/gap question. If A1.6 determines CRKWH100 was resized (no scale), then ISTD-PDS7
becomes **the entire chip task**.

**Status:** not requested. Access is **by request only**.

**What it is:**
- 18,527 images, original CCD imagery at 0.91 mm/pixel
- Has distress labels (not chip labels — we create those with human annotation)
- Must verify scale propagation through any crops/resizing
- Must confirm data-use terms and parent IDs
- Paper: https://www.mdpi.com/2072-4292/15/7/1750

**What I need:**
1. You or a faculty contact sends the access request via the MDPI paper
2. When access is granted, verify delivered files match the documented 0.91 mm/pixel
3. Inspect original scale-preserving files and asphalt subset
4. Place at `data/external/istd_pds7/`

**After access:** We'll need to create human chip annotations on selected patches.

---

### 9. Indian Seasonal Paved/Unpaved Dataset — **INDIAN ROBUSTNESS/CHALLENGE SET (CRITICAL)**

**Priority:** HIGH — required for wet/unsupported-surface validation

**Why it matters:** The final_plan §4.2 designates this as the **Indian robustness/challenge set**, specifically for testing wet appearance and unsupported surfaces. This addresses conditions that foreign datasets cannot represent.

**What it is:**
- 4,242 Nashik/Mumbai original images plus rotated versions and video
- Captures seasonal variations, wet surfaces, unpaved roads
- Must group rotations, resized copies and video siblings (not independent samples)
- No assumed metric scale, chip labels, GPS track, or certified condition score
- Paper: https://pmc.ncbi.nlm.nih.gov/articles/PMC8933537/
- Dataset: https://data.mendeley.com/datasets/tj2m7zz4rg/2

**What I need:**
1. Download from the Mendeley link above
2. Place at `data/external/indian_seasonal/`
3. Keep the original folder structure
4. Report the actual size

**After download:** We'll group rotated/augmented versions and video frames to avoid treating them as independent roads.

---

### 10. `D4`/`H6` — Config files and a contract, when you are ready

Not blocking today, listed so it is not a surprise later:

- `configs/camera/`, `configs/features/`, `configs/scoring/` are **empty**; my
  measurement config currently exists only as Python dataclasses (`H6`).
- The backend owns the Pydantic/OpenAPI contract. I need to hand over field names,
  units, null reasons and version identifiers (`H2`) before the frontend can consume
  real results.

---

### 11. Colab — I will ask before you spend compute

Not needed yet. The learned challenger (`E4`) is gated behind Gate 0, because
training on unverified-scale, un-annotated data would produce numbers that mean
nothing. **When we get there I will tell you the expected runtime, the dataset
size and the GPU class before you start anything.**

---

### Priority order — smallest set to unblock the most

**Current priority order (corrected to match final_plan.md; supersedes the older per-item priority wording above):**

| Priority | Item | Effort for you | Blocks |
|---|---|---|---|
| 1 | **RDD2022 India subset** (item 7) | Browser download | Every Indian distress claim |
| 2 | **ISTD-PDS7 access** (item 8) | One email to authors | Scaled aggregate work (if A1.6 fails) |
| 3 | **Indian seasonal dataset** (item 9) | Browser download | Wet/unsupported-surface validation |
| 4 | `A1.6` crop-vs-resize | One email to Dr. Zou | All CRKWH100 metric output |
| 5 | `A2.2`/`A2.3` two-human review | ~1 hour, two people | Gate 0 verdict |
| 6 | `D3` judge definitions | One conversation | Feature specification finalization |
| 7 | `C8` camera access | Lab conversation | Live validation |
| 8 | `D4` dependencies | One approval | Learned model training |

**Critical realization:** Items 1-3 are **core datasets** the plan requires but we don't have yet. These should have been priority 1 from the start.

## Implementation review

Review date: 2026-10-16. The fixes and validation below record the implementation review, not a new run during documentation consolidation.

### Scope and project context

Reviewed repository Markdown documentation, including `final_plan.md`, `ML_ROLE.md` and all `docs/ml/` notes, and audited implemented ML measurements, data auditing, quality checks, evaluation and training/inference utilities. Preserved pre-existing work and restricted fixes to ML-owned paths.

The objective is evidence-backed road surface assessment: quality and metric geometry gates → aggregate/distress measurements → supported known-good comparison → human-calibrated condition assessment. Inclination is separate. Public foreign imagery is provisional evidence, not Indian-road or live-camera acceptance. Missing evidence must not become a measured zero, a fabricated physical unit or a confident Good score.

Implemented foundations include scale/plane geometry, classical watershed/tiling, aggregate and distress feature extraction, provisional quality checks, data audits and evaluation utilities. `backend/reference/` and `backend/scoring/` remain placeholders; this review did not manufacture their missing training evidence.

### Corrected defects

#### Inference and distress evaluation

- Fixed inference writing into a temporary mask, which could leave all predictions empty. The cross-source evaluator now unions native-resolution model raster masks, retaining holes and branches instead of filling exterior polygons.
- Shared raster scoring between inference and manifest self-checks. Corrected `dice_p90` from the 10th to the 90th percentile; retained a separately named p10.
- Missing YOLO prediction files are now empty predictions against available ground truth, rather than omitted missed detections. Missing raster predictions fail explicitly rather than shrinking the evaluation cohort.
- Raster ground-truth extent/negative metadata now comes from actual masks rather than assumed manifest summaries.
- Dataset preparation rejects missing masks and image/mask size mismatches.
- Crack skeleton physical lengths apply x/y scale to each adjacency displacement, rather than an equal-area isotropic approximation. Distress feature method version is `distress-v2`.
- Corrected training guidance about development/test separation and what segmentation metrics establish. Training no longer explicitly permits overwriting an existing run.

#### Aggregate measurements and evaluation

- Particle sizes now respect the requested centroid counting ROI while using the selected instance's full area.
- Physical gap lengths and provisional gap annotations now transform x/y displacements separately. Example: an 11 px horizontal separation at sx=2, sy=1 mm/px is 22 mm, not approximately 15.56 mm.
- Ignored/distress areas are restricted to observed surface. Gap resolution uses a conservative anisotropic limit.
- Instance evaluation handles sparse IDs, applies ignore masks to instance/count metrics and disallows zero-overlap matches. Matching maximizes valid matches rather than using greedy IoU selection.
- Homographies are normalized before determinant-based singularity checks, avoiding rejection solely because an otherwise equivalent matrix has a small scalar multiplier.
- Corrected equal-area scale documentation: it is appropriate for area-derived diameters, not arbitrary directional lengths.

#### Data audit and quality

- Audits reject nonfinite coordinates and invalid classes, detect nested orphan labels, inspect labels even for corrupt images, avoid perceptual matching on failed decodes, preserve pair indices and avoid treating malformed polygons as genuine negatives.
- Duplicate Hamming comparisons work with NumPy 1.x; contact-sheet output failures/truncation and invalid inputs are checked and provenance describes actual rendered files.
- Quality batch discovery excludes directories, supports WebP, preserves source channels/bit depth and distinguishes repeated basenames by relative path.
- Quality preprocessing no longer averages alpha into surface brightness. Integer bit depths are mapped to a fixed 0–255 intensity range before sharpness/contrast checks, without per-image contrast stretching. Nonfinite image inputs are rejected and nonfinite sharpness thresholds are invalid.
- Quality policy is now `quality-v2`; old quality reports remain historical and have not been silently regenerated.
- Removed a duplicate test definition and stray copied assertions in the dataset audit tests.

### Metrics: what is actually supported

Existing saved evidence includes:

| Report | Interpretation |
|---|---|
| `reports/ml/synthetic_f1_separated.json` | Synthetic instance F1 1.000 |
| `reports/ml/synthetic_f1_touching.json` | Synthetic instance F1 approximately 0.877 |
| `reports/ml/synthetic_f1_merged.json` | No valid instance accuracy claim for indistinguishable merged geometry |
| `reports/ml/marker_sweep.json` | Historical selected synthetic holdout instance F1 approximately 0.839 |
| `reports/ml/crkhw100_real_eval.json` | Real-image descriptive diagnostics/determinism, not chip accuracy |
| `reports/ml/crkhw100_quality_gate.json` | Historical provisional quality report; all 100 lack verified scale |

These saved reports predate this review and were not regenerated or presented as post-fix accuracy. No saved trained-distress/cross-source, Indian-road or live-camera accuracy result was found during review. No retraining or real-weight inference was performed. Consequently **there is no evidence-backed model-accuracy gain to claim**. Fixes improve correctness of measurements and the ability to assess performance honestly; scores may move up or down when reevaluated.

Do not tune against CRKWH100 and still call it untouched test evidence. If its failures inform model selection, thresholds or preprocessing, designate it development and obtain a fresh independently grouped test. Dataset names alone do not prove source independence. A GT-vs-GT self-check validates evaluator plumbing, not prediction accuracy.

### Remaining limitations and useful next steps

1. Confirm original-image/source ancestry and frozen group splits before training or claiming cross-source independence.
2. Obtain sufficient reviewed intact negatives and Indian distress masks. An all-positive or nearly all-positive set cannot establish false-alarm behavior.
3. Run the training/inference package with actual weights and save run manifests, versions, weight/config hashes and per-sample predictions. Use development data for tuning, not final test.
4. Acquire independently reviewed chip/gap labels and verified scale before tuning the aggregate baseline to real particle counts. Thousands of texture-noise instances are not a validated chip measurement.
5. Complete rig calibration, operating-envelope validation, per-rig quality thresholds and live acceptance. Source-scale agreement is not physical calibration.
6. Implement reference/scoring only with supported-domain, known-good and condition-rating evidence; no arbitrary weights or Good/Bad bands.
7. The existing polygon rasterization parser can silently skip malformed rows; run the stricter dataset audit before evaluation. Legacy YOLO directory evaluation also has a 416×416 fallback when paired imagery is absent, so supply actual images for trustworthy geometry. Its best-overlap instance diagnostic is not one-to-one instance AP/F1.
8. Existing Markdown notes contain historical contradictions (for example training/validation-folding claims and stronger source-independence language). Actual scripts and this review's caveats should govern use; the final plan remains authoritative.

### Validation

- `python -B -m pytest tests/ml -q -p no:cacheprovider`: **287 passed**, 8 expected provisional-annotation warnings.
- `python -B -m pytest -q -p no:cacheprovider`: **355 passed**, 9 warnings.
- `git diff --check`: no whitespace errors; Git emitted Windows line-ending conversion notices.
- Added focused regression files for aggregate, distress, audit and quality fixes. Tests validate software arithmetic/control flow and mocked inference, not road-domain accuracy or independent physical measurement.

No model download, cloud training or paid service invocation was performed. No commits were created.
