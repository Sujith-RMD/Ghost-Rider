# Ghost-Rider — ML Role Changelog

Owner: ML role only (`docs/ml/` per `docs/ML_ROLE.md` §1 and `docs/PROJECT_SKELETON_SETUP.md` §3).
Scope of this log: `backend/{quality,geometry,aggregate,distress,reference,scoring}/`,
`training/`, `data_manifests/`, `annotation_guides/`, `eval/`,
`configs/{camera,features,scoring}/`, `tests/ml/`, `reports/ml/`, `docs/ml/`.

Authoritative scope: `docs/final_plan.md`. This log records what was actually done,
what was actually run, and what was actually observed. It is not a plan document.

---

## 1. Maintenance rules

An entry is added **after** each of these events, never before:

1. A feature, module, config, manifest, guide or evaluation script is added or changed.
2. A training or evaluation run is executed (even a failed or aborted one).
3. A Gate 0 / data-admission decision is made (admit, quarantine, defer).
4. A test or benchmark is run, including runs that fail.

Rules:

- **No entry without evidence.** Each entry states the exact command(s) run and the
  observed result. If something was not run, it is written as "not run", not as passing.
- **`null` is not `0`.** Never record an unavailable measurement as a measured value.
- **Failed results are kept.** A failing gate stays in the log; it is not rewritten
  after a later success. Superseded entries get a `Superseded by:` pointer instead.
- **Temporary scripts are deleted** once they have served their purpose, and the entry
  says so. `tests/ml/` holds only checks worth keeping (final plan §13.4).
- **Status vocabulary** is fixed: `verified` (command run, result observed),
  `implemented-unverified` (code written, not run), `blocked` (dependency missing),
  `failed` (run and did not meet its stated check), `deferred`.
- Anything that changes a shared contract, dependency, unit or scientific meaning is
  *proposed* under `docs/ml/` for the owning role — never edited directly in their area.

### Entry template

```text
### YYYY-MM-DD — <short title>
Type: feature | run | data-admission | decision-request | calibration | eval
Status: verified | implemented-unverified | blocked | failed | deferred
Files:
  - <path> (added|changed|removed)
Command / evidence:
  <exact command(s) and observed output summary>
What it does:
  <2-4 sentences>
Checks:
  <what was asserted and what passed/failed>
Limitations:
  <what this does NOT establish>
Decision needed from user:
  <exact question, or "none">
```

---

## 2. Environment baseline

Recorded once, at first run, because every later "verified" claim depends on it.

| Item | Value | Verified how |
|---|---|---|
| OS | win32, bash (Git Bash) shell | host system info |
| Python | 3.14.0 | `python --version` |
| numpy | 2.4.3 | `python -c "import numpy; print(numpy.__version__)"` |
| opencv | 5.0.0 | `python -c "import cv2; print(cv2.__version__)"` |
| scipy | 1.17.0 | import check |
| scikit-learn | 1.8.0 | import check |
| PyTorch | 2.14.0+cpu | import check — **CPU build, no local CUDA** |
| pytest | 9.0.2 | `python -m pytest --version` |
| scikit-image | **absent** | `ModuleNotFoundError` |
| segmentation-models-pytorch | **absent** | `ModuleNotFoundError` |

Notes:

- The final plan (§11.2) assumes Python 3.11 "where compatible" and lists
  scikit-image, scikit-learn, PyTorch + `segmentation-models-pytorch`. The local
  interpreter is 3.14, and PyTorch is a CPU build. Training is planned on Colab
  (final plan §1), so the local interpreter only has to run classical CV, geometry,
  unit tests and evaluation scripts.
- `backend/requirements.txt` is backend-owned and is **not** modified by this role.
  Missing ML-side dependencies are requested in `docs/ml/` instead.
- Local CUDA absence is not a blocker for Gate 0 or for the classical baseline.

---

## 3. Entries

### 2026-10-16 - Completion check found two small defects in the review-artifact writer; both fixed and re-verified
Type: bugfix + run
Status: verified
Files:
  - `eval/dataset_audit.py` (changed: `sheet_shape` -> explicit `sheet_shape_hwc` in (height, width, channels) order for both writers; `write_annotation_patches` now returns `out_path` like `write_contact_sheet`)
  - `reports/ml/{crkhw100_contact_sheet.png,crkhw100_annotation_patches.png,sheet_meta.json}` (regenerated)
  - `annotation_guides/aggregate_patch_annotation_template.csv` (regenerated, byte-identical)
  - `reports/ml/{contact_sheet_meta.json,annotation_patches_meta.json}` (removed: superseded by the single combined `sheet_meta.json`, and they carried the old inconsistent keys)
Command / evidence:
  The trigger was a check I had not run this session: I edited
  `eval/dataset_audit.py` to add the patch sheet *after* the last contact-sheet
  verification, so the contact-sheet path was unverified. Regenerating it
  through the edited code gave exit 0 and a real file - (1054, 1280, 3),
  **20 of 20 tiles non-blank**, caption carrying "scale UNVERIFIED", no
  `scale_mm_per_px` key - and in doing so exposed two inconsistencies:

  1. **`sheet_shape` was reported in different orders by two writers in the same
     file.** `write_contact_sheet` reported `[width, height]`; the patch writer I
     had just added reported `[height, width, channels]`. Measured on the actual
     file: decoded shape (1054, 1280, 3) against metadata `[1280, 1054]` - i.e.
     the metadata contradicted the file. Two orders for one key is how a consumer
     silently transposes an image. Both now report `sheet_shape_hwc` in
     (height, width, channels) order.
  2. **The two writers used different keys for the same thing**: `out_path` vs
     `path`. A verification script written against one broke on the other. Both
     now return `out_path`.

  Re-verified after the fixes: `SHEET_VERIFY=0` - contact sheet (1054, 1280, 3)
  with 20/20 tiles and 0 blank, metadata matching the file exactly; annotation
  sheet (1306, 512, 3) with 10/10 tiles and 0 blank; `out_path` present and the
  old `path` key absent in both; no mm-claim key in either; both captions carry
  the unverified warning. `python -m pytest tests -q` -> **154 passed**, exit 0.
  The CSV template was regenerated from the corrected metadata and is
  **byte-identical** to the previous file, so the correction changed no annotation
  instruction.
What it does:
  Removes two ways a review artifact could be misread by software downstream, and
  replaces two overlapping metadata files with one combined record.
Checks:
  - Both PNGs decoded and measured rather than assumed present.
  - Metadata shape asserted equal to the decoded file shape, in both sheets.
  - The regenerated CSV was diffed against the previous version and is identical.
Limitations:
  - These are metadata-consistency fixes in a helper; they change no measurement.
  - The contact sheet and patch sheet remain unopened by human reviewers, which is
    the outstanding A2.2/A2.3 work.
Decision needed from user:
  None for this repair.

