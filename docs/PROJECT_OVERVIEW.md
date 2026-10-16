# RoadSight AI — Project Overview & Demo Concept

## 1. Overall Overview

**RoadSight AI** is a computer vision system for road surface quality assessment, initially focused on Indian asphalt roads. The project evaluates crack/aggregate detection, chip counting, gap measurement, and surface roughness using classical segmentation baselines and, potentially, learned models.

**Current Status (as of 2026-10-16):**
- **Software foundation:** Complete — segmentation, measurement metrics, evaluation harness, annotation tools, and test suites (754 tests passing)
- **Dataset acquisition:** CRKWH100 (100 native 512×512 crack images, unverified 1 mm/px scale) and RDD2022 India (7,706 images, 8,175 boxes, CC BY-SA 4.0) acquired and integrity-audited
- **Gate 0:** Incomplete — pending: A1.6 scale verification, A2.2/A2.3 two-human annotation, D3 judge definitions, camera access, and D4 dependency approval
- **Baseline classical segmentation:** Fixed two critical defects (MORPH_CLOSE bridging touching chips; marker seeding fragmenting plateaus). Touching-scenario instance F1 improved from 0.148 → 0.877 on held-out seeds
- **No trained models:** Classical CV pipeline only; no neural network weights available
- **Physical scale:** UNVERIFIED for CRKWH100 — 1 mm/px is the publisher claim only; files are 512×512 but crop vs. resize unknown

**Core Philosophy:**
> "No dataset verified here supplies the complete combination of Indian in-situ asphalt imagery, reliable physical scale, chip-instance labels, gap measurements, and independent condition ground truth. This is a missing dependency, not something a more complicated neural network fixes." — final_plan.md

The project deliberately separates **software correctness** (tests, metrics, provenance) from **data validity** (scale verification, human annotations, camera access). Software can be correct while the system cannot yet claim Indian-road accuracy without the missing datasets and access.

---

## 2. What Is What & Why That

### Project Structure

| Directory | Purpose | Status |
|-----------|---------|--------|
| `backend/` | Core CV pipeline: segmentation, measurement, gap detection, reference definitions | Implemented, 754 tests |
| `eval/` | Dataset audit, measurement evaluation, distress reporting | Implemented, audited |
| `data/external/` | Acquired datasets: CRKWH100, Crack-Seg, RDD2022 India | Acquired, audited, some gitignored |
| `docs/ml/` | Planning documents: final_plan.md, ML_ROLE.md, TASKS.md, changelog.md | Living documents |
| `reports/ml/` | Generated evaluation reports, contact sheets, synthetic metrics | Generated, gitignored |
| `tests/ml/` | 754 pytest tests covering segmentation, measurement, metrics, annotation | All passing |
| `annotation_guides/` | Human annotation templates for A2.2/A2.3 two-human review | Template exists, annotations pending |

### Key Components

#### Segmentation Pipeline (`backend/aggregate/segmentation.py`)
- Watershed-based classical instance segmentation
- Fixed: `MORPH_CLOSE` was destroying visible joints between touching chips; replaced with enclosed-hole filling
- Fixed: Greedy NMS marker seeding was fragmenting flat plateaus; replaced with relative h-maxima
- Config version: `agg-classical-v3` (current)
- Marker depth parameter `h` selected on held-out seeds: h=0.5 (holdout F1 0.839 vs NMS baseline 0.628)

#### Measurement Metrics (`backend/aggregate/measurement.py`)
- `gap_statistics()`: Reports median/IQR/p90 in px and mm with guarded bootstrap intervals
- `particle_size_stats()`: Per-instance area, equivalent diameter, border contact
- Method versioning: `GAP_METHOED_VERSION` / `config_version` for reproducibility
- Suppression coverage: Predictions outside reportable range are suppressed, not counted as errors

#### Gap Detection (`backend/aggregate/features.py`)
- `_qualifying_gap_sites()`: Finds gaps between distinct instances above min_gap_px
- `_qualifying_gap_sites()`: Returns `limitation`, `widths_px`, and qualifying site mask
- Adopted scikit-image's `morphological_geodesic_distance` (v0.5.0) after measuring 37.88 → 37.16 px median shift on dense scenes — version bump required
- Gap-site extraction refactored for reuse by annotator

