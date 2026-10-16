# Annotation guide — the ML_ROLE label set

**Task:** B7 · **Owner:** ML role (`docs/ML_ROLE.md` §1, `annotation_guides/` is
ML-writable) · **Date:** 2026-10-16
**Status:** `implemented-unverified` — the guide is written; no double-labelled
pilot set exists yet (tasks B8, A2.3 are blocked on two humans).

This fixes the **definitions** every annotator must apply so that labels are
consistent between people and reproducible later. It uses the exact label set
named in `docs/ML_ROLE.md` §2. Nothing here invents a class; each one is
traceable to the final plan.

---

## If you have no domain expertise, read this first

The honest answer to "can I annotate this myself with no background?" is **yes for
distress, no for aggregate** — and the difference is not about skill, it is about
what the label requires.

### Tier 1 — you can do this today: distress masks

`crack`, `pothole`, `repair_or_patch`, plus the `ignore` and `valid_surface` masks.

**Why this is realistic without domain expertise:** these are *visual* categories,
not engineering judgements. RDD2022 — the dataset this project is built on — was
labelled by crowd workers, not pavement engineers. You are not being asked to
decide *why* a crack is there or how severe it is. You are being asked to outline
what you can see.

Three rules that carry almost all of the difficulty:

1. **Outline the crack's real width, not its centreline.** If a crack is 4 pixels
   wide, the mask is 4 pixels wide. A 1-px line understates extent by ~75%.
2. **When you cannot tell, use `ignore`.** This is the safety valve. An uncertain
   region is excluded from both training and evaluation. A wrong-but-confident
   label is worse than an ignored one, because it looks like data.
3. **Do not label what you cannot see at this resolution.** If the image is too
   blurry or the crack is 1 pixel wide, `ignore` the region.

This unblocks the highest-value next step in the plan: the Indian distress mask
subset (final plan Phase 4, task B9).

### Tier 2 — achievable alone, and it trains you: self-consistency

The plan's disagreement floor (task A2.3) requires **two independent humans**. You
are one, so that specific number is not available and must not be faked.

What *is* available is your own consistency, and measuring it is the single most
useful thing you can do before annotating at scale:

1. Annotate **20 images**.
2. Set them aside for **at least 3 days** — long enough that you do not remember
   the specifics.
3. Re-annotate the same 20 **blind**, without looking at your first pass.
4. Measure agreement, and report it as **`intra_annotator_agreement`**.

This is *not* `inter_annotator_agreement` and the report must say so. It measures
how repeatable you are, not whether two people agree.

The real value is diagnostic: **any image you disagree with yourself on is an image
you cannot reliably label.** Those go to `ignore`. After two or three rounds this
converges on a short list of genuinely ambiguous cases, and that list is exactly
what the `ignore` policy and the annotation guide exist for. You will also find
your own consistency improving, which is the training effect you are looking for.

### Tier 3 — genuinely blocked. Do not attempt.

- **Chip / aggregate / gap annotation.** This needs (a) *verified* physical scale,
  and (b) a judgement about whether separate chips are resolvable at this
  resolution. Both are unresolved (tasks A1.6, A2.2). Tracing speckle and calling
  it chips is the specific failure final plan §5.1 step 7 forbids.
- **`human_condition`.** Needs two blinded raters plus a third adjudicator (task
  B10), and is pending D3's confirmed definitions of "chip boundary width" and
  "roughness".
- **Any millimetre figure.** CRKWH100's 1 mm/px is unverified (A1.6) and RDD
  supplies no scale at all. Label in pixels; never in mm.

---

## Ground rules (final plan §6.3)

1. **Label from the native-resolution pixels, not from a model.** The unaided
   human pilot comes *before* any model proposal (SAM2 may only *propose*, after
   the pilot, and every accepted proposal is reviewed — task B12).
2. **When in doubt, use `ignore`.** An uncertain region is excluded from both
   training and evaluation rather than guessed. A wrong confident label is worse
   than an ignored region.
3. **Do not manufacture chip ground truth.** If separate chips are not resolvable
   at this resolution (see `CHIP_VISIBILITY_EVIDENCE.md`), do **not** trace
   speckle and call it chips. That is the failure mode final plan §5.1 step 7
   explicitly forbids.
4. **Group before splitting.** Rotations, resized copies, adjacent frames and
   video siblings of one source must stay in one split (task B1). Do not treat
   them as independent roads.

