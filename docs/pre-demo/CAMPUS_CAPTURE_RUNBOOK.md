# Campus capture runbook

Use original phone files and keep them local. Do not invent GPS, distance, physical scale, or road-quality scores. The current analyzer produces exploratory pixel-space candidates; a manual ROI limits the reported region but does not validate chip counts.

## Start the local app

From the repository root, in two PowerShell windows:

```powershell
$env:GHOST_RIDER_DISABLE_DOTENV = '1'
$env:GHOST_RIDER_DB_PATH = '.runtime/demo/road_quality.db'
$env:UPLOADS_DIR = '.runtime/demo/uploads'
$env:LOCAL_UPLOADS_PUBLIC = 'true'
$env:AWS_S3_BUCKET_NAME = ''
.venv\Scripts\python.exe -m uvicorn backend.api.server:app --host 127.0.0.1 --port 8000
```

```powershell
cd web
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8000'
npm run build
npm run preview -- --host 127.0.0.1 --port 4173
```

Open `http://127.0.0.1:4173`. The production build uses the real API; do not use the development fixture app as integration evidence.

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
