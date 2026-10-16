# Data admission — Gate 0

**Consolidated:** 2026-10-16 · **Owner:** ML role (`docs/ML_ROLE.md` §2).
**Authority:** `docs/final_plan.md` §4.2, §4.3, §5.1 and §6.1.

This document combines admission decisions, acquisition priorities and chip-visibility
evidence. The source inventory also drew on `3ultraanalysis.md`. Use
[TASKS.md](TASKS.md) for actions, ownership and human review, and
[changelog.md](changelog.md) for dated history. Scientific interpretation follows
[the implementation review](TASKS.md#implementation-review); the final plan remains authoritative.
Older task/history assertions are not automatically current scientific conclusions.

**Status: Gate 0 is NOT complete.** Crack-Seg is conditionally admitted for a
narrow internal crack-mask role. CRKWH100 imagery and crack GT are obtained;
permission is resolved, but delivered scale is unverified. No source is fully
admitted for chip counting or gap-width measurement. Chip counting remains a
mandatory requirement, not a claim already met.

## Gate 0 requirements and current decisions

Final plan §5.1 requires:

> "Gate output: `DATA_ADMISSION.md`, sample contact sheet, original-source
> manifests, small reviewed annotation set, supported feature-size range, and an
> explicit go/no-go for chips and gaps separately."

Steps 2, 4 and 6 require humans: two people independently judge separate chips
and adjacent boundary gaps at native resolution, double-label 10 patches without
model suggestions, measure disagreement and set resolvable size ranges. Scripts,
contact sheets and segmentation diagnostics do not substitute for these steps.

| Question | Current decision |
|---|---|
| Are aggregate chips independently established as resolvable? | **Not yet.** Historical CRKWH100 heuristics are adverse, but independent human review is outstanding. |
| Are boundary gaps resolvable? | **Undetermined.** No reviewed lower reporting limit. |
| Is Crack-Seg admitted for distress work? | **Yes, conditionally:** one non-metric, non-Indian, internal crack-mask backup; no redistribution. |
| Is a source admitted for chip count or metric gap width? | **No.** |
| Is Gate 0 complete? | **No.** Verified delivered scale, reviewed chip/gap labels and separate go/no-go decisions remain required. |

## Crack-Seg — conditional admission

**Source:** Ultralytics archive, 2025-08-21. **Decision:** `ADMIT_CONDITIONAL`,
narrow role only. Machine-readable record:
`data_manifests/crack_seg_ultralytics_2025-08-21.json`.

### Provenance and content

| Field | Verified value |
|---|---|
| Download URL | https://github.com/ultralytics/assets/releases/download/v0.0.0/crack-seg.zip |
| HTTP status | 200 |
| Archive size | 96,089,865 bytes = 91.64 MiB (documentation claims approximately 91.6 MB) |
| SHA-256 | `814b566d61e890024d15f22a3e6b14e252f781ab83f60a8d59e6684817efecdc` |
| Storage | `data/external/crack-seg`, gitignored and uncommitted |
| Audit command | `python -m eval.dataset_audit --path data/external/crack-seg --name "crack-seg"` |
| Images | 4,029; all decode, 0 failures |
| Splits | train 3,717 / val 200 / test 112 |
| Resolution/channels | All exactly 416×416; 1 distinct resolution; 3-channel RGB |
| Labels | YOLO instance-segmentation polygons, single class `0: crack` |
| Polygons | 5,290; 667,295 points; mean 126.1 points/polygon |
| Pairing | 0 images without labels; 0 orphan label files |
| Coordinate audit | 0 out-of-range polygons, unparsable lines or degenerate polygons |
| Empty labels | 1, retained as a possible valid negative, not deleted |

Final plan §4.3 requires distinguishing centerlines from actual-width masks.
Over 400 sampled images, `2 × rasterised_area / polygon_perimeter` gave median
stroke width **8.94 px**, p10 **4.62 px**, p90 **16.69 px**. A centerline would
collapse toward 1 px. The audit classified these as **real-width outlines**,
supporting pixel-space defect extent, not physical calibration or proof of
annotation accuracy.

### Leakage and ancestry

| Check | Result |
|---|---|
| Roboflow parent prefixes | 1,549 |
| Parents spanning splits | 0 |
| Exact duplicate pairs | 1, both within test; 111 unique test images, not 112 |
| Cross-split dHash ≤ 6 candidates | 18 |
| Candidates confirmed by 64×64 mean-centred Pearson correlation | 0 |
| Candidates rejected as coarse-hash false positives | 18 |

These checks found no confirmed cross-split leakage, not proof of complete
source independence. Filenames follow `<parent_id>.rf.<32-hex>`; the artifact
supplies no upstream source list, per-image attribution or parent licences.
Upstream ancestry remains untraceable and final plan §6.1/§4.3 provenance
requirements remain unmet.

### Rights, limits and permitted use

The documentation says **Public Domain**, but shipped `crack-seg.yaml` has an
**AGPL-3.0** header and no separate data licence. **User decision 2026-10-15:**
accept internal method development only, no redistribution, and do not cite it
as an admitted public source. This is a scoped project decision, not resolution
of upstream rights. The user also explicitly approved `data/external/crack-seg`
on **2026-10-15**, since `docs/ML_ROLE.md` did not name a `data/` location.

Permitted under the final plan's **at most one crack-mask backup** rule:
crack-mask pretraining, distress pipeline/method development, non-metric crack
presence and relative pixel-space extent. Crack-Seg occupies that backup slot.

Forbidden: Indian-road performance claims; mm/cm width, length or area; use as
aggregate/chip data or a known-good reference; redistribution; adding a second
foreign crack-mask backup; treating the test split as 112 independent items.
Uniform 416×416 delivery has unknown pre-export resizing and no GSD: physical
outputs must be `null`, with scale source `unscaled`.

The one empty label is only a possible negative; the test split has **zero
negatives**. This nearly all-positive set cannot establish false-alarm behavior.

## CRKWH100 — obtained, rights resolved, scale unverified

Primary repository: https://github.com/qinnzou/DeepCrack (Zou et al., IEEE TIP
2019). The repository describes **100 pavement images**, a **line-array camera**
and **1 mm GSD**. A separate Liu et al., Neurocomputing 2019 project is also
called DeepCrack; do not mix the projects or infer identity from a mirror.

