"""D10 contract tests with synthetic metadata, not fitted reference data."""

from dataclasses import FrozenInstanceError, fields, replace
from hashlib import sha256
import json

import pytest

from backend.reference.compatibility import (
    FeatureDefinition,
    PhysicalScaleDomain,
    ReferenceArtifact,
    ReferenceDefinitionMismatch,
    revise_reference,
)


@pytest.fixture
def definition():
    return FeatureDefinition(
        min_diameter_mm=2, min_gap_mm=1,
        measurement_version="measure-v1", segmentation_version="segment-v1",
        gap_version="gap-v1", texture_version="texture-v1",
        physical_scale_domain=PhysicalScaleDomain("synthetic-roi-v1", 0.2, 0.5, 0.3, 0.6),
    )


@pytest.fixture
def artifact(definition):
    return ReferenceArtifact("synthetic-reference-v1", definition)


def test_exact_definition_is_compatible(artifact, definition):
    assert artifact.require_compatible(replace(definition)) is artifact
    assert artifact.definition_fingerprint == definition.fingerprint


def test_canonical_json_is_stable_and_schema_tagged(definition):
    payload = json.loads(definition.canonical_json())
    assert payload["schema_version"] == "reference-feature-definition-v1"
    assert payload["min_diameter_mm"] == 2.0
    assert payload["physical_scale_domain"]["min_sy_mm_per_px"] == 0.3
    assert definition.canonical_json() == json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
    )
    assert definition.fingerprint == sha256(definition.canonical_json().encode("utf-8")).hexdigest()
    assert len(definition.fingerprint) == 64


def test_integer_and_float_inputs_have_identical_fingerprints(definition):
    assert replace(definition, min_diameter_mm=2.0, min_gap_mm=1.0).fingerprint == definition.fingerprint
    domain = PhysicalScaleDomain("fixed-v1", 1, 1, 2, 2)
    assert domain == PhysicalScaleDomain("fixed-v1", 1.0, 1.0, 2.0, 2.0)
    assert type(domain.min_sx_mm_per_px) is float


CHANGES = [
    ("min_diameter_mm", 3), ("min_gap_mm", 1.5),
    ("measurement_version", "measure-v2"), ("segmentation_version", "segment-v2"),
    ("gap_version", "gap-v2"), ("texture_version", "texture-v2"),
]


@pytest.mark.parametrize("name,value", CHANGES)
def test_every_feature_change_blocks_old_reference_and_requires_new_version(
    artifact, definition, name, value,
):
    changed = replace(definition, **{name: value})
    assert changed.fingerprint != definition.fingerprint
    with pytest.raises(ReferenceDefinitionMismatch) as exc:
        artifact.require_compatible(changed)
    assert exc.value.changed_fields == (name,)
    assert exc.value.expected_fingerprint == definition.fingerprint
    assert exc.value.current_fingerprint == changed.fingerprint
    with pytest.raises(ValueError, match="different reference_version"):
        revise_reference(artifact, reference_version=artifact.reference_version, definition=changed)
    revised = revise_reference(artifact, reference_version="synthetic-reference-v2", definition=changed)
    assert revised.require_compatible(changed) is revised
    with pytest.raises(ReferenceDefinitionMismatch):
        revised.require_compatible(definition)
    assert artifact.definition == definition


@pytest.mark.parametrize("name,value", [
    ("domain_id", "synthetic-roi-v2"),
    ("min_sx_mm_per_px", 0.1), ("max_sx_mm_per_px", 0.7),
    ("min_sy_mm_per_px", 0.2), ("max_sy_mm_per_px", 0.8),
])
def test_every_scale_domain_change_requires_new_reference(artifact, definition, name, value):
    domain = replace(definition.physical_scale_domain, **{name: value})
    changed = replace(definition, physical_scale_domain=domain)
    with pytest.raises(ReferenceDefinitionMismatch) as exc:
        artifact.require_compatible(changed)
    assert exc.value.changed_fields == ("physical_scale_domain",)
    with pytest.raises(ValueError, match="different reference_version"):
        revise_reference(artifact, reference_version=artifact.reference_version, definition=changed)
    revised = revise_reference(artifact, reference_version="synthetic-reference-v2", definition=changed)
    assert revised.require_compatible(changed) is revised


