# Ghost-Rider — ML Role Changelog

Historical record of ML implementation, runs, decisions and defects; not a live
status tracker. Authority: `../final_plan.md`; ownership: `../ML_ROLE.md` and
`../PROJECT_SKELETON_SETUP.md`. Scope includes ML backend modules, training,
evaluation, manifests, annotation guides, ML configs, tests and reports.

## Current navigation

- [TASKS.md](TASKS.md): task status, user actions and implementation review.
- [DATA_ADMISSION.md](DATA_ADMISSION.md): dataset acquisition, provenance,
  permissions, visibility evidence and admission decisions.
- This file: standalone history and experimental evidence.

The former `NEEDED_FROM_USER.md` and `IMPLEMENTATION_REVIEW.md` now belong in
`TASKS.md`; the former `DATASET_PLAN.md` and `CHIP_VISIBILITY_EVIDENCE.md` now
belong in `DATA_ADMISSION.md`. Old names below identify historical artifacts,
not current navigation. Paths outside this directory are repository-relative.

## Recording conventions and environment

Record work after it happens, including failed/aborted runs. Keep evidence and
limitations; unavailable measurements are `null`, never measured zero. Statuses:
`verified` (observed execution), `implemented-unverified`, `blocked`, `failed`,
`deferred`. A historical passing run is not a claim about today's suite. Shared
contracts, dependencies, units and scientific meanings require owner review.
Temporary diagnostic scripts are deleted after use; lasting checks belong in tests.

Initial baseline, observed 2026-10-15 via version/import commands:

| Component | Recorded value |
|---|---|
| Platform | win32, Git Bash |
| Python | 3.14.0 |
| NumPy / OpenCV | 2.4.3 / 5.0.0 |
| SciPy / scikit-learn | 1.17.0 / 1.8.0 |
| PyTorch | 2.14.0+cpu; no local CUDA |
| pytest | 9.0.2 |
| scikit-image / segmentation-models-pytorch | Both initially absent (`ModuleNotFoundError`) |

The plan assumes Python 3.11 where compatible; Colab was designated for training.
Local CPU work covers classical CV, geometry, tests and evaluation. Backend-owned
`backend/requirements.txt` was not changed by the ML role. Later scikit-image
installation is recorded below, not retroactively applied to this baseline.

## History

Dates are chronological; same-day entries follow the original recorded milestone
sequence, not independently established timestamps.

### 2026-10-15 — Changelog and synthetic measurement core established

The log was created after actual environment checks; it established no dataset or
model-quality claim. The user chose measurement core plus tests as the first slice,
and CRKWH100 as the first scale-documented candidate, with ISTD-PDS7/GAPs fallbacks.

Implemented `backend/geometry/{scale,plane}.py` and
`backend/aggregate/{segmentation,features,measurement}.py`: explicit `PlanarScale`
lineage; valid-pixel area × sx × sy / 1e6; crop/resize handling; area uncertainty;
plane homography `H = K[r1 r2 t]`; local mm/px from Jacobian singular values;
watershed instances, density, coverage, medial-axis gaps and versioned JSON.

A background-flood defect first caused four test failures: a radius-12 disk had
293 px² instead of 441 (34% shortfall), diameter 19.31 rather than 24 px. In a
25×25 window labels were `{-1: 56, 1: 276, 2: 293}`; background marker 1 stole
92 particle pixels. Negated-distance watershed without a background marker fixed
the cause; clipping foreground alone could not recover mislabeled pixels.

Evidence after repair:

- `python -m pytest tests/ml -q`: **92 passed in 3.36s**; full rerun also 92 passed.
- `python -m compileall -q backend/geometry backend/aggregate`: passed; package
  imports exposed 13 geometry and 15 aggregate public names.
- Deleted temporary accuracy script: four radius-12 disks each measured 441 px²
  (+0.0%); equivalent diameter 23.70 versus 24.0 px (−1.25%). Two bars separated
  by 11 facing-pixel centres gave median gap 11.0 px / 5.5 mm, 190 sites,
  IQR 0.0 mm.