### Acquisition provenance and permission

- Parent imagery folder: https://1drv.ms/f/s!AittnGm6vRKLtylBkxVXw5arGn6R.
  On **2026-10-15**, its four subfolders were confirmed as `CrackLS315`,
  `CRKWH100`, `Stone331`, `Stone331_mask`. The README reuses this link for three
  datasets. `CrackTree260` has a separate link; no separate `CRKWH100 GT` folder
  appeared in this parent.
- Initial access returned a JS-only OneDrive shell; no archive size was published
  or programmatically verified. That historical limitation is superseded for the
  downloaded CRKWH100 archive, not for every sibling folder.
- Delivered imagery: **100 PNGs, all 512×512**, 100/100 decode, 0 failures;
  **26,533,247 bytes (25.30 MiB)** zipped. Recorded checksum abbreviation:
  `e6da26f7…42889b` (not a full reproducible checksum here).
  Storage: `data/external/deepcrack/CRKWH100/images/`.
  Audit: `reports/ml/crkhw100_audit.json`. No shipped splits, 0 exact duplicates.
- Original repository terms said **"collected for academic research"**; a mirror
  claimed **CC BY 4.0**, which was not authoritative. **Resolved 2026-10-15** by
  direct permission from originating author **Dr. Qin Zou**, supervising
  professor: **solo academic project, non-commercial, no redistribution,
  attribution required**. Audit records `rights_status=granted_by_author`.
  This resolves the project's rights gate only, not scale or visibility.
- Crack GT links recorded in the source notes:
  https://1drv.ms/f/s!AittnGm6vRKLglyfiCw_C6BDeFsP and
  https://1drv.ms/u/s!AittnGm6vRKLglyfiCw_C6BDeFsP.
  Intended separate location: `data/external/deepcrack/CRKWH100_GT/`.
  **Obtained and admitted for distress evaluation 2026-10-16:** 100 binary BMP
  masks, 512×512, values 0/255, paired 1:1; manifest
  `data/manifests/crkhw100_test.json`.

The GT acquisition was originally prioritized to find intact negatives, because
Crack-Seg has only one possible negative. **All 100 CRKWH100 masks contain crack
GT: this acquisition supplies ZERO negatives.** It labels cracks, not chips or
gaps. A GT-vs-GT raster self-check returning 1.0 validates evaluator plumbing,
not model accuracy.

### Scale and independence constraints

**A1.6 is unresolved:** crop (GSD preserved) versus resize (GSD changed) is
unknown for the 512×512 files. Dr. Zou is now unreachable; author confirmation
and native originals cannot currently be obtained through that route. Keep
`scale_source=unverified`; **publish no mm values from CRKWH100**. Do not assume
that native originals necessarily carry visible chips or that downsampling has
been proven.