def test_multiple_changes_reported_in_definition_order(artifact, definition):
    changed = replace(definition, texture_version="texture-v2", min_diameter_mm=4)
    with pytest.raises(ReferenceDefinitionMismatch) as exc:
        artifact.require_compatible(changed)
    assert exc.value.changed_fields == ("min_diameter_mm", "texture_version")


def test_unchanged_definition_allows_same_or_new_reference_version(artifact, definition):
    for version in (artifact.reference_version, "synthetic-refit-v2"):
        revised = revise_reference(artifact, reference_version=version, definition=definition)
        assert revised.reference_version == version
        assert revised.require_compatible(definition) is revised
        assert revised.definition_fingerprint == artifact.definition_fingerprint


def test_renaming_reference_does_not_override_definition_mismatch(artifact, definition):
    renamed = replace(artifact, reference_version="renamed-v2")
    assert renamed.definition_fingerprint == artifact.definition_fingerprint
    with pytest.raises(ReferenceDefinitionMismatch):
        renamed.require_compatible(replace(definition, min_diameter_mm=3))


BAD_NUMBERS = [None, 0, -1, float("nan"), float("inf"), -float("inf"), True, False, "1", [], 10**400]


@pytest.mark.parametrize("name", ["min_diameter_mm", "min_gap_mm"])
@pytest.mark.parametrize("value", BAD_NUMBERS)
def test_invalid_reporting_limits_rejected(definition, name, value):
    with pytest.raises(ValueError, match="finite positive"):
        replace(definition, **{name: value})


@pytest.mark.parametrize("name", [f.name for f in fields(PhysicalScaleDomain) if f.name != "domain_id"])
@pytest.mark.parametrize("value", BAD_NUMBERS)
def test_invalid_scale_domain_numbers_rejected(definition, name, value):
    with pytest.raises(ValueError, match="finite positive"):
        replace(definition.physical_scale_domain, **{name: value})


@pytest.mark.parametrize("name", ["min_sx_mm_per_px", "min_sy_mm_per_px"])
def test_reversed_scale_bounds_rejected(definition, name):
    with pytest.raises(ValueError, match="reversed"):
        replace(definition.physical_scale_domain, **{name: 10})


@pytest.mark.parametrize("value", [None, "", " ", "v 1", "v1\n", " unknown ", "unknown", "Unvalidated", [], 1, "é1"])
@pytest.mark.parametrize("name", ["measurement_version", "segmentation_version", "gap_version", "texture_version", "domain_id", "reference_version"])
def test_invalid_identifiers_rejected(artifact, definition, name, value):
    with pytest.raises(ValueError):
        if name == "domain_id":
            replace(definition.physical_scale_domain, domain_id=value)
        elif name == "reference_version":
            replace(artifact, reference_version=value)
        else:
            replace(definition, **{name: value})


def test_records_are_deeply_immutable(artifact, definition):
    for obj, name, value in (
        (artifact, "reference_version", "v2"),
        (definition, "min_diameter_mm", 3),
        (definition.physical_scale_domain, "domain_id", "v2"),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(obj, name, value)
    # Serialized copies cannot mutate the fingerprint or nested domain.
    before = definition.fingerprint
    payload = json.loads(definition.canonical_json())
    payload["physical_scale_domain"]["domain_id"] = "changed"
    assert definition.fingerprint == before


@pytest.mark.parametrize("operation", [
    lambda a, d: replace(d, physical_scale_domain={}),
    lambda a, d: replace(d, physical_scale_domain=None),
    lambda a, d: ReferenceArtifact("v1", {}),
    lambda a, d: a.require_compatible(None),
    lambda a, d: a.require_compatible({}),
    lambda a, d: revise_reference(None, reference_version="v2", definition=d),
    lambda a, d: revise_reference(a, reference_version="v2", definition=None),
])
def test_wrong_contract_types_rejected(artifact, definition, operation):
    with pytest.raises(TypeError):
        operation(artifact, definition)