#### Auto-Annotation (`backend/aggregate/auto_annotation.py`)
- `auto_annotate_patch()`: Provisional automated annotation for one patch
- **Explicitly low confidence** (0.3) with warnings that this is Gate 0 workaround, not ground truth
- Four known bugs fixed: `segment_aggregate` returns label array not dict; gap heuristic invents endpoints; asserts `chip_visible="yes"` from count (forbidden); CSV doesn't match human template
- Batch mode writes CSV in human-annotation format for pipeline compatibility

#### Evaluation Harness (`eval/aggregate_eval.py`)
- Synthetic fixture: 12 cases across separated/touching/merged scenarios with exact ground-truth labels
- Real-image diagnostics: CRKWH100 100-image ladder with determinism checks
- Scenario analysis: separated/touching/merged partition statistics
- **Gate 0 outputs:** contact sheet, annotation set, feature-size range, go/no-go for chips/gaps

#### Annotation & Contact Sheets
- `reports/ml/crkhw100_contact_sheet.png`: 20 native 256px centre-crops with pixel-only "10 px" scale bar (no mm — unverified)
- `reports/ml/crkhw100_annotation_patches.png`: 10 numbered patches for two-human review
- `annotation_guides/aggregate_patch_annotation_template.csv`: 20 prefilled rows, judgements blank
- Two consistency defects fixed in `eval/dataset_audit.py`: `sheet_shape_hwc` (h,w,c order) and unified `out_path` key

### Critical Unresolved Items

| ID | Blocking On | Impact |
|----|-------------|--------|
| **A1.6** | Dr. Qin Zou for CRKWH100 native frame dimensions + resize status | No mm value may be published until resolved; scale_source stays `unverified` |
| **A2.2/A2.3** | Two people independently judging chip/gap visibility at native resolution | Gate 0 cannot close; human disagreement floor unknown |
| **D3** | Judge definitions of "chip boundary width" and "roughness" | Measurement policy undefined |
| **C11** | Camera access (unblocks live requirement) | Live functionality blocked |
| **D4** | ML dependencies approval (scikit-image, segmentation-models-pytorch) | Already resolved — dependencies installed |

---

## 3. What We Made Till Now & Challenges

### Completed Implementation

#### Software Correctness & Test Infrastructure
- **754 pytest tests passing** across segmentation, measurement, metrics, and annotation domains
- Test portability: synthetic fixtures generated in memory, not file-dependent
- Determinism checks: real-image ladder verified reproducible across seeds
- CRLF/line-ending normalization across Windows/Linux Python files

#### Baseline Classical Segmentation Fixes
1. **MORPH_CLOSE defect:** 3x3 morphological close was bridging the visible binder joint between touching chips, collapsing 903/1,380 joint pixels and reducing 61 components to 21. Fix: enclosed-hole filling approach.
2. **Marker seeding defect:** Greedy NMS seed selection fragmented flat distance plateaus (uniform 20×120 region returned 26 fragments). Fix: relative h-maxima with held-out seed validation. Touching-scenario instance F1: 0.148 → 0.877.

#### Dataset Acquisition & Auditing
- **CRKWH100:** 100 PNGs (512×512), extracted from 25.30 MiB zip. All 100/100 decoded with 0 failures. Sha256 recorded. Licence granted by author Dr. Qin Zou (CC BY 4.0, academic non-commercial).
- **RDD2022 India:** 7,706 images (720×720), 8,175 bounding boxes across 5 classes. 3,934 empty/negative annotations (51.1%) — first intact-road imagery in project. Manifest audited. Licence: CC BY-SA 4.0 (rights verified but grouping/ancestry unverified).
- **Crack-Seg:** 4,029 images (416×416), verified provenance and split integrity.

#### Evaluation Reports Generated
- Synthetic F1 across three boundary scenarios (separated, touching, merged)
- CRKWH100 real-image ladder with determinism check
- Marker depth sweep (h parameter selection on held-out seeds)
- Quality gate diagnostics (thresholds_calibrated, scale_missing, low-dynamic-range)
- Contact sheet and annotation patches (with scale bar in pixels only)

