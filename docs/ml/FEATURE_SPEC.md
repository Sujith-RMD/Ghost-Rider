# Feature, unit and null-behaviour specification

**Task:** H1, H2, I8 · **Owner:** ML role (`docs/ML_ROLE.md` §1) · **Date:** 2026-10-16
**Status:** `implemented-unverified` — every field here exists in tested code; the
*values* are proven on synthetic geometry and admitted foreign imagery, not on
Indian roads or a live camera.

This is the handoff document the backend needs to publish the Pydantic/OpenAPI
contract (H2) and the frontend needs to render results honestly (H1). It fixes,
for each measurement: **what it means, its unit, when it is `null`, and when it is
a real `0`.** The single rule that runs through all of it:

> **`null` is not `0`.** `null` = "this could not be measured" (missing scale,
> no evidence, unsupported input). `0.0` = "measured, and it is genuinely zero"
> (a road area with no cracks is `0.0`, not `null`).

Every number carries a **`scale_source`**. Metric quantities (`*_mm`, `*_m2`,
`*_per_m2`) are `null` unless the image has a verified scale
(`backend/geometry/scale.py`); a real `0.0` requires a verified scale *and* a
measured-empty region.

---

## 1. Geometry / scale — `backend/geometry/scale.py`

| Field | Unit | `null` when | `0.0` when |
|---|---|---|---|
| `sx_mm_per_px`, `sy_mm_per_px` | mm/px | `scale_source = unscaled` | never (a 0 scale is invalid) |
| `scale_source` | enum | never | — |
| `relative_area_uncertainty` | fraction | either axis uncertainty unknown, or unscaled | never |

`scale_source` vocabulary (fixed, final plan §6.1 item 7): `source_calibrated` |
`rig_calibrated` | `reference_measured` | `unscaled`. Cropping **preserves**
scale; resizing **changes** it (`mm/px ÷ resize_factor`) and appends a lineage
note. There is no blanket mm/px copied across dataset versions.

## 2. Inclination / grade — `backend/geometry/grade.py` (task G1)

Kept **separate from surface condition** (a steep smooth road is a good surface
on a steep grade). It is a **formal requirement** until measured or exempted.

| Field | Unit | `null` when | Notes |
|---|---|---|---|
| `grade_percent` | % (rise/run ×100) | not measured (`validity = unmeasured`) | `0.0` = measured flat road |
| `grade_deg` | degrees | not measured | always consistent with `grade_percent` |
| `crossfall_percent` | % | not measured | transverse; independent of longitudinal |
| `uncertainty_percent` | % | unknown | travels with the value |
| `grade_source` | enum | never | see below |
| `validity` | enum | never | `valid`/`unmeasured`/`uncalibrated_sensor` |

`grade_source`: `inclinometer` | `rig_imu` | `survey` | `reference_surface` are
admissible. **`phone_pitch` and `google_elevation` are refused** — constructing
one raises (task G4). A `rig_imu` grade is `uncalibrated_sensor` (not `valid`)
until independently validated (task G3).

## 3. Aggregate count & size — `backend/aggregate/features.py`

| Field | Unit | `null` when | `0.0`/`0` when |
|---|---|---|---|
| `n_instances_in_roi` | count | never | `0` = no qualifying particle in ROI |
| `count_density_per_m2` | particles/m² | unscaled, or eligible area is `null` | `0.0` = verified empty ROI |
| `coverage_fraction` | fraction [0,1] | no eligible mask | `0.0` = eligible area with no aggregate |
| `particle_size.equivalent_diameter_mm` | mm | unscaled | — |
| `particle_size.*` | mm | unscaled | per-statistic |

`equivalent_diameter` is a **projected 2D appearance**, explicitly *not* sieve
size or internal gradation (final plan §7.3). Counting uses an interior ROI with
a context margin; border-touching instances are flagged, not silently dropped.


## 4. Gap statistics — `backend/aggregate/features.py`

Documented medial-axis method (v2): the non-aggregate region is skeletonised
(Zhang-Suen); at each medial site the width is the centre-to-centre distance
between the facing aggregate pixels, and it counts only when the two belong to
**different instances** (excludes ROI edges and isolated particles).

| Field | Unit | `null` when | Notes |
|---|---|---|---|
| `gap.median_mm`, `iqr_mm`, `p90_mm` | mm | unscaled, or no valid sites | — |
| `gap.median_px` | px | no valid sites | pixel-space fallback |
| `gap.sample_count` | count | never | `0` = no qualifying gap sites |
| `gap.min_gap_px` | px | never | declared lower reporting limit |

