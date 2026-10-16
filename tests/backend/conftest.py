"""Test-suite isolation for the backend tests.

The service reads a developer's ``backend/.env``, which — for the AWS smoke test
— may hold **real** AWS credentials. Tests must never depend on, or accidentally
reach, live AWS, so before any backend module is imported we:

* disable dotenv loading (``GHOST_RIDER_DISABLE_DOTENV=1``),
* clear AWS credentials inherited from the shell,
* point boto3 away from ``~/.aws`` and the EC2 metadata service.

The inline worker is disabled so durable jobs are processed deterministically by
the test itself instead of a background thread.
"""

import os

# --- must be set before backend modules import ---------------------------------
os.environ["GHOST_RIDER_DISABLE_DOTENV"] = "1"
os.environ.setdefault("GHOST_RIDER_INLINE_WORKER", "false")
os.environ["DISTRESS_MODEL_PATH"] = "tests/fixtures/uninstalled-india-detector.pt"

# Neutralise any credentials inherited from the shell so `.env` (already disabled)
# and the ambient environment cannot make the suite talk to live AWS.
for _key in (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_PROFILE",
    "AWS_DEFAULT_PROFILE",
    "BEDROCK_MODEL_ID",
    "AWS_S3_BUCKET_NAME",
):
    os.environ.pop(_key, None)

# Keep the local-storage / rule-template paths active and deterministic.
os.environ["AWS_REGION"] = "ap-southeast-2"
os.environ["BEDROCK_ENABLED"] = "false"

# Never read ~/.aws and never probe the EC2 metadata service from tests.
os.environ["AWS_SHARED_CREDENTIALS_FILE"] = os.devnull
os.environ["AWS_CONFIG_FILE"] = os.devnull
os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