The historical adjacent-frame check found consecutive-image correlation median
**+0.020**, versus random-pair control **+0.006**. This weakens a simple
contiguous-crop hypothesis; it does **not** establish independent frames, roads,
sessions, ancestry or source independence.

The GT was historically designated a held-out cross-source distress test on the
basis of different sensor, resolution and geography from Crack-Seg. Those
attributes and dataset names do not prove independent ancestry. Confirm original
sources and frozen group splits. If CRKWH100 failures inform preprocessing,
thresholds or model selection, designate it **development**, not untouched test,
and obtain fresh independently grouped test evidence.

Potential uses are appearance/texture-proxy development, crack diagnostics and
reviewed surface analysis, not validated chip counts. Any proposed appearance
reference still needs supported-domain and independently reviewed known-good
evidence; possession alone does not admit it as a known-good reference.

## Dataset acquisition

Acquisition priorities below retain the 2026-10-16 plan while updating completed
acquisitions. Chip counting is mandatory, making a new verified chip-scale source
the critical path. Send both request-gated scale-source requests early because
access has latency. Do not download everything: move on when rights, access,
scale or visibility blocks a source. Track actions/review in [TASKS.md](TASKS.md).

### Priority 1 — immediate work and downloads

| Source | Disposition and consumer | Evidence, links and constraints |
|---|---|---|
| CRKWH100 crack GT | Former first download; now obtained. E8/E10, I12/I15, A1.12-era negative-search motivation, distress evaluation | Links and delivered-mask facts above. **Zero intact negatives**, so the original false-alarm motivation is unmet. |
| RDD2022 India subset | **Obtained and integrity-audited; admission pending:** primary Indian distress source; E8/E9/I12, `distress_india_test`, India claim | https://github.com/sekilab/RoadDamageDetector · https://arxiv.org/abs/2209.08538. **47,420 total images across six countries**, not India-only. Boxes require manually drawn masks for precise segmentation. Freeze Indian test groups before annotation-driven training. Blocks every Indian distress claim. |
| Pavementscapes | Download priority for optional preferred distress-mask pretraining; E8 and exploratory E4/E5 chip pilot | https://github.com/tongzheng1992/Pavementscapes · https://arxiv.org/pdf/2208.00775. **4,000 top-down grayscale images, 6 damage categories**. Top-down geometry motivates a pilot, not admission for chips. Claimed **1–2 mm GSD unverified**; inspect delivered files and group sibling crops. |

### RDD India local archive audit — 2026-10-16

`eval/rdd_archive_audit.py` streamed the 14,163,599,360-byte DatasetNinja tar without extraction. All 142,272 members were inspected; all **9,665 Indian images** decoded at **720×720**, with no decode failures, invalid boxes, image/annotation dimension mismatches or exact Indian image duplicates. Individual image hashes are recorded; full archive SHA-256 was not computed. Report: `reports/ml/rdd_india_archive_audit.json`.

| Split | Images and paired JSONs | Boxes | Empty annotations |
|---|---:|---:|---:|
| Train | 7,706 | 8,175 | 3,934 |
| Test | 1,959 | 0 | 1,959 |

Train class counts: pothole 3,187; alligator crack 2,021; longitudinal crack 1,735; other corruption 1,119; transverse crack 113. **These are bounding boxes, not defect areas or masks.** `other corruption` is not automatically a supported class. Empty test JSONs mean labels are unpublished, not an intact-negative test set. Empty train annotations require human completeness review before negative supervision. All metadata sidecars are empty, so road/site/session independence is unverified; absence of exact duplicates does not resolve near-duplicate leakage.

The mirror licence declares CC BY-SA 4.0 and links the originating competition rules; the exact text and hashes are preserved in the report. Original-source rights verification, reviewed overlays, grouped splits and actual-width masks remain admission gates. This audit permits inventory/feasibility conclusions, not training approval, Indian model accuracy, verified GSD or live acceptance.

### Priority 2 — request scale sources and obtain Indian robustness data

