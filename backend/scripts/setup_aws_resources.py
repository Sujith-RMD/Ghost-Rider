#!/usr/bin/env python3
"""Provision and verify the AWS resources Ghost-Rider needs on EC2.

What it does
------------
1. Resolves configuration exactly like the API does (``app.config`` / ``.env``).
2. Creates the S3 bucket (``AWS_S3_BUCKET_NAME``) when it does not exist,
   honouring the configured region (``LocationConstraint`` for non ``us-east-1``).
3. Applies an S3 Lifecycle rule that expires raw uploaded frames under
   ``S3_RAW_PREFIX`` (default ``uploads/``) after ``--expire-days`` (default 7)
   to conserve storage credits.  Mask overlays under ``S3_MASK_PREFIX``
   (``masks/``) are deliberately **not** expired: they are the audit evidence.
4. Prints the minimal IAM policy the instance role needs (``s3:PutObject``,
   ``s3:GetObject``, ``bedrock:InvokeModel``) and, unless ``--skip-probe`` is
   passed, proves those permissions work with a temporary probe object and a
   1-token Bedrock call.

Usage
-----
::

    # from the repo root (venv active)
    python backend/scripts/setup_aws_resources.py --dry-run     # show the plan
    python backend/scripts/setup_aws_resources.py               # provision + verify
    python backend/scripts/setup_aws_resources.py --json        # machine readable

Idempotent: safe to re-run.  Exits 0 on success, 1 on provisioning/permission
failure, 2 on usage or configuration problems.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    import s3_service
    from app.config import get_settings
except ImportError as exc:  # pragma: no cover - usage error
    print(f"ERROR: cannot import the backend package ({exc}).", file=sys.stderr)
    print(f"       Run this script from the backend directory or set PYTHONPATH={BACKEND_DIR}", file=sys.stderr)
    raise SystemExit(2)

logger = logging.getLogger("ghost_rider.setup")

PROBE_KEY_TEMPLATE = "{prefix}.ghost-rider-permission-probe"
PROBE_BODY = b"ghost-rider permission probe"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def error_code(exc: BaseException) -> str:
    """Best-effort AWS error code."""
    try:
        return str(((getattr(exc, "response", {}) or {}).get("Error", {}) or {}).get("Code", "")) or type(exc).__name__
    except Exception:  # pragma: no cover - defensive
        return type(exc).__name__


def minimal_iam_policy(bucket: str, region: str, *, include_optional: bool = True) -> Dict[str, Any]:
    """The IAM policy an EC2 instance role needs to run Ghost-Rider.

    Required
    --------
    ``s3:PutObject``     upload raw frames + mask overlays
    ``s3:GetObject``     presigned rendering of stored artefacts
    ``bedrock:InvokeModel``  generate repair recommendations

    Optional but recommended
    ------------------------
    ``s3:ListBucket``    lets ``/health/deep`` verify the bucket with head_bucket
    ``s3:DeleteObject``  enables the delete-probe and future cleanup tooling
    """
    statements: List[Dict[str, Any]] = [
        {
            "Sid": "GhostRiderObjectAccess",
            "Effect": "Allow",
            "Action": ["s3:PutObject", "s3:GetObject"],
            "Resource": f"arn:aws:s3:::{bucket}/*",
        },
        {
            "Sid": "GhostRiderBedrockInvoke",
            "Effect": "Allow",
            "Action": ["bedrock:InvokeModel"],
            "Resource": f"arn:aws:bedrock:{region}::foundation-model/*",
        },
    ]
    if include_optional:
        statements.append(
            {
                "Sid": "GhostRiderOptional",
                "Effect": "Allow",
                "Action": ["s3:ListBucket", "s3:DeleteObject"],
                "Resource": [f"arn:aws:s3:::{bucket}", f"arn:aws:s3:::{bucket}/*"],
            }
        )
    return {"Version": "2012-10-17", "Statement": statements}


def probe_s3_permissions(bucket: str, prefix: str) -> Dict[str, Any]:
    """Prove PutObject/GetObject(/DeleteObject) work with a temporary object."""
    client = s3_service.get_s3_client()
    if client is None:
        return {"status": "skipped", "reason": "s3_client_unavailable"}

    key = PROBE_KEY_TEMPLATE.format(prefix=prefix or "")
    result: Dict[str, Any] = {"key": key, "bucket": bucket}
    try:
        client.put_object(Bucket=bucket, Key=key, Body=PROBE_BODY, ContentType="text/plain")
        result["put_object"] = "ok"
    except Exception as exc:
        result["put_object"] = "failed"
        result["put_error"] = error_code(exc)
        result["status"] = "failed"
        return result

    try:
        response = client.get_object(Bucket=bucket, Key=key)
        body = response["Body"].read()
        result["get_object"] = "ok" if body == PROBE_BODY else "mismatched_body"
    except Exception as exc:
        result["get_object"] = "failed"
        result["get_error"] = error_code(exc)
        result["status"] = "failed"
        return result

    try:
        client.delete_object(Bucket=bucket, Key=key)
        result["delete_object"] = "ok"
    except Exception as exc:
        result["delete_object"] = "denied"
        result["delete_error"] = error_code(exc)
        result["note"] = ("s3:DeleteObject is optional; the object left behind expires with the "
                          "lifecycle rule on the raw prefix.")

    result["status"] = "ok" if result.get("put_object") == "ok" and result.get("get_object") == "ok" else "failed"
    return result


def probe_bedrock(model_id: str) -> Dict[str, Any]:
    """Prove ``bedrock:InvokeModel`` works with a minimal 1-token completion."""
    client = bedrock_service.get_bedrock_client(fast=True)
    if client is None:
        return {"status": "skipped", "reason": "bedrock_client_unavailable", "model": model_id}

    started = time.perf_counter()
    try:
        client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": "ping"}]}],
            inferenceConfig={"maxTokens": 5, "temperature": 0},
        )
        return {
            "status": "ok",
            "model": model_id,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    except Exception as exc:
        code = error_code(exc)
        lowered = code.lower()
        if "throttl" in lowered or "toomanyrequests" in lowered:
            return {"status": "ok", "model": model_id, "warning": f"authorized but throttled ({code})"}
        if any(marker in lowered for marker in ("accessdenied", "unauthorized", "unrecognizedclient",
                                                "invalidsignature", "expiredtoken")):
            status, hint = "failed", "the instance role is missing bedrock:InvokeModel"
        elif any(marker in lowered for marker in ("validation", "resourcenotfound", "modelnotready",
                                                  "modelnotenabled", "modelerror")):
            status = "failed"
            hint = (f"enable model access for '{model_id}' in the Bedrock console "
                    "(Model access -> Manage model access)")
        else:
            status, hint = "unverified", "could not reach Bedrock from here"
        return {"status": status, "model": model_id, "error": code, "hint": hint}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provision the S3 bucket + lifecycle rule and verify the IAM permissions Ghost-Rider needs.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--bucket", default=None, help="override AWS_S3_BUCKET_NAME")
    parser.add_argument("--region", default=None, help="override AWS_REGION")
    parser.add_argument("--prefix", default=None,
                        help="object prefix holding raw frames (override S3_RAW_PREFIX)")
    parser.add_argument("--expire-days", type=int, default=None,
                        help="days before raw frames expire (override S3_LIFECYCLE_EXPIRE_DAYS)")
    parser.add_argument("--no-create", action="store_true", help="fail instead of creating a missing bucket")
    parser.add_argument("--skip-lifecycle", action="store_true", help="do not touch the lifecycle policy")
    parser.add_argument("--skip-probe", action="store_true", help="skip the permission probes")
    parser.add_argument("--print-policy-only", action="store_true", help="print the IAM policy and exit")
    parser.add_argument("--dry-run", action="store_true", help="show the plan without calling AWS")
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="debug logging")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(message)s",
    )

    settings = get_settings()
    bucket = (args.bucket or settings.AWS_S3_BUCKET_NAME or "").strip()
    region = (args.region or settings.AWS_REGION or "us-east-1").strip()
    prefix = (args.prefix if args.prefix is not None else settings.S3_RAW_PREFIX).strip()
    expire_days = int(args.expire_days if args.expire_days is not None else settings.S3_LIFECYCLE_EXPIRE_DAYS)
    policy = minimal_iam_policy(bucket or "<bucket>", region)
    report: Dict[str, Any] = {
        "bucket": bucket or None,
        "region": region,
        "raw_prefix": prefix,
        "mask_prefix": settings.S3_MASK_PREFIX,
        "expire_days": max(1, expire_days),
        "credentials": "configured" if settings.aws_credentials_present else "missing",
        "endpoint_url": settings.AWS_S3_ENDPOINT_URL,
    }

    def emit(payload: Dict[str, Any], human: str) -> None:
        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(human)

    if args.print_policy_only:
        print(json.dumps(policy, indent=2))
        return 0

    if not bucket:
        logger.error("AWS_S3_BUCKET_NAME is empty: set it in backend/.env or pass --bucket")
        return 2

    print("=" * 78)
    print("Ghost-Rider AWS resource setup")
    print("=" * 78)
    print(f"  bucket        : {bucket}")
    print(f"  region        : {region}")
    print(f"  raw prefix    : '{prefix}'  (expires after {max(1, expire_days)} days)")
    print(f"  mask prefix   : '{settings.S3_MASK_PREFIX}'  (retained)")
    print(f"  credentials   : {report['credentials']}")
    print(f"  endpoint url  : {settings.AWS_S3_ENDPOINT_URL or '(AWS default)'}")
    print("=" * 78)

    if args.dry_run:
        print("\nDRY RUN - nothing was changed. Steps that would run:")
        print(f"  1. head_bucket/create_bucket            -> s3://{bucket} in {region}")
        print(f"  2. put_bucket_lifecycle_configuration   -> Expiration.Days={max(1, expire_days)}, "
              f"Filter.Prefix='{prefix}'")
        if not args.skip_probe:
            print(f"  3. put/get/delete probe object          -> s3://{bucket}/{prefix}.ghost-rider-permission-probe")
            print(f"  4. bedrock converse probe               -> {settings.BEDROCK_MODEL_ID} @ {settings.bedrock_region}")
        print("\nMinimal IAM policy for the EC2 instance role:")
        print(json.dumps(policy, indent=2))
        report["dry_run"] = True
        report["iam_policy"] = policy
        if args.json:
            print(json.dumps(report, indent=2, default=str))
        return 0

    exit_code = 0

    # ---- 1. bucket ------------------------------------------------------- #
    print("\n[1/4] Ensuring the bucket exists ...")
    try:
        bucket_state = s3_service.ensure_bucket(bucket, region, create=not args.no_create)
        report["bucket_created"] = bool(bucket_state.get("created"))
        print(f"      {'created' if bucket_state.get('created') else 'already present'}: "
              f"s3://{bucket_state['bucket']} ({bucket_state['region']})")
    except s3_service.S3UnavailableError as exc:
        logger.error("Bucket setup failed: %s", exc)
        report["bucket_error"] = str(exc)
        report["iam_policy"] = policy
        emit(report, "")
        return 1

    # ---- 2. lifecycle ---------------------------------------------------- #
    if args.skip_lifecycle:
        print("\n[2/4] Lifecycle policy skipped (--skip-lifecycle).")
        report["lifecycle"] = {"status": "skipped"}
    else:
        print("\n[2/4] Applying the raw-frame expiry lifecycle rule ...")
        try:
            lifecycle = s3_service.put_bucket_lifecycle_policy(
                prefix=prefix, expire_days=max(1, expire_days), bucket=bucket
            )
            report["lifecycle"] = {"status": "applied", **lifecycle}
            print(f"      rule '{lifecycle['rule_id']}' -> Expiration.Days="
                  f"{lifecycle['expire_days']} on prefix '{lifecycle['prefix']}' "
                  f"({lifecycle['total_rules']} rule(s) total)")
            current = s3_service.get_bucket_lifecycle_policy(bucket)
            if current:
                for rule in current.get("Rules", []):
                    print(f"      active: {rule.get('ID')} | prefix="
                          f"{rule.get('Filter', {}).get('Prefix', '(whole bucket)')!r} | "
                          f"expire={rule.get('Expiration', {}).get('Days')}d | {rule.get('Status')}")
        except s3_service.S3UnavailableError as exc:
            logger.error("Lifecycle setup failed: %s", exc)
            report["lifecycle"] = {"status": "failed", "error": str(exc)}
            exit_code = 1

    # ---- 3. permissions -------------------------------------------------- #
    if args.skip_probe:
        print("\n[3/4] Permission probes skipped (--skip-probe).")
        report["s3_probe"] = {"status": "skipped"}
        report["bedrock_probe"] = {"status": "skipped"}
    else:
        print("\n[3/4] Verifying S3 object permissions ...")
        s3_probe = probe_s3_permissions(bucket, prefix)
        report["s3_probe"] = s3_probe
        if s3_probe.get("status") == "ok":
            print(f"      PutObject/GetObject ok (probe key '{s3_probe['key']}', delete="
                  f"{s3_probe.get('delete_object')})")
        else:
            print(f"      FAILED: {s3_probe}")
            exit_code = 1

        print("\n[3/4] Verifying bedrock:InvokeModel ...")
        bedrock_probe = probe_bedrock(settings.BEDROCK_MODEL_ID)
        report["bedrock_probe"] = bedrock_probe
        if bedrock_probe.get("status") == "ok":
            print(f"      converse probe ok ({bedrock_probe.get('latency_ms', 'n/a')} ms)"
                  f"{' - ' + bedrock_probe['warning'] if bedrock_probe.get('warning') else ''}")
        else:
            print(f"      {bedrock_probe.get('status').upper()}: {bedrock_probe.get('error')} - "
                  f"{bedrock_probe.get('hint', '')}")

    # ---- 4. report ------------------------------------------------------- #
    print("\n[4/4] Minimal IAM policy for the EC2 instance role:")
    print(json.dumps(policy, indent=2))
    report["iam_policy"] = policy
    report["next_steps"] = [
        f"Set AWS_S3_BUCKET_NAME={bucket} and AWS_REGION={region} in backend/.env",
        "Restart the service: sudo systemctl restart ghost-rider",
        "Verify from the app: curl -s http://127.0.0.1:8000/health/deep | python -m json.tool",
    ]

    print("\n" + "=" * 78)
    print(f"RESULT: {'SUCCESS' if exit_code == 0 else 'COMPLETED WITH FAILURES'}")
    for step in report["next_steps"]:
        print(f"  -> {step}")
    print("=" * 78)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
