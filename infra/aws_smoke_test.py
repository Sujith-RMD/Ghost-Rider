#!/usr/bin/env python
"""Ghost-Rider AWS preflight + smoke test.

Runs the two early integration checks the role brief requires before the main
project budget is committed:

1. **Private S3 round-trip** — using the same code path the API uses
   (``backend.s3_service``): presigned **PUT** upload, ``HEAD`` verification,
   presigned **GET** read-back, then cleanup. Creates the bucket private
   (block-public-access + SSE) only if it does not already exist.
2. **Authorized Bedrock Converse** — one minimal ``converse`` call to confirm
   model access in the chosen region.

It prints account/ARN but never prints secret material.

Usage (from the repository root)
--------------------------------
    .venv\\Scripts\\python.exe infra\\aws_smoke_test.py --region ap-southeast-2 --bucket ghost-rider-road-storage

To smoke a different AWS account, point at its own dotenv file (so the default
account's ``backend/.env`` is untouched):

    .venv\\Scripts\\python.exe infra\\aws_smoke_test.py --env-file backend\\.env.sujith

or use a named profile: ``--profile sujith``.

Credentials are resolved through boto3's default chain: explicit ``.env`` keys,
a shared profile, or an EC2/ECS instance role.

Ownership: Backend & AWS AI
Reference: docs/backend/AWS_SMOKE_TEST.md, docs/final_plan.md (Section 2)
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 128  # valid magic header, tiny body

# Nova models in ap-southeast-2 are served through cross-region inference profiles.
# The bare model id (amazon.nova-micro-v1:0) is rejected with
# "on-demand throughput isn't supported"; the regional profile id is required.
DEFAULT_MODEL = "apac.amazon.nova-micro-v1:0"


def _smoke_s3(args) -> bool:
    import boto3
    import httpx
    from botocore.exceptions import ClientError

    from backend import s3_service  # imported here so env is set first

    s3 = boto3.client("s3", region_name=args.region)

    # --- ensure the bucket exists and is private -----------------------------
    try:
        s3.head_bucket(Bucket=args.bucket)
        print(f"[ok] bucket exists: {args.bucket}")
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchBucket", "NotFound"):
            print(f"[..] creating private bucket {args.bucket} in {args.region}")
            try:
                if args.region == "us-east-1":
                    s3.create_bucket(Bucket=args.bucket)
                else:
                    s3.create_bucket(
                        Bucket=args.bucket,
                        CreateBucketConfiguration={"LocationConstraint": args.region},
                    )
                s3.put_public_access_block(
                    Bucket=args.bucket,
                    PublicAccessBlockConfiguration={
                        "BlockPublicAcls": True,
                        "IgnorePublicAcls": True,
                        "BlockPublicPolicy": True,
                        "RestrictPublicBuckets": True,
                    },
                )
                s3.put_bucket_encryption(
                    Bucket=args.bucket,
                    ServerSideEncryptionConfiguration={
                        "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
                    },
                )
                print("[ok] bucket created (private, SSE-S3)")
            except ClientError as exc2:
                code2 = exc2.response.get("Error", {}).get("Code", "")
                print(f"[FAIL] could not create bucket: {exc2}")
                if code2 == "AccessDenied":
                    if "service control policy" in str(exc2):
                        print(
                            "       -> denied by an AWS Organizations service control policy (SCP),\n"
                            "          which applies account-wide (console included). Ask your org admin to\n"
                            f"          create bucket '{args.bucket}' in {args.region}, or to allow\n"
                            "          's3:CreateBucket' for this account."
                        )
                    else:
                        print(
                            "       -> your credentials may not create buckets (least-privilege policy).\n"
                            f"          Create the bucket '{args.bucket}' once in the AWS console\n"
                            f"          (region {args.region}, Block all public access ON, SSE-S3),\n"
                            "          then re-run this script."
                        )
                return False
        elif code in ("403", "AccessDenied"):
            print(f"[FAIL] bucket {args.bucket} exists but access denied: {exc}")
            return False
        else:
            print(f"[FAIL] head_bucket error: {exc}")
            return False

    if not s3_service.is_s3_enabled():
        print("[FAIL] s3_service.is_s3_enabled() is False — check AWS creds/region/bucket env")
        return False

    # --- presigned PUT upload ------------------------------------------------
    key = f"smoke/{uuid.uuid4().hex}.jpg"
    put_url = s3_service.get_presigned_put_url(key, content_type="image/jpeg", expires_in=300)
    if not put_url:
        print("[FAIL] get_presigned_put_url returned None")
        return False
    print(f"[ok] presigned PUT issued for {key}")

    with httpx.Client(timeout=30.0) as client:
        put = client.put(put_url, content=JPEG, headers={"Content-Type": "image/jpeg"})
        if put.status_code not in (200, 201):
            print(f"[FAIL] PUT upload failed: HTTP {put.status_code} {put.text[:200]}")
            return False
        print("[ok] object uploaded via presigned PUT")

        head = s3.head_object(Bucket=args.bucket, Key=key)
        if int(head["ContentLength"]) != len(JPEG):
            print(f"[FAIL] size mismatch: stored={head['ContentLength']} expected={len(JPEG)}")
            return False
        print(f"[ok] HEAD verified (ContentLength={head['ContentLength']})")

        get_url = s3_service.get_presigned_url(key, expires_in=300)
        got = client.get(get_url)
        if got.status_code != 200 or got.content != JPEG:
            print(f"[FAIL] presigned GET read-back mismatch (HTTP {got.status_code})")
            return False
        print("[ok] presigned GET read-back matches uploaded bytes")

    if not args.keep:
        s3.delete_object(Bucket=args.bucket, Key=key)
        print("[ok] test object cleaned up")

    return True


def _smoke_bedrock(args) -> bool:
    import boto3
    from botocore.exceptions import ClientError

    client = boto3.client("bedrock-runtime", region_name=args.region)
    try:
        response = client.converse(
            modelId=args.model,
            messages=[{"role": "user", "content": [{"text": "Reply with the single word: ready"}]}],
            inferenceConfig={"maxTokens": 16, "temperature": 0.0},
        )
        text = response["output"]["message"]["content"][0]["text"].strip()
        usage = response.get("usage", {})
        print(f"[ok] Bedrock Converse model={args.model} text={text!r} usage={usage}")
        return True
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        print(f"[FAIL] Bedrock {code}: {exc}")
        if code in ("AccessDeniedException", "ResourceNotFoundException"):
            print(f"       -> grant model access for '{args.model}' in region {args.region}")
        elif code == "ValidationException" and "inference profile" in str(exc):
            print(
                "       -> ap-southeast-2 serves Nova via cross-region inference profiles; use e.g.\n"
                "          --model apac.amazon.nova-micro-v1:0"
            )
        return False
    except Exception as exc:  # pragma: no cover - network/region issues
        print(f"[FAIL] Bedrock error: {type(exc).__name__}: {exc}")
        return False


def _parse_args():
    parser = argparse.ArgumentParser(description="Ghost-Rider AWS preflight + smoke test")
    parser.add_argument(
        "--env-file",
        default=str(REPO_ROOT / "backend" / ".env"),
        help="dotenv file with credentials (default: backend/.env)",
    )
    parser.add_argument("--profile", default=None, help="AWS named profile (overrides keys in --env-file)")
    parser.add_argument("--region", default=None)
    parser.add_argument("--bucket", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--keep", action="store_true", help="keep the test object in the bucket")
    parser.add_argument("--skip-s3", action="store_true")
    parser.add_argument("--skip-bedrock", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    # Load credentials from the chosen dotenv file before boto3 is used; boto3's
    # default chain does not read .env files on its own.
    try:
        from dotenv import load_dotenv

        env_path = Path(args.env_file)
        if not env_path.is_absolute():
            env_path = REPO_ROOT / env_path
        if env_path.is_file():
            load_dotenv(env_path, override=True)
            print(f"[ok] loaded credentials file: {env_path}")
        else:
            print(f"[warn] credentials file not found: {env_path}")
    except Exception as exc:  # pragma: no cover - optional dependency
        print(f"[warn] could not load credentials file: {exc}")

    if args.profile:
        # A named profile must win over static keys in the env file.
        for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
            os.environ.pop(key, None)
        os.environ["AWS_PROFILE"] = args.profile

    args.region = args.region or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "ap-southeast-2"
    args.bucket = args.bucket or os.getenv("AWS_S3_BUCKET_NAME") or "ghost-rider-road-storage"
    args.model = args.model or os.getenv("BEDROCK_MODEL_ID") or DEFAULT_MODEL

    # The resolved region/bucket must be visible to ``backend.s3_service``.
    os.environ["AWS_REGION"] = args.region
    os.environ["AWS_S3_BUCKET_NAME"] = args.bucket

    import boto3

    print(f"region={args.region} bucket={args.bucket} model={args.model}")

    # --- credentials preflight ----------------------------------------------
    try:
        identity = boto3.client("sts", region_name=args.region).get_caller_identity()
        print(f"[ok] credentials: account={identity['Account']} arn={identity['Arn']}")
    except Exception as exc:
        print(f"[FAIL] no usable AWS credentials: {type(exc).__name__}: {exc}")
        print("       set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (backend/.env) or configure a profile/role")
        return 1

    ok = True
    if not args.skip_s3:
        ok = _smoke_s3(args) and ok
    if not args.skip_bedrock:
        ok = _smoke_bedrock(args) and ok

    print("SMOKE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
