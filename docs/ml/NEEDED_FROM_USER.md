# What I need from you

Owned by the ML role (`docs/ML_ROLE.md` §1). Every item here is something the ML
agent **cannot** do alone: a human judgement, an access request, a licence
decision, hardware, or authority over a file I do not own.

Ordered by how much it blocks. Item 1 is the biggest.

Updated 2026-10-16: item 3 now has a **fillable** artifact (a numbered 10-patch
sheet plus a CSV template), so the human review no longer needs anything from me
first. Nothing else in this file changed.

---

## 1. `A1.6` — Is the CRKWH100 512×512 a crop or a resize? **BLOCKING EVERYTHING METRIC**

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

## 2. `D8` - The DeepCrack licence - **RESOLVED 2026-10-15**

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

### Recorded

| Field | Value |
|---|---|
| `rights_status` | `granted_by_author` |
| Basis | Direct permission from the originating author / supervisor |
| Scope | Solo academic project: manual annotation of exposed aggregate, texture-measurement development and validation, non-commercial |
| Redistribution | Not granted unless stated otherwise - **do not redistribute the images** |
| Attribution | Required; see `attribution_text` in the audit JSON |
| Written into | `reports/ml/crkhw100_audit.json` under `rights` |
| Written proof | `AUTHOR_GRANT_PENDING_FILE` - save the grant (email/letter) here when convenient |

### What this does **not** resolve

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
## 3. `A2.2` + `A2.3` — The human visibility review **BLOCKING THE GATE 0 VERDICT**

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

## 4. `D3` — The judge's exact definitions

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

## 5. `C8` — Camera access

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

## 6. `D4` — Approve ML-side dependencies

**Why it blocks:** the learned aggregate challenger needs
`segmentation-models-pytorch`; `scikit-image` is also absent (I worked around it
with a local `skeletonize_2d`, decision `D6`).

**Current state:** numpy 2.4.3, opencv 5.0.0, scipy 1.17.0, scikit-learn 1.8.0,
torch 2.14.0+**cpu**, pytest 9.0.2, Python 3.14.0.

**What I need:** approve the dependencies **and** who adds them.
`backend/requirements.txt` and `pyproject.toml` are **not mine to edit**, so either
you change them or you tell me to write a proposal in `docs/ml/` for the backend
owner.

---

## 7. RDD2022 India subset — **PRIMARY INDIAN DISTRESS SOURCE (CRITICAL)**

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

## 8. ISTD-PDS7 — **ONLY PUBLIC SCALED AGGREGATE CANDIDATE (CRITICAL)**

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

## 9. `D4`/`H6` — Config files and a contract, when you are ready

Not blocking today, listed so it is not a surprise later:

- `configs/camera/`, `configs/features/`, `configs/scoring/` are **empty**; my
  measurement config currently exists only as Python dataclasses (`H6`).
- The backend owns the Pydantic/OpenAPI contract. I need to hand over field names,
  units, null reasons and version identifiers (`H2`) before the frontend can consume
  real results.

---

## 10. Colab — I will ask before you spend compute

Not needed yet. The learned challenger (`E4`) is gated behind Gate 0, because
training on unverified-scale, un-annotated data would produce numbers that mean
nothing. **When we get there I will tell you the expected runtime, the dataset
size and the GPU class before you start anything.**

---

## Summary — smallest set to unblock the most

| Priority | Item | Effort for you |
|---|---|---|
| 1 | `A1.6` crop-vs-resize | one email, or tell me how the zip was made |
| 2 | `A2.2`/`A2.3` open `reports/ml/crkhw100_annotation_patches.png` with a second person and fill `annotation_guides/aggregate_patch_annotation_template.csv` | ~1 hour, two people |
| 3 | `D8` DeepCrack licence | one decision |
| 4 | `D3` judge definitions | one conversation |
| 5 | RDD2022 India + ISTD-PDS7 access | browser + one email |
| 6 | `C8` camera access | a conversation with the lab |
| 7 | `D4` dependencies | one approval |
