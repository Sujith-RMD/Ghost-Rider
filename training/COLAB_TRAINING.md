# Colab training runbook — both distress models

Companion to **`training/COLAB_TRAINING.ipynb`** — upload that file to Colab
(*File → Upload notebook*) and run the cells in order. This document explains what
the notebook does and what the output numbers mean.

No GPU is required to follow this. A free Colab T4 runs the whole thing.

`COLAB_E8.md` was the previous single-model runbook; it is superseded.

---

## The one thing to get right

**No data is committed to the repo.** The 14 GB RDD archive, the Crack-Seg zip and
the CRKWH100 masks are all local-only. Google Drive is the bridge between your
laptop and Colab.

Put this on Drive **once**:

```
roadsight_data.zip     crack-seg.zip + CRKWH100_gt/    ~120 MB
rdd2022_india/         extracted India images + manifest.json   ~0.5 GB
```

> **Do not upload `rdd2022-DatasetNinja.tar`.** It is 14 GB and it will blow
> through a free Drive quota. The India subset that actually gets trained on is
> 0.5 GB. `training/prepare_india_distress.py` already did the selection locally.

---

## The two models, and why they are separate

| | A · `distress_yoloseg` | B · `india_detection` |
|---|---|---|
| Source | Crack-Seg (foreign) | **RDD2022 India** |
| Labels | polygons | **boxes only** |
| Resolution | 416×416 close-up | 720×720 oblique |
| Feeds | defect **area** measurement | the **India claim** |

Final plan §8.2 sanctions the second ("a small YOLO detector on RDD India is a
temporary localization baseline") and explicitly warns: *"Do not build both as
mandatory permanent branches unless evaluation establishes a need."* Model B is
therefore **provisional** until Indian mask annotation exists.

Building the India model is still worth it now, because it produces the one number
nothing else can: a false-positive rate on **intact** Indian roads.

---

## Expected output

| Artifact | Where | What it is |
|---|---|---|
| `best.pt` | `runs/roadsight/<name>/weights/` | trained weights → copied to Drive |
| `crosssource_eval.json` | `reports/ml/` | model A scored on CRKWH100 |
| val metrics | printed by `yolo detect val` | model B's mAP50 on the frozen dev split |

Weights go to Drive, **not** git — they are large binaries and do not belong in
history. Reports and manifests do go to git, because they are the evidence.

---

## Reading the numbers

### Model A (cross-source)

| Metric | Reading it |
|---|---|
| `pixel_iou_mean` | Overlap of predicted cracks with true cracks |
| `pixel_precision_mean` | Of predicted crack pixels, how many were real |
| `pixel_recall_mean` | Of real crack pixels, how many were found |
| `dice_p10` | The bad tail — a mean hides the 10% worst images |
| `extent_ratio_pred_over_gt` | Systematically over- or under-sizing cracks |

Two caveats travel with every report:

1. **`false_alarm_measurable: false`.** CRKWH100 is a crack dataset — all 100
   images contain cracks. Pixel metrics are measurable against their crack and
   background pixels. An **intact-image false-alarm rate is not measurable**
   without representative negatives. *(This is exactly what model B fixes.)*
2. **All metrics are in pixels.** CRKWH100's 1 mm/px claim is unverified, so no mm
   or m² figure may be derived from these images.

### Model B (India)

- `mAP50` on the 1,541 frozen dev images.
- The per-class table; `transverse crack` has only 113 boxes in the whole split,
  so its score is unstable and should be reported as indicative only.
- **The false-positive rate on the 3,934 negative images.** This is the first
  time the project has been able to measure it at all. Until this model, Crack-Seg
  gave 1 negative in 4,029 and CRKWH100 gave 0.

---

## What "good" looks like

No target has been frozen. Final plan §13.2 requires thresholds to be set on
development evidence *before* final testing, judgement is:

- Model A's Dice comfortably above the trivial baselines (predict-nothing is 0.0;
  predict-everything is ≈ 0.007 here, since crack extent averages 0.36%).
- `dice_p10` not catastrophically below the mean, which would mean a few images
  carry the score.
- Model B's mAP well above the trivial box baseline, and a false-positive rate
  low enough that a good/bad flag means something.
- Audit training-source ancestry before calling CRKWH100 independent of Crack-Seg.
  A different dataset name is not proof of disjoint source images.

---

## If it fails

| Symptom | Cause and fix |
|---|---|
| `clone failed` | Private repo. Use the `https://<TOKEN>@github.com/...` form the cell prints. |
| `'roadsight_data.zip' not found under /content/drive/MyDrive` | Wrong name, or nested in a folder. Read the candidates the cell printed. |
| `unzip: cannot create extraction directory` | Should not happen — `extract()` creates parents first. Report it if you see it. |
| `ModuleNotFoundError: No module named 'training'` | The `%cd` was skipped or run out of order. Re-run Step 1. |
| `DataLoader worker ... exited unexpectedly` | Colab dataloader quirk. Halve `--batch`; do not raise epochs. |
| CUDA out of memory at 720 | `--batch 4`, or `--imgsz 640`. |
| Loss will not drop at all | Overfit one image (batch 1). If that fails, the **labels** are wrong, not the learning rate. |
| Model A good on Crack-Seg, poor on CRKWH100 | Expected — that is domain shift, not a bug. Diagnose on development data. |
| Model B mAP near zero | Check the `assert len(imgs) == len(lbls)` cell passed. An all-empty label set would still "train". |
| Runtime disconnected mid-run | Colab free tier has a ~12 hour cap; the notebook does not checkpoint. Restart from Step 6 with fewer epochs. |

---

## After training

1. Keep `best.pt` on Drive and record its sha256 in `docs/ml/changelog.md`.
2. Push `reports/ml/*.json` and any updated manifest to the repo.
3. Update `docs/ml/TASKS.md`: model B moves from `[ ]` to `[~]` — it is a
   localization baseline, **not** a defect-area measurement (final plan §8.2).
4. The aggregate engine is untouched by this runbook and remains the blocked
   dependency. See `docs/ml/TASKS.md` A2/B9.
