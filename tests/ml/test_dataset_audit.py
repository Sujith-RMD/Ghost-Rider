"""Unit tests for the ``eval/dataset_audit.py`` helper functions (task J7).

Owned by the ML role (`docs/ML_ROLE.md` section 1, ``eval/`` is ML-writable).

Task J7 in ``docs/ml/TASKS.md`` records that the admission-audit helpers were
"exercised only on real archives, so not regression-protected". A real-archive
run is a smoke test, not a regression suite: it reports numbers but asserts
nothing about the *helpers* in isolation. These tests pin the behaviour of each
pure helper so a future refactor cannot silently change what "duplicate",
"out of range" or "cross-split near-duplicate" mean.

Honesty rules mirrored from the module under test:

* An **empty label file is a possible valid negative**, not an error, so it is
  counted separately from unparsable content.
* A dHash Hamming hit is a **candidate**, not a confirmed duplicate; only the
  two-stage correlation confirms it. These tests keep that distinction intact.
* ``_split_of`` must never *guess* a split - an unplaceable image is
  ``"unknown"`` so it cannot silently inflate a held-out set.

These tests are arithmetic and parsing logic on synthetic inputs. They establish
nothing about any real road dataset.
"""

from __future__ import annotations

import numpy as np
import pytest

from eval.dataset_audit import (
    ROBOFLOW_PREFIX,
    _find_label,
    _split_of,
    confirm_pairs,
    dhash,
    find_near_duplicate_pairs,
    parse_yolo_segment_label,
    polygon_stroke_width_px,
)


# --------------------------------------------------------------- YOLO parsing


def _write(tmp_path, name: str, text: str):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_parse_valid_polygon_counts_points_and_class(tmp_path):
    # One polygon: a triangle (3 points -> 6 coordinates) of class 0.
    path = _write(tmp_path, "a.txt", "0 0.1 0.1 0.5 0.1 0.3 0.6\n")
    parsed = parse_yolo_segment_label(path)
    assert parsed["polygons"] == 1
    assert parsed["points_total"] == 3
    assert parsed["classes"] == {"0": 1}
    assert parsed["unparsable_lines"] == 0
    assert parsed["too_few_points"] == 0
    assert parsed["out_of_range_polygons"] == 0
    assert len(parsed["coordinates"]) == 1


def test_parse_multiple_polygons_and_classes(tmp_path):
    path = _write(
        tmp_path,
        "b.txt",
        "0 0.1 0.1 0.5 0.1 0.3 0.6\n1 0.2 0.2 0.6 0.2 0.4 0.7 0.9 0.3\n",
    )
    parsed = parse_yolo_segment_label(path)
    assert parsed["polygons"] == 2
    assert parsed["classes"] == {"0": 1, "1": 1}
    assert parsed["points_total"] == 3 + 4


def test_empty_label_is_a_valid_negative_not_an_error(tmp_path):
    # Final plan section 6.1 item 3: report empty label files as possible valid
    # negatives rather than deleting them. polygons == 0 AND unparsable == 0 is
    # the "empty" signature the audit counts separately.
    path = _write(tmp_path, "empty.txt", "\n   \n")
    parsed = parse_yolo_segment_label(path)
    assert parsed["polygons"] == 0
    assert parsed["unparsable_lines"] == 0
    assert parsed["too_few_points"] == 0


def test_unparsable_line_is_counted_not_raised(tmp_path):
    path = _write(tmp_path, "c.txt", "0 0.1 0.1 0.5 0.1 0.3 0.6\nnot numbers here\n")
    parsed = parse_yolo_segment_label(path)
    assert parsed["unparsable_lines"] == 1
    assert parsed["polygons"] == 1  # the good line still parses


def test_too_few_points_is_counted(tmp_path):
    # A 2-point "polygon" has 4 coordinates (< 6) and is degenerate.
    path = _write(tmp_path, "d.txt", "0 0.1 0.1 0.5 0.1\n")
    parsed = parse_yolo_segment_label(path)
    assert parsed["too_few_points"] == 1
    assert parsed["polygons"] == 0