This is a **pixel-space separation between facing boundary pixels**, *not* binder
thickness, void depth, or "the width of every dark region" (task D3 is still open
on the judge's exact definition).

## 5. Texture proxies — `backend/aggregate/features.py`

| Field | Unit | `null` when |
|---|---|---|
| `glcm_contrast_mm`, `homogeneity_mm`, `energy_mm`, `correlation_mm` | unitless | unscaled |
| `gradient_energy_mm` | 1/mm² | unscaled |
| `lbp_uniformity_mm` | fraction | unscaled |

Unscaled imagery returns **all `None`** with a `limitation` string, never a
fabricated number. These are unitless/scale-dependent **proxies**, never mm
roughness or physical MTD/MPD (final plan §7.3). Two documented caveats: a 3×3
Sobel is a null operator at the Nyquist frequency (a near-pixel-scale surface can
read as low gradient energy), and a physical offset must quantise to whole pixels,
so the effective offset set depends on declared scale.

## 6. Distress — `backend/distress/features.py`

| Field | Unit | `null` when | `0.0` when |
|---|---|---|---|
| `crack_skeleton_length_m` | m | unscaled | `0.0` = verified no crack |
| `defect_extent_fraction` | fraction | no mask/valid area | `0.0` = clean surface |

Skeleton length sums **step** distances (diagonal = √2) so diagonal cracks are not
under-reported by ~29%.

## 7. Quality / validity — `backend/quality/validity.py`

Status vocabulary (final plan §11.5): `accepted` | `limited` | `rejected`, each with
reason codes (`decode_failed`, `unsupported_channels`,
`inadequate_source_resolution`, `insufficient_sharpness`, `clipped_highlights`,
`clipped_shadows`, `low_dynamic_range`, `scale_missing`).

- `scale_missing` is **not an image defect** — it yields `limited` and
  `is_metric_evidence = false`. A clean unscaled image supports appearance
  observations but never mm / cm² / count/m².
- `thresholds_calibrated` is **`false`** and travels in every report (task C11,
  blocked on camera). Nothing here is a calibrated rejection policy.

---

## 8. Record provenance & versioning (H2)

Every assessment record should carry these version identifiers together, so a
change in any one invalidates dependent results (final plan §9.2):

`config_version` (`measure-v1`) · `segmentation_version` (`agg-classical-v3`) ·
`gap_method_version` (`gap-medial-v2`) · `texture_method_version`
(`texture-proxy-v1`) · `quality_policy_version` (`quality-v2`) ·
`scale_source` · `grade_source`/`grade_validity` · (`score_policy_version` and
`reference_version` — **pending**, scoring/reference not yet implemented).

**Proposed scientific-record fields for the backend contract (H2):** mirror the
tables above 1:1; for each measurement emit `{value, unit, scale_source,
null_reason?, limitation?}`. `null_reason` is a short code
(`unscaled`/`unmeasured`/`no_valid_samples`/`quality_rejected`/`not_implemented`)
so neither service nor UI can blur "measured zero" with "unknown". ML supplies
this; backend owns the Pydantic/OpenAPI schema (`docs/contracts/`).

## 9. Runnable evaluation and provenance tools

### Fixed comparison floors on available masks

```sh
python -m eval.distress_baselines --manifest data/manifests/crkhw100_test.json --out reports/ml/crkhw100_trivial_baselines.json
```

This verifies stored GT hashes and reports always-background/always-foreground predictions. It does **not** train or tune anything. On the current 100 CRKWH100 masks, pooled foreground prevalence is 0.357479%, all-background Dice is 0 and all-foreground Dice is 0.007124. False-alarm behavior is unknown because there are no intact negative frames. These results do not establish model quality.

### Actual-weight inference (when weights are available)

`python -m training.evaluate_crosssource --weights <local-checkpoint.pt> --manifest <manifest.json> --out <report.json> --save-predictions <new-directory>`

Paths in a manifest retain the existing process-working-directory convention. Each sample requires a unique portable `sample_id`, `image` and `gt_mask`; optional `group_id` must identify an independently reviewed parent/site, not a filename. Reports include local-weight/manifest SHA-256, confidence, library versions and saved binary PNG paths. No automatic model download occurs. The prediction directory must not already exist. Prediction-call wall-time p50/p95 includes loading/pre/postprocessing/materialization; model load and any model-only timing are separately labeled. This is **not** capture-to-result service latency. No real-model latency/accuracy was measured in this implementation session.

Read pooled TP/FP/FN/TN and micro IoU/precision/recall/Dice alongside legacy macro means and **GT-positive-only Dice**. Macro empty-denominator scores can be misleading; undefined micro ratios are null. Reports distinguish:

- negative-frame false-alarm rate: any predicted foreground on a GT-negative frame;
- no-foreground miss rate: GT-positive frames with no predicted foreground;
- zero-overlap positive-frame rate: GT-positive frames with TP=0, including spatially disjoint predictions.

Counts/denominators accompany every rate. These are frame/pixel metrics, not object-level detection AP. Group-bootstrap 95% intervals require complete explicit grouping and at least 10 supporting groups for that metric; otherwise null plus reason. Ten is a reporting safeguard, not proof of adequate sample size or independence.

### Count, gap and scale errors

`python -m eval.measurement_eval <measurements.json> --out <report.json>`

Input schema (the values below are **synthetic arithmetic only**):

```json
{
  "evidence_type": "synthetic",
  "metric": "gap",
  "unit": "px",
  "samples": [
    {"sample_id": "patch-a", "group_id": "synthetic-parent-a", "truth": 10, "prediction": 12},
    {"sample_id": "patch-b", "group_id": "synthetic-parent-b", "truth": 5, "prediction": null, "null_reason": "unresolvable"}
  ]
}
```

Use `annotation_source_scale` for public-label agreement and `physical_live` only for independent physical checks. `physical_live` rejects pixel units. `metric` is `count`, `gap` or `length`; units are `count` for count, otherwise `px`/`mm`/`m`. Each input is one inspected observation; do not omit rejected observations. Null predictions require reasons. Reports retain suppressed coverage and zero-truth absolute errors, exclude zero truth only from relative errors, and report signed bias, MAE, median/p95 errors, per-group results and guarded group intervals. Count/gap endpoints and ground truth still require independent annotation; the software does not create it.

### Group before cropping, and freeze before tuning

`python -m training.group_splits <input.json> <new-split-manifest.json> --seed 42`

Each sample needs `sample_id`, `source_id` and explicit grouping evidence (`parent_id`, `site_id`, `road_id`, `session_id`, `sequence_id`, `duplicate_group_id`, or reviewed links). Shared identifiers connect within a source; top-level `near_duplicate_links` connects explicit sample-ID pairs, including cross-source ancestry. Connected components cannot cross splits. At least three groups are required. Allocation targets 60/20/20 by groups, not by crops, and does not guarantee class balance. `--frozen-manifest` preserves existing assignments; conflicting new evidence fails rather than silently moving test samples. `--overwrite` is required to replace output. Separate evaluation roles remain explicit; obtaining a metadata split is not road-held-out proof or data admission.

### Calibration/reference guards

- `backend.geometry.profile.CameraProfile.require_scale(current_signature)` must be called before a live capture supplies physical scale. Unknown/changed device, resolution, focus, zoom, capture crop, stabilization or mount, or absent/failed/mismatched validation, raises rather than silently reusing calibration. Rechecking creates explicit signature-and-scale-bound evidence. Software cannot discover unreported rig movement or authenticate the supplied physical report. Actual rig calibration remains outstanding.
- `backend.reference.compatibility.ReferenceArtifact.require_compatible(definition)` rejects changed feature definitions. `revise_reference()` requires a new reference version when diameter/gap limits, method versions or physical scale domain change. This is an artifact identity gate, not a fitted known-good comparator or condition score.

### Indian archive audit

```sh
python -m eval.rdd_archive_audit --archive data/external/rdd2022-DatasetNinja.tar --output reports/ml/rdd_india_archive_audit.json --decode-budget-seconds 75
```

Streams without extraction; decode budget counts decoder time, not total wall time. The current run decoded all Indian images. See [data admission](DATA_ADMISSION.md#rdd-india-local-archive-audit--2026-10-16) for exact inventory, mirror-rights caveats, grouping/mask gates and why empty test annotations are not negatives. Generated JSON metrics and audit reports under `reports/ml/` are now eligible for version control so collaborators can inspect the evidence. Review reports for sensitive data before adding them; raw datasets and the CRKWH100 pixel-containing review sheets remain excluded. Tests must not require an uncommitted local generated report.