| Source | Disposition and consumer | Evidence, links and constraints |
|---|---|---|
| **ISTD-PDS7** | **Highest-priority access request**, not obtained; first public scaled-aggregate feasibility candidate; A1.9/A3.x, E4/E5, chip count/size, gap width, candidate chip-scale reference | https://www.mdpi.com/2072-4292/15/7/1750. **18,527 images**, paper documents **0.91 mm/px** on original CCD imagery. Access by author request. Delivered per-file GSD and human visibility must be verified; existing labels are distress, not chips. Not already admitted or calibrated. |
| GAPs originals / v2 / 10m | Request-gated backup scaled imagery and distress-mask/reference-method validation | https://www.tu-ilmenau.de/universitaet/fakultaeten/fakultaet-informatik-und-automatisierung/profil/institute-und-fachgebiete/institut-fuer-technische-informatik-und-ingenieurinformatik/fachgebiet-neuroinformatik-und-kognitive-robotik/data-sets-code/german-asphalt-pavement-distress-dataset-gaps. `pip install gaps-dataset`; email signed academic PDF access form. Claimed original **1.2 mm/px**; 10m release has **20 expert-labelled 5030×11505 images**, few independent scenes, **6 FGSV classes**. Verify delivered scale, rights and grouping. |
| Indian seasonal paved/unpaved | Required Indian robustness/challenge set; download after Priority 1; `india_challenge_test`, wet appearance and unsupported surfaces | https://data.mendeley.com/datasets/tj2m7zz4rg/2. **4,242 Nashik/Mumbai originals**, plus rotations and video. Start from originals; group rotated/resized/video siblings. Not obtained; blocks wet/unsupported-surface validation. No verified metric scale. |

ISTD-PDS7 is the request to chase; GAPs is a backup, not evidence that the chip
gate is already satisfied. Neither published GSD nor top-down geometry proves
human-labelable particles, physical calibration or a known-good reference.

### Already held, optional, deferred and excluded sources

| Source | Disposition | Unique evidence, intended use and restrictions |
|---|---|---|
| Crack-Seg | Held; conditional single crack-mask backup | Audit and restrictions above; D8/I16 software work, E8/E10. Not chips, negatives coverage or India evidence. |
| CRKWH100 | Held; scale-unverified pilot | 100 × 512×512; D7 texture proxies and appearance/crack diagnostics. Historical negative-search intent failed with GT acquisition. See visibility evidence below. |
| RaymondAllen/asphalt-3d-laser-texture | Held but **deferred/excluded from RGB appearance reference and chip truth** | **900 3-D height maps at 0.05 mm/px + PTV, CC-BY-4.0**. Geometry/texture-proxy validation and MTD/MPD study only: unpaired height maps do not validate RGB→texture mapping. |
| StreetSurfaceVis | Optional, not obtained | **9,122 German street-level images**; scene-quality/map integration checks, different viewpoint/task from chip analysis. |
| comma2k19 | Deferred; small excerpt only if replay needed before live capture | https://github.com/commaai/comma2k19; **MIT**, approximately **100 GB** full set, video plus sensor metadata. Sync/route-demo plumbing only, neither chip-scale data nor grade labels. |
| RoadCrack_DL_HY-corrected | Reserve, not an additional admitted backup | HuggingFace, **3.01 GB**, **2,189 images**, **4 crack classes**, reported clean/zero-leakage splits. Non-commercial licence, non-Indian; independently audit claims. Consider only if E8 needs a justified replacement under the one-backup rule. |
| CrackLS315 | Optional only if more CRKWH100-family visibility samples needed | **315 images**, same claimed GSD; parent OneDrive link above. Laser illumination may inform resolution-limit exploration, but final plan §4.2 excludes it from training/anchoring the appearance reference. Scale still requires verification. |
| Stone331 / Stone331_mask | Do not acquire for this task | Cut-stone cutting-surface imagery, not road; excluded from appearance reference. Parent folder above. |
| CrackTree260 | Do not acquire as another backup | Separate link in the primary repository; same family as Crack-Seg, which occupies the single backup slot. |
| Mendeley RSCD variants | Excluded | **27 surface-state categories**, not PSCI grades. |
| UAV-PDD2023 | Excluded from chip measurement; otherwise deferred | **CC-BY-4.0**, UAV domain; reconsider only to address a measured failure, not as current task evidence. |
| SDNET2018 | Rejected | Concrete-classification detour; generic encoder simpler. |
| KITTI / BDD100K / Mapillary | Rejected for now | Driving scenes are not chip labels; large downloads without a chip consumer. |
| Roboflow loose-aggregate / 8 mm–40 mm projects | Rejected as calibration/road truth | Loose particles are not embedded pavement; physical size in a name is not image scale. Annotation-method practice only. |
| MVTec AD / DTD / generic textures / synthetic Voronoi stones | Algorithm tests only | Validate software/arithmetic, never road-condition truth. |
| Multiple foreign crack-mask backups | Excluded | Final plan §4.3 permits at most one; Crack-Seg occupies the slot. |