def test_odd_coordinate_count_is_counted_as_too_few(tmp_path):
    # 5 coordinates cannot form x/y pairs -> len(coords) % 2 != 0.
    path = _write(tmp_path, "e.txt", "0 0.1 0.2 0.3 0.4 0.5\n")
    parsed = parse_yolo_segment_label(path)
    assert parsed["too_few_points"] == 1


def test_out_of_range_polygon_is_flagged(tmp_path):
    # Coordinates must lie in [0, 1]; 1.5 is out of range.
    path = _write(tmp_path, "f.txt", "0 0.1 0.1 1.5 0.1 0.3 0.6\n")
    parsed = parse_yolo_segment_label(path)
    assert parsed["out_of_range_polygons"] == 1
    assert parsed["polygons"] == 1  # still counted as a polygon, just flagged


def test_exactly_one_is_not_out_of_range(tmp_path):
    # The upper bound is inclusive (1.0 + tolerance); a coordinate of exactly
    # 1.0 must not be flagged.
    path = _write(tmp_path, "g.txt", "0 0.0 0.0 1.0 0.0 1.0 1.0\n")
    parsed = parse_yolo_segment_label(path)
    assert parsed["out_of_range_polygons"] == 0


# ----------------------------------------------------------- stroke width


def test_stroke_width_of_a_fat_rectangle_is_its_width():
    # A rectangle 0.2 wide (in normalised x) by 0.6 tall on a 100x100 canvas is
    # ~20 px wide. 2*area/perimeter of a long thin rectangle tends to its short
    # side, so the estimate should land near 20 px.
    rect = np.array([[0.4, 0.1], [0.6, 0.1], [0.6, 0.9], [0.4, 0.9]])
    widths = polygon_stroke_width_px([rect], 100, 100)
    assert len(widths) == 1
    assert 15.0 < widths[0] < 22.0


def test_centerline_collapses_to_about_one_pixel():
    # A degenerate, zero-height polygon approximates a centerline label. Final
    # plan section 4.3: a centerline collapses to ~1 px, a real-width mask does
    # not. This is the discriminator the audit relies on.
    line = np.array([[0.1, 0.5], [0.5, 0.5], [0.9, 0.5], [0.5, 0.501]])
    widths = polygon_stroke_width_px([line], 100, 100)
    assert widths  # something is produced
    assert widths[0] < 2.5


def test_stroke_width_skips_degenerate_few_point_polygons():
    line = np.array([[0.1, 0.5], [0.9, 0.5]])  # 2 points -> skipped
    assert polygon_stroke_width_px([line], 100, 100) == []


# ------------------------------------------------------------------- dHash


def test_dhash_is_deterministic():
    rng = np.random.default_rng(0)
    img = rng.integers(0, 255, size=(64, 64), dtype=np.uint8)
    assert dhash(img) == dhash(img)


def test_dhash_identical_images_match_and_different_do_not():
    rng = np.random.default_rng(1)
    a = rng.integers(0, 255, size=(64, 64), dtype=np.uint8)
    b = a.copy()
    c = rng.integers(0, 255, size=(64, 64), dtype=np.uint8)
    assert dhash(a) == dhash(b)
    assert dhash(a) != dhash(c)


def test_dhash_inverts_with_gradient_direction():
    # A left-to-right dark-to-bright ramp and its mirror must differ.
    ramp = np.tile(np.linspace(0, 255, 64, dtype=np.uint8), (64, 1))
    assert dhash(ramp) != dhash(ramp[:, ::-1].copy())


# ------------------------------------------------------- near-duplicate pairs


def test_near_duplicates_only_across_splits():
    # hashes [0,1,0], splits [train,test,train].
    # Cross-split pairs within distance 1: (0,1) train/test dist 1, and
    # (1,2) test/train dist 1. Same-split pair (0,2) train/train is correctly
    # EXCLUDED - same-split duplicates are not cross-split leakage.
    hashes = np.array([0, 1, 0], dtype=np.uint64)
    splits = ["train", "test", "train"]
    pairs = find_near_duplicate_pairs(hashes, splits, max_distance=1)
    assert pairs == [(0, 1, 1), (1, 2, 1)]
    # The same-split pair (0,2) is absent.
    assert (0, 2, 0) not in pairs