### 2026-10-16 - C10: image-validity gate implemented and exercised on 100 real images
Type: feature + run
Status: verified
Files:
  - `backend/quality/validity.py` (added); `backend/quality/__init__.py` (changed)
  - `eval/quality_gate.py` (added)
  - `tests/ml/test_quality_validity.py` (added, 18 tests)
  - `reports/ml/crkhw100_quality_gate.json` (generated, gitignored)
Command / evidence:
  Red first: `python -m pytest tests/ml/test_quality_validity.py` ->
  `ImportError: cannot import name 'QUALITY_STATUSES' from 'backend.quality'`,
  exit status 2, before any implementation existed.
  After implementation: `set -o pipefail; python -m pytest tests -q` ->
  **154 passed**, exit status 0.
  Real run: `python -m eval.quality_gate --path
  data/external/deepcrack/CRKWH100/images --out
  reports/ml/crkhw100_quality_gate.json` -> GATE_EXIT=0, **100 images,
  status {'limited': 100}, reasons {'scale_missing': 100, 'low_dynamic_range': 10}**.

  Two defects found by the tests rather than by review:
  1. `cv2.Laplacian(float32_source, cv2.CV_64F)` raises on this OpenCV build -
     "Unsupported combination of source format (=5), and destination format (=6)".
     Sharpness is now measured on an 8-bit source, which also keeps the definition
     identical to the one behind the audit's real-image numbers.
  2. **My own fixtures were wrong**: 200 px images against a 256 px source
     minimum, so four tests were being rejected for *resolution* before ever
     reaching the sharpness and contrast logic they were written to check. Caught
     by the assertion failing, not by reading the code.
  Sharpness definition cross-checked against real data: CRKWH100 `1000.png`
  gives Laplacian variance **2067.4**, inside the audit's recorded range
  (min 51 / median 435 / max 2721 over 100 images), so the units agree.
What it does:
  Implements the validity side of final plan section 7.2 and the
  `accepted`/`limited`/`rejected` status plus reason codes of section 11.5, with
  two honesty rules built in: a missing scale is `limited` (`scale_missing`) and
  `is_metric_evidence=false`, never a rejection of a good image; and
  `QualityPolicy.thresholds_calibrated` is `false` by default and travels into
  every report, because section 7.2 requires per-rig calibration from labelled
  accepted/rejected examples (C11) and explicitly warns that one universal
  Laplacian threshold can mistake smooth good asphalt for blur.
Checks:
  - Every status and reason code asserted to come from the declared vocabulary.
  - Multiple simultaneous reasons are all reported, not just the first.
  - A flat image, a glare-clipped frame and a sub-resolution frame are rejected;
    a low-contrast but sharp frame is only `limited`; a clean unscaled frame is
    `limited` with `scale_missing` and not metric evidence.
  - `thresholds_calibrated is False` asserted on both the policy and the report.
  - Rejected and limited counts are reported beside the accepted count, as
    section 13.3 requires for auditing the excluded set.
Limitations:
  - **The thresholds are not calibrated.** They are engineering defaults, and the
    report says so on every run. Nothing here is a validated rejection policy.
  - **0 images were rejected.** At these provisional thresholds the gate did not
    bind on any real frame, so it has not yet been shown to reject anything real;
    its value so far is the `limited`/`scale_missing` verdict, which is the honest
    label for all 100 CRKWH100 frames while A1.6 is unresolved.
  - The 10 `low_dynamic_range` frames are a real observation about that set (the
    dark acquisitions) but the 40 grey-level floor is provisional.
  - No Indian imagery, no live frames, and no camera rig - so this cannot yet
    satisfy any part of the operating-envelope requirement by itself.
Decision needed from user:
  C11 (per-rig threshold calibration) needs camera access; A1.6 keeps every
  CRKWH100 frame metric-unavailable.

### 2026-10-16 - Planning documents corrected to match final_plan.md authority
Type: documentation
Status: verified
Files:
  - `docs/ml/TASKS.md` (changed: A1.8-A1.13 expanded with final_plan citations, blocking priority reordered)
  - `docs/ml/NEEDED_FROM_USER.md` (changed: items 7-9 expanded, summary table corrected with new priorities)
  - `docs/ml/DATA_ADMISSION.md` (changed: section 4 restructured with status key, critical gap analysis added)
Command / evidence:
  Cross-referenced against `docs/final_plan.md` §4.2 "Selected sources and their
  exact roles". Verified every dataset's stated role matches the authority document.
What it does:
  Corrects a critical planning error: TASKS.md was derived from final_plan.md but
  understated the priority of three core datasets. RDD2022 India (PRIMARY Indian
  distress source), ISTD-PDS7 (ONLY public scaled aggregate candidate), and Indian
  seasonal (Indian robustness set) were listed as open items without emphasizing
  that they block entire claim categories. The corrected documents now:
  - Mark A1.8, A1.9, A1.11 as `[!]` blocked-on-user with BLOCKING annotations
  - Reorder the user-facing priority table (RDD2022/ISTD-PDS7/seasonal now 1-2-3)
  - Add a critical gap analysis showing we have 2 sources but are missing 3 core ones
  - Cite final_plan section numbers for every dataset role
Checks:
  - Every dataset in final_plan §4.2 table now appears in TASKS.md and DATA_ADMISSION.md
  - Blocking annotations match the plan's language ("primary", "only", "first conditional")
  - No dataset has been promoted above its stated role
  - The user priority summary reflects actual project blockers, not alphabetical order
Limitations:
  - Documentation only; no datasets obtained
  - The three core datasets remain unavailable
  - Gate 0 still cannot close without at least one scaled aggregate source
Decision needed from user:
  Download/request the three core datasets (RDD2022 India, ISTD-PDS7, Indian seasonal)
  as the highest priority, before A1.6 or A2.2/A2.3.

### 2026-10-16 - A3.2: two real baseline defects fixed, the fixture made honest, marker depth chosen on held-out seeds
Type: feature + run
Status: verified
Files:
  - `backend/aggregate/segmentation.py` (changed: `MORPH_CLOSE` -> enclosed-hole filling; greedy-NMS markers -> relative h-maxima; new `min_instance_area_px`, `hole_fill_max_area_px`, `marker_method`, `marker_h_max_fraction`; `config_version` `agg-classical-v1` -> `agg-classical-v2`)
  - `eval/aggregate_eval.py` (changed: fixture scenarios separated/touching/merged with an explicit seam, `ignore` rule for unresolvable instance truth, held-out `sweep_marker_params`, `real_image_diagnostics`)
  - `eval/dataset_audit.py` (changed: `select_annotation_patches`, `write_annotation_patches`)
  - `tests/ml/test_measurement_core.py`, `tests/ml/test_eval_metrics.py` (changed: 23 new tests)
  - `annotation_guides/aggregate_patch_annotation_template.csv` (added)
  - `reports/ml/{synthetic_f1_separated,synthetic_f1_touching,synthetic_f1_merged,marker_sweep,crkhw100_real_eval,sheet_meta}.json`, `reports/ml/crkhw100_annotation_patches.png` (generated, gitignored; the sheet metadata was later folded into the single combined `sheet_meta.json`)
