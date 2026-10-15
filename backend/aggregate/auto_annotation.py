"""Provisional automated annotation - a labelled placeholder, never ground truth.

Owned by the ML role (``docs/ML_ROLE.md`` section 1).

Why this exists: Gate 0 needs reviewed labels before anything can be trained or
scored, and the two-human review (tasks A2.2/A2.3) needs two people and time. The
team has a time constraint, so this module keeps development moving by producing
**provisional** labels that are explicitly marked as machine output.

What it deliberately does *not* do, because the final plan forbids it (section
5.1 step 7: do not create pseudo-ground-truth and claim the requirement solved):

* It never answers `chip_visible` / `gap_visible`. Those are statements about what
  **a human can see**, and a segmentation count cannot establish them. They are
  written as ``not_assessed`` with the machine evidence recorded beside them, so a
  human answer can replace them later without a schema change.
* It never invents a gap width. Gap endpoints come from the same documented
  medial-axis, opposing-distinct-instance method as
  :func:`backend.aggregate.features.gap_statistics`, reusing one implementation
  rather than a second guess.

Every result carries ``source="automated_provisional"``, a low
``confidence`` and a ``UserWarning`` at call time, and the machine rows are written
in **the same columns as the human template**
(``annotation_guides/aggregate_patch_annotation_template.csv``) with the annotator
column filled in, so human rows can simply be added next to them later.

Replacement is the intended path: humans fill ``annotation_guides/`` rows with
their own judgement; downstream code reads provenance, so nothing breaks when the
machine rows stop being the only ones.
"""

from __future__ import annotations

import csv
import warnings
from dataclasses import dataclass
from math import pi, sqrt
from pathlib import Path
from typing import Literal, Sequence

import numpy as np

from backend.aggregate.features import gap_endpoints
from backend.aggregate.segmentation import (
    WatershedConfig,
    instance_properties,
    segment_aggregate,
)
from backend.geometry.scale import PlanarScale

__all__ = [
    "NOT_ASSESSED",
    "PROVISIONAL_CONFIDENCE",
    "AutoAnnotation",
    "auto_annotate_patch",
    "find_one_gap",
    "write_annotations_csv",
    "batch_auto_annotate",
]

NOT_ASSESSED = "not_assessed"
"""The only value a machine may write for a human-perception question."""

PROVISIONAL_CONFIDENCE = 0.3
"""Fixed low confidence. There is no validation behind it, so a high number
would be a claim."""


@dataclass(frozen=True)
class AutoAnnotation:
    """One patch's provisional annotation, with its provenance attached.

    The schema is a superset of what a human annotator can supply, so switching
    provenance does not change the downstream shape.
    """

    # Core
    instance_mask: np.ndarray
    chip_count: int

    # Human-only questions. A machine may not answer these, so they carry
    # NOT_ASSESSED and the evidence that a human would use is recorded instead.
    chip_visible: str = NOT_ASSESSED
    gap_visible: str = NOT_ASSESSED

    # Gap, from the documented opposing-instance method
    gap_endpoint_a_xy: tuple[int, int] | None = None
    gap_endpoint_b_xy: tuple[int, int] | None = None
    gap_width_px: float | None = None
    gap_width_mm: float | None = None
    gap_site_count: int = 0

    # Chip size evidence
    median_chip_diameter_px: float | None = None
    median_chip_diameter_mm: float | None = None
    coverage_fraction: float | None = None

    # Provenance - the reason this is safe to keep
    source: Literal["automated_provisional", "human"] = "automated_provisional"
    confidence: float = PROVISIONAL_CONFIDENCE
    notes: str = ""
    patch_id: str = ""
    annotator_id: str = "auto_v1"
    config_version: str = ""

    def describe(self) -> dict:
        return {
            "patch_id": self.patch_id,
            "chip_count": self.chip_count,
            "chip_visible": self.chip_visible,
            "gap_visible": self.gap_visible,
            "gap_endpoint_a_xy": list(self.gap_endpoint_a_xy) if self.gap_endpoint_a_xy else None,
            "gap_endpoint_b_xy": list(self.gap_endpoint_b_xy) if self.gap_endpoint_b_xy else None,
            "gap_width_px": self.gap_width_px,
            "gap_width_mm": self.gap_width_mm,
            "median_chip_diameter_px": self.median_chip_diameter_px,
            "median_chip_diameter_mm": self.median_chip_diameter_mm,
            "coverage_fraction": self.coverage_fraction,
            "source": self.source,
            "confidence": self.confidence,
            "notes": self.notes,
            "annotator_id": self.annotator_id,
        }


def find_one_gap(
    labels: np.ndarray, min_gap_px: float = 3.0
) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
    """Endpoints of the median-width qualifying gap, or ``(None, None)``.

    Reuses :func:`backend.aggregate.features.gap_endpoints`, which only accepts a
    site whose facing boundaries belong to **two distinct instances**. The earlier
    version of this module invented endpoints from a background distance value,
    which could land inside a chip and bore no relation to any boundary.
    """
    found = gap_endpoints(np.asarray(labels), min_gap_px=float(min_gap_px))
    if not found:
        return None, None
    return found["endpoint_a_xy"], found["endpoint_b_xy"]


