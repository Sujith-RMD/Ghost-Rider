# India RDD2022 YOLOv8n run

## Result

Completed a 60-epoch pretrained YOLOv8n detection run on the frozen RDD2022 India train/development split using a Colab Tesla T4. The Ultralytics stride rounded the configured 720-pixel input up to 736 pixels. The best checkpoint reached development precision **0.395**, recall **0.349**, mAP@0.50 **0.337**, and mAP@0.50:0.95 **0.152** across 1,541 development images and 1,640 labeled boxes.

The full metric record is [rdd_india_yolov8n_colab_final_metrics.json](../../reports/ml/rdd_india_yolov8n_colab_final_metrics.json). Colab produced a 6,623,293-byte bundle with checkpoint SHA-256 `ff477bb3aaeb3559bf8f3c040acf55ab3b468b520c21fb8d6bc1fa9d03204881` and bundle SHA-256 `335c88959c85df631a0f67d18b7a64247c72066043d3ff553cab523d9cf39a9a`. The bundle is in the Colab notebook export cell: [open the training notebook](https://colab.research.google.com/drive/1ehQoGV8odkb_TpHc_p8sTe_R8aphx2J_).

## Class results

| Class | Dev images | Boxes | Precision | Recall | mAP@0.50 | mAP@0.50:0.95 |
|---|---:|---:|---:|---:|---:|---:|
| Alligator crack | 340 | 387 | 0.510 | 0.563 | 0.546 | 0.262 |
| Longitudinal crack | 255 | 365 | 0.390 | 0.271 | 0.261 | 0.115 |
| Other corruption | 179 | 223 | 0.446 | 0.493 | 0.415 | 0.205 |
| Pothole | 300 | 642 | 0.530 | 0.376 | 0.387 | 0.151 |
| Transverse crack | 18 | 23 | 0.099 | 0.0435 | 0.0748 | 0.0281 |

Block crack and repair are absent from this India split, so those classes have no measured performance. Transverse crack has too few examples for a stable claim.

## Local integration and inference check

The extracted checkpoint is installed at the ignored path
`models/india_rdd2022_yolov8n/best.pt` (6,527,786 bytes). Its SHA-256 matches
the Colab run: `ff477bb3aaeb3559bf8f3c040acf55ab3b468b520c21fb8d6bc1fa9d03204881`.
The bundle ZIP was verified in Colab; only the extracted checkpoint was available
for this local installation. The API uses the checkpoint when present, runs on
CUDA when available and otherwise uses CPU, and reports an explicit unavailable
status when the file is missing. The weight file is ignored by Git and must be
copied to this path on each deployment.

Local CPU inference on a labeled development example (`India_000024.jpg`)
returned an alligator-crack box at confidence 0.642. A saved visual preview is
[India_000024_predictions.jpg](../../reports/ml/india_yolov8n_inference/India_000024_predictions.jpg).
The complete sample record is
[sample_inference_results.json](../../reports/ml/india_yolov8n_inference/sample_inference_results.json).

On the 783 images whose development annotation files are empty, inference at
confidence 0.25 returned at least one box for 95 images (12.13%), with 107 boxes
total. See the per-image record in
[empty_dev_false_positive_audit.json](../../reports/ml/india_yolov8n_inference/empty_dev_false_positive_audit.json).
These are empty annotations, not confirmed defect-free roads, so 12.13% is an
empty-label alert rate rather than a verified false-positive rate. Human review
is required before treating detections as evidence.

The backend stores this localization evidence on samples and the desktop client
draws boxes over the original image. It remains separate from measurements and
quality scoring.

## Data checks and limitations

The archive passed CRC integrity checks. All 7,706 train/development images decoded, with zero corrupt images and zero invalid label rows. There are 3,934 empty label files in train and 783 in development; YOLO treated these as background images. The separate prediction-count audit on the 783 empty-label development images was completed locally on CPU and is summarized above.

The split is random-held-out and road/session independence is not established. Results are a localization baseline, not a validated live-road India result, not segmentation, and not an area or physical measurement. Do not use these boxes to compute chip area, crack width, roughness, or a calibrated Good/Bad score. The detector has substantial misses and alerts; human review and live-road validation remain necessary before treating detections as dependable evidence.

The model is an exploratory detector with substantial missed detections and false alerts, not a production-ready road-quality model. It cannot provide calibrated physical measurements or a Good/Bad score.