## The label set

## Two-person pilot (distress only)

1. Select 20 native-resolution India RDD images from distinct source/road groups;
   include visible distress and apparently intact road. Record source, parent/group,
   image hash and split role before annotation. Keep all 20 outside model training.
2. Two annotators independently paint `crack`, `pothole`, `repair_or_patch`,
   `valid_surface` and `ignore` from the original pixels. Do not show either
   annotator the other's work or RDD boxes during the first pass. Save separate
   manifests with annotator IDs; never overwrite the first pass.
3. Compare class masks on their common native-resolution canvas. A third teammate
   reviews disagreements, retains both original masks and writes an adjudicated
   mask only with a reason. If the visible boundary remains ambiguous, mark it
   `ignore`; do not force agreement.
4. Report per-image/per-class pixel agreement and the number/area of ignored
   regions. Label this a small pilot, not accuracy evidence or an independent test.
   `human_condition` still needs its agreed rubric; chip/gap annotation still
   needs verified scale and visibility evidence.

Do not use the RDD development split as a final test. These annotations are a
human-reviewed pilot, not a replacement for source provenance, group separation
or a frozen held-out evaluation set.

| Label | What it marks | Notes |
|---|---|---|
| `visible_aggregate_instance` | One exposed-aggregate particle (chip) that is individually distinguishable | Only when it genuinely is. If chips are not separable here, mark the area `ignore` and record that in the pilot sheet — do not invent instances. Instance-level: each particle is its own id. |
| `ignore` | Region excluded from training AND evaluation | Ambiguous chips, unresolved speckle, heavy shadow/glare, motion blur, or anything two annotators would clearly disagree on. Never scored as background. |
| `valid_surface` | Asphalt surface that is measurable in this frame | The denominator mask. Driveways, markings, gravel, mud and non-asphalt are **outside** this. Kept separate from damage so a damaged-but-supported patch is still valid surface (final plan §9.1). |
| `crack` | A crack — a linear/near-linear surface separation | Real-width outline, not a 1-px centreline (final plan §4.3). Extent/length derive from this mask. |
| `pothole` | A pothole — a bowl-shaped loss of surface with visible depth | Distinguish from a shallow scuff: a pothole loses surface *depth*, not just colour. |
| `repair_or_patch` | A previous repair / patch / seal band | Marked so it is **not** counted as distress, and so surface-family / severity logic can treat it separately. A repair is not automatically "good" or "bad". |
| `surface_family` | The material/appearance class of the supported surface (e.g. asphalt, concrete, gravel, unpaved) | Image-level or region-level. Used for the **domain-support** gate so an unfamiliar material is *abstained on*, not mis-scored as damaged (final plan §9.1). |
| `human_condition` | A whole-patch condition rating from the agreed rubric | **Pending D3.** The judge's exact definitions of "chip boundary width" and "roughness" are not yet confirmed, so the rubric is provisional until then. Two blinded raters + a third adjudicator (task B10). |

## Aggregation notes

- `crack` and `pothole` feed `distress burden D`; `visible_aggregate_instance`
  feeds count/size/texture features. The two are **separate** evidence streams
  and must not be merged into one "damage" mask.
- `ignore` regions are removed from every denominator, so excluding a pothole from
  texture never erases its distress contribution (denominator safeguard, final
  plan §7.3).
- `surface_family` gates *domain support*; it must never be used to discard a
  damaged patch as "unfamiliar material".

## Tooling

`annotation_guides/annotate.html` is a single-file browser tool that needs **no
install, no Python and no internet** — open the file, click *Load folder*, pick a
folder of images, and paint masks with a brush. It writes one small JSON per image
plus a CSV index, in the ML_ROLE label vocabulary above.

It exists because "I do not know how to annotate datasets" is much more often
"there is no tool I can actually start with" than it is "I cannot tell a crack
from a pothole". Brush painting with an undo button and a fixed label set removes
the tooling barrier completely; the judgement remains, which is why the
self-consistency protocol above is still required.

## What this guide does NOT establish

It defines labels, not results. No double-labelled set exists yet, so the
**inter-annotator disagreement floor** (task A2.3 / A3.3) is unmeasured — it
requires two humans and is not obtainable by one person measuring themselves.

The **intra-annotator** self-consistency number described above is achievable
today and is the honest substitute. It must always be labelled
`intra_annotator_agreement` so it is never read as inter-annotator agreement.