def auto_annotate_patch(
    image: np.ndarray,
    scale: PlanarScale | None = None,
    patch_id: str = "",
    config: WatershedConfig | None = None,
    min_gap_px: float = 3.0,
) -> AutoAnnotation:
    """Segment one patch and return a provisional annotation.

    ``image`` is 8-bit gray or 3-channel, native resolution. ``scale`` is optional
    and defaults to unscaled: with no verified ground sampling distance, chip size
    and gap width stay in pixels and their millimetre fields are ``None``.
    """
    warnings.warn(
        f"auto_annotate_patch({patch_id!r}): provisional machine annotation. "
        "It is not validated ground truth and cannot answer whether a human can "
        "see chips or gaps. Replace with human labels before claiming performance.",
        UserWarning,
        stacklevel=2,
    )

    config = config or WatershedConfig()
    labels = segment_aggregate(image, config)

    props = instance_properties(labels)
    chip_count = len(props)
    diameters = [p.equivalent_diameter_px for p in props if p.area_px > 0]
    median_diameter_px = float(np.median(diameters)) if diameters else None

    coverage = float(np.count_nonzero(labels) / labels.size) if labels.size else None

    found = gap_endpoints(labels, min_gap_px=min_gap_px)
    if found is None:
        a_xy = b_xy = None
        gap_width_px = None
        gap_width_mm = None
        site_count = 0
    else:
        a_xy = found["endpoint_a_xy"]
        b_xy = found["endpoint_b_xy"]
        gap_width_px = float(found["width_px"])
        gap_width_mm = (
            None if scale is None or not scale.is_scaled
            else gap_width_px * float(scale.equivalent_mm_per_px)
        )
        site_count = int(found["site_count"])

    median_diameter_mm = None
    if scale is not None and scale.is_scaled and median_diameter_px is not None:
        # Equivalent diameter scales linearly with mm/px: d_mm = d_px * mm_per_px.
        median_diameter_mm = median_diameter_px * float(scale.equivalent_mm_per_px)

    notes = (
        f"machine evidence: {chip_count} instances, coverage {coverage:.3f}, "
        f"median diameter {median_diameter_px:.1f}px"
        if chip_count and coverage is not None and median_diameter_px is not None
        else "machine evidence: no resolvable instances"
    )

    return AutoAnnotation(
        instance_mask=labels,
        chip_count=chip_count,
        gap_endpoint_a_xy=a_xy,
        gap_endpoint_b_xy=b_xy,
        gap_width_px=gap_width_px,
        gap_width_mm=gap_width_mm,
        gap_site_count=site_count,
        median_chip_diameter_px=median_diameter_px,
        median_chip_diameter_mm=median_diameter_mm,
        coverage_fraction=coverage,
        source="automated_provisional",
        confidence=PROVISIONAL_CONFIDENCE,
        notes=notes,
        patch_id=patch_id,
        annotator_id="auto_v1",
        config_version=config.config_version,
    )


HUMAN_TEMPLATE_COLUMNS = (
    "patch_id",
    "source_image",
    "patch_top_px",
    "patch_left_px",
    "crop_px",
    "sheet_png",
    "annotator",
    "chip_visible",
    "chip_count",
    "gap_visible",
    "gap_endpoint_a_xy",
    "gap_endpoint_b_xy",
    "zoom_effect",
    "notes",
)


def _endpoint_text(endpoint: tuple[int, int] | None) -> str:
    return "" if endpoint is None else f"{endpoint[0]},{endpoint[1]}"


def write_annotations_csv(
    results: Sequence[AutoAnnotation],
    out_path: str | Path,
    source_image: str = "",
    top: int = 0,
    left: int = 0,
    sheet_png: str = "",
) -> None:
    """Write machine rows in **exactly** the human template's columns.

    Column parity is the interoperability requirement: humans can add their rows
    to the same file later and no downstream reader changes. The annotator column
    carries ``auto_v1`` so provenance survives a round trip.
    """
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(HUMAN_TEMPLATE_COLUMNS)
        for result in results:
            height, width = result.instance_mask.shape[:2]
            writer.writerow(
                [
                    result.patch_id,
                    source_image,
                    top,
                    left,
                    min(height, width),
                    sheet_png,
                    result.annotator_id,
                    result.chip_visible,
                    result.chip_count,
                    result.gap_visible,
                    _endpoint_text(result.gap_endpoint_a_xy),
                    _endpoint_text(result.gap_endpoint_b_xy),
                    NOT_ASSESSED,
                    result.notes,
                ]
            )


def batch_auto_annotate(
    image_paths: Sequence[str | Path],
    output_csv: str | Path,
    scale: PlanarScale | None = None,
    config: WatershedConfig | None = None,
    patch_index: dict[str, dict] | None = None,
) -> list[AutoAnnotation]:
    """Annotate several patches and write them in the human template's format.

    ``patch_index`` optionally maps a patch id to ``{"source_image", "top",
    "left"}`` so the rows carry the same provenance the human rows will carry.
    """
    import cv2

    patch_index = patch_index or {}
    results: list[AutoAnnotation] = []
    for path in map(Path, image_paths):
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            warnings.warn(f"could not read {path}, skipped", UserWarning, stacklevel=2)
            continue
        results.append(auto_annotate_patch(image, scale=scale, patch_id=path.stem, config=config))

    if results:
        first_meta = patch_index.get(results[0].patch_id, {})
        write_annotations_csv(
            results,
            output_csv,
            source_image=first_meta.get("source_image", ""),
            top=int(first_meta.get("top", 0)),
            left=int(first_meta.get("left", 0)),
            sheet_png=first_meta.get("sheet_png", ""),
        )
    return results