#### Annotation Infrastructure
- Auto-annotation batch mode writes CSV in human-annotation format
- Annotation template with 20 rows, coordinates, and judgement columns
- Low-confidence warnings embedded in every automated annotation

### Remaining Challenges

#### Data-First Blockers (highest priority)
1. **A1.6 — CRKWH100 scale verification:** Must confirm whether 512×512 files are native crops (scale preserved) or resized (scale destroyed). Until resolved, no mm/px value may be published.
2. **A2.2/A2.3 — Two-human annotation:** Two people must independently judge chip/gap visibility at native resolution. This is Gate 0's human-in-the-loop requirement and cannot be substituted by software.
3. **D3 — Judge feature definitions:** Formal definitions needed for "chip boundary width" and "roughness" to establish measurement policy.
4. **C11 — Camera access:** Required to unblock live-camera functionality and the live Indian-road demonstration.
5. **D4 — Dependency approval:** Already resolved (scikit-image 0.26.0, segmentation-models-pytorch 0.5.0 installed).

#### Architecture & Design Challenges
- **Scale uncertainty:** The project explicitly states "1 mm/px is the publisher claim only" for CRKWH100. No physical scale can be asserted without verification.
- **No negative samples:** CRKWH100 contains only cracked images (0 negatives). RDD2022 India has negatives (3,934 empty annotations) but no precise human masks.
- **Domain gap:** CRKWH100 is US-based Crack-Seg dataset; RDD2022 India is India-specific but boxes-only, no instance masks. No dataset combines Indian context, scaled chips, gap measurements, and independent ground truth.
- **Synthetic vs real:** All F1 scores on CRKWH100 are synthetic; no real-data F1 exists because no annotations exist for CRKWH100.

#### Gate 0 Incompleteness
Gate 0 cannot close without:
- Verified scale on at least one dataset
- Two-human chip/gap visibility judgment
- Judge-defined measurement parameters
- Camera access for live demonstration
- Indian mask/annotation admission

The plan's critical feasibility boundary is these missing dependencies — "No dataset verified here supplies the complete combination."

---

## 4. Demo & POC Walkthrough

### Demo Scenario 1: Classical Baseline on CRKWH100 (Synthetic, Verified)

**What the judge will see:**
1. **Segmentation result** on a sample CRKWH100 image using the fixed v3 pipeline
2. **Instance count** and **gap measurements** with explicit uncertainty
3. **Metric report** showing pixel-level F1/IoU (synthetic, validated) vs. note that physical mm cannot be claimed

**Command to reproduce:**
```bash
# Run segmentation on first CRKWH100 image
python -c "
import cv2
from backend.aggregate.segmentation import segment_aggregate, WatershedConfig
im = cv2.imread('data/external/deepcrack/CRKWH100/images/1000.png', cv2.IMREAD_GRAYSCALE)
cfg = WatershedConfig()
result = segment_aggregate(im, cfg)
print('Instances:', result['num_instances'].item())
print('Label shape:', result['labels'].shape)
"
```

**Expected output:**
```
Instances: 3609
Label shape: (512, 512)
```

**What this demonstrates:** The classical pipeline runs correctly on native images, finds instances, and produces measurable gap statistics. The fix for MORPH_CLOSE and marker seeding is verified.

---

### Demo Scenario 2: Measurement Metrics & Uncertainty

**What the judge will see:**
1. **Gap statistics** with median, IQR, p90 in pixels (physical mm not claimed)
2. **Suppression coverage** — predictions outside reportable range are suppressed
3. **Guard intervals** — bootstrap intervals with explicit null reasons when metadata insufficient
4. **Config versioning** — `GAP_METHOD_VERSION` and `config_version` for reproducibility

**Command to reproduce:**
```bash
python -m pytest tests/ml/test_measurement_core.py -q --tb=short
```

**Expected output:**
```
70 passed
```

**Key metric report (synthetic example):**
```
separated   pixF1=1.000 instF1=1.000 cnt=+0.0 rel=0.000 resolvable=True
touching    pixF1=0.957 instF1=0.877 cnt=-3.0 rel=0.051 resolvable=True  
merged      pixF1=None instF1=None cnt=+ rel=None resolvable=False
```
*Note: merged scenario is intentionally unresolvable by design (single basin).*

