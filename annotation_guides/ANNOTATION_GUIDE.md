# Annotation guide — the ML_ROLE label set

**Task:** B7 · **Owner:** ML role (`docs/ML_ROLE.md` §1, `annotation_guides/` is
ML-writable) · **Date:** 2026-10-16
**Status:** `implemented-unverified` — the guide is written; no double-labelled
pilot set exists yet (tasks B8, A2.3 are blocked on two humans).

This fixes the **definitions** every annotator must apply so that labels are
consistent between people and reproducible later. It uses the exact label set
named in `docs/ML_ROLE.md` §2. Nothing here invents a class; each one is
traceable to the final plan.

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

## What this guide does NOT establish

It defines labels, not results. No double-labelled set exists yet, so the
**human disagreement floor** (task A2.3 / A3.3) is unmeasured, and no model error
may be compared against it until two people have double-labelled the 10 patches in
`aggregate_patch_annotation_template.csv`.