### Admission safeguards and remaining coverage gaps

Before use, record URL, version/date, archive bytes/checksum, exact reuse terms,
upstream parents and named consumer; run
`python -m eval.dataset_audit --path <dir> --name <name>` with actual values.
Scale is **per delivered file**, not a blanket dataset property. Group original
images, roads, sessions, adjacent frames, near-duplicates, rotations and resized
siblings **before** crops/splits. Freeze Indian test data before annotation-driven
training; fit normalizers, reference statistics, thresholds and model choices on
development groups only.

Current coverage is a foreign crack backup, a scale-unverified pilot and a locally audited Indian bounding-box archive,
not Indian acceptance or validated aggregate measurement:

- Chip count/size and gaps: ISTD-PDS7 first candidate, GAPs backup; Pavementscapes
  exploratory geometry only. CRKWH100 and Crack-Seg supply no verified metric scale.
- Texture proxies: CRKWH100 development; prospective ISTD-PDS7 and seasonal wet
  challenges. Height-map geometry does not validate an RGB mapping.
- Distress: Crack-Seg pixel masks; obtained RDD India boxes (manual masks remain required),
  Pavementscapes masks and GAPs masks. CRKWH100 GT supports restricted evaluation.
- Negatives/false alarms: Crack-Seg has one possible negative and none in test;
  CRKWH100 GT has none. Reviewed intact negatives must still be obtained;
  RDD, Pavementscapes and seasonal data are candidates, not established coverage.
- India claims require RDD2022 India and appropriate masks; wet/unsupported-surface
  robustness requires the seasonal challenge set. RDD India is in hand but not admitted; seasonal data remains unavailable.
- Route replay has no immediate acquisition need; comma2k19 remains optional.

## Chip visibility evidence

**Historical measurement date:** 2026-10-16. **Feeds:** A1.6, A2.2/A2.4, A3.2,
E3. The measurements below are reproducible-style segmentation diagnostics on
delivered pixels, **not independent human verdicts, chip ground truth or proof
of sensor resolution**. Historical notes called these “three independent
measurements”; they share imagery and processing assumptions and do not establish
statistical or source independence. The implementation review supersedes their
stronger conclusions.

### Pixel-space motivation

The historical target was exposed aggregate roughly **4–20 mm** across. At the
**unverified claimed** CRKWH100 scale of 1 mm/px, that would be **4–20 px**
diameter, **2–10 px** inscribed radius and approximately **12–314 px²** area.
A 10 mm circular chip would span 10 px and approximately 78 px². These are
conditional calculations, not measurements in physical units. Coarser sampling
can prevent resolution, but no delivered GSD has been established here.

### Historical methodology and numerical results

Diagnostics used delivered **512×512** files and were repeated after
`agg-classical-v1` → `agg-classical-v3` (h-maxima markers, hole filling and
minimum-instance-area filtering). The reported qualitative result persisted;
that does not exclude shared preprocessing or segmentation failure.

1. **Foreground distance transform:** reported largest inscribed circle
   **3.2–6.0 px across six sampled images**. This is a property of the chosen
   foreground, not an algorithm-independent bound on visible chip size.
2. **Instance distribution, six images, then-current configuration:**
   **3,121–3,790 fragments**, median area **8 px**, median equivalent diameter
   **3.19 px**, p90 area **23 px**. These fragments are not validated particles.
3. **Multi-scale median-filter sweep:** counts fell without a plateau.

| Median filter k | Regions | Median top-10 area (px²) | Maximum area (px²) |
|---|---|---|---|
| 1 | 14,170 | 46 | 87 |
| 3 | 5,368 | 104 | 145 |
| 5 | 2,927 | 131 | 237 |
| 9 | 1,410 | 174 | 349 |
| 15 | 517 | 153 | 197 |
| 21 | 156 | 77 | 226 |
| 31 | 19 | 36 | 178 |

The historical interpretation of **1,410 → 517 → 156** was progressive speckle
merging rather than stable particles. An illustrative assumption of **0.25 m²**
and approximately **500 chips/m²** gives approximately **125 chips/image**;
neither area nor density was established for these delivered images. Absence
of a plateau is adverse algorithmic evidence, not a necessary-and-sufficient
visibility test.

Earlier pilot settings also returned approximately **2,150 instances/image**
with `brighter` polarity and **3,742** with `darker`, up to **0.54 coverage**.
The historical **3.91–5.53 mm** median “diameter” used an unverified scale and
is **not a permissible physical measurement**. Thousands of texture-noise
instances cannot be reported as chip counts.

