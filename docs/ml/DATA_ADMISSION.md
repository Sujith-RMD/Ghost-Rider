# Data admission — Gate 0

Owner: ML role (`docs/ML_ROLE.md` §2, Gate 0). Authority: `docs/final_plan.md`
§4.2, §4.3, §5.1 and §6.1. This document records **decisions and evidence**, not
plans. Machine-readable record: `data_manifests/crack_seg_ultralytics_2025-08-21.json`.

Status: **one source audited, no source fully admitted for the chip task.**
Gate 0 is **NOT complete** — see §5.

---

## 1. What Gate 0 actually requires

Final plan §5.1 lists seven steps and this exact output:

> "Gate output: `DATA_ADMISSION.md`, sample contact sheet, original-source
> manifests, small reviewed annotation set, supported feature-size range, and an
> explicit go/no-go for chips and gaps separately."

Steps 2, 4 and 6 are **human** steps: two people independently decide whether
separate chips and boundary gaps are *visible* at native resolution, double-label
10 patches, and set the resolvable size range. Those cannot be performed by the
ML agent alone, and no script substitutes for them. They are **outstanding**.

---

## 2. Source 1 — Crack-Seg (Ultralytics), archive 2025-08-21

**Decision: `ADMIT_CONDITIONAL`, narrow role only.**

### 2.1 Provenance — verified

| Field | Value |
|---|---|
| Download URL | `https://github.com/ultralytics/assets/releases/download/v0.0.0/crack-seg.zip` |
| HTTP status | 200 |
| Archive size | 96,089,865 bytes = 91.64 MiB (docs claim ~91.6 MB — matches) |
| sha256 | `814b566d61e890024d15f22a3e6b14e252f781ab83f60a8d59e6684817efecdc` |
| Landing path | `data/external/crack-seg` — gitignored, **not committed** |
| Audit tool | `python -m eval.dataset_audit --path data/external/crack-seg --name "crack-seg"` |

### 2.2 Content — verified

| Field | Value |
|---|---|
| Images | 4,029 — all decode, **0 failures** |
| Splits | train 3,717 / val 200 / test 112 |
| Resolution | **all exactly 416×416, 1 distinct resolution** |
| Channels | 3 (RGB) |
| Labels | YOLO instance-segmentation polygons, single class `0: crack` |
| Polygons | 5,290 total, 667,295 points, mean 126.1 points/polygon |
| Pairing | 0 images without a label, 0 orphan label files |
| Coordinate validity | 0 out-of-range polygons, 0 unparsable lines, 0 degenerate polygons |
| Empty labels | 1 file — **kept as a possible valid negative, not deleted** |

### 2.3 The check §4.3 specifically demands: centerline vs real-width

Final plan §4.3 requires Crack-Seg to *"distinguish centerline labels from
actual-width masks."* Measured, sampled over 400 images:

| Metric | Value |
|---|---|
| Median stroke width | **8.94 px** |
| p10 / p90 | 4.62 px / 16.69 px |

Method: `2 × rasterised_area / polygon_perimeter`. A centerline collapses to
about 1 px. **Verdict: real-width outlines**, so this dataset can support defect
*extent* — unlike a centerline set.

### 2.4 Leakage audit

| Check | Result |
|---|---|
| Roboflow parent prefixes | 1,549 |
| Parents spanning multiple splits | **0** — the export kept parents intact |
| Exact duplicate pairs | 1, **both inside `test`** → test holds 111 unique images, not 112 |
| Cross-split near-duplicate candidates (dHash ≤ 6) | 18 |
| — confirmed by pixel correlation | **0** |
| — rejected as coarse-hash false positives | **18** |

The 18 candidates initially looked like leakage. A second stage (64×64
mean-centred Pearson correlation) rejected **all** of them. Reporting the raw
dHash threshold as leakage would have been a false alarm; the two-stage result is
the honest one. Parent grouping independently found no cross-split parents.

### 2.5 Blocking problems

1. **Ancestry is untraceable from the artifact.** Filenames are
   `<parent_id>.rf.<32-hex>` — a Roboflow export with 1,549 parent ids — but no
   upstream source list, per-image attribution or parent licence ships with it.
   §6.1 requires upstream parents, and §4.3 requires tracing ancestry.
2. **Licence conflict.** The docs page states *Public Domain*; the shipped
   `crack-seg.yaml` carries an *AGPL-3.0* header. No separate data licence exists.
   → **Redistribution is not authorised.** Internal method development only.
   *Resolved by user decision 2026-10-15: accepted, scoped to internal use only,
   no redistribution, and not to be cited as an admitted public source.*
3. **No scale, and no native resolution.** The uniform 416×416 means a
   pre-export resize of unknown factor. There is no ground sampling distance, so
   every metric output must be `null` and the scale source is `unscaled`.
4. **Not Indian, not chip texture.** It cannot support the India claim, the
   chip-count/gap task, or the known-good reference.

### 2.6 Permitted and forbidden use

**Permitted** — behind the §4.3 limit of *"at most one crack-mask backup"*:

- crack-mask pretraining and pipeline/method development for the distress engine;
- non-metric crack presence and relative extent work on pixel-space masks.

Dataset storage: raw files live in `data/external/crack-seg`, which is gitignored
and uncommitted. `docs/ML_ROLE.md` names no `data/` directory, so this location
was **explicitly approved by the user on 2026-10-15** rather than assumed.

**Forbidden:**

- any claim about Indian road performance;
- any metric width/length/area in mm or cm;
- use as the known-good reference or as an aggregate/chip source;
- redistribution, or pairing it with a second foreign crack-mask set as a
  second "backup";
- treating the test split as 112 independent items while the duplicate remains.

---