- Tests distinguish unscaled `None` from measured `0.0`; `require_scaled()`
  raises `UnscaledError`. Downsampling by two doubles mm/px and preserves area.
  A 1.5 m down-looking camera at f=1000 px gives 1.5 mm/px at the principal point.
- One isolated particle produces no gap sites; sub-`min_gap_px` gaps are omitted.
  Distress does not remove itself from the denominator. ROI selection uses
  centroids; records, including unscaled ones, serialize to JSON.

Limitations: synthetic arithmetic/plumbing only, not pavement accuracy. Gaps need
opposing boundaries from different instances, so merged-instance internal gaps are
missed; pixel-centre separation includes boundary pixels. Watershed ridge pixels
remain unassigned. Learned models, quality gate, reference and scoring were absent.

The six fixture/test modules were then consolidated into
`tests/ml/test_measurement_core.py`, retaining `tests/ml/conftest.py` for imports.
`set -o pipefail; python -m pytest tests -q`: **92 passed**, exit 0. Explicit pytest
status replaced earlier piped-output status ambiguity; no tests were dropped.

### 2026-10-15 — Crack-Seg audited and conditionally admitted

Origin: [Ultralytics release](https://github.com/ultralytics/assets/releases/download/v0.0.0/crack-seg.zip).
HTTP 200; archive **96,089,865 bytes (91.64 MiB)**; SHA-256
`814b566d61e890024d15f22a3e6b14e252f781ab83f60a8d59e6684817efecdc`.
Raw data: `data/external/crack-seg/` (gitignored, uncommitted). Committed record:
`data_manifests/crack_seg_ultralytics_2025-08-21.json`.

Added `eval/dataset_audit.py`. Run:
`python -m eval.dataset_audit --path data/external/crack-seg --name "crack-seg" --out reports/ml/crack_seg_audit.json`
returned exit 0.

| Audit evidence | Result |
|---|---|
| Images / decode failures | 4,029 / 0; all 416×416 RGB |
| Train / val / test | 3,717 / 200 / 112 |
| Labels / pairing problems | 4,029 / 0; one empty label retained as possible negative |
| Geometry | 5,290 polygons, 667,295 points, mean 126.1 points; class `0: crack`; no out-of-range coordinates |
| Sampled width (400 images) | Median 8.94 px; p10 4.62, p90 16.69; real-width outlines, not centrelines |
| Parent prefixes | 1,549; none span splits |
| Exact duplicates | One pair, both in test: only 111 unique test images |
| Cross-split dHash candidates | 18 at distance ≤6; all rejected by pixel correlation, zero confirmed |

Decision: `ADMIT_CONDITIONAL`, the **single** crack-mask backup allowed by plan
§4.3: internal non-metric, non-Indian method development only. No chip/gap or
known-good-reference use. Uniform resized exports have unknown ancestry/scale;
metric outputs must be null. Public Domain documentation conflicts with an
AGPL-3.0 YAML header; upstream attribution/licences are untraceable.

The user explicitly approved `data/` storage (`keep data/`) and **internal use
only, no redistribution**, not citation as an admitted public source. This scoped
ancestry risk rather than removing it. The manifest recorded the decisions and
still parsed as JSON. `ML_ROLE.md` had zero literal `data/` occurrences, so storage
permission was not assumed. Audit helpers were then exercised on real data but
not yet unit-tested (closed on 2026-10-16).

### 2026-10-15 — Tracker and DeepCrack download selection

`TASKS.md` was derived from `ML_ROLE.md` and `final_plan.md`, grouping obligations
A–J with source citations and evidence-backed statuses. Content review, not an
execution result; a tracker is not proof and can go stale.

A user screenshot confirmed the shared OneDrive parent contained exactly
`CrackLS315`, `CRKWH100`, `Stone331`, `Stone331_mask`; no separate CRKWH100 GT
folder or CrackTree260. Folder sizes were unknown until download. Selection:
CRKWH100 for the pilot; CrackLS315 optional for visibility only (laser imagery
cannot anchor appearance reference); exclude cut-stone Stone331 and redundant
CrackTree260 because Crack-Seg already occupies the backup slot.

### 2026-10-15 — CRKWH100 audit and first real-image pilot failed to transfer

`CRKWH100.zip`: **26,533,247 bytes (25.30 MiB)**; SHA-256
`e6da26f7546897662573ffe9d9a7c11a867b68b5f9e389afe06faae7a042889b`.
Stored at `data/external/deepcrack/CRKWH100/images/`, gitignored. Audit exit 0:
100 RGB images, all 512×512, zero decode failures/exact duplicates, no split
folders (`unknown: 100`), no GT shipped (100 missing labels, zero orphan labels).
`reports/ml/crkhw100_audit.json` and a 20-tile native-resolution 256 px centre-crop
contact sheet were generated. Initial sheet: 1280×1024, approximately 2.5 MB.

Pilot on 12 real images using the **unverified publisher claim** of 1 mm/px:

| Polarity | Instances/image | Then-reported equivalent diameter | Coverage |
|---|---:|---:|---:|
| Brighter | 2,150 | 3.91 mm | 0.149 |
| Darker | 3,742 | 5.53 mm | 0.540 |

These historical mm outputs are **not publishable measurements**. Crop versus
resize of the delivered 512×512 files was unknown; `scale_source` remained
unverified. Counts showed pathological oversegmentation, not real chip counts.
The first polarity probe accidentally passed `None` config, producing identical
rows; it was discarded and rerun with the polarity actually applied.

Bottom/top 8-row adjacency correlation: median +0.020 versus random +0.006,
zero pairs above 0.8; recorded conclusion was independent rather than contiguous
frames. Gray mean averaged 91.4 (53.7–162.6), gray std 16.6; Laplacian variance
min/median/max 51/435/2,721. No human chips/gaps go/no-go existed.

### 2026-10-15 — Unverified physical scale removed from review artifact

The contact sheet incorrectly drew `10px = 10mm`. `eval/dataset_audit.py` changed
to a pixel-only `10 px` bar, caption “scale UNVERIFIED: 1 mm/px is the publisher
claim only”, `claimed_mm_per_px`, and `scale_verified: false`.
Both `--skip-audit` and combined audit/sheet paths passed (CONTACT_EXIT=0,
COMBINED_PATH_EXIT=0, REPORT_ASSERT_STATUS=0). PNG verification passed:
1054×1280×3, body mean 96.4/std 31.9/range 0–255, zero blank tiles out of 20.
No key could imply verified scale. Only 512×512 sources/256 px tiles were tested.

### 2026-10-15 — Public licence investigation, then direct author permission

Checked [qinnzou/DeepCrack](https://github.com/qinnzou/DeepCrack) and GitHub API:
`license: null`, `mirror_url: null`; README copyright statement only “This
dataset was collected for academic research.” Contact: Dr. Qin Zou,
`qzou@whu.edu.cn`; repository then had 366 stars, 79 forks, last push 2023-10-29.
A third-party CC BY 4.0 assertion could not establish rights. IEEE is the
publication venue, not the data-rights grantor. Zou/TIP 2019 must not be confused
with Liu/Neurocomputing 2019, also called DeepCrack.

The former `NEEDED_FROM_USER.md` (current location: `TASKS.md`) was corrected:
it had described the removed mm bar and overstated licensing as blocking a pilot
already executed. Rights gated publishable claims, not internal development.
The audit then lacked a rights field, so it was not yet an admission record.
A malformed changelog heading/encoding write was repaired: 10 date entries,
15 em-dashes, zero replacement characters/mojibake; unintended UTF-8 BOM removed.

Subsequently, the user reported direct permission from originating author and
supervisor Dr. Qin Zou. Licence decision **D8** closed; A1.7 closed. The audit's
new rights block recorded:

- `rights_status: granted_by_author`; solo academic, non-commercial project;
  manual aggregate annotation and texture-measurement development/validation.
- Attribution required, citation embedded; redistribution **not granted/unstated**.
- `permission_artifact: AUTHOR_GRANT_PENDING_FILE`: written artifact still absent.

This did not verify scale or replace two-human review. Two failed literal tracker
edits were traced to U+2014 em-dash versus U+002D hyphen; dash-agnostic matching
fixed them. Historical “D8” was overloaded between this licence decision and the
separate distress-feature task; task context distinguishes them.

### 2026-10-16 — User-action list and first aggregate evaluation harness

The former `NEEDED_FROM_USER.md` (now `TASKS.md`) collected human review, scale,
judge definitions, camera/dependency access, gated datasets and approval before
Colab spending. It was a request list, not completion evidence.

Added `eval/aggregate_eval.py` and `tests/ml/test_eval_metrics.py` for pixel
precision/recall/F1/IoU/Dice, greedy instance IoU matching and count errors.
`python -m pytest tests -q`: **113 passed**, exit 0. Twelve synthetic cases per
scenario and 100 real images ran successfully; real determinism had zero mismatches.

A test incorrectly expected a 50/50 split to miss at IoU 0.5 (equality qualifies);
it was replaced by 60/144 overlap (0.417) plus an explicit threshold-boundary test.
Missing median precision/recall aggregation was also repaired. Initial uniform /
touching instance F1 **0.508 / 0.183** were later superseded by fixture repairs;
those reports were removed to prevent reuse. Separated F1 **1.000** was unaffected.
No real-image F1 existed without annotations.

### 2026-10-16 — Baseline/fixture defects repaired; synthetic marker selection

Changed `backend/aggregate/segmentation.py`, `eval/aggregate_eval.py` and review
artifact helpers. `python -m pytest tests -q`: **136 passed**, exit 0 (23 added).
Eight new fixture/min-area/hole-fill tests failed before implementation; one
captured failure was an unexpected `min_instance_area_px` keyword. Patch-selection
test and implementation were written together: no red state observed for that helper.

Distinct defects and evidence:

- **Unanswerable fixture:** identical-intensity touching chips hid true boundaries.
  Seed 3: chip 46 had only 6 px area but distance-transform maximum 23.2 px;
  26/53 chips had no marker. F1 0.148 measured fixture unfairness. `touching` now
  has visible binder seams (contrast 135 gray levels); deliberately `merged`
  truth is `ignore`, `instance_gt_resolvable: false`, instance scores null.
- **Morphological close erased seams:** Otsu preserved all seam pixels, giving
  61 components for 60 chips; 3×3 close flipped 903/1,380 seam pixels and reduced
  components to 21. Same-case F1 was 0.228 with close versus 0.700 without.
  Replaced with enclosed-hole filling, default max 16 px², constrained below the
  declared minimum particle area.
- **Greedy NMS over-seeded plateaus:** a uniform 20×120 bar became 26 fragments;
  relative h-maxima produced one. Marker depth uses each component's peak.
- **New implementation too slow:** per-component/per-hole loops timed out at
  600 s. Vectorized `ndi.maximum`, `ndi.maximum_position`, `np.isin` reduced one
  real 512×512 image to 0.14 s and a synthetic case to 0.12 s; reports completed.

Marker sweep: training seeds 0–7, selection seeds 5000–5007, touching scenario.
NMS held-out median F1 **0.628**, count error +16; h=0.5 **0.839**, error −2.5.
h=0.9 reached 0.877 but was rejected as tending toward one particle per connected
region. Rule: smallest depth within 0.05 of best; tested on fabricated rows.
Reported cases used seeds 0–11, not the selection block.

Final `agg-classical-v2`, 12 cases each:

| Scenario | Instance F1 | Other evidence |
|---|---:|---|
| Separated | 1.000 | Pixel F1 1.000; count error 0; unchanged across h grid |
| Touching | 0.877 | Pixel F1 0.955; precision 0.887, recall 0.842; relative count error 0.051 |
| Merged | null | Unresolvable instances; pixel F1 0.991 |

Real CRKWH100 diagnostics remained **descriptive, unscored**. Medians over 100:

| Polarity | Minimum area px² | Instances | Median diameter px |
|---|---:|---:|---:|
| Brighter | 0 / 50 / 200 | 2,919.5 / 146.5 / 18 | 3.57 / 9.85 / 20.34 |
| Darker | 0 / 50 / 200 | 1,300.5 / 162 / 46 | 3.74 / 11.35 / 25.82 |

Synthetic reports carry `not_real_road_evidence: true`; circular-fixture h=0.5 is
not pavement validation. Minimum instance area still defaulted to zero; a real
limit needs verified scale and human labels. No CRKWH100 mm claim was enabled.

Generated unaided 10-patch sheet and
`annotation_guides/aggregate_patch_annotation_template.csv`: PNG 1306×512×3,
mean 93.0/std 33.2/range 0–255, zero blank tiles, no resize/model overlay.
Reports live under gitignored `reports/ml/` (`synthetic_f1_*`, `marker_sweep`,
`crkhw100_real_eval`, review sheets/metadata).

### 2026-10-16 — Dataset priorities corrected against plan authority

Content review against final plan §4.2 corrected understated blockers in tracker,
admission and the former user-action document (now `TASKS.md`):
RDD2022 India is the **primary Indian distress** source; ISTD-PDS7 the **only
public scaled aggregate candidate**; Indian seasonal imagery the **Indian
robustness/challenge** source. They became user-blocked A1.8/A1.9/A1.11, priority
1–2–3. Having Crack-Seg plus a small unverified-scale pilot did not replace them.
No datasets were obtained by this documentation change.

### 2026-10-16 — Provisional image-validity gate

Added `backend/quality/validity.py`, `eval/quality_gate.py`, 18 tests. Before
implementation the test import failed (exit 2); after it, full tests:
**154 passed**, exit 0. Real command:
`python -m eval.quality_gate --path data/external/deepcrack/CRKWH100/images --out reports/ml/crkhw100_quality_gate.json`.
Exit 0: **100 limited**, reasons `scale_missing: 100`, `low_dynamic_range: 10`;
**zero rejected**. `1000.png` Laplacian variance 2067.4 agreed with audit units.

Tests exposed unsupported OpenCV float32→CV_64F Laplacian conversion; sharpness
now uses 8-bit input. Four fixtures initially used 200 px images below a 256 px
minimum, testing resolution rather than intended sharpness/contrast; corrected.

`accepted`/`limited`/`rejected` and all simultaneous reasons are reported.
Missing scale means limited, `is_metric_evidence=false`, not automatic rejection.
`quality-v1` has `thresholds_calibrated=false` in policy and reports. Flat/glare/
sub-resolution rejection was synthetic only; the 40-level contrast floor was
provisional. No validated real rejection behaviour, rig envelope, Indian or live
frame claim; C11 requires per-rig labelled calibration.

### 2026-10-16 — Review-artifact metadata inconsistencies fixed

Regenerating a previously unverified contact-sheet path exposed shape-order and
return-key mismatches: contact metadata `[width,height]` contradicted decoded
1054×1280×3, while patches used HWC; writers returned `out_path` versus `path`.
Both now use `sheet_shape_hwc` and `out_path`. Two overlapping metadata files
were replaced by combined `reports/ml/sheet_meta.json`.

SHEET_VERIFY=0: contact 1054×1280×3, 20/20 nonblank; patches 1306×512×3, 10/10
nonblank; metadata matched decoded shapes, old keys absent, unverified captions
present, no mm-claim keys. Regenerated CSV was byte-identical. Full tests:
**154 passed**, exit 0. No measurement changed; human review remained outstanding.

### 2026-10-16 — Fixed-scale texture proxies (D7)

Added `texture_statistics`, `TextureStatistics`, `TEX_METHOD_VERSION` in
`backend/aggregate/features.py`: four-direction GLCM contrast/homogeneity/energy/
correlation (unitless), mean squared Sobel magnitude divided by pixel area
(1/mm²), and LBP uniform-pattern fraction (≤2 circular transitions, unitless).
Offsets are requested in mm through `PlanarScale`, not arbitrary pixel distances.

Twenty new tests; measurement module **122 passed**. Six equivalent-pixel-offset
comparisons across physical scales matched; color/gray, determinism and invalid
input checks passed. Corrections/limitations:

- Checkerboard Sobel energy is exactly **0.0000**, not high: 3×3 Sobel has a
  Nyquist null. `np.gradient` gave 255. Fine alternating texture can look smooth.
- Initial LBP circular Hamming-distance average inverted “uniformity”; corrected
  definition gives flat 1.0, checkerboard 0.0.
- `sin(x/4)` has period 8π (~25.1 px), not 4. Exact 4 px square-wave fixture
  gives quarter/half/three-quarter/full-period correlation 0/−1/0/+1.
- Physical offsets quantize to pixels; a 1 mm request at 2 mm/px is dropped,
  never invented by upsampling.

Concurrent `test_auto_annotation.py` imported missing `PROVISIONAL_CONFIDENCE`;
left other-role work untouched. At that point **171 passed excluding that file**,
not a clean full-suite claim. J7/J8 were still open then.

### 2026-10-16 — Native-resolution tiling and instance merging (E6/D9)

Added `backend/aggregate/tiling.py` (`segment_tiled`, `measure_tiled`,
`tile_windows`) and optional labels to `measure_surface`. Ten tiling tests.
Three defects repaired: tail-shift origins produced overlapping interior ROIs
(replaced by evenly spaced origins); a 15,313 px fragment absorbed legitimate
chips (require shared pixels ≥0.5 of smaller fragment); measurement discarded
stitched labels and re-segmented (now passes them through).

Pinning flatten sigma from tile 16.0 to whole-image 64.0 did **not** fix the
failure; retained for scale consistency, not credited as its cause. Actual issue:
Otsu on background-only tiles invented 13.6% foreground versus 0.5% whole-frame
foreground. Synthetic seven radius-12 disks (441 px each) centred on boundaries:

| Minimum area px² | 128/32 | 128/64 | 160/48 | 192/48 | 256/64 (tile/overlap px) |
|---|---:|---:|---:|---:|---:|
| 0 | 2073 | 2859 | 2612 | 2282 | 1049 |
| 20 | 104 | 126 | 122 | 97 | 50 |
| 40 | 9 | 9 | 9 | 9 | 9 |
| 60 | 7 | 7 | 7 | 7 | 7 |
| 100 | 7 | 7 | 7 | 7 | 7 |

Default zero therefore remained a documented cross-owner dependency, not silently
overridden. Deliberately disabling merge counted 20 instead of 7, showing the
test detects splitting. Tests also checked nonoverlapping interiors, equal origin
gaps, whole/tiled area/density agreement, null scale and degenerate shapes.
Concurrent segmentation work reported `agg-classical-v3`; `dataclasses.replace`
preserved newly added fields. Auto-annotation import failure remained unrelated.
E4/E5/E8 still needed reviewed labels; no real chip accuracy followed from tiling.

### 2026-10-16 — Distress measurements and evaluation (feature D8/I16)

Added `backend/distress/features.py`, `eval/distress_eval.py`, 20 feature tests:
`crack_skeleton_length_m`, `defect_extent_fraction`, `distress_metrics` and YOLO
polygon rasterizers. Skeleton length sums forward-neighbor step distances once:
20 diagonal steps equal `20*sqrt(2)/1000` m at 1 mm/px; naive pixel count is
70.7% of true length (~29% short). Evaluation CLI accepts labels and optional GT;
GT-vs-GT pixel IoU/precision/recall/Dice and instance IoU were **1.0**.

Crack-Seg test split, 112 images (not 112 unique), all distressed: extent
mean/median/p90/max **1.98% / 1.64% / 3.88% / 5.82%**; mean mask pixels **3,428**,
mean skeleton pixels **453**. Pixel-only output records unknown GSD in
`scale_note`. This was label measurement, not learned-model performance.

Only one empty label in all 4,029 images (**0.025%**), none in test: false-alarm
behaviour was unmeasurable. The then-proposed CRKWH100 GT download was expected
to help identify negatives; that expectation was disproved by the later audit.
Harness-before-training ordering retained; E4/E5/E8 had not run.

### 2026-10-16 — Acquisition plan and author-unreachable constraint

The former `DATASET_PLAN.md` (now `DATA_ADMISSION.md`) mapped named sources,
roles, acquisition paths and consumers in four tiers. User reported Dr. Zou
unreachable. Author verification of crop versus resize/native originals was
therefore recorded as unavailable; CRKWH100 scale stayed unverified, **no mm
publication**. This did not revoke the earlier reported permission grant.

The former `CHIP_VISIBILITY_EVIDENCE.md` (now `DATA_ADMISSION.md`) recorded chips
not resolvable in delivered files. The chip branch consequently depended on
request-gated **ISTD-PDS7 (0.91 mm/px)** or **GAPs (1.2 mm/px)**, with self-capture
also a later option. No supported calibrated Indian-road chip claim existed.
The plan's proposed negative-source benefit of CRKWH100 GT was historical, not
an observed result; all-positive GT was established in the next milestone.

Acquisition links recorded from the DeepCrack README:

- [Images/shared parent](https://1drv.ms/f/s!AittnGm6vRKLtylBkxVXw5arGn6R)
- [CRKWH100 GT](https://1drv.ms/u/s!AittnGm6vRKLglyfiCw_C6BDeFsP)
- [Baidu mirror](https://pan.baidu.com/s/1PWiBzoJlc8qC8ffZu2Vb8w), password `zfoo`

No download occurred during that documentation milestone. Earlier instructions
used an `/f/` GT link; the `/u/` link above was the later verbatim README record.

### 2026-10-16 — Raster GT admitted for cross-source test; E8 package prepared

Obtained 100 CRKWH100 BMP masks, 512×512, binary 0/255, paired pixel-exactly 1:1;
manifest `data/manifests/crkhw100_test.json`. Every image had crack GT: **zero
negatives**, disproving the acquisition plan's expectation. False alarms remained
unmeasurable with data in hand.

A BMP-to-YOLO-polygon conversion was rejected: **225,881** polygon pixels versus
**93,711** true crack pixels (**2.41×**), mean IoU **0.34**, 95/100 images lost
their crack entirely. External contours/fill of thin branched networks destroyed
raster information. Converter deleted; test GT and evaluation remain raster-space.
`eval/distress_eval.py --manifest` self-check returned pixel IoU/precision/recall/
Dice **1.0**, with `false_alarm_measurable: false` carried into reports.

Prepared, **not trained**:

- `training/train_distress_yoloseg.py`: YOLO polygon baseline, Crack-Seg train+val
  **3,917 images**; val folded into fitting because evaluation is cross-source
  CRKWH100, not the small in-distribution split. Test never used for fitting.
- `training/evaluate_crosssource.py`: raster scoring on the CRKWH100 manifest.
- `training/COLAB_E8.md`: setup, two-epoch smoke test, full run/evaluation/export,
  metric interpretation and caveats. User runs Colab; no model results claimed.

A U-Net/ResNet18 challenger per plan §8.1 should be retained only if it beats the
baseline on unseen parents. Cross-source labels permit a genuine different-source
test, not an Indian performance or negative-set claim.

J8 closed: scikit-image **0.26.0** became available;
`test_skeletonize_matches_scikit_image_exactly` passed exact comparison. Decision:
keep local `skeletonize_2d` in production, scikit-image as test oracle only.

### 2026-10-16 — Audit-helper tests closed J7; transient suite failure investigated

`tests/ml/test_dataset_audit.py`: **26 tests** covering polygon parsing, valid
empty negatives, unparsable/too-few-point counters, fat-rectangle versus collapsed
centreline width, degenerate skips, deterministic dHash and geometry classification.
Full ML suite: **298 passed on three consecutive runs**.

One earlier run failed
`test_particle_sizes_select_roi_centroids_but_keep_full_instance_area`. It passed
alone and in three unchanged reruns. The original investigation attributed the
transient failure to concurrent writing/collection of a half-written test module;
no code was changed to suppress it. These are historical observations, not a fresh
validation of the current tree. No model had trained; negatives and chip data
remained unavailable.

### 2026-10-16 — ML documentation consolidated from seven files to three

Documentation-only consolidation: retain `TASKS.md` for status, user actions and
implementation review; `DATA_ADMISSION.md` for acquisition/admission and visibility;
and this standalone history. The four superseded document names are mapped in
Current navigation. This entry records the seven-to-three organization, not a
claim that this changelog-only edit deleted those files or completed their moves.

The changelog was read in full in chunks, then condensed to remove repeated entry
templates, long boilerplate and stale duplicated context. Numerical evidence,
failed runs, permissions/provenance, limitations and superseding decisions remain
historical. No training/evaluation rerun or new scientific result accompanies this
edit; only `docs/ml/changelog.md` was written.

## Historical decision and implementation register

For current status use the two navigation documents; this register preserves
otherwise easy-to-lose decisions and outstanding items at the recorded milestones.

- D1: measurement core first; D2: CRKWH100 first with ISTD-PDS7/GAPs fallbacks;
  D5: real data next, partly resolved 2026-10-15.
- D3: judge definitions of “chip boundary width” and “roughness” needed confirmation;
  final-plan §7.3 definitions were provisional.
- D4: learned-challenger dependencies/environment file needed backend-owner review.
  D6 local skeletonization concern was subsequently resolved by J8's exact oracle
  comparison, not by adding a production dependency.
- D7: Crack-Seg internal-only permission scopes, but does not cure, ancestry risk.
  Licence D8: author permission reported; written artifact remained pending.
  Feature D8 is a separate identifier. D9: `data/` storage explicitly approved.
  D10: backend-owned repository note about gitignored raw storage remained open.
- Feature/unit specification under `docs/ml/`, shared-contract proposals and
  machine-readable `configs/features/` were still outstanding in the original
  register; Python dataclasses/code carried definitions meanwhile.
- Quality implementation debt was partly closed by `validity.py`; embedding its
  verdict in `measure_surface` remained separate. Threshold calibration, human
  gap endpoints, supported size limits and formal Gate 0 review were not established.
- Crack-Seg's admission never admitted a chip source. Later CRKWH100 GT admission
  was for crack cross-source evaluation, not scale/aggregate admission. No distress
  training, Indian fine-tuning, score/reference validation or wet-surface validation
  result is claimed by this history.

### Reproducibility pointers

Audit CLI: `python -m eval.dataset_audit --path <dir> --name <id> --out <json>`.
Generated reports/review images under `reports/ml/` are gitignored; provenance
records include `data_manifests/`, the later `data/manifests/crkhw100_test.json`
and `DATA_ADMISSION.md`. The two manifest paths reflect historical artifacts,
not an asserted migration between them.

Recorded version identifiers: `measure-v1`, `gap-medial-v1`, `quality-v1`
(uncalibrated). Aggregate history moved from `agg-classical-v1` to `v2`, with
concurrent work later reporting `v3`. NMS marker mode reproduces the v1 marker
choice only: v2 cleanup changed too, so it is not bit-comparable to v1. Any change
in measured-output definitions requires renewed reference/score validation
(final plan §9.2), not silent reuse of old evidence.