### Interpretation, alternatives and human verdict

The historical conclusion “chip-scale structure is not resolvable” and assertion
“this is not a segmentation failure” were too strong. Current conclusion:
**the delivered CRKWH100 pilot has not demonstrated reliable chip/gap measurement;
human visibility, physical scale and real-label accuracy remain unresolved.**

Downsampling of a long line-array scan is one hypothesis; native cropping is
another. Neither is established. If files were crops preserving scale, the
historical note proposed re-examining the lossy high-pass/segmentation path.
Agreement among these heuristics cannot rule that out. The former inexpensive
route of asking Dr. Zou for native files is currently blocked by his being
unreachable; prioritize ISTD-PDS7 and GAPs instead.

This is neither a project-wide chip no-go nor a chip go. Adequately scaled,
human-labelable imagery has not been evaluated. Do not manufacture ground truth
from watershed or SAM2 output; proposals require human review after the unaided
pilot, and test labels must be independently produced. Historical distress
contrast/real-width crack evidence does not establish trained distress accuracy,
Indian-road performance or live-camera acceptance.

## Unresolved gates and review handoff

The action/review authority is [TASKS.md](TASKS.md), especially A1–A3 and B;
[changelog.md](changelog.md) preserves history rather than current acceptance.

- **Acquisition/provenance:** obtain ISTD-PDS7/GAPs, verify delivered per-file scale
  and rights; obtain RDD India and seasonal challenges; confirm original-source
  ancestry and frozen group partitions. A1.6 remains blocked, not resolved by permission.
- **Independent human visibility:** inspect approximately **20–30** appropriately
  scaled native images; two people separately judge chips and adjacent gaps.
  Zooming must not merely enlarge ambiguity. A2.2/A2.3/A2.4 are outstanding.
- **Unaided annotation:** double-label **10 patches**, measure disagreement,
  compare model error to that floor and inspect split/merge errors (opposing count
  errors can cancel). Declare separate chip-count and gap-width go/no-go and
  minimum resolvable sizes. No script can close these human gates.
- **Artifacts already available:** `reports/ml/crkhw100_contact_sheet.png`
  contains **20 native 256 px centre-crops**, evenly sampled, never resized, with
  a **pixel-only 10 px bar**, not a mm bar.
  `reports/ml/crkhw100_annotation_patches.png` contains **10 numbered native
  256 px patches**, no model overlays; paired with
  `annotation_guides/aggregate_patch_annotation_template.csv` (**20 prefilled
  rows**, coordinates included, judgments blank). Artifacts are not completed review.
- **Real baseline validation:** contact sheet/pilot generation is no longer wholly
  pending, but reviewed real chip/gap labels, supported feature ranges and
  model-vs-human comparisons remain absent. Saved
  `reports/ml/crkhw100_real_eval.json` is descriptive/determinism evidence only.
- **Quality and scale:** `reports/ml/crkhw100_quality_gate.json` is a historical
  provisional report; all 100 lack verified scale. `quality-v2` changed checks;
  old reports were not silently regenerated. Source-scale agreement is not rig
  calibration; operating-envelope/per-rig threshold and live acceptance remain.
- **Negatives and claims:** obtain sufficient independently reviewed intact
  negatives and Indian distress masks. Save actual-weight inference/run manifests,
  versions, hashes and per-sample predictions before model-accuracy claims. The
  implementation review found no saved trained-distress/cross-source,
  Indian-road or live-camera accuracy result, and claimed no evidence-backed gain.
- **Conditional planning decisions:** can humans label chips at claimed
  **0.91 mm/px**? If not, synthetic-only validation narrows the claim to synthetic
  performance, not fulfillment of real-road chip counting. Does Pavementscapes'
  delivered GSD survive inspection, limiting it to distress if not? Is replay
  needed before live capture (promoting comma2k19)? Is GPU access available for
  E4/E5's learned challenger (otherwise only a measurement pipeline is available)?
- **Reference/scoring:** admit supported-domain, known-good and human condition
  evidence before reference training, scoring weights or Good/Bad bands. Foreign
  public imagery is provisional evidence, not Indian or live-camera acceptance.

Missing evidence must remain unknown/`null`, not measured zero, fabricated
physical units or a confident condition score. Gate 0 cannot close until a
suitable scaled aggregate source is admitted and independent human review
supports separate chip and gap decisions.
