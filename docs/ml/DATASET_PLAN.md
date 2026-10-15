# Dataset acquisition plan — what to download, and what each one is for

**Date:** 2026-10-16 · **Feeds:** final plan §4.2, §4.3, §5 · **Owner:** ML role

Derived from final plan §4.2 (the authoritative source list) plus the verified
inventory in `3ultraanalysis.md`. Every entry states its role, so no dataset is
downloaded without a named consumer.

## Situation constraints

- **Dr. Zou is unreachable.** So the CRKWH100 1 mm/px claim (`A1.6`) can never be
  confirmed from the author, and the native line-array originals cannot be
  requested. CRKWH100 scale stays `unverified` and **no mm value may be published
  from it.** It remains usable for appearance, texture-proxy development and
  negatives.
- **Chip counting is mandatory.** That makes a chip-scale source the critical
  path, and it must come from somewhere other than Zou.

---

## Tier 1 — download now (unblocks work already in progress)

| # | Dataset | Link | Why now | Feeds |
|---|---|---|---|---|
| 1 | **CRKWH100 crack GT** | `https://1drv.ms/u/s!AittnGm6vRKLglyfiCw_C6BDeFsP` | Crack-Seg has **1 negative in 4,029 images** and the test split has **zero**, so false alarms cannot be measured at all. CRKWH100 images without crack GT are clean negatives from one camera and one surface family. | E8, E10, I12, I15, distress false-alarm measurement, A1.12 |
| 2 | **RDD2022 — India subset** | `github.com/sekilab/RoadDamageDetector` · paper `arxiv.org/abs/2209.08538` | The plan's *primary Indian distress source*. Nothing Indian exists in the project yet. Freeze an Indian test subset **before** any annotation-driven training. | E8, E9, I12, `distress_india_test`, India claim |
| 3 | **Pavementscapes** | `github.com/tongzheng1992/Pavementscapes` · paper `arxiv.org/pdf/2208.00775` | 4,000 **top-down** grayscale images, 6 damage categories. Top-down is the correct geometry for counting particles on a plane — every other candidate is oblique or unknown. Also the plan's preferred distress-mask pretraining source. | E8 pretraining, chip pilot, E4/E5 |

## Tier 2 — request access (the chip critical path)

These are the only documented chip-scale sources that do not involve Zou. Both
are request-gated, so send both requests on day one; they have latency.

| # | Dataset | Link | Claimed scale | Feeds |
|---|---|---|---|---|
| 4 | **ISTD-PDS7** | paper `mdpi.com/2072-4292/15/7/1750` — access by request to the authors | **0.91 mm/px** on original CCD imagery; 18,527 images | Chip counting (A1.9, A3.x, E4/E5), gap width, chip-scale reference. **The single most important request.** |
| 5 | **GAPs v2 / GAPs 10m** | `tu-ilmenau.de/…/german-asphalt-pavement-distress-dataset-gaps` — `pip install gaps-dataset`, email the signed PDF form | **1.2 mm/px** (original); 10m release is 20 expert-labelled 5030×11505 images | Chip backup, distress masks (6 FGSV classes), reference-method validation |

> **ISTD-PDS7 is the one to chase.** Its paper documents a per-image GSD, which
> is exactly what CRKWH100 lacks. If it arrives, the chip requirement has a real
> scale to stand on. Note the plan's caution: a published GSD must be confirmed
> against the *delivered* files, because the CRKWH100 experience shows a claimed
> scale and a delivered file are not the same thing.

## Tier 3 — already in hand

| Dataset | State | Feeds | Limitation |
|---|---|---|---|
| **Crack-Seg** | 4,029 images, 5,290 real-width crack polygons | D8 ✅, I16 ✅, E8, E10 | 416×416, scale unknown, ~no negatives |
| **CRKWH100** | 100 images × 512×512 | Texture proxies (D7), negatives, appearance reference | Chips **not resolvable** (see `CHIP_VISIBILITY_EVIDENCE.md`); scale unverifiable |
| **asphalt-3d-laser-texture** | 900 3-D height maps @ 0.05 mm/px + PTV, CC-BY-4.0 | Texture-proxy validation, MTD/MPD study | Height maps are **not paired RGB**, so they validate geometry, not an RGB→texture mapping. Plan defers it for good reason |

