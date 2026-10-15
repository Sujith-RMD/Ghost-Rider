"""Region-aware Bedrock model-id resolution.

``ap-southeast-2`` (and other ``ap-*``/``eu-*`` regions) reject on-demand invocation
of the bare ``amazon.nova-*-v1:0`` id; the geo-prefixed cross-region inference
profile is required. These tests pin that behaviour for the helper and for the
:class:`Settings` default, and assert that already-correct configurations are
left untouched.
"""

import pytest

from backend.app.config import Settings
from backend.bedrock_models import inference_profile_prefix, promote_nova_model_id


@pytest.mark.parametrize(
    ("region", "expected"),
    [
        ("ap-southeast-2", "apac."),
        ("ap-northeast-1", "apac."),
        ("eu-central-1", "eu."),
        ("us-east-1", None),
        ("", None),
        (None, None),
    ],
)
def test_inference_profile_prefix(region, expected):
    assert inference_profile_prefix(region) == expected


@pytest.mark.parametrize(
    ("model_id", "region", "expected"),
    [
        ("amazon.nova-micro-v1:0", "ap-southeast-2", "apac.amazon.nova-micro-v1:0"),
        ("amazon.nova-lite-v1:0", "ap-northeast-1", "apac.amazon.nova-lite-v1:0"),
        ("amazon.nova-micro-v1:0", "eu-west-1", "eu.amazon.nova-micro-v1:0"),
        # Already-prefixed ids are idempotent.
        ("apac.amazon.nova-micro-v1:0", "ap-southeast-2", "apac.amazon.nova-micro-v1:0"),
        # Regions where on-demand works are untouched.
        ("amazon.nova-micro-v1:0", "us-east-1", "amazon.nova-micro-v1:0"),
        # Non-Nova models are never rewritten.
        ("anthropic.claude-3-haiku-20240307-v1:0", "ap-southeast-2", "anthropic.claude-3-haiku-20240307-v1:0"),
        (None, "ap-southeast-2", None),
    ],
)
def test_promote_nova_model_id(model_id, region, expected):
    assert promote_nova_model_id(model_id, region) == expected


def test_settings_promotes_bare_nova_default_for_ap_southeast_2():
    # conftest clears BEDROCK_MODEL_ID and sets AWS_REGION=ap-southeast-2.
    settings = Settings()
    assert settings.BEDROCK_MODEL_ID == "apac.amazon.nova-micro-v1:0"


def test_settings_promotion_respects_explicit_profile_id():
    settings = Settings(BEDROCK_MODEL_ID="apac.amazon.nova-lite-v1:0", AWS_REGION="ap-southeast-2")
    assert settings.BEDROCK_MODEL_ID == "apac.amazon.nova-lite-v1:0"


def test_settings_does_not_rewrite_for_working_region():
    settings = Settings(BEDROCK_MODEL_ID="amazon.nova-micro-v1:0", AWS_REGION="us-east-1")
    assert settings.BEDROCK_MODEL_ID == "amazon.nova-micro-v1:0"
