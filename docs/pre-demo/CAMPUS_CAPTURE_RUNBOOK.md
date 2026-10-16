# Campus capture runbook

Use original phone files and keep them local. Do not invent GPS, distance, physical scale, or road-quality scores. The current analyzer produces exploratory pixel-space candidates; a manual ROI limits the reported region but does not validate chip counts.

Before starting, install `models/india_rdd2022_yolov8n/best.pt` locally and verify its SHA-256 is `ff477bb3aaeb3559bf8f3c040acf55ab3b468b520c21fb8d6bc1fa9d03204881` with `Get-FileHash models/india_rdd2022_yolov8n/best.pt -Algorithm SHA256`. Keep the weight out of Git. Confirm the app reports `distress_detection.status: success`; an upload alone does not prove the detector ran.

## Start the local app

From the repository root, in two PowerShell windows:

```powershell
$env:GHOST_RIDER_DISABLE_DOTENV = '1'
$env:GHOST_RIDER_LOCAL_ONLY = 'true'
$env:GHOST_RIDER_DB_PATH = '.runtime/demo/road_quality.db'
$env:UPLOADS_DIR = '.runtime/demo/uploads'
$env:LOCAL_UPLOADS_PUBLIC = 'true'
.venv\Scripts\python.exe -m uvicorn backend.api.server:app --host 127.0.0.1 --port 8000
```

`GHOST_RIDER_LOCAL_ONLY=true` is the explicit safety switch: uploads and images stay on local disk, and S3 and Bedrock calls are disabled even if AWS keys, a shared profile, or an instance role are available. Reports use the deterministic local template. Do not rely on an empty bucket variable to disable cloud storage; configuration supplies the default bucket when it is empty.

```powershell
cd web
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8000'
npm run build
npm run preview -- --host 127.0.0.1 --port 4173
```

Open `http://127.0.0.1:4173`. The production build uses the real API; do not use the development fixture app as integration evidence.
If preview uses a different port, set `CORS_ORIGINS` to that exact browser origin before starting the API, then rebuild the frontend with the matching `VITE_API_BASE_URL`.

## Copy and inspect captures

```powershell
$capture = 'D:\RoadSightDemo'
New-Item -ItemType Directory -Force "$capture\originals", "$capture\frames", "$capture\evidence" | Out-Null
Copy-Item 'C:\path\to\phone\photos\*' "$capture\originals" -File
Copy-Item 'C:\path\to\phone\videos\walk.mp4' "$capture\originals\walk.mp4"
```

Check image decoding and native dimensions:

```powershell
.venv\Scripts\python.exe -c "import cv2,sys; p=sys.argv[1]; im=cv2.imread(p); print({'path':p,'decoded':im is not None,'width_px':None if im is None else im.shape[1],'height_px':None if im is None else im.shape[0]})" "$capture\originals\road.jpg"
```

Keep the ruler/reference visible in the original capture. Calibration is not yet automated; physical values remain unavailable until calibration is reviewed and validated.

## Extract video frames

FFmpeg must be installed and available as `ffmpeg`:

```powershell
ffmpeg -i "$capture\originals\walk.mp4" -vf "fps=1" -q:v 2 "$capture\frames\frame_%05d.jpg"
ffmpeg -ss 00:00:03.500 -i "$capture\originals\walk.mp4" -frames:v 1 "$capture\frames\selected_003500.jpg"
```

One frame per second is a review/sample rate, not a distance or continuous-coverage measurement. Preserve the video and note the source filename and timestamp for any selected frame.

## Run processing evidence

For a downward-facing pavement-only frame, omit the ROI mask and note that full-frame is a provisional road assumption. For an oblique image, first create a same-resolution binary PNG mask (white = inspected road, black = everything else) and review it manually. The supplied mask constrains downstream pixel measurements; it does not make candidate labels ground truth.

```powershell
.venv\Scripts\python.exe -m eval.processing_evidence --image "$capture\originals\road.jpg" --output-dir "$capture\evidence\road"
.venv\Scripts\python.exe -m eval.processing_evidence --image "$capture\originals\oblique.jpg" --roi-mask "$capture\originals\oblique_road_roi.png" --output-dir "$capture\evidence\oblique"
```

Review `manifest.json`, `original.*`, and the stage PNGs. Reject blurry, wet, heavily shadowed, or incorrectly masked examples rather than treating them as clean training/testing data. Do not put raw campus imagery or model weights in Git without explicit privacy and rights review.

## Upload through the local API

```powershell
$image = "$capture\originals\road.jpg"
$bytes = [System.IO.File]::ReadAllBytes($image)
$slot = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/v1/uploads' -ContentType 'application/json' -Body (@{ filename = [IO.Path]::GetFileName($image); content_type = 'image/jpeg'; expected_size = $bytes.Length } | ConvertTo-Json)
Invoke-RestMethod -Method Put -Uri "http://127.0.0.1:8000$($slot.upload_url)" -ContentType 'image/jpeg' -Body $bytes
$job = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/v1/uploads/$($slot.upload_id)/finalize" -ContentType 'application/json' -Body (@{ source_mode = 'upload' } | ConvertTo-Json)
"Job queued: $($job.job_id). Open Assess/Samples in the app to follow the stored result."
```

For video frames, repeat the same upload for a small reviewed selection. Do not report frame count as distance. GPS-backed route location is available only from real device metadata and valid fixes.

## Review and record campus transfer

For each original JPEG or selected MP4 frame, record the source file and video timestamp (if applicable), image dimensions, camera angle, lighting/wetness, upload/job/sample IDs, detector status and inference time, each predicted class/confidence/box, and whether a human reviewer agrees that each box lies on the relevant road defect. Record visible defects the model misses, wrong-class boxes, boxes on vehicles/sky/shadows, and unusable images. Keep a small reviewed set of positive and visibly clear images; do not infer accuracy from a single successful prediction. The RDD India model was trained on forward-looking road scenes, so downward-facing phone imagery has unmeasured domain shift until this review is done.

Keep watershed candidate counts separate from YOLO distress boxes. Full-frame candidates on oblique scenes can include sky, vegetation and vehicles; use a reviewed road ROI or mark the result unsuitable. Crack width, pothole depth, chip density, road grade and quality score remain unavailable without separately validated measurements and calibration.