Command / evidence:
  `set -o pipefail; python -m pytest tests -q` -> `136 passed`, exit status 0
  (from 113 at the start of this entry).
  Red-then-green was followed for the new behaviour: the 8 new tests for the
  fixture scenarios, the minimum-area filter and the hole-fill limit were run
  **before** the implementation and all 8 failed (exit status 1). The machine
  output quoted one of them exactly -
  `TypeError: WatershedConfig.__init__() got an unexpected keyword argument
  'min_instance_area_px'` - and the fixture tests failed as a group on the new
  keyword arguments as well. The fixture messages themselves were not captured in
  the terminal tail, so they are described here rather than quoted.
  `python -m eval.aggregate_eval --synthetic-cases 12 --seed 0 --scenario
  {separated,touching,merged} --out reports/ml/synthetic_f1_*.json` -> exit 0.
  `python -m eval.aggregate_eval --images data/external/deepcrack/CRKWH100/images
  --out reports/ml/crkhw100_real_eval.json` -> exit 0.
  `python -m eval.aggregate_eval --sweep-markers --out
  reports/ml/marker_sweep.json` -> exit 0.
  `python -m eval.dataset_audit ... --annotation-patches
  reports/ml/crkhw100_annotation_patches.png` -> PATCH_EXIT=0; the PNG was opened
  and measured, not merely confirmed to exist: 1306x512x3, mean 93.0, std 33.2,
  range 0-255, **0 of 10 tiles blank**, `resized: false`, `model_overlay: false`.

  **Defect A - the fixture asked an unanswerable question.** In the old touching
  fixture, chips were placed in contact at *identical intensity*, so the
  ground-truth boundary between them was invisible by construction. Measured on
  seed 3: chip 46 had area 6 px yet a distance-transform maximum of **23.2 px**,
  i.e. the value was describing the merged blob, not the chip. 26 of 53 chips had
  no marker inside them. Instance F1 0.148 was therefore measuring the fixture's
  unfairness, while final plan section 6.3 classifies an unresolvable boundary as
  `ignore`. Fixed: the `touching` scenario now draws the binder joint along the
  ground-truth boundary (measured contrast 135.0 grey levels), the `merged`
  scenario deliberately does not, and `merged` now reports `instance_gt_resolvable:
  false` with instance scores `null` instead of a misleading low number.

  **Defect B - a real production defect: the morphological close destroyed the
  visible boundary.** Measured: the Otsu foreground kept the joint dark at 100% of
  seam pixels and produced **61 connected components for 60 chips**, but the 3x3
  `MORPH_CLOSE` flipped **903 of 1,380 joint pixels back to foreground** and
  collapsed those 61 components to **21**. Instance F1 on the same case was
  **0.228 with the close, 0.700 without it**. Fixed by replacing the close with
  `_fill_enclosed_holes` (bounded by `hole_fill_max_area_px=16`, validated to stay
  strictly below `min_instance_area_px` so hole filling can never swallow the
  smallest particle a config claims to resolve).

  **Defect C - a real production defect: greedy NMS seeded markers along flat
  plateaus.** Measured on a uniform 20x120 bright bar: `marker_method='nms'`
  returned **26 fragments**, relative h-maxima return **1 region**, which is what a
  region with no visible internal boundary is. Fixed with relative h-maxima
  anchoring each marker to its own component peak, so the rule does not depend on
  absolute blob size or brightness.

  **Held-out selection of the marker depth** (`--sweep-markers`, train seeds 0-7,
  held-out seeds 5000-5007, touching scenario, selection on the hold-out column):
  nms baseline hold-out median instance F1 **0.628** (count error +16);
  h=0.5 -> **0.839** (count error -2.5); h=0.9 -> 0.877 but **rejected**: at that
  depth the marker stage degenerates towards one particle per connected region,
  which under-splits any real merge whose joint is too faint to break the
  foreground. The documented rule selects the smallest depth within 0.05 of the
  best, and the rule is unit-tested on fabricated rows so it cannot silently become
  an argmax.

  **Performance defect found and fixed in my own new code.** The first h-maxima
  implementation looped per connected component and per background hole; a full
  report run **timed out at 600 s**. Vectorised with `ndi.maximum`,
  `ndi.maximum_position` and `np.isin`: one real 512x512 image now segments in
  **0.14 s**, one synthetic case in **0.12 s**, and the full report set completes
  inside the timeout.

  Final synthetic scores, `agg-classical-v2`, 12 cases each, same seeds:
  `separated` instance F1 **1.000** (pixel F1 1.000, count error 0.000);
  `touching` instance F1 **0.877** (pixel F1 0.955, precision 0.887, recall 0.842,
  relative count error 0.051) against **0.148** before both fixes;
  `merged` instance scores `null` (unresolvable truth), pixel F1 0.991.

  Real CRKWH100 (100 images, no annotations): determinism holds; descriptive
  instance-count ladder only, **no score implied** - all values are medians over
  the 100 images, written exactly as measured (the .5 values are medians of an
  even count). Polarity `brighter`: min-area 0 -> 2,919.5 instances at 3.57 px
  median diameter, 50 px^2 -> 146.5 at 9.85 px, 200 px^2 -> 18 at 20.34 px.
  Polarity `darker`: 0 -> 1,300.5 at 3.74 px, 50 px^2 -> 162 at 11.35 px,
  200 px^2 -> 46 at 25.82 px.
What it does:
  Removes two defects that were making the classical baseline look far worse than
  it is, and removes a defect that was making my own evaluation instrument look
  like a model failure. It also makes the human-review step fillable: a numbered
  10-patch unaided sheet and a CSV template, so two annotators can produce the
  disagreement floor final plan section 5.1 step 4 asks for.
Checks:
  - Defects A, B and C were each **measured before** being fixed, and the measured
    numbers are recorded here rather than only the improved result.
  - Red-then-green observed for the new tests (8 failures before implementation).
  - Held-out selection used a different seed block (5000-5007) from the reported
    cases (0-11), so the reported number is not the number the parameter was
    fitted on.
  - The `separated` control did not degrade for any h (1.000 across the whole grid).
  - `merged` now returns instance scores as `null`, asserted by a test.
Limitations:
  - **Still not real-road accuracy.** No annotations exist for CRKWH100, so no
    real F1 can be computed. Every number above is against synthetic geometry
    with exact labels, and `not_real_road_evidence: true` travels in every report.
  - **A1.6 is unchanged**: crop-vs-resize of the 512x512 delivery is still
    undetermined, so no mm value from this source may be published. The real-image
    ladder is deliberately unit-free for that reason.
  - The h-maxima depth was selected on the synthetic touching fixture, which has a
    circular-particle geometry. It is a defensible default, not a validated value
    for pavement imagery.
  - `min_instance_area_px` defaults to 0 (keep everything). Choosing a real value
    requires the declared minimum resolvable particle size, which needs verified
    scale and human labels.
  - TDD ordering deviation, recorded rather than hidden: for
    `select_annotation_patches` the test and the implementation were written in the
    same edit, so no red state was observed for that one function.
