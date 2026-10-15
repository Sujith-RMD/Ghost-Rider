# Ghost-Rider Backend - Running Guide

**Owner:** Backend & AWS AI  
**Last Updated:** 16 October 2026

## Quick Start

Run from the **repository root** with the project virtualenv (`.venv`). The v1
application lives in `backend.api.server`; the legacy `backend/main.py` (`/routes`
+ YOLO pipeline) still exists for the older demo path but is **not** the v1
contract.

```powershell
# from the repository root
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt pytest

# Run the v1 API (starts an inline worker thread by default)
.venv\Scripts\python.exe -m uvicorn backend.api.server:app --reload --host 0.0.0.0 --port 8000

# Optional: run the worker as a separate process (deployed two-process layout)
$env:GHOST_RIDER_INLINE_WORKER = "false"
$env:PYTHONPATH = "."
.venv\Scripts\python.exe -m backend.worker --poll 1.0
```

The upload → durable job → sample slice and the worker lifecycle are documented in
[UPLOAD_JOB_SAMPLE_SLICE.md](UPLOAD_JOB_SAMPLE_SLICE.md).

## Environment Variables

Create a `.env` file in the backend directory:

```env
# Server
GHOST_RIDER_HOST=0.0.0.0
GHOST_RIDER_PORT=8000
LOG_LEVEL=INFO

# Uploads
UPLOADS_DIR=backend/uploads
MAX_UPLOAD_MB=25

# Database
GHOST_RIDER_DB_PATH=backend/road_quality.db

# AWS S3
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=ap-southeast-2
AWS_S3_BUCKET_NAME=ghost-rider-road-storage
# Optional endpoint pin (LocalStack/MinIO, or any S3-compatible endpoint).
# In this account it is REQUIRED: presigned URLs must be built on the regional
# host. Without it the presigner emits s3.amazonaws.com, which S3 answers with
# a 307 redirect that invalidates the signature (host is a signed header).
AWS_S3_ENDPOINT_URL=https://s3.ap-southeast-2.amazonaws.com

# S3 behavior
S3_RETURN_PRESIGNED=true
PRESIGNED_URL_TTL=3600
S3_RAW_PREFIX=uploads/
S3_MASK_PREFIX=masks/

# Model
WARMUP_MODEL=true

# Worker / durable jobs
GHOST_RIDER_INLINE_WORKER=true   # false when running the worker as its own process
GHOST_RIDER_JOB_MAX_ATTEMPTS=3
GHOST_RIDER_JOB_LEASE_SECONDS=300
GHOST_RIDER_MODEL_VERSION=measure-v1
GHOST_RIDER_FEATURE_VERSION=quality-v1
GHOST_RIDER_SCORING_VERSION=not-implemented
```

## API Endpoints

See [docs/contracts/endpoints.md](docs/contracts/endpoints.md) for full specification.

### Health
- `GET /` - Basic health check
- `GET /health` - Service status
- `GET /health/deep` - Deep diagnostics with dependency probes

### Routes (Legacy simple API)
- `POST /routes` - Create route session
- `GET /routes` - List routes
- `POST /routes/{id}/images` - Upload image
- `POST /routes/{id}/process` - Start processing
- `GET /routes/{id}/results` - Get results

### v1 API (Full contract)
- `POST /v1/uploads` - Create upload (returns S3 PUT presign or local URL)
- `PUT  /v1/uploads/{id}/local` - Bounded local/streaming upload (S3-less path)
- `POST /v1/uploads/{id}/finalize` - Verify, persist metadata, queue analysis
- `POST /v1/sessions` - Create session
- `POST /v1/sessions/{id}/frames` - Add frame
- `POST /v1/sessions/{id}/finish` - Close session
- `GET /v1/jobs/{id}` - Durable job status (+ `result_sample_id`)
- `GET /v1/samples/{id}` - Sample results
- `GET /v1/sessions/{id}/segments` - Route segments
- `POST /v1/reports` - Generate report
- `GET /v1/health` - Model/worker/storage readiness

## Testing

```powershell
# from the repository root (pyproject sets testpaths/pythonpath)
.venv\Scripts\python.exe -m pytest tests/backend -q
```

## Deployment

See `scripts/` for deployment helpers:

- `scripts/setup_aws_resources.py` - Create S3 bucket and lifecycle
- `scripts/deploy_ec2_native.sh` - EC2 deployment script
- `scripts/ghost-rider.service` - systemd service file

## Troubleshooting

### Model won't load
- Check CUDA availability: `python -c "import torch; print(torch.cuda.is_available())"`
- Set `WARMUP_MODEL=false` to skip startup loading
- Model loads on first request if warmup fails

### S3 errors
- Verify credentials: `aws sts get-caller-identity`
- Check bucket exists: `aws s3 ls s3://ghost-rider-road-storage`
- For local testing, use LocalStack or MinIO

### Database errors
- Check file permissions on `road_quality.db`
- WAL mode requires write access to directory
- Backup: `cp road_quality.db road_quality.db.backup`

## Architecture

```
backend/
├── main.py           # LEGACY FastAPI app (/routes), YOLO pipeline
├── api/
│   ├── server.py     # v1 app factory + lifespan (uvicorn backend.api.server:app)
│   └── v1.py         # v1 endpoints (/v1/uploads, jobs, sessions, samples, reports, health)
├── worker.py         # worker: consumes bounded queue + durable jobs, idempotent writes
├── queues.py         # v1 DDL owner (upload_slots, jobs, job_events, sessions, frames, samples, ...)
├── schemas.py        # Pydantic models (API contract)
├── database.py       # SQLite persistence (WAL, per-call connections)
├── s3_service.py     # S3 upload/presign (GET + PUT), local fallback
├── bedrock_service.py# Legacy Bedrock helper
├── pipeline.py       # Legacy CV processing pipeline
├── app/
│   ├── config.py     # Settings (pydantic-settings)
│   └── health.py     # /health and /health/deep
├── ingestion/        # upload/live/replay adapters + bounded queue + telemetry
├── routes/           # route aggregation + coverage truth
├── reports/          # factual reports + Bedrock narrative
└── scripts/          # EC2 deployment + AWS resource setup
```

## Configuration Management

Settings are managed via `app/config.py` using pydantic-settings:
- Environment variables take priority
- `.env` files are loaded automatically
- `reload_settings()` for credential rotation

Never hardcode credentials. Use IAM roles in production.