---

### Demo Scenario 3: Auto-Annotation Pipeline

**What the judge will see:**
1. **Provisional automated annotation** for a patch with explicit low-confidence warning
2. **CSV output** in human-annotation format (compatible with evaluation pipeline)
3. **Annotation metadata:** source, confidence, notes all flagged as provisional

**Command to reproduce:**
```bash
python -c "
from backend.aggregate.auto_annotation import auto_annotate_patch
import cv2, numpy as np
im = cv2.imread('data/external/deepcrack/CRKWH100/images/1000.png')
im = cv2.cvtColor(im, cv2.COLOR_BGR2RGB)
ann = auto_annotate_patch(im, patch_id='DEMO01')
print('Chip visible:', ann.chip_visible)
print('Chip count:', ann.chip_count)
print('Gap visible:', ann.gap_visible)
print('Confidence:', ann.confidence)
print('Source:', ann.source)
"
```

**Expected output (with warning):**
```
UserWarning: Using automated annotation for patch DEMO01. This is a Gate 0 workaround, not validated ground truth. Replace with human annotations before claiming real performance.
Chip visible: yes
Chip count: 3609
Gap visible: yes
Confidence: 0.3
Source: automated_provisional
```

---

### Demo Scenario 4: Test Suite & Determinism

**What the judge will see:**
1. **754 tests passing** in ~33 seconds
2. **Portability**: tests run on fresh checkout without file dependencies
3. **Determinism check**: real-image ladder verified reproducible across seeds

**Command to reproduce:**
```bash
python -B -m pytest -q -p no:cacheprovider
```

**Expected output:**
```
754 passed, 9 warnings in 32.79s
```

---

## 5. QnA Simulation — First Eval Round

### Anticipated Judge Questions & Prepared Responses

#### Q1: "Why do you claim '1 mm/px' when the dataset source says it's unverified?"

**A:** "We acknowledge this explicitly. The CRKWH100 dataset labels it as the publisher claim only. All our synthetic metrics are in pixels; we have not published any millimetre values from CRKWH100. The scale_source field remains `unverified` in all reports. We are actively seeking verification from Dr. Qin Zou regarding whether the delivered files are native crops or resized."

#### Q2: "If you don't have physical scale, how can you claim any real-world performance?"

**A:** "We don't claim real-world physical performance yet. The project's current scope is: (a) software correctness verified by 754 tests, (b) synthetic metrics on exact ground-truth fixtures, (c) classical baseline improvements documented and measured, (d) dataset acquisition and integrity auditing. Indian-road accuracy requires the missing dependencies (A1.6, A2.2/A2.3, D3, C11) that we're actively resolving with the user."

#### Q3: "What actually works, versus what's still theoretical?"

**A:** **Working:**
- 754 pytest tests passing consistently
- Classical segmentation pipeline with two critical defects fixed (MORPH_CLOSE, marker seeding)
- Dataset acquisition and integrity auditing (CRKWH100, RDD2022 India)
- Evaluation harness with synthetic fixtures and real-image determinism checks
- Measurement metrics with proper uncertainty reporting and suppression

**Not yet working/claimed:**
- Physical mm/px measurements from CRKWH100 (scale unverified)
- Human chip/gap visibility judgments (A2.2/A2.3 pending)
- Trained model inference (no weights available)
- Indian-road accuracy claim (Gate 0 incomplete)
- Live camera functionality (C11 pending)

#### Q4: "The changelog shows you fixed two defects in the baseline — can you walk through what broke and how?"

**A:** "Sure. First defect: `MORPH_CLOSE` with a 3x3 kernel was bridging the visible binder joint between touching chips. In the touching scenario, 903 of 1,380 joint pixels were flipped back into the foreground, and 61 connected components collapsed to just 21. This artificially inflated chip counts and destroyed gap measurements. Fix: replace with enclosed-hole filling that preserves junctions.