Decision needed from user:
  A1.6 (crop-vs-resize), the A2.2/A2.3 human review using the new patch sheet, and
  D3 (judge definitions).

### 2026-10-16 - F1/accuracy harness built; synthetic ground truth only; 113 tests
Type: feature + run
Status: verified
Files:
  - `eval/aggregate_eval.py` (added)
  - `tests/ml/test_eval_metrics.py` (added)
  - `reports/ml/synthetic_f1_{uniform,touching,separated}.json`, `reports/ml/crkhw100_real_eval.json` (generated, gitignored)
Command / evidence:
  `python -m pytest tests -q` -> `113 passed` (from 92), exit status 0.
  `python -m eval.aggregate_eval --synthetic-cases 12 --seed 0 --scenario ...` and
  `--images data/external/deepcrack/CRKWH100/images` -> all exit status 0.
  Determinism on 100 real images: `deterministic: true`, 0 mismatched indices.
What it does:
  Adds the per-task evaluation harness ML_ROLE section 4 asks for: pixel
  precision/recall/F1/IoU/Dice, greedy instance matching at an IoU threshold, and
  signed/absolute/relative count error, plus a synthetic case generator whose
  instance labels are **exact**, so "F1" is a measured number rather than a hope.
Checks:
  - Two defects in **my own** work were found and fixed rather than reported:
    (1) a test asserted that an even 50/50 split of one particle scores zero true
      positives - but each half then has IoU exactly 0.5, which the harness credits
      at a 0.5 threshold. The test's geometry was changed to an unequal 60/144
      split (IoU 0.417) and a second test now documents the boundary explicitly.
    (2) The summary block omitted `median_pixel_precision` and
      `median_pixel_recall`; they were computed per case and never aggregated. The
      aggregation was added instead of working around it in the print script.
Limitations:
  - **Superseded by the entry above.** The `uniform`/`touching` numbers recorded
    then (instance F1 0.508 / 0.183) came from the fixture defect described above
    and were removed from disk, not left to be misread. `separated` (1.000) was
    unaffected.
  - No real-image F1 exists: no annotations exist for these images.
Decision needed from user:
  None for this entry.

### 2026-10-16 - `NEEDED_FROM_USER.md` created: every blocker in one place
Type: documentation
Status: verified
Files:
  - `docs/ml/NEEDED_FROM_USER.md` (added)
Command / evidence:
  No command: content review against `docs/ML_ROLE.md` and `docs/final_plan.md`.
What it does:
  Collects, in one ordered file, only the items the ML role cannot do alone: the
  A1.6 crop-vs-resize question, the two-human visibility review, the judge's
  definitions, camera access, dependency approval, the two gated datasets and the
  rule that Colab compute is requested before it is spent.
Checks:
  - Ordered by how much each item blocks, with the smallest-set-to-unblock table
    at the end.
  - Every item states why it blocks and exactly what is needed, not just a label.
Limitations:
  - A request list, not evidence. Nothing in it is done until it is answered.
Decision needed from user:
  All items in the file.

### 2026-10-15 - D8 RESOLVED: CRKWH100 permission granted by the originating author
Type: decision + documentation

**D8 (DeepCrack / CRKWH100 licence) is closed.** Dr. Qin Zou, who produced
CRKWH100, is the supervising professor on this solo project and has granted
permission directly.

This is the strongest provenance available and it supersedes the whole public
information problem: GitHub's `license` field being `null`, the README's
single-sentence "Copy Right", and the third-party **CC BY 4.0** mirror claim are
all now moot, because permission from the owner overrides whatever a third party
asserts. No IEEE involvement exists or is needed - IEEE is the journal DeepCrack
was published in, not a party that grants data rights.

### Recorded

`reports/ml/crkhw100_audit.json` gains a `rights` block that did not exist
before:

| Field | Value |
|---|---|
| `rights_status` | `granted_by_author` |
| `basis` | Direct permission from the originating author / supervisor |
| `scope` | Solo academic project; manual aggregate annotation, texture-measurement development and validation; non-commercial |
| `redistribution` | `not_granted_unstated` - do not redistribute the images |
| `attribution_required` | true, with the citation string embedded |
| `permission_artifact` | `AUTHOR_GRANT_PENDING_FILE` |

That field is the one the previous entry flagged as missing. Without it the audit
recorded scale status but could be misread as having cleared rights.

### Documentation updated

- `NEEDED_FROM_USER.md` section 2 rewritten as **RESOLVED**, with the
  copy-pasteable permission email **removed** since it is no longer needed.
- `TASKS.md`: **A1.7 closed**; the D8 row removed from "Blocked on the user right
  now" and remaining rows renumbered 1-5.

### Explicitly NOT resolved by this

- **A1.6 remains open.** Permission settles *rights*, not *scale*. Crop-vs-resize
  of the 512x512 delivery is still undetermined, so `scale_source` stays
  `unverified`, `contact_sheet.scale_verified` stays `false`, and **no mm value
  from CRKWH100 may be published yet**. Worth noting the author can now be asked
  directly, which turns a research risk into a short question to a supervisor.
- **A2.2/A2.3 two-human review still needs two people.** Unrelated to licensing.

### Defect found and repaired while editing

Two prior edits to `TASKS.md` failed silently against this file because it uses
**em dash U+2014**, not hyphen U+002D. Both render as `-` in a terminal, so
exact-string matching appeared correct in every manual check. Resolved by using a
dash-agnostic character class. Recorded because the same trap will hit any future
script that edits these docs by literal match.

### ID collision noted, not fixed

`TASKS.md` uses the identifier **D8 twice**: line ~111 for a feature task
("Crack skeleton length and defect mask area") and previously for the licence
decision. The licence meaning is now closed, so only one live meaning remains,
but the collision should be renumbered at some point to avoid future ambiguity.

**Not done / still open:** no written grant artifact filed yet
(`AUTHOR_GRANT_PENDING_FILE`); A1.6 and A2.2/A2.3 unchanged.

### 2026-10-15 - D8 licence facts verified against the authoritative source; two doc defects repaired
Type: documentation + investigation

**D8 (DeepCrack / CRKWH100 licence) - licence state now established from the
authoritative source instead of inferred.**

Checked 15 Oct 2026 against the origin:

| Source | Finding |
|---|---|
| GitHub API `repos/qinnzou/DeepCrack`, field `license` | **null** - no LICENSE file exists |
| GitHub API field `mirror_url` | **null** - GitHub records no official mirror |
| README "Copy Right", complete text | one sentence: "This dataset was collected for academic research." |
| README "Contact" | Dr. Qin Zou, `qzou@whu.edu.cn` |
| repo stats | 366 stars, 79 forks, last push 2023-10-29 |

The conflict with a third-party **CC BY 4.0** claim is real but unresolvable from
public information: author silence is not a licence grant, and a third party's
grant cannot substitute for one. Recorded as **unresolved**. Not papered over,
not inferred, not upgraded.

**Two defects found and fixed in `NEEDED_FROM_USER.md`.**

