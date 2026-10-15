"""Synthetic regressions for admission tooling, not road accuracy evidence."""

import ast
from pathlib import Path

import cv2
import numpy as np
import pytest

from backend.quality import QualityPolicy
from eval import dataset_audit as audit_tools
from eval.quality_gate import run_gate


def image(path, size=64, channels=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    shape = (size, size) if channels is None else (size, size, channels)
    arr = np.random.default_rng(4).integers(30, 220, shape, dtype=np.uint8)
    assert cv2.imwrite(str(path), arr)
    return path


@pytest.mark.parametrize("token", ["nan", "inf", "-inf", "-1", "0.5"])
def test_invalid_class_is_reported_without_crash(tmp_path, token):
    path = tmp_path / "label.txt"
    path.write_text(f"{token} 0 0 1 0 1 1\n", encoding="utf-8")
    parsed = audit_tools.parse_yolo_segment_label(path)
    assert parsed["unparsable_lines"] == 1
    assert parsed["polygons"] == 0


@pytest.mark.parametrize("token", ["nan", "inf", "-inf"])
def test_nonfinite_coordinate_is_not_a_valid_polygon(tmp_path, token):
    path = tmp_path / "label.txt"
    path.write_text(f"0 0 0 1 0 1 {token}\n", encoding="utf-8")
    parsed = audit_tools.parse_yolo_segment_label(path)
    assert parsed["unparsable_lines"] == 1
    assert parsed["coordinates"] == []


def test_audit_labels_even_when_images_do_not_decode(tmp_path):
    for split in ("train", "test"):
        path = tmp_path / "images" / split / "bad.png"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"invalid image")
    label = tmp_path / "labels/train/bad.txt"
    label.parent.mkdir(parents=True)
    label.write_text("0 0 0 1 1\n", encoding="utf-8")
    orphan = tmp_path / "labels/test/nested/orphan.txt"
    orphan.parent.mkdir(parents=True)
    orphan.write_text("", encoding="utf-8")
    report = audit_tools.audit(tmp_path, "synthetic")
    assert report["decode"]["failures"] == 2
    assert report["labels"]["images_without_label"] == 1
    assert report["labels"]["empty_label_files"] == 0
    assert report["labels"]["problems"] == {"too_few_points": 1}
    assert report["labels"]["orphan_label_files"] == 1
    assert report["leakage"]["cross_split_near_duplicate_candidates"] == 0


def test_near_pair_indices_survive_decode_failure(tmp_path):
    image(tmp_path / "images/test/a.png")
    (tmp_path / "images/test/b.png").write_bytes(b"broken")
    image(tmp_path / "images/train/c.PNG")
    report = audit_tools.audit(tmp_path, "synthetic")
    assert report["leakage"]["candidate_verdicts"] == {"confirmed": 1}
    pair = report["leakage"]["confirmed_pairs"][0]
    assert Path(pair["a"]).name == "a.png"
    assert Path(pair["b"]).name == "c.PNG"


def test_directory_is_not_a_label(tmp_path):
    path = image(tmp_path / "a.png")
    path.with_suffix(".txt").mkdir()
    assert audit_tools._find_label(path) is None


def test_annotation_write_failure_is_not_success(tmp_path, monkeypatch):
    image(tmp_path / "source/a.png")
    monkeypatch.setattr(audit_tools.cv2, "imwrite", lambda *args: False)
    with pytest.raises(SystemExit, match="failed to write"):
        audit_tools.write_annotation_patches(
            tmp_path / "source", tmp_path / "sheet.png", count=1, crop_px=32
        )


def test_annotation_mixed_size_does_not_publish_truncated_patch(tmp_path):
    image(tmp_path / "source/a.png", size=64)
    image(tmp_path / "source/b.png", size=16)
    with pytest.raises(ValueError, match="bounds"):
        audit_tools.write_annotation_patches(
            tmp_path / "source", tmp_path / "sheet.png", count=2, crop_px=32
        )


def test_contact_sheet_lists_only_rendered_images(tmp_path):
    image(tmp_path / "source/a.png")
    (tmp_path / "source/b.png").write_bytes(b"broken")
    meta = audit_tools.write_contact_sheet(
        tmp_path / "source", tmp_path / "sheet.png", tile_px=32
    )
    assert meta["tiles"] == 1
    assert meta["sampled_files"] == ["a.png"]
    assert meta["sheet_shape_hwc"] == list(cv2.imread(str(tmp_path / "sheet.png")).shape)


def test_contact_sheet_rejects_all_failed_decodes(tmp_path):
    (tmp_path / "bad.png").write_bytes(b"broken")
    with pytest.raises(SystemExit, match="no tiles"):
        audit_tools.write_contact_sheet(tmp_path, tmp_path / "sheet.png")


@pytest.mark.parametrize("kwargs", [{"columns": 0}, {"columns": -1}, {"tile_px": 0}])
def test_contact_sheet_invalid_layout(tmp_path, kwargs):
    image(tmp_path / "a.png")
    with pytest.raises(ValueError):
        audit_tools.write_contact_sheet(tmp_path, tmp_path / "sheet.png", **kwargs)


def test_quality_discovery_and_unique_paths(tmp_path):
    image(tmp_path / "a/same.png")
    image(tmp_path / "b/same.png")
    image(tmp_path / "c.webp")
    (tmp_path / "directory.png").mkdir()
    report = run_gate(tmp_path, max_listed=0)
    assert report["images"] == 3
    assert len({row["file"] for row in report["per_image"]}) == 3
    assert report["rejected_or_limited_examples"] == []
    assert report["reason_counts"]["scale_missing"] == 3


def test_quality_preserves_source_channels(tmp_path):
    image(tmp_path / "gray.png")
    policy = QualityPolicy(supported_channels=(3,), min_source_px=1)
    report = run_gate(tmp_path, policy=policy)
    assert report["reason_counts"]["unsupported_channels"] == 1


def test_quality_negative_limit_rejected(tmp_path):
    with pytest.raises(ValueError, match="max_listed"):
        run_gate(tmp_path, max_listed=-1)


def test_quality_note_matches_calibration(tmp_path):
    image(tmp_path / "a.png")
    report = run_gate(tmp_path, policy=QualityPolicy(thresholds_calibrated=True))
    assert "provisional" not in report["note"]
    assert "engineering defaults" not in report["note"]


def test_existing_test_module_compiles_and_has_unique_tests():
    path = Path(__file__).with_name("test_dataset_audit.py")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    assert len(names) == len(set(names))
