# AWS Smoke Test — S3 (private) + Bedrock (authorized)

**Owner:** Backend & AWS AI
**Status:** Bedrock verified live; S3 pending bucket creation
**Last Updated:** 16 October 2026
**Script:** `infra/aws_smoke_test.py`
**Reference:** `docs/final_plan.md` §2, §11.1–11.2

Run this once, early, before committing project budget, to confirm the two
required integrations actually work in the chosen account/region. It is
deliberately tiny.

## What it checks

1. **Credentials** — `sts:GetCallerIdentity` (prints account + ARN, never secrets).
2. **Private S3 round-trip** using the *real* API code path (`backend/s3_service`):
   - verifies the bucket exists (and, when permitted, creates it private in
     `ap-southeast-2` with Block Public Access + SSE-S3),
   - issues a presigned **PUT**, uploads a 132-byte JPEG,
   - `HEAD`s the object and checks the size,
   - issues a presigned **GET**, downloads, and byte-compares,
   - deletes the test object (unless `--keep`).
3. **Bedrock Converse** — one minimal `converse` call to confirm model access.

> **Region is `ap-southeast-2` only.** The account's Organizations **service
> control policy** (`p-fakk0ucg`) restricts resource creation to `ap-southeast-2`
> (Sydney): `s3:CreateBucket` is explicitly denied elsewhere — verified denied in
> `ap-south-1`, allowed in `ap-southeast-2`. The IAM policy also denies
> `s3:ListAllMyBuckets` (and the bucket-management actions `s3:PutLifecycleConfiguration`,
> `s3:DeleteBucket`). Object operations on an existing bucket *are* allowed.
>
> **Presigned URLs need the regional endpoint pinned.** With `boto3` 1.43.x the
> S3 presigner emits URLs against the *global* host `s3.amazonaws.com`, which S3
> answers with a `307 TemporaryRedirect`; because `host` is a signed header the
> redirected request fails with `SignatureDoesNotMatch`. Fix: set
> `AWS_S3_ENDPOINT_URL=https://s3.ap-southeast-2.amazonaws.com` (honoured by
> `backend/s3_service.py`). Script creating the bucket prints a clear hint
> instead of failing silently when creation is denied.

## Providing credentials (do not commit them)

Preferred — create `backend/.env` (gitignored):

```env
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=ap-southeast-2
AWS_S3_BUCKET_NAME=ghost-rider-road-storage
AWS_S3_ENDPOINT_URL=https://s3.ap-southeast-2.amazonaws.com  # required: see note above
BEDROCK_MODEL_ID=apac.amazon.nova-micro-v1:0
```

Alternatively export them in the shell, or configure a named profile
(`AWS_PROFILE`). The deployed EC2 environment should use an **IAM instance role**;
`s3_service` resolves credentials through boto3's default chain, so no static keys
are required there (see `is_s3_enabled`).

## Run

```powershell
# from the repository root
.venv\Scripts\python.exe infra\aws_smoke_test.py --region ap-southeast-2 --bucket ghost-rider-road-storage
```

Useful flags: `--model apac.amazon.nova-micro-v1:0`, `--skip-s3`, `--skip-bedrock`, `--keep`.

Exit code is `0` on PASS and `1` on FAIL.

### Expected output (example)

```
region=ap-southeast-2 bucket=ghost-rider-road-storage model=apac.amazon.nova-micro-v1:0
[ok] credentials: account=123456789012 arn=arn:aws:iam::123456789012:user/ghost-rider-dev
[ok] bucket exists: ghost-rider-road-storage
[ok] presigned PUT issued for smoke/<hex>.jpg
[ok] object uploaded via presigned PUT
[ok] HEAD verified (ContentLength=132)
[ok] presigned GET read-back matches uploaded bytes
[ok] test object cleaned up
[ok] Bedrock Converse model=apac.amazon.nova-micro-v1:0 text='ready' usage={'inputTokens': .., 'outputTokens': .., 'totalTokens': ..}
SMOKE: PASS
```

## Minimum IAM permissions

- `sts:GetCallerIdentity`
- S3 (scoped to the bucket): `s3:PutObject`, `s3:GetObject`, `s3:HeadObject`,
  `s3:DeleteObject`, `s3:ListBucket`. Bucket *management* actions
  (`s3:CreateBucket`, `s3:DeleteBucket`, `s3:PutBucketPublicAccessBlock`,
  `s3:PutEncryptionConfiguration`, `s3:ListAllMyBuckets`) may be denied — the bucket
  is created once out-of-band by an admin.
