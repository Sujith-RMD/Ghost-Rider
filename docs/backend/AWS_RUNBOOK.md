# Ghost-Rider — AWS Runbook & Cost Controls

**Owner:** Backend & AWS AI
**Last Updated:** 16 October 2026
**Region:** `ap-southeast-2` (Sydney) — the only region this account may create resources in (org SCP `p-fakk0ucg` is region-scoped; see `AWS_SMOKE_TEST.md`)

## 1. Deployed architecture (one path, per final plan)

```
                    ┌─────────────────────────────┐
   HTTPS (443) ───▶ │ EC2 (single host)           │
                    │  ├─ FastAPI (uvicorn)       │  backend.api.server:app
                    │  └─ worker (systemd unit)   │  python -m backend.worker
                    │  ├─ SQLite on EBS (WAL)     │  backend/road_quality.db
                    │  └─ /uploads (local media)  │  fallback + S3 cache
                    └─────────────────────────────┘
                              │                │
                    private S3 ◀──── presigned PUT/GET (upload + render)
                    Bedrock   ◀──── POST /v1/reports (converse, cached by fact hash)
```

No DynamoDB/RDS/API Gateway/Kubernetes: SQLite on EBS with controlled writes is the
documented store. The inline worker thread is a dev-only convenience; production
runs the worker as its own systemd service.

## 2. Deploy

```bash
# on the EC2 host, from the repo checkout
sudo bash backend/scripts/deploy_ec2_native.sh        # writes .env with placeholders
sudoedit /opt/ghost-rider/.env                        # fill AWS keys (or use an instance role)
sudo systemctl restart ghost-rider
```

The deploy script generates `backend/.env` with `AWS_REGION=ap-southeast-2`.
Detail: `backend/scripts/deploy_ec2_native.sh`, service file `backend/scripts/ghost-rider.service`.

**Required environment (see `RUNNING.md` for the full list):**

```env
AWS_REGION=ap-southeast-2
AWS_S3_ENDPOINT_URL=https://s3.ap-southeast-2.amazonaws.com   # REQUIRED (see AWS_SMOKE_TEST.md)
AWS_S3_BUCKET_NAME=ghost-rider-road-storage
BEDROCK_MODEL_ID=apac.amazon.nova-micro-v1:0
```

The endpoint pin is **mandatory in this account**: without it the boto3 presigner
emits the global `s3.amazonaws.com` host, which S3 answers with a 307 redirect
that breaks the signature. The deployed host should prefer an **IAM instance
role** over static keys (`s3_service` resolves credentials through boto3's
default chain, so no keys are needed on the box).

## 3. Operational procedures

| Task | Procedure |
|---|---|
| Restart API | `sudo systemctl restart ghost-rider` |
| Restart worker | `sudo systemctl restart ghost-rider-worker` |
| Logs | `journalctl -u ghost-rider -u ghost-rider-worker -f` |
| Reprocess a stuck job | `python -m backend.worker` claims any job whose lease expired automatically; manual: `worker.process_job_by_id(job_id)` |
| Requeue a failed job | `UPDATE jobs SET status='queued', attempt_count=0, error_reason=NULL WHERE job_id=?` |
| DB backup (consistent) | `sqlite3 road_quality.db ".backup backup.db"` (WAL mode; the API/worker use per-call connections) |
| Verify AWS path | `.venv\Scripts\python.exe infra\aws_smoke_test.py` (must print `SMOKE: PASS`) |
| Health | `GET /v1/health` (model/worker/storage readiness), `GET /health/deep` (live S3 probe) |

**Recovery semantics already implemented (and tested):** jobs are claimed with a
`JOB_LEASE_SECONDS` lease; a crashed worker's job is reclaimed by the next worker
after lease expiry; a job exceeding `GHOST_RIDER_JOB_MAX_ATTEMPTS` fails with
`attempt_limit_exceeded`; frame/job writes are idempotent on
`(session_id, frame_index, model_version)`, so no retry can double-store.

## 4. Failure playbook