1. **Stale self-contradicting instruction.** The sheet description still told
   reviewers the contact sheet carries a "10 mm-equivalent scale bar". That bar
   was removed in the prior turn (A1.6 repair) and replaced with a pixel-only
   `10 px` bar plus an explicit
   "scale UNVERIFIED: 1 mm/px is the publisher claim only" caption. The document
   therefore described an artifact that no longer existed, and would have
   misdirected the two human reviewers on the single question Gate 0 turns on.
   Rewritten to state the bar is pixel-only and to judge visibility on what is
   visible rather than on an assumed physical scale.
2. **D8 over-claimed the block.** The section stated the licence question
   "blocks the chip-visibility pilot". The pilot has already been executed on
   these images. D8 gates **publishable claims**, not development. Retitled
   "It is not blocking your work - only your claims", with the distinction made
   explicit so the tracker does not stall work that is already done.

**Also recorded:** `crkhw100_audit.json` carries scale status but **no rights
field**, so the audit can be misread as having cleared rights. A `rights_status`
field is now required before the audit may be cited as an admission record.
Value deliberately unset pending the user's decision.

**Action taken:** documentation only. No licence inferred, no rights assumed, no
data redistributed, no claim upgraded. A copy-pasteable permission request to
`qzou@whu.edu.cn` is now in `NEEDED_FROM_USER.md`, and the conservative interim
reading (internal academic research; no redistribution; not citable as an
admitted public benchmark) is stated so development continues without waiting
for a reply.

**Housekeeping defect found and repaired in this log itself.** An earlier attempt
appended this entry as a top-level `## 11.` heading after section 5, which does
not match this file's structure - entries belong under `## 3. Entries` as
`### YYYY-MM-DD` items. The bad block was removed. The mis-decode repair that
restored the file also stripped a UTF-8 BOM added by that same bad write.
Verified after repair: 10 date entries, 15 real em-dashes, zero U+FFFD
replacement characters, zero remaining mojibake sequences.

**Not done / still open:** no email sent - the team sends it. `rights_status`
unset. D8 remains unresolved until written terms are obtained or the dataset is
dropped.


### 2026-10-15 — Defect fixed: contact sheet asserted an unverified physical scale
Type: feature + run
Status: verified (defect found, cause fixed, re-verified)
Files:
  - `eval/dataset_audit.py` (changed: scale bar now pixel-only, `--caption` strip added, `scale_mm_per_px` renamed to `claimed_mm_per_px` with an explicit `scale_verified: false`)
  - `reports/ml/crkhw100_contact_sheet.png` (regenerated)
  - `reports/ml/crkhw100_audit.json` (regenerated)
Command / evidence:
  Before: the sheet drew a bar annotated `10px = 10mm`, given
  `--scale-mm-per-px 1.0`, while task A1.6 records the CRKWH100 scale as
  **UNVERIFIED** (512x512 delivery, crop-vs-resize undetermined). The artifact
  handed to the two human reviewers therefore asserted a physical scale nobody
  has verified.
  After: bar annotated in pixels only (`10 px`), plus a caption strip reading
  "... scale UNVERIFIED: 1 mm/px is the publisher claim only".
  `--skip-audit` path -> CONTACT_EXIT=0. Combined audit+sheet path ->
  COMBINED_PATH_EXIT=0, REPORT_ASSERT_STATUS=0.
  PNG verified as a real artifact, not just a written file: decodes to
  (1054, 1280, 3); body mean 96.4, std 31.9, range 0-255; **0 of 20 tiles blank**;
  caption strip present. PNG_VERIFY_STATUS=0.
What it does:
  Removes a claim from a review artifact. The reviewers' judgement is the only
  route to the Gate 0 chips/gaps decision, so the sheet must not pre-assert the
  scale it is meant to help them assess.
Checks:
  - Both edited call sites exercised: `--skip-audit` and the combined path.
  - The output PNG was opened and measured, not merely confirmed to exist.
  - Metadata renamed so no key implies a verified scale; asserted absent.
Limitations:
  - The caption states the 1 mm/px figure as the publisher's claim; that claim is
    still unverified and still gates every metric output from this source.
  - Tile geometry is asserted at 256 px; only 512x512 sources have been tested.
Decision needed from user:
  None for this repair.

### 2026-10-15 — CRKWH100 audited; 512x512 scale question opened; first real-data classical pilot
Type: run + data-admission
Status: verified (audit + pilot), blocked (scale + human review)
Files:
  - `reports/ml/crkhw100_audit.json` (generated, gitignored)
  - `reports/ml/crkhw100_contact_sheet.png` (generated, gitignored; 2.5 MB, 1280x1024)
  - `eval/dataset_audit.py` (changed: added `write_contact_sheet` and the `--contact-sheet` flags)
  - `data/external/deepcrack/CRKWH100/images/` (added, gitignored, not committed)
Command / evidence:
  Archive: `CRKWH100.zip`, 26,533,247 bytes (25.30 MiB),
  sha256 `e6da26f7546897662573ffe9d9a7c11a867b68b5f9e389afe06faae7a042889b`.
  `python -m eval.dataset_audit --path data/external/deepcrack/CRKWH100 ...` ->
  AUDIT_EXIT_STATUS=0. Measured: **100 images, 0 decode failures, all exactly
  512x512**, 3-channel; no split folders (`unknown: 100`); **no GT masks shipped**
  (100 images without label, 0 orphan labels); 0 exact duplicates.
  Contact sheet: 20 native-resolution 256 px centre-crops, evenly sampled across
  the set, 10 mm scale bar at the claimed 1 mm/px, tiles **never resized** ->
  CONTACT=0.
  Classical pilot on 12 real images at the claimed 1 mm/px:
  polarity `brighter` -> **2,150 instances/image**, median equivalent diameter
  3.91 mm, coverage 0.149; polarity `darker` -> **3,742 instances/image**,
  5.53 mm, coverage 0.540.
  Adjacency test (bottom 8 rows of image i vs top 8 rows of i+1): median
  correlation **+0.020** vs random-pair control **+0.006**, 0 pairs above 0.8 ->
  the 100 files are **independent frames, not contiguous crops**.
  Pixel stats: gray mean avg 91.4 (min 53.7, max 162.6); gray std avg 16.6;
  Laplacian variance min 51 / median 435 / max 2,721.
What it does:
  Audits the second admitted source and runs the first classical pilot on real
  imagery, which is the Gate 0 step that could not be done on synthetic data.
  Also adds contact-sheet generation to the audit tool, because final plan
  section 5.1 requires one and it must be native resolution.
Checks:
  - Decode of all 100 images, not a sample.
  - Both the audit and the contact sheet reported exit status 0 explicitly.
  - The polarity probe was **re-run after a bug was found**: the first attempt
    passed `None` for the config, so `polarity` was never applied and both rows
    printed identical numbers. That result was discarded, not reported.
  - Adjacency was tested against a random-pair control, so "no adjacency" is a
    comparison, not an impression.
