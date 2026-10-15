# Colab training run — distress engine (E8)

**No GPU needed to follow this.** A free Colab T4 finishes it in ~10-15 minutes.
Verify dataset reuse and redistribution rights before uploading data; public download access alone does not establish permission.

---

## Step 0 — get the code and data into Colab

**Option A — from Google Drive (recommended)**

1. On your laptop, zip the repo's `data/external` folder (Crack-Seg + CRKWH100):
   ```powershell
   Compress-Archive -Path data\external\crack-seg,data\external\CRKWH100_gt,data\external\deepcrack `
                    -DestinationPath $env:USERPROFILE\Desktop\roadsight_data.zip
   ```
2. Upload `roadsight_data.zip` to Google Drive (any folder; note the path).
3. Also zip the repo itself, or clone it fresh. Simplest: upload a zip too.

**Option B — re-download Crack-Seg in Colab** (91.6 MB; subject to verified reuse rights)

```python
!wget -q https://github.com/ultralytics/assets/releases/download/v0.0.0/crack-seg.zip
!unzip -q crack-seg.zip -d /content/data/external
```

For CRKWH100 (25 MB) and its GT, in Colab:

```python
!mkdir -p /content/data/external/deepcrack /content/data/external/CRKWH100_gt
# paste the OneDrive direct-download URLs from DeepCrack's README
```

---

## Step 1 — open the notebook and install

Open <https://colab.research.google.com>, **Runtime → Change runtime type → T4 GPU**,
then in the first cell:

```python
!pip install -q ultralytics
import sys, os
if "/content" not in sys.path:
    sys.path.insert(0, "/content")
print("ready")
```

---

## Step 2 — mount Drive and unzip

```python
from google.colab import drive
drive.mount("/content/drive")

!unzip -q "/content/drive/MyDrive/roadsight_data.zip" -d /content/data/external
# verify:
!ls /content/data/external
!ls /content/data/external/crack-seg/images | head
!ls /content/data/external/CRKWH100_gt/CRKWH100_gt | head -3
```

Expected:
```
crack-seg   CRKWH100_gt   deepcrack
train  test  val
1000.bmp  1001.bmp  1002.bmp
```

---

## Step 3 — train

```python
!python -m training.train_distress_yoloseg \
    --data /content/data/external/crack-seg \
    --epochs 60 --imgsz 416 --batch 16 --device 0
```

Expected tail output: a JSON block with `save_dir`, the seed, and a note that
evaluation is cross-source. The weights land in
`runs/roadsight/distress_yoloseg/weights/best.pt`.

**Sanity check first (2 minutes, confirms the pipeline works):**
```python
!python -m training.train_distress_yoloseg --data /content/data/external/crack-seg \
    --epochs 2 --imgsz 416 --batch 8 --device 0 --name smoke_test
```
If this finishes, the data paths are correct. Kill it and run the real thing.

---

## Step 4 — evaluate cross-source

```python
!python -m training.evaluate_crosssource \
    --weights runs/roadsight/distress_yoloseg/weights/best.pt \
    --manifest /content/data/manifests/crkhw100_test.json \
    --out /content/reports/ml/crosssource_eval.json
```

This scores the model on **CRKWH100** — a different sensor, resolution (512 vs
416) and geography from Crack-Seg. That is the honest cross-source test, and it
is *not* an Indian test.

---

## Step 5 — bring the results back

```python
from google.colab import files
files.download("/content/reports/ml/crosssource_eval.json")
files.download("runs/roadsight/distress_yoloseg/weights/best.pt")
```

Then drop `crosssource_eval.json` into the repo at `reports/ml/` so it is
recorded with the run.

---

## What the numbers will mean

| Metric | Reading it |
|---|---|
| `pixel_iou_mean` | Overlap of predicted cracks with true cracks |
| `pixel_precision_mean` | Of predicted crack pixels, how many were real |
| `pixel_recall_mean` | Of real crack pixels, how many were found |
| `dice_p10` | The bad tail — a mean hides the 10% worst images |
| `extent_ratio_pred_over_gt` | Systematically over- or under-sizing cracks |

**Two caveats printed with every report:**

1. **`false_alarm_measurable: false`.** CRKWH100 is a crack dataset — all 100
   images contain cracks. Pixel precision, recall, IoU and Dice are measurable
   against their background and crack pixels. An **intact-image false-alarm
   rate** is not measurable without representative negative images.
2. **All metrics are in pixels.** CRKWH100's 1 mm/px claim is unverified, so no
   millimetre or m² figure may be derived from these images.

## What "good" looks like

No target has been frozen — the plan requires thresholds to be set on
development evidence, before final testing (final plan §13.2). When you get the
numbers, judgement is:

- Dice comfortably above the trivial "predict nothing" baseline (0.0) and above
  "predict every pixel" (≈ 0.007 here, since crack extent averages 0.36%)
- `dice_p10` not catastrophically below the mean, which would mean a few images
  carry the score
- Audit training-source ancestry before calling CRKWH100 independent. A different
  dataset name or sensor is not proof of disjoint source images; cross-source
  Dice need not be lower because annotation and difficulty also differ.

## If it fails

| Symptom | First move (final plan §8.4) |
|---|---|
| Loss will not drop | Drop to 1 image and overfit it; if that fails, the labels or the loader are wrong |
| Good train, poor cross-source | Diagnose shift on development data. If these test results inform changes, this set becomes development and a fresh independent test is needed |
| Predicts everything as crack | Check mask post-processing and imbalance; tune confidence only on development data |
| Very slow | Lower `batch` or `imgsz`, keep `device 0` |