| Failure | Behaviour | Action |
|---|---|---|
| Worker crash mid-job | Lease expires → job reclaimed by another worker | None (self-healing); check `job_events` history |
| S3 unreachable | `upload_file_to_s3` / presign degrade to local `/uploads` URLs (never raise); jobs still succeed with local media | Restore network; objects already in S3 keep working |
| Bedrock error/timeout | Report path falls back to the deterministic factual template (`factual_template_used=true`), generation still completes | Check model access; retries are built in (3 attempts, budget 20 s) |
| Queue overflow (camera faster than worker) | Frames are **dropped** and counted (`dropped_count`), never queued unboundedly; API stays responsive | Reduce capture rate or raise worker throughput; do NOT raise the queue bound |
| Analysis exception | Upload job fails with `inference_error:<Type>` and **no sample is stored** | Inspect logs; requeue after fix |

## 5. Measured service latency (CPU, 16 Oct 2026)

Measured on this development host (Intel 64-family, Python 3.12.13, cv2 5.0.0,
numpy 2.5.4, scipy 1.18.1) with the ML team's synthetic generator
(`eval.aggregate_eval.make_synthetic_case`, 512×512 frames, 60 aggregate
instances each, 8 seeds after one warm-up):

| Metric | Value |
|---|---|
| Per-frame pipeline (decode → quality → measure) | **median 1.8 s**, mean 1.6 s, max 2.5 s |
| Throughput (single core) | ≈ 0.6 frames/sec |
| Count accuracy vs generator ground truth | 60/60 instances on all 8 seeds |

Implication (per final plan: measure before proposing GPU spend): a single CPU
worker sustains ~0.6 fps — enough for one camera stream at ≤0.5 fps capture
cadence with headroom, but a **second concurrent stream or a higher cadence
needs either a bigger instance type or GPU inference**. The pipeline is pure
CPU (numpy/scipy/cv2; no torch), so the GPU decision belongs to the ML owner and
must be re-measured on the deployed instance type before any spend.

## 6. Cost controls

| Resource | Control | Status |
|---|---|---|
| S3 raw frames | Lifecycle rule `ghost-rider-expire-raw-uploads` (expire `uploads/` after `S3_LIFECYCLE_EXPIRE_DAYS=7`, abort incomplete multiparts) | ✅ **Live** (applied 16 Oct 2026 via `infra/s3-lifecycle.json`; verified through `s3_service.get_bucket_lifecycle_policy`) |
| S3 storage class | Standard only; images are small (JPEG) | OK |
| Presigned URLs | TTL bounded (`PRESIGNED_URL_TTL`, cap 5 min for upload slots) | OK |
| Bedrock | Narrative cached by assessment/version hash; max 16–220 output tokens; fallback template on failure | OK |
| EC2 | Single instance; no NAT/ALB beyond the host's own security group | OK |
| Smoke test cost | 132-byte object + 1 Converse call (≤16 tokens), deleted in-run | Negligible |

**No budget alarms exist yet** — create a AWS Budgets alarm (e.g. $10/month
threshold) when the deployed instance type is chosen.

## 7. Known gaps (honest status)

- S3 bucket management is fully closed: lifecycle rule live; IAM grants
  `s3:PutLifecycleConfiguration` / `s3:GetLifecycleConfiguration`
  (`s3:ListAllMyBuckets` remains denied — bucket listing is not needed).
- Scoring (`backend/scoring/`) and reference (`backend/reference/`) packages are
  still empty: `SegmentResult.score/reference` stay `null` — no SQI yet, and
  none is fabricated. Jobs therefore complete as `partial`, not `succeeded`.
- Distress: the measurement path is wired (crack-mask metrics + canonical
  features), but runtime crack **detection** awaits the ML model artifact.
- Live-camera transport: endpoints exist; a real hardware test has not been run
  (camera-access track).
- Real GPS-driven 50 m segmentation: binning implemented; needs real route data.
- Deployment rehearsal: this runbook has not been executed on a live EC2 host.

Run history and AWS integration details: `AWS_SMOKE_TEST.md`. Contract status:
`CONTRACT_STATUS.md`.