Limitations:
  - **The 1 mm/px claim is NOT verified.** Every file is exactly 512x512, which is
    not obviously a raw line-array frame; crop (scale preserved) versus resize
    (scale destroyed) is undetermined. `scale_source` for CRKWH100 stays
    unverified and **no mm value from this source may be published**.
  - **The classical baseline fails on real data**: ~2,150-3,742 instances per
    512x512 image is pathological oversegmentation, and 3.91-5.53 mm is far too
    small for road aggregate. The synthetic-tuned config does not transfer. No
    result from this pilot is a chip measurement.
  - **No chips/gaps go/no-go was produced.** It requires two humans at native
    resolution, which an agent cannot perform.
  - No GT masks in this zip; the separate CRKWH100 GT link was not downloaded.
  - DeepCrack licence still unresolved, so nothing here can be cited as validated.
Decision needed from user:
  A1.6 crop-vs-resize, D8 licence, and the A2.2/A2.3 human visibility review.

### 2026-10-15 — Task tracker created from ML_ROLE.md and final_plan.md
Type: feature
Status: verified
Files:
  - `docs/ml/TASKS.md` (added)
Command / evidence:
  No command: a document derived only from `docs/ML_ROLE.md` and
  `docs/final_plan.md`. Verification was content review, not execution.
What it does:
  Lists every ML-role obligation grouped A-J with a citation to its source
  section, marking achieved items struck through, plus partial, open and blocked
  status. Closes with the six items currently blocked on the user.
Checks:
  - Every task cites a source section; nothing was invented beyond the two
    authority documents and the user's working instructions.
  - Achieved items map to real evidence: 92 passing tests, audit JSON, contact
    sheet, manifests, admission document, changelog entries.
  - Two writing defects were found and fixed during review: a stray `[ !]` status
    marker and a leftover thinking fragment in A1.1.
Limitations:
  - It is a tracker, not proof. A struck-through item still rests on the evidence
    recorded in the corresponding changelog entry.
  - Statuses go stale; the file must be updated alongside the changelog.
Decision needed from user:
  None.

### 2026-10-15 — DeepCrack folder contents confirmed; download list fixed
Type: data-admission
Status: verified (contents), blocked (download)
Files:
  - `docs/ml/DATA_ADMISSION.md` (changed: section 3 folder contents confirmed, section 6 item 1 replaced with an explicit download list)
Command / evidence:
  User-supplied screenshot of the OneDrive parent folder
  (`1drv.ms/f/s!AittnGm6vRKLtylBkxVXw5arGn6R`) showing exactly four subfolders:
  `CrackLS315`, `CRKWH100`, `Stone331`, `Stone331_mask`.
What it does:
  Resolves the open question of what that shared link contains, and confirms the
  README reuses one link for three different datasets. Replaces the vague
  "download CRKWH100" instruction with a take / optional / do-not-take list,
  each justified by a final-plan section.
Checks:
  - Screenshot contradicts the README's per-dataset link hints, which is exactly
    why the folder had to be inspected rather than assumed.
  - No separate `CRKWH100 GT` folder is present, so the README's separate GT link
    may still be required; that is stated as an open branch, not a guess.
  - `CrackTree260` is absent from this folder, consistent with it having its own
    link.
Limitations:
  - Folder *sizes* are still unknown; OneDrive reports them only when the
    download starts. No size will be quoted as fact.
  - Nothing has been downloaded, so the DeepCrack licence question (D8) is still
    open and still blocks the chip-visibility pilot.
Decision needed from user:
  Download `CRKWH100` to `data/external/deepcrack/CRKWH100/` and report the size;
  decide D8 (DeepCrack licence).

### 2026-10-15 — Two user decisions recorded: dataset storage location and Crack-Seg licence
Type: data-admission
Status: verified
Files:
  - `data_manifests/crack_seg_ultralytics_2025-08-21.json` (changed: `licence.user_decision`, new `storage` block)
  - `docs/ml/DATA_ADMISSION.md` (changed: section 2.5 item 2 mark resolved, section 2.6 storage note, section 6 item 4 closed)
  - `docs/ml/changelog.md` (changed)
Command / evidence:
  No command: these are user decisions obtained through a direct prompt. Recorded
  verbatim as: storage = `keep data/` (approved), licence = `internal use only,
  no redistribution`.
What it does:
  Closes the two open questions raised by the Crack-Seg admission, so the manifest
  records an approved state instead of leaving a decision implicit in prose.
Checks:
  - `data_manifests/crack_seg_ultralytics_2025-08-21.json` still parses as JSON.
  - `docs/ML_ROLE.md` was verified to name no `data/` directory (0 occurrences of
    the literal `data/`), confirming the storage location genuinely needed approval.
Limitations:
  - The Crack-Seg ancestry itself is still untraceable; the decision scopes the
    risk, it does not remove it.
  - Neither decision resolves the DeepCrack CRKWH100 licence question, which is
    still open and blocks the chip-visibility pilot.
Decision needed from user:
  None for this entry.

### 2026-10-15 — Crack-Seg downloaded, audited, admitted conditionally
Type: run + data-admission
Status: verified
Files:
  - `eval/dataset_audit.py` (added)
  - `eval/__init__.py` (added)
  - `data_manifests/crack_seg_ultralytics_2025-08-21.json` (added)
  - `docs/ml/DATA_ADMISSION.md` (added)
  - `data/external/crack-seg/**` (added, **gitignored**, not committed)
Command / evidence:
  `curl -L --fail -o data/external/crack-seg.zip <release url>` -> HTTP 200,
  96,089,865 bytes (91.64 MiB, matching the documented ~91.6 MB),
  sha256 `814b566d61e890024d15f22a3e6b14e252f781ab83f60a8d59e6684817efecdc`.
  `python -m eval.dataset_audit --path data/external/crack-seg --name "crack-seg"
  --out reports/ml/crack_seg_audit.json` -> AUDIT_EXIT_STATUS=0.
  Measured: 4,029 images, **0 decode failures**, all exactly 416x416, 3-channel;
  splits train 3,717 / val 200 / test 112; 4,029 label files, **0 pairing
  problems**, 1 empty label file, 5,290 polygons, 667,295 points (mean 126.1);
  0 out-of-range coordinates; class `0: crack` only.
  Label geometry: median stroke width **8.94 px** (p10 4.62, p90 16.69) over 400
  sampled images -> `real_width_outline`, not a centerline.
  Leakage: 1,549 parent prefixes, **0 spanning multiple splits**; 1 exact
  duplicate pair (**both inside test**); 18 dHash cross-split candidates ->
  **0 confirmed, 18 rejected** by pixel correlation.
What it does:
  Obtains real data and runs the section 6.1 admission audit: inventory, decode
  of every image, label integrity, image-label pairing, label-geometry class,
  parent-lineage grouping and duplicate ancestry with a confirmation stage.
  Decision recorded: **ADMIT_CONDITIONAL** as the single allowed crack-mask
  backup, non-metric, non-Indian, no redistribution.