## Tier 4 — optional, deferred, or rejected

| Dataset | Decision | Reason |
|---|---|---|
| **Indian seasonal paved/unpaved** (`data.mendeley.com/datasets/tj2m7zz4rg/2`) | **Tier 2 priority** — download after Tier 1 | The only Indian robustness set; wet appearance and unsupported surfaces. Feeds `india_challenge_test`. Group rotations/resized/video siblings. |
| **comma2k19** (`github.com/commaai/comma2k19`, MIT) | Deferred | Replay plumbing only. Not chip-scale, not a grade label. ~100 GB. Take only if a route demo is needed before live capture. |
| **RoadCrack_DL_HY-corrected** (HuggingFace, 3.01 GB) | Reserve | 2,189 clean images, 4 crack classes, zero-leakage splits — high quality, but non-commercial licence and not Indian. Better than Crack-Seg for splits; take if E8 needs more data. |
| **UAV-PDD2023** (CC-BY-4.0) | Deferred | UAV domain, not chip measurement. Take only to fix a measured failure. |
| **SDNET2018** | Rejected | Concrete classification is a detour; a generic encoder is simpler. |
| **KITTI / BDD100K / Mapillary** | Rejected for now | Driving-scene data are not chip labels. Large downloads with no chip consumer. |
| **Roboflow loose-aggregate / 8 mm–40 mm projects** | Rejected as calibration | Loose particles are not embedded pavement; a size in a class name is not image scale. Usable only as annotation-method practice. |
| **MVTec AD, DTD, synthetic Voronoi stones** | Algorithm tests only | Synthetic shapes validate arithmetic, never road-condition truth. |

---

## Coverage matrix — which branch each dataset serves

| Branch | CRKWH100 | Crack-Seg | RDD22-IN | Pavementscapes | ISTD-PDS7 | GAPs | Indian seasonal | CRKWH100 GT |
|---|---|---|---|---|---|---|---|---|
| Chip count / size (A, E4-E6) | ✗ unresolvable | — | — | ✓ geometry | **✓ scale** | ✓ backup | — | — |
| Gap width (D4/D5) | ✗ | — | — | — | **✓** | ✓ | — | — |
| Texture proxies (D7, F1) | ✓ have it | — | — | — | ✓ | — | ✓ wet | — |
| Distress masks (D8, E8) | — | **✓ have it** | ✓ boxes | ✓ masks | | ✓ masks | — | — |
| **Negatives / false alarms** | — | ✗ none | ✓ | ✓ | | | ✓ | **✓ intended** |
| India performance claim | — | — | **✓ required** | — | — | — | ✓ | — |
| Metric scale (mm) | ✗ unverified | ✗ | ✗ | ✗ unverified | **✓ 0.91 mm** | ✓ 1.2 mm | ✗ | ✗ |
| Route/demo replay | — | — | — | — | — | — | — | — |

`✓` = usable, `✗` = not usable, blank = not applicable.

## Read this before downloading anything

1. **Do not download everything.** The plan is explicit: move to the next source
   when access, rights, scale or visibility blocks progress.
2. **Record provenance before use.** URL, version, checksum, exact reuse terms,
   upstream parents. Run `python -m eval.dataset_audit --path <dir> --name <name>`.
3. **Scale is per-file, not per-dataset.** A published GSD must survive the
   delivered file. CRKWH100 proves it may not.
4. **Group before splitting.** Rotations, resized copies and video siblings of
   one frame must land in the same split (Mendeley seasonal set, Pavementscapes
   crops).
5. **Freeze the Indian test subset before annotation-driven training**, or the
   India claim becomes circular.

## Open decisions that change this plan

| Decision | Consequence if it goes the other way |
|---|---|
| Can humans chip-label at 0.91 mm/px (A2.2)? | If not, chip counting needs synthetic ground truth and the claim narrows to "validated on synthetic" |
| Does Pavementscapes' delivered GSD survive inspection? | Determines whether Tier-1 item 3 serves chips or only distress |
| Does a route need replay before live capture? | Pulls comma2k19 into Tier 2 |
| Is a GPU available for E4/E5 training? | Without it, chips stays a measurement pipeline without the learned challenger |
