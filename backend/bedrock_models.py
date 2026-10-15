"""Amazon Bedrock model-id helpers (region-aware, dependency-free).

Amazon Nova models are not always invocable by their bare model id. In several
regions (notably ``ap-*`` and ``eu-*``) the Bedrock runtime rejects on-demand
invocation of ``amazon.nova-micro-v1:0`` with::

    ValidationException: Invocation of model ID amazon.nova-micro-v1:0 with
    on-demand throughput isn't supported. Retry your request with the ID or ARN
    of an inference profile that contains this model.

The fix is to call the *cross-region inference profile* id instead, which is the
bare id prefixed by its geography: ``apac.amazon.nova-micro-v1:0`` in
``ap-southeast-2`` (verified live), ``eu.amazon.nova-*`` in Europe, etc.

:func:`promote_nova_model_id` performs that rewrite only where we know on-demand
invocation fails, so setups that already work are left untouched.

Ownership: Backend & AWS AI
"""

from __future__ import annotations

from typing import Final, Mapping

#: Region prefix -> cross-region inference profile prefix.
#:
#: Only prefixes where on-demand invocation of the bare Nova id is rejected are
#: listed. ``us-*`` is intentionally omitted because on-demand invocation works
#: there; promoting it would change behaviour for setups that already function.
INFERENCE_PROFILE_PREFIXES: Final[Mapping[str, str]] = {
    "ap-": "apac.",
    "eu-": "eu.",
}

#: Model families that may need the inference-profile rewrite.
_NOVA_PREFIX: Final[str] = "amazon.nova-"


def inference_profile_prefix(region: str | None) -> str | None:
    """Return the inference-profile prefix for *region*, or ``None`` if not needed.

    >>> inference_profile_prefix("ap-southeast-2")
    'apac.'
    >>> inference_profile_prefix("us-east-1") is None
    True
    """
    text = (region or "").strip().lower()
    for region_prefix, profile_prefix in INFERENCE_PROFILE_PREFIXES.items():
        if text.startswith(region_prefix):
            return profile_prefix
    return None


def promote_nova_model_id(model_id: str | None, region: str | None) -> str | None:
    """Rewrite a bare Nova model id to its regional inference profile id.

    Non-Nova ids, already-prefixed ids, and regions that do not need a profile
    are returned unchanged.

    >>> promote_nova_model_id("amazon.nova-micro-v1:0", "ap-southeast-2")
    'apac.amazon.nova-micro-v1:0'
    >>> promote_nova_model_id("apac.amazon.nova-micro-v1:0", "ap-southeast-2")
    'apac.amazon.nova-micro-v1:0'
    >>> promote_nova_model_id("amazon.nova-micro-v1:0", "us-east-1")
    'amazon.nova-micro-v1:0'
    """
    if not model_id:
        return model_id
    model = model_id.strip()
    if not model.startswith(_NOVA_PREFIX):
        return model  # already prefixed (contains a dot) or a non-Nova model
    prefix = inference_profile_prefix(region)
    if not prefix:
        return model
    return f"{prefix}{model}"


__all__ = [
    "INFERENCE_PROFILE_PREFIXES",
    "inference_profile_prefix",
    "promote_nova_model_id",
]
