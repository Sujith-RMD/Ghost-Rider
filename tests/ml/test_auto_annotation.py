"""Tests for the provisional automated annotator.

Owned by the ML role (`docs/ML_ROLE.md` section 1).

This module exists to keep development moving while the two-human review (A2.2/
A2.3) is outstanding, so its job is to produce a *labelled* provisional annotation
that cannot be mistaken for ground truth. The tests therefore pin the honesty
properties harder than the numbers: a machine may count regions, but it may not
declare that a human can see chips, and it may not invent a gap width that is not
between two opposing instance boundaries (final plan section 7.3).

They also pin interoperability: the user's requirement was that human annotation
must be droppable in later without anything breaking, so the machine-written rows
must be expressible in the same template as the human ones.
"""

from __future__ import annotations

import csv

import numpy as np
import pytest

from backend.aggregate.auto_annotation import (
    PROVISIONAL_CONFIDENCE,
    NOT_ASSESSED,
    auto_annotate_patch,
    find_one_gap,
)
from backend.aggregate.features import gap_statistics
from backend.geometry import PlanarScale, ScaleSource

SCALE_1MM = PlanarScale.calibrated(1.0, 1.0, ScaleSource.SOURCE_CALIBRATED, "synthetic")


def _two_bars_image() -> np.ndarray:
    """Two bright bars with a known 11 px separation, as an 8-bit image."""
    image = np.full((200, 200), 60, dtype=np.uint8)
    image[40:60, :] = 200
    image[70:90, :] = 200
    return image


def _two_bar_labels() -> np.ndarray:
    labels = np.zeros((200, 200), dtype=np.int32)
    labels[40:60, :] = 1
    labels[70:90, :] = 2
    return labels


# ------------------------------------------------------- it must actually run


def test_auto_annotate_returns_a_label_map_and_a_count():
    # Regression: the original read `result["labels"]` from segment_aggregate,
    # which returns a bare int32 label *array*, so every call raised.
    result = auto_annotate_patch(_two_bars_image(), patch_id="BARS")
    assert isinstance(result.instance_mask, np.ndarray)
    assert result.instance_mask.ndim == 2
    assert result.chip_count == int(
        np.count_nonzero(np.unique(result.instance_mask) > 0)
    )
    assert result.chip_count >= 2


def test_auto_annotate_measures_the_gap_it_reports():
    # The gap it claims must be the documented opposing-instance separation, not
    # an invented pair of coordinates.
    result = auto_annotate_patch(_two_bars_image(), patch_id="BARS")
    assert result.gap_endpoint_a_xy is not None
    assert result.gap_endpoint_b_xy is not None
    ax, ay = result.gap_endpoint_a_xy
    bx, by = result.gap_endpoint_b_xy
    reported = float(np.hypot(bx - ax, by - ay))
    reference = gap_statistics(_two_bar_labels(), SCALE_1MM, min_gap_px=3.0).median_px
    assert reference is not None
    assert reported == pytest.approx(reference, abs=1.0)


def test_gap_endpoints_land_on_two_different_instances():
    # Endpoints are (x, y) and must be actual pixels of two *different* instances.
    labels = _two_bar_labels()
    result = auto_annotate_patch(_two_bars_image(), patch_id="BARS")
    ax, ay = result.gap_endpoint_a_xy
    bx, by = result.gap_endpoint_b_xy
    label_a = int(labels[ay, ax])
    label_b = int(labels[by, bx])
    assert label_a > 0 and label_b > 0
    assert label_a != label_b


# ------------------------------------------- honesty: what a machine may claim


def test_a_machine_may_not_declare_that_a_human_can_see_chips():
    # Final plan section 5.1 step 7 forbids pseudo-ground-truth. Visibility is a
    # human property; a segmentation count cannot establish it, so the field must
    # read "not_assessed" rather than "yes".
    result = auto_annotate_patch(_two_bars_image(), patch_id="BARS")
    assert result.chip_visible == NOT_ASSESSED
    assert result.gap_visible == NOT_ASSESSED


def test_the_annotation_is_marked_provisional_with_low_confidence():
    result = auto_annotate_patch(_two_bars_image(), patch_id="BARS")
    assert result.source == "automated_provisional"
    assert result.confidence <= PROVISIONAL_CONFIDENCE
    assert result.annotator_id.startswith("auto")


def test_the_annotation_emits_a_warning_so_it_cannot_be_used_unwittingly():
    with pytest.warns(UserWarning, match="provisional|Provisional"):
        auto_annotate_patch(_two_bars_image(), patch_id="BARS")


def test_unscaled_input_still_produces_pixel_space_output():
    result = auto_annotate_patch(_two_bars_image(), patch_id="BARS")
    # No scale supplied -> nothing may be reported in millimetres.
    assert result.gap_width_mm is None
    assert result.median_chip_diameter_mm is None


# ------------------------------------------------------- it must fit the template


def test_machine_rows_use_the_human_template_columns(tmp_path):
    from backend.aggregate.auto_annotation import write_annotations_csv

    out = tmp_path / "machine.csv"
    results = [auto_annotate_patch(_two_bars_image(), patch_id="BARS")]
    write_annotations_csv(results, out, source_image="bars.png", top=0, left=0)

    template_columns = list(
        csv.reader(open("annotation_guides/aggregate_patch_annotation_template.csv"))
    )[0]
    machine_columns = list(csv.reader(out.open(encoding="utf-8")))[0]
    assert machine_columns == template_columns


def test_a_human_row_can_be_appended_without_the_schema_changing(tmp_path):
    # The point of the whole design: humans land later and nothing breaks.
    from backend.aggregate.auto_annotation import write_annotations_csv

    out = tmp_path / "machine.csv"
    write_annotations_csv(
        [auto_annotate_patch(_two_bars_image(), patch_id="BARS")],
        out, source_image="bars.png", top=0, left=0,
    )
    rows = list(csv.reader(out.open(encoding="utf-8")))
    rows.append(["BARS", "bars.png", "0", "0", "256", "sheet.png", "A",
                 "yes", "7", "yes", "10,40", "10,70", "resolves", ""])
    with out.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)
    parsed = list(csv.DictReader(out.open(encoding="utf-8")))
    assert [row["annotator"] for row in parsed] == ["auto_v1", "A"]
    assert parsed[1]["chip_visible"] == "yes"