- Bedrock: `bedrock:InvokeModel` (Converse uses this action)

## Cost

Negligible: one ~132-byte object for a few seconds, plus one Converse call capped at
16 output tokens. Bucket creation and lifecycle are free; storage/serving of the test
object is deleted in the same run. No GPU, no EC2.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `[FAIL] no usable AWS credentials` | Set `backend/.env`, env vars, or a profile; or attach an instance role |
| `[FAIL] s3_service.is_s3_enabled() is False` | Bucket name not set, or credentials not resolvable for the app's config |
| `[FAIL] could not create bucket: AccessDenied` | Bucket creation denied — if the message cites a **service control policy**, an org admin must create the bucket (console is also blocked); otherwise create it once in the console and re-run |
| `AccessDeniedException` on Bedrock | Request/grant model access for the model in that region (Bedrock console → Model access). A transient form is "account is currently being verified" (usually clears within 2 h) |
| `ValidationException: ... inference profile ...` | `ap-southeast-2` serves Nova only via cross-region inference profiles; use `apac.amazon.nova-micro-v1:0` |
| `ValidationException: model not found` | Wrong model id or region |
| `IllegalLocationConstraintException` | Region/bucket mismatch (the script handles `ap-southeast-2` correctly) |
| `307 TemporaryRedirect` / `SignatureDoesNotMatch` on presigned PUT/GET | Presigner emitted the **global** host (`s3.amazonaws.com`); the redirect breaks the signed `host` header. Fix: pin `AWS_S3_ENDPOINT_URL=https://s3.ap-southeast-2.amazonaws.com` (honoured by `s3_service`) |
| `AccessDenied` on `PutBucketLifecycleConfiguration` | Bucket-management action denied by the IAM policy (same class as `CreateBucket`/`ListAllMyBuckets`); raw-frame expiry must be applied by an admin — optional |

## Result log

**Run 1 — 16 October 2026 (account `431223004441`, region `ap-south-1`)**

| Field | Value |
|-------|-------|
| Date run | 16 Oct 2026 |
| Account / region | `431223004441` / `ap-south-1` |
| Bucket | `ghost-rider-road-storage` — **not created**; `s3:CreateBucket` denied by Organizations SCP `p-fakk0ucg` (account-wide) |
| Bedrock model + latency | `apac.amazon.nova-micro-v1:0` — **OK** (sub-second, 7 in / 2 out tokens). Bare `amazon.nova-micro-v1:0` rejected: needs an inference profile. |
| Object round-trip (must be equal) | blocked pending bucket creation |
| Outcome | **Partial** — Bedrock verified; S3 blocked by org SCP |

Follow-up: an org admin creates `ghost-rider-road-storage` in `ap-south-1`
(Block all public access ON, SSE-S3), then re-run to complete the S3 round-trip.
Bedrock is confirmed working and the backend now auto-promotes the bare Nova id to
`apac.amazon.nova-micro-v1:0` for `ap-*`/`eu-*` regions
(see `backend/bedrock_models.py`). — *Resolved by Run 2 below: the SCP turned
out to be region-scoped (creation allowed in `ap-southeast-2`), and the bucket
was created there.*

**Run 2 — 16 October 2026 (account `431223004441`, region `ap-southeast-2`)**

| Field | Value |
|-------|-------|
| Date run | 16 Oct 2026 |
| Account / region | `431223004441` / `ap-southeast-2` |
| Bucket | `ghost-rider-road-storage` — **created** (private: Block Public Access ON, SSE-S3). Creation in `ap-south-1` remained SCP-denied; the SCP is region-scoped. |
| Bedrock model + latency | `apac.amazon.nova-micro-v1:0` — **OK** (`ready`, 7 in / 2 out tokens). |
| Object round-trip (must be equal) | **PASS** — presigned PUT (132-byte JPEG) → HEAD (ContentLength=132) → presigned GET byte-match → cleanup. All through `backend/s3_service`. |
| Config change required | `AWS_S3_ENDPOINT_URL=https://s3.ap-southeast-2.amazonaws.com` pinned in `backend/.env` — without it the presigner emits the global `s3.amazonaws.com` host, which 307-redirects and fails the signature. |
| Outcome | **PASS** — full S3 round-trip + Bedrock verified. |

Post-PASS app-level checks (same day): `upload_file_to_s3`, `resolve_media_url`
refresh and batch presigning all return working regional URLs (HTTP 200).
`s3:PutLifecycleConfiguration` is denied by the IAM policy — the raw-frame
expiry rule remains optional and admin-applied.
