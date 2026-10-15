# Chip visibility evidence — what the measured data says

**Status:** measurement complete. Decision pending A1.6/A1.9 (source metadata).
**Date:** 2026-10-16. **Feeds:** A1.6, A2.2, A2.4, A3.2, E3.

Chip counting is a stated project requirement and remains in scope. This
document records what the imagery in hand actually contains, because the
requirement can only be met if the measurement is physically possible.

## The requirement, in pixels

A chip is exposed aggregate roughly 4–20 mm across. At the CRKWH100 *claimed*
ground sampling distance of 1 mm/pixel that is 4–20 px diameter, i.e. an
inscribed radius of 2–10 px and an area of 12–314 px². Anything the sensor
actually delivers coarser than that makes counting arithmetically impossible,
regardless of the algorithm or the annotator.

## What was measured

Three independent measurements, all on the delivered 512×512 files, all
repeated after the other role updated the segmentation config
(`agg-classical-v1` → `agg-classical-v3`, which added h-maxima markers, hole
filling and a minimum-instance-area filter). The conclusion did not change, so
it is not an artefact of one config.

**1. Distance-transform ceiling.** The largest inscribed circle anywhere in the
foreground is 3.2–6.0 px across six sampled images. A 10 mm chip at 1 mm/px
needs 10 px.

**2. Instance size distribution** (current config, six images): 3,121–3,790
fragments, median area 8 px, median equivalent diameter **3.19 px**, p90 area
23 px. A 10 mm chip is 78 px². Essentially no fragment reaches chip scale.

**3. Multi-scale stability sweep.** If chip structure existed, blob detection at
the chip scale would *stabilise* — a roughly constant count and size over a
range of smoothing. Instead the count falls monotonically and never plateaus:

| median filter k | regions | median top-10 area | max area |
|---|---|---|---|
| 1 | 14,170 | 46 | 87 |
| 3 | 5,368 | 104 | 145 |
| 5 | 2,927 | 131 | 237 |
| 9 | 1,410 | 174 | 349 |
| 15 | 517 | 153 | 197 |
| 21 | 156 | 77 | 226 |
| 31 | 19 | 36 | 178 |

1,410 → 517 → 156 is progressive merging of an undifferentiated speckle field,
not the emergence of discrete particles. A chip mosaic on 0.25 m² at ~500
chips/m² would give ~125 chips per image and would hold stable across several
scales. No such plateau exists.

## Conclusion, stated honestly

**Chip-scale structure is not resolvable in the CRKWH100 512×512 delivery.**
This is not a segmentation failure: three different methods agree, and the whole
image works fine for distress-level contrast. It is a statement about what the
pixels contain.

The most likely cause is exactly **A1.6**. A line-array pavement scan is a long
strip, so the native capture is far larger than 512×512 per frame. If the
delivered files were *downsampled* to 512×512, the true GSD is much coarser than
1 mm/px and chips occupy well under one pixel — which matches every measurement
above. If they are *crops* of a native scan, the GSD is preserved and the chips
should be visible, which would contradict the measurements and force a
re-examination of the lossy high-pass in the segmentation path.

These two possibilities are distinguishable in one question to Dr. Zou, and that
question is A1.6.

## Why this is not a no-go

A no-go would require evidence that chips are unmeasurable *given adequate
data*. That has not been shown. What is shown is that this particular delivery
does not carry the feature. Two independent routes remain open, both of which
preserve the chip requirement:

1. **A1.6 — obtain the native CRKWH100 files.** If the 512×512 files are
   downsamples, the originals carry the chips. Dr. Zou is the dataset author and
   on the project, so this is the cheapest possible resolution.
2. **A1.9 — ISTD-PDS7**, whose paper documents 0.91 mm/px on original CCD
   imagery. This is the only *documented* chip-scale source found, and it is an
   access request rather than a download.

## What must not happen

Per final plan §5.1 step 7: do not manufacture chip ground truth from
watershed or SAM2 output and call the requirement met. An unsupervised mask on
a speckle field where no chips are resolvable would produce a plausible-looking
count with no physical meaning, and it would fail the first time anyone zoomed
in.

## What this does not affect

Distress measurement is unaffected. Crack-Seg carries real crack polygons with
real-width outlines, and the distress engine and its evaluation harness
(`backend/distress/features.py`, `eval/distress_eval.py`) are implemented and
tested on it.