## 3. Source 2 — DeepCrack CRKWH100 (the plan's chip-visibility pilot)

**Decision: NOT AUDITED — awaiting manual download.**

Verified facts from the primary repository ([qinnzou/DeepCrack](https://github.com/qinnzou/DeepCrack)):
100 pavement images, line-array camera, **1 mm ground sampling distance**.

What could **not** be verified:

| Item | Status |
|---|---|
| Archive size | **Not published anywhere.** Archive is an OneDrive folder (`1drv.ms/f/s!AittnGm6vRKLtylBkxVXw5arGn6R`) that returns a JS-only shell — no listing or size readable programmatically. A mirror also states no size. |
| Licence | Repo says only *"collected for academic research"*; a mirror claims *CC BY 4.0*. **Conflict.** |
| Identity | Two different projects are both called "DeepCrack": Zou et al., IEEE TIP 2019 (the repo read here) and Liu et al., Neurocomputing 2019 (cited by the mirror). Do not mix their files. |
| Folder contents | **CONFIRMED 2026-10-15.** The shared link is a parent folder containing exactly four subfolders: `CrackLS315`, `CRKWH100`, `Stone331`, `Stone331_mask`. This confirms the README reuses one link for three different datasets. No separate `CRKWH100 GT` folder appears here, so the README's separate GT link must be checked if masks are not inside `CRKWH100`. `CrackTree260` is **not** in this folder (it has its own link). |
| Individual folder sizes | Still unknown. OneDrive reports the size only when the download starts, so the user should report it at that point. |

This needs a browser session, which only the user can do. Nothing has been
downloaded and **no size will be quoted as fact**.

---

## 4. Compliance against the plan's dataset roles

| Source | Plan role (§4.2 / §4.3) | Our status |
|---|---|---|
| RDD2022 India subset | Primary Indian distress source | **Not obtained.** Still the primary Indian source. |
| ISTD-PDS7 | First scaled aggregate-feasibility candidate, 0.91 mm/px, access by request | **Not requested.** The only candidate that addresses chips and gaps. |
| DeepCrack CRKWH100 | Access fallback + independent chip-visibility pilot | Pending manual download (§3). |
| GAPs original / 10m | Backup scaled imagery, 1.2 mm/px, academic form | Not requested. |
| Pavementscapes | Optional distress-mask pretraining | Not obtained. Optional. |
| Indian seasonal paved/unpaved | Indian robustness/challenge set | Not obtained. |
| Crack-Seg | §4.3: *"at most one crack-mask backup"* | **Admitted conditionally** — this is that one backup. |
| Mendeley RSCD, UAV-PDD2023, SDNET2018, loose-aggregate sets, generic texture sets | Explicitly not admitted (§4.3) | Not used. No silent promotion. |

No candidate has been promoted silently, and Crack-Seg has **not** been promoted
above its §4.3 backup role.

---

## 5. Explicit go / no-go

| Question | Answer |
|---|---|
| Are individual **aggregate chips** resolvable in any admitted source? | **CANNOT BE DETERMINED YET.** No scale-documented chip imagery has been obtained. Crack-Seg is crack imagery and cannot answer it. |
| Are **boundary gaps** resolvable? | **CANNOT BE DETERMINED YET.** Same blocker. No lower reporting limit can be declared. |
| Is Crack-Seg admitted for the distress engine? | **YES, conditionally** — one crack-mask backup, non-metric, non-Indian, no redistribution. |
| Is any source admitted for the chip-count or gap task? | **NO.** |
| Is Gate 0 complete? | **NO.** |

---

## 6. Outstanding, and who must do it

**User / human, required before Gate 0 can close:**

1. Download **only `CRKWH100`** from the parent folder
   `https://1drv.ms/f/s!AittnGm6vRKLtylBkxVXw5arGn6R` (the folder shown in the
   2026-10-15 screenshot). Place it at `data/external/deepcrack/CRKWH100/`,
   keeping original filenames intact, and report the download size.

   If that folder contains **no masks**, also download the README's separate
   CRKWH100 GT link: `https://1drv.ms/f/s!AittnGm6vRKLglyfiCw_C6BDeFsP` →
   `data/external/deepcrack/CRKWH100_GT/`.

   **Take now:** `CRKWH100` — the plan's chip-visibility + 1 mm GSD pilot.

   **Optional, only if CRKWH100's asphalt subset is too small for the visibility
   pilot:** `CrackLS315` (315 images, same GSD, more frames for a human chip/gap
   check). Section 4.2 excludes laser illumination from the *appearance
   reference*, so it can inform resolution limits but must not train or anchor the
   known-good reference.

   **Do not take:** `Stone331` and `Stone331_mask` — cut-stone cutting-surface
   imagery, not road, and section 4.2 keeps cut-stone data out of the appearance
   reference. Also **do not** download `CrackTree260` from its separate link: it
   belongs to the same family as Crack-Seg, and section 4.3 permits *at most one*
   crack-mask backup, which Crack-Seg already occupies.
2. Two people independently inspect 20–30 images at native resolution and answer:
   can separate chips be distinguished, and can adjacent boundary gaps be located?
   Zooming must not merely magnify ambiguity.
3. Double-annotate 10 small patches **without** model suggestions, and report the
   disagreement floor.
4. Decide whether the DeepCrack licence statement ("academic research") is
   acceptable for this project, since the mirror's CC BY 4.0 claim conflicts.

*(The Crack-Seg licence question is closed: user decision 2026-10-15 scoped it to
internal use only with no redistribution.)*

**ML agent, once imagery exists:** generate the Gate 0 contact sheet at native
resolution, run the classical pilot, compute the human-vs-model comparison, and
record the supported feature-size range with a separate go/no-go for chips and
gaps.