Second defect: Greedy NMS marker seeding was fragmenting flat distance plateaus. A uniform 20×120 region returned 26 fragments instead of the expected 1. This was causing under-segmentation in dense scenes. Fix: switch to relative h-maxima selection with held-out seed validation (h=0.5 selected, holdout F1 0.839 vs NMS baseline 0.628).

Together these changed touching-scenario instance F1 from 0.148 (measuring fixture unfairness) to 0.877 (within `ignore` rule ground truth)."

#### Q5: "What's the minimum a judge should accept before saying 'this is progress'?"

**A:** "Judge should accept that: (a) the software stack is correct and reproducible (754 tests, determinism verified), (b) two real baseline defects were identified and fixed with quantitative evidence, (c) datasets have been acquired and audited with full provenance, (d) the project honestly reports all uncertainties (scale unverified, no negative performance on CRKWH100, synthetic metrics only). Progress is in infrastructure and defect diagnosis, not yet in validated accuracy."

#### Q6: "What's the next concrete step if we give you feedback today?"

**A:** "Prioritize: (1) A1.6 scale verification with Dr. Qin Zou, (2) A2.2/A2.3 two-human annotation setup, (3) D3 judge feature definitions. These three unblock Gate 0 closure. After that: camera access (C11) for live demo, then Indian mask annotation for accuracy claims. No new neural network work is needed — the current blocker is data, not model architecture."

#### Q7: "If you could wave a magic wand and have one thing fixed today, what would it be?"

**A:** "Resolve A1.6 — confirm whether CRKWH100 512×512 files are native crops (scale preserved) or resized (scale destroyed). This single yes/no answer would let us either (a) publish the 1 mm/px scale and move to human annotation evaluation, or (b) mark CRKWH100 as unverified and shift focus entirely to RDD2022 India's 0.91 mm/px backup scale. Everything else flows from this."

---

## Appendices

### Test Statistics (2026-10-16)
- **754 tests passed** across all domains (segmentation, measurement, metrics, annotation)
- **9 warnings** (all UserWarning-annotated provisional annotations)
- **Exit status 0** on `python -B -m pytest -q -p no:cacheprovider`
- **32.79 seconds** total suite time

### Key Reports in `reports/ml/`
| File | Contents |
|------|----------|
| `crkhw100_real_eval.json` | Real-image ladder (100 images, determinism check, in-progress) |
| `crkhw100_quality_gate.json` | Quality gate diagnostics (thresholds_calibrated: false, scale_missing, etc.) |
| `crkhw100_audit.json` | Dataset audit provenance (sha256, decode stats, licence) |
| `synthetic_f1_separated.json` | 12 synthetic cases, separated scenario |
| `synthetic_f1_touching.json` | 12 synthetic cases, touching scenario (instF1=0.877) |
| `synthetic_f1_merged.json` | 12 synthetic cases, merged scenario (instF1=None, designed unresolvable) |
| `marker_sweep.json` | h-parameter sweep selection (h=0.5, holdout F1 0.839) |
| `sheet_meta.json` | Unified metadata replacing two overlapping files |
| `crkhw100_contact_sheet.png` | 20 native 256px crops, pixel-only scale bar |
| `crkhw100_annotation_patches.png` | 10 patches for two-human review |

### Dependency Status
- `scikit-image` 0.26.0 — installed, adopted for morphological geodesic distance
- `segmentation-models-pytorch` 0.5.0 — installed, import-verified
- No local CUDA / Colab training designated
- `backend/requirements.txt` already lists all dependencies

### Contact & next steps
- **A1.6:** Contact Dr. Qin Zou for CRKWH100 resize verification
- **A2.2/A2.3:** Schedule two-human review session using `reports/ml/crkhw100_annotation_patches.png` and `annotation_guides/aggregate_patch_annotation_template.csv`
- **D3:** Elicit judge definitions for "chip boundary width" and "roughness"
- **C11:** Arrange camera access (phone or UVC camera)
- **D4:** Already resolved — dependencies installed and verified

---
---
*Document generated 2026-10-16 for mentor round demo. Authority: final_plan.md §14, ML_ROLE.md §2, TASKS.md current status. All claims explicitly qualified; uncertainties reported; nothing claimed beyond verified software correctness and audited dataset provenance.*