def test_near_duplicates_respects_distance_threshold():
    # 0b0000 vs 0b1111 is distance 4; threshold 2 must exclude it.
    hashes = np.array([0, 15], dtype=np.uint64)
    splits = ["train", "test"]
    assert find_near_duplicate_pairs(hashes, splits, max_distance=2) == []
    assert find_near_duplicate_pairs(hashes, splits, max_distance=4) == [(0, 1, 4)]


def test_near_duplicates_no_self_or_reverse_pairs():
    hashes = np.array([7, 7], dtype=np.uint64)
    splits = ["train", "test"]
    # Identical but cross-split -> one pair, reported once, not (1,0) as well.
    assert find_near_duplicate_pairs(hashes, splits, max_distance=0) == [(0, 1, 0)]


# ------------------------------------------------------- split placement


def test_split_of_recognises_standard_dirs(tmp_path):
    for sub, expected in [
        ("train/x.png", "train"),
        ("val/x.png", "val"),
        ("valid/x.png", "val"),
        ("test/x.png", "test"),
        ("images/train/x.png", "train"),
    ]:
        p = tmp_path / sub
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"")
        assert _split_of(p, tmp_path) == expected


def test_split_of_returns_unknown_when_unplaceable(tmp_path):
    # Module docstring: never guess. An image outside any split directory is
    # "unknown" so it cannot inflate a held-out set.
    p = tmp_path / "misc/x.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")
    assert _split_of(p, tmp_path) == "unknown"


# ---------------------------------------------------------- label discovery


def test_find_label_maps_images_to_labels(tmp_path):
    img = tmp_path / "images" / "train" / "a.jpg"
    img.parent.mkdir(parents=True, exist_ok=True)
    img.write_bytes(b"")
    lbl = tmp_path / "labels" / "train" / "a.txt"
    lbl.parent.mkdir(parents=True, exist_ok=True)
    lbl.write_text("0 0.1 0.1 0.5 0.1 0.3 0.6\n", encoding="utf-8")
    assert _find_label(img) == lbl


def test_find_label_falls_back_to_sibling(tmp_path):
    img = tmp_path / "a.png"
    img.write_bytes(b"")
    lbl = tmp_path / "a.txt"
    lbl.write_text("", encoding="utf-8")
    assert _find_label(img) == lbl


def test_find_label_returns_none_when_absent(tmp_path):
    img = tmp_path / "lonely.jpg"
    img.write_bytes(b"")
    assert _find_label(img) is None


# ------------------------------------------------------- roboflow parent regex


def test_roboflow_prefix_extracts_parent():
    m = ROBOFLOW_PREFIX.match("road_01.rf.abcdef12")
    assert m is not None
    assert m.group("parent") == "road_01"


def test_roboflow_prefix_does_not_match_plain_name():
    assert ROBOFLOW_PREFIX.match("road_01") is None


# ----------------------------------------------------- confirm_pairs verdicts


def _tmp_gray(tmp_path, name: str, arr: np.ndarray):
    import cv2

    p = tmp_path / name
    cv2.imwrite(str(p), arr)
    return p


def test_confirm_pairs_rejects_uncorrelated_images(tmp_path):
    rng_a = np.random.default_rng(10)
    rng_b = np.random.default_rng(99)
    a = rng_a.integers(0, 255, size=(64, 64), dtype=np.uint8)
    b = rng_b.integers(0, 255, size=(64, 64), dtype=np.uint8)
    _tmp_gray(tmp_path, "a.png", a)
    _tmp_gray(tmp_path, "b.png", b)

    results = confirm_pairs(tmp_path, ["a.png", "b.png"], [(0, 1, 1)])
    assert len(results) == 1
    # Two independent noise images must not be "confirmed" as duplicates.
    assert results[0]["verdict"] in ("rejected", "probable")


def test_confirm_pairs_confirms_identical_images(tmp_path):
    rng = np.random.default_rng(5)
    a = rng.integers(0, 255, size=(64, 64), dtype=np.uint8)
    _tmp_gray(tmp_path, "a.png", a)
    _tmp_gray(tmp_path, "b.png", a)  # identical content

    results = confirm_pairs(tmp_path, ["a.png", "b.png"], [(0, 1, 1)])
    assert results[0]["verdict"] == "confirmed"
    assert results[0]["correlation"] == pytest.approx(1.0, abs=1e-6)
