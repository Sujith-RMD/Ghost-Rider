"""Standalone reference-definition compatibility contract (D10).

No reference statistics are fitted or supplied here. Passing this gate proves
only definition identity, not reference quality, model validation or F1/F2
completion. Callers must enforce the declared scale domain against actual
measurement geometry and must accurately version all estimator configuration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from hashlib import sha256
import json
from math import isfinite
import re


_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+\-]*", re.ASCII)


def _identifier(name: str, value: str) -> None:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{name} must be a nonempty identifier without whitespace")
    if value.lower() in ("unknown", "unvalidated"):
        raise ValueError(f"{name} must identify an explicit version/domain")


def _positive(name: str, value: float) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a finite positive number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} must be a finite positive number") from exc
    if not isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return number


@dataclass(frozen=True)
class PhysicalScaleDomain:
    """Supported physical sampling range, per axis, in mm per source pixel.

    ``domain_id`` identifies the validated geometry/ROI/scale-lineage policy,
    not a camera height or guessed GSD. Equal bounds express a fixed scale.
    The bounds are declarations, not evidence of physical validation.
    """

    domain_id: str
    min_sx_mm_per_px: float
    max_sx_mm_per_px: float
    min_sy_mm_per_px: float
    max_sy_mm_per_px: float

    def __post_init__(self) -> None:
        _identifier("domain_id", self.domain_id)
        for field in fields(self):
            if field.name != "domain_id":
                object.__setattr__(self, field.name, _positive(field.name, getattr(self, field.name)))
        if self.min_sx_mm_per_px > self.max_sx_mm_per_px:
            raise ValueError("x scale domain bounds are reversed")
        if self.min_sy_mm_per_px > self.max_sy_mm_per_px:
            raise ValueError("y scale domain bounds are reversed")


@dataclass(frozen=True)
class FeatureDefinition:
    """Immutable meaning of features consumed by a reference.

    Lower reporting limits are physical millimetres, never pixel counts. Method
    versions must cover all behavior/configuration affecting measurements,
    including physical texture offsets and eligibility/counting policies.
    """

    min_diameter_mm: float
    min_gap_mm: float
    measurement_version: str
    segmentation_version: str
    gap_version: str
    texture_version: str
    physical_scale_domain: PhysicalScaleDomain

    def __post_init__(self) -> None:
        for name in ("min_diameter_mm", "min_gap_mm"):
            object.__setattr__(self, name, _positive(name, getattr(self, name)))
        for name in ("measurement_version", "segmentation_version", "gap_version", "texture_version"):
            _identifier(name, getattr(self, name))
        if not isinstance(self.physical_scale_domain, PhysicalScaleDomain):
            raise TypeError("physical_scale_domain must be a PhysicalScaleDomain")

    def canonical_json(self) -> str:
        """Stable schema-tagged UTF-8 JSON input to the definition fingerprint."""
        return json.dumps(
            {"schema_version": "reference-feature-definition-v1", **asdict(self)},
            sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False,
        )

    @property
    def fingerprint(self) -> str:
        return sha256(self.canonical_json().encode("utf-8")).hexdigest()


class ReferenceDefinitionMismatch(ValueError):
    """The current measurements must not be compared with this reference."""

    def __init__(self, expected: FeatureDefinition, current: FeatureDefinition) -> None:
        self.expected_fingerprint = expected.fingerprint
        self.current_fingerprint = current.fingerprint
        self.changed_fields = tuple(
            field.name for field in fields(expected)
            if getattr(expected, field.name) != getattr(current, field.name)
        )
        super().__init__("reference feature definition mismatch: " + ", ".join(self.changed_fields))


@dataclass(frozen=True)
class ReferenceArtifact:
    """Identity metadata only; no fitted statistics/model or acceptance claim."""

    reference_version: str
    definition: FeatureDefinition

    def __post_init__(self) -> None:
        _identifier("reference_version", self.reference_version)
        if not isinstance(self.definition, FeatureDefinition):
            raise TypeError("definition must be a FeatureDefinition")

    @property
    def definition_fingerprint(self) -> str:
        return self.definition.fingerprint

    def require_compatible(self, current: FeatureDefinition) -> ReferenceArtifact:
        """Raise on any definition change; return this artifact on exact match."""
        if not isinstance(current, FeatureDefinition):
            raise TypeError("current must be a FeatureDefinition")
        if self.definition_fingerprint != current.fingerprint:
            raise ReferenceDefinitionMismatch(self.definition, current)
        return self


def revise_reference(
    previous: ReferenceArtifact,
    *,
    reference_version: str,
    definition: FeatureDefinition,
) -> ReferenceArtifact:
    """Require a new reference version when any feature meaning changes.

    Produces metadata, not a refitted reference. A new version does not make an
    incompatible definition compatible with the previous artifact. Persistence
    owners must retain version history; this helper cannot detect reuse of a
    version from older history not supplied to it.
    """
    if not isinstance(previous, ReferenceArtifact):
        raise TypeError("previous must be a ReferenceArtifact")
    revised = ReferenceArtifact(reference_version, definition)
    if (previous.definition_fingerprint != revised.definition_fingerprint
            and previous.reference_version == revised.reference_version):
        raise ValueError("changed feature definition requires a different reference_version")
    return revised