Checks:
  - Decode of all 4,029 images, not a sample.
  - Every audit number came from the tool run above, at exit status 0.
  - The 18 near-duplicate candidates were **not** reported as leakage; they were
    rejected by a stronger test, and both stages are recorded.
  - No candidate was silently promoted above its final-plan section 4.3 role.
Limitations:
  - **No chips or gaps were assessed.** Crack-Seg is crack imagery; it cannot
    answer the chip-count/gap question at all.
  - `scale_source = unscaled`. Uniform 416x416 means a pre-export resize of
    unknown factor, so no GSD exists and all metric output must be null.
  - Upstream ancestry is untraceable from the artifact, and the licence is
    contradictory (docs say Public Domain, the shipped YAML header says AGPL-3.0).
  - The audit tool's own helpers are not unit-tested; they were exercised on a
    real 4,029-image archive at exit 0.
Decision needed from user:
  Licence question in `docs/ml/DATA_ADMISSION.md` section 6 item 4.

### 2026-10-15 — Measurement-core tests consolidated from 6 files to 2
Type: feature + run
Status: verified
Files:
  - `tests/ml/test_measurement_core.py` (added)
  - `tests/ml/helpers.py`, `tests/ml/test_geometry_scale.py`,
    `tests/ml/test_geometry_plane.py`, `tests/ml/test_aggregate_segmentation.py`,
    `tests/ml/test_aggregate_features.py`, `tests/ml/test_measure_surface.py`
    (removed)
Command / evidence:
  `set -o pipefail; python -m pytest tests -q` -> `92 passed`, exit status 0
  (printed explicitly, because the earlier runs were piped through `tail` and
  would otherwise have reported `tail`'s status, not pytest's).
What it does:
  Folds all 92 measurement-core tests and their synthetic fixtures into a single
  module with one shared import header and one shared set of constants.
Checks:
  - Test count is unchanged at 92, so no test was dropped in the merge.
  - `tests` is run as a whole, not just `tests/ml`, so the import shim is proven
    not to disturb other test directories.
Limitations:
  - `tests/ml/conftest.py` is deliberately kept: without it `import backend`
    only resolves when `python -m pytest` runs from the repo root. It is import
    infrastructure, not a leftover.
Decision needed from user:
  None.

### 2026-10-15 — Measurement core implemented and verified on synthetic ground truth
Type: feature + run
Status: verified
Files:
  - `backend/geometry/__init__.py` (changed)
  - `backend/geometry/scale.py` (added)
  - `backend/geometry/plane.py` (added)
  - `backend/aggregate/__init__.py` (changed)
  - `backend/aggregate/segmentation.py` (added)
  - `backend/aggregate/features.py` (added)
  - `backend/aggregate/measurement.py` (added)
  - `tests/ml/conftest.py` (added)
  - `tests/ml/helpers.py` (added)
  - `tests/ml/test_geometry_scale.py` (added)
  - `tests/ml/test_geometry_plane.py` (added)
  - `tests/ml/test_aggregate_segmentation.py` (added)
  - `tests/ml/test_aggregate_features.py` (added)
  - `tests/ml/test_measure_surface.py` (added)
Command / evidence:
  `python -m pytest tests/ml -q` -> `92 passed in 3.36s` (exit 0).
  `python -m compileall -q backend/geometry backend/aggregate` -> COMPILE OK.
  `python -c "import backend.geometry, backend.aggregate"` -> clean import, 13 and 15 public names.
  Measured accuracy on synthetic ground truth (temporary script, since deleted):
  4 disks of radius 12 px -> area 441 px vs 441 px truth (+0.0%), equivalent diameter
  23.70 px vs 24.0 px (-1.25%); two bars with an 11 px facing-pixel separation ->
  gap median 11.0 px / 5.5 mm, n = 190 qualifying sites, IQR 0.0 mm.
What it does:
  Implements the physical measurement core: `PlanarScale` with explicit
  `scale_source` lineage, the plan's `valid_pixels x sx x sy / 1e6` area formula,
  resize lineage (crop preserves scale, resize changes it), area-uncertainty
  propagation, plane homography `H = K[r1 r2 t]`, local mm/px from the Jacobian
  singular values, polygon area, a marker-watershed aggregate baseline with
  instance properties, count density, union coverage, medial-axis gap statistics,
  and `measure_surface` producing a versioned JSON record.
Checks:
  - Unscaled imagery returns `None` for every metric value while pixel counts and
    scale-free ratios survive; a measured zero returns `0.0`. Asserted directly.
  - `require_scaled()` raises `UnscaledError` where metric geometry is mandatory.
  - Downsampling by 2 doubles mm/px and preserves physical area (400 px at 1 mm/px
    == 100 px at 2 mm/px).
  - Down-looking camera at 1.5 m with f = 1000 px gives exactly 1.5 mm/px at the
    principal point; plane origin maps to the principal point.
  - An isolated single particle yields **zero** qualifying gap sites, so an open
    background region cannot be reported as a chip gap.
  - A gap below the declared `min_gap_px` is not reported at all.
  - Distress area is recorded separately and does not remove itself from
    measurement (denominator safeguard).
  - ROI margin excludes an instance whose centroid is outside the interior ROI.
  - Every record is JSON-serializable, including the all-null unscaled case.
Limitations:
  - This validates arithmetic, units, null-versus-zero behaviour and plumbing
    **only**. It establishes nothing about real pavement imagery.
  - The gap method is an approximation: it requires the opposing boundary to
    belong to a different instance, so a genuine narrow gap inside one merged
    instance is missed rather than guessed. The plan expects human endpoint
    labels to validate this later.
  - Gap width is a pixel-centre separation between facing boundary pixels and
    therefore includes those two pixels; the lower reporting limit is declared
    separately as `min_gap_px`.
  - The learned challenger, quality gate, reference and scoring do not exist yet.
Decision needed from user:
  None for this slice. Next slice needs the DeepCrack CRKWH100 sample download
  (already chosen as the data source) and a decision on whether to start the
  annotation guide/pilot or the `docs/ml/` contract proposal first.

### 2026-10-15 — Segmentation defect found and corrected (background-flood bias)
Type: run
Status: verified (defect found, cause fixed, re-verified)
Files:
  - `backend/aggregate/segmentation.py` (changed)
Command / evidence:
  Before the fix, `pytest tests/ml` reported 4 failures. A temporary diagnostic
  script showed the watershed output for a 12 px-radius synthetic disk as
  `{-1: 56, 1: 276, 2: 293}` inside a 25x25 window: the **background marker (1)
  claimed 92 pixels inside the particle**, and the particle basin kept only
  293 px^2 instead of 441 px^2 (a 34% area shortfall, diameter 19.31 px vs 24).
  After switching the watershed surface from the image gradient to the negated
  distance transform and removing the background marker, the same disk measured
  441 px^2 (+0.0%) and `tests/ml` reported `92 passed`.
What it does:
  Root cause: on a flat particle interior the flood from a background marker
  crosses the rim and steals interior area; clipping to the foreground cannot
  repair it because the pixels already carry the background label. Also, splitting
  on the image gradient puts the cut at the object rim rather than at the neck
  between touching particles.
Checks:
  - Re-ran the full suite after the change: `92 passed`.
  - Recorded the defect, the measured evidence and the corrected measurement in
    this entry rather than only keeping the passing result.
Limitations:
  - Ridge pixels between two touching basins stay background, so a small amount
    of aggregate area between touching chips is unassigned by construction.
  - Only synthetic disks and bars were tested; no real chip image was involved.
Decision needed from user:
  None.

### 2026-10-15 — ML changelog established; environment baseline recorded
Type: feature
Status: verified
Files:
  - `docs/ml/changelog.md` (added)
Command / evidence:
  `python --version`, `import numpy/cv2/scipy/sklearn/torch`, `python -m pytest --version`
  — all returned the versions in §2; `scikit-image` and `segmentation-models-pytorch`
  raised `ModuleNotFoundError`.
What it does:
  Creates the ML-role change log required by this role's working agreement, with fixed
  status vocabulary, a mandatory evidence field and a baseline environment table so
  later "verified" claims can be checked against the interpreter that produced them.
Checks:
  - Every §2 row was produced by an actual command in this session, not recalled.
  - No fabricated metrics, scores, thresholds or dataset sizes appear in this file.
Limitations:
  - Establishes nothing about data availability, model quality or physical measurement.
  - PyTorch is CPU-only locally; Colab remains the training environment.
Decision needed from user:
  Which first ML feature slice to implement (see §4).

---

## 4. Open decisions and blockers

| # | Decision / blocker | Why it matters | Who resolves | State |
|---|---|---|---|---|
| D1 | Which ML slice to implement first | Answered: measurement core + tests (implemented and verified, see §3) | user | **resolved 2026-10-15** |
| D2 | Which scale-documented source to pursue first | Answered: DeepCrack CRKWH100 (`.gitignore`d download, 100 images, stated 1 mm/pixel). ISTD-PDS7 request and GAPs form remain fallbacks | user + dataset owner | **resolved 2026-10-15** |
| D3 | Exact judge definitions of "chip boundary width" and "roughness" | Feature definitions in final plan §7.3 are provisional until confirmed | judge/team liaison | **open** |
| D4 | Whether ML-side dependencies (`scikit-image`, `segmentation-models-pytorch`) should be added, and by which environment file | Needed for the learned aggregate challenger; file ownership sits with backend | user → backend owner | **open** |
| D5 | Which slice comes next | Partly answered: real data first. Crack-Seg admitted conditionally; CRKWH100 pending manual download | user | **partly resolved 2026-10-15** |
| D6 | `scikit-image` is absent, so `skeletonize_2d` is implemented locally in `backend/aggregate/features.py`. Confirm the local implementation is acceptable rather than adding the dependency | Avoids a dependency change, but adds ~50 lines of algorithm code the ML role now owns | user | **open** |
| D7 | Crack-Seg upstream ancestry and data licence are untraceable and contradictory (docs say Public Domain, shipped YAML header says AGPL-3.0) | Governs whether Crack-Seg may be used at all beyond internal method development, and whether it can ever be redistributed or cited | user + Ultralytics contact | **resolved 2026-10-15**: internal use only, no redistribution, not citable as an admitted public source. Ancestry risk scoped, not removed |
| D8 | DeepCrack CRKWH100 licence: repo says only "collected for academic research", a mirror claims CC BY 4.0 | Blocks the chip-visibility pilot, which is the only path to a chips/gaps go/no-go | user | **open** |
| D9 | Dataset storage location `data/` is not named in `docs/ML_ROLE.md` (0 literal occurrences), so it was outside the explicit writable list | Raw datasets must live outside Git (final plan section 16) and `.gitignore` already ignores `data/`, but the ML role needed approval to use it | user | **resolved 2026-10-15**: `data/` approved for raw dataset storage |
| D10 | Should a repo-level note (owned by backend) document that `data/` holds gitignored raw datasets | Helps the next person find the data without reading the ML changelog; `.gitignore` and root docs are not ML-owned | backend owner | **open** |

---

## 5. Pointers

- Gate 0 outputs (when produced): `docs/ml/DATA_ADMISSION.md`, `data_manifests/`,
  `reports/ml/`.
- Feature/unit/null-behaviour specification: to be written under `docs/ml/`.
  The implemented definitions currently live in `backend/aggregate/features.py`
  and `backend/geometry/scale.py`; a written specification under `docs/ml/` is
  still outstanding.
- Contract change requests to the backend owner: to be written under `docs/ml/`.

### Audit tooling

| Tool | Purpose | Run |
|---|---|---|
| `eval/dataset_audit.py` | Reusable dataset admission audit: inventory, decode of every image, label integrity, pairing, label-geometry class, parent lineage, duplicate ancestry with confirmation stage | `python -m eval.dataset_audit --path <dir> --name "<id>" --out <json>` |

Generated audit reports land in `reports/ml/` and are gitignored; the committed
record is the manifest in `data_manifests/` plus `docs/ml/DATA_ADMISSION.md`.

### Version identifiers in use

| Identifier | Value | Where |
|---|---|---|
| Measurement record | `measure-v1` | `MeasurementConfig.config_version` |
| Classical aggregate segmentation | `agg-classical-v2` | `WatershedConfig.config_version` (`v1` is reproducible via `marker_method='nms'`; `v2` also changed the clean-up step, so it is not bit-comparable to `v1`) |
| Gap method | `gap-medial-v1` | `features.GAP_METHOD_VERSION` |
| Quality validity policy | `quality-v1` | `QualityPolicy.policy_version` (`thresholds_calibrated=False` until C11) |

Changing any of these changes measured output and therefore requires a new
reference/score validation (final plan section 9.2).

### Known implementation debt

| Item | Why it matters |
|---|---|
| No written feature/unit specification under `docs/ml/` yet; definitions live in code | The plan asks for a versioned feature spec so backend and frontend cannot blur units |
| `configs/features/` is still empty; `MeasurementConfig`/`WatershedConfig` are code-only dataclasses | The plan wants measurement mappings in `configs/features/`; a machine-readable config is deferred until something outside Python needs it |
| ~~`backend/quality/` has no validity/reason-code implementation~~ | **Resolved 2026-10-16** (`backend/quality/validity.py` + `eval/quality_gate.py`, 18 tests). `measure_surface` still records limitations as strings rather than embedding the verdict; wiring the gate into the measurement record is the remaining step |
| Gap method unvalidated against human endpoints | The plan requires endpoint/mask agreement checks in the Gate 0 pilot |
| Gate 0 incomplete | No chips/gaps go/no-go exists yet; it needs human inspection of scale-documented imagery that has not been obtained |
| No distress engine, and Crack-Seg is only a conditional mask backup | The learned crack model, its Indian fine-tuning and its evaluation are all outstanding |
| `eval/dataset_audit.py` helpers have no unit tests | Exercised on a real 4,029-image archive, but not regression-protected |
