import numpy as np

from backend.aggregate.segmentation import WatershedConfig
from backend.aggregate.tiling import TilingConfig, segment_tiled, segment_tiled_with_stages
from backend import analysis
from eval.processing_evidence import build_bundle


def test_tiled_processing_evidence_matches_the_production_candidate_labels():
    image = np.full((96, 112), 90, dtype=np.uint8)
    yy, xx = np.ogrid[:96, :112]
    image[(yy - 46) ** 2 + (xx - 46) ** 2 <= 15 ** 2] = 180
    image[(yy - 46) ** 2 + (xx - 72) ** 2 <= 15 ** 2] = 180
    watershed = WatershedConfig(min_instance_area_px=8, hole_fill_max_area_px=4)
    tiling = TilingConfig(tile_px=64, overlap_px=16)

    labels, stages = segment_tiled_with_stages(image, tiling, watershed)

    assert np.array_equal(labels, segment_tiled(image, tiling, watershed))
    assert stages["candidate_labels"].shape == image.shape
    assert stages["distance_transform"].shape == image.shape
    assert stages["otsu_binary"].shape == image.shape
    assert stages["markers"].shape == image.shape
    assert np.issubdtype(stages["candidate_labels"].dtype, np.integer)


def test_analysis_adapter_can_return_stages_without_changing_its_measurement():
    image = np.full((320, 320), 90, dtype=np.uint8)
    yy, xx = np.ogrid[:320, :320]
    image[(yy - 160) ** 2 + (xx - 160) ** 2 <= 45 ** 2] = 180

    ordinary = analysis.measure_frame(image)
    traced = analysis.measure_frame(image, include_processing_stages=True)

    assert traced["metrics"].chip_count == ordinary["metrics"].chip_count
    assert traced["processing_stages"]["candidate_labels"].shape == image.shape
    assert traced["quality"].status == ordinary["quality"].status


def test_bundle_preserves_original_and_marks_candidate_count_unvalidated(tmp_path):
    import cv2

    source = tmp_path / "road.png"
    image = np.full((320, 320, 3), 90, dtype=np.uint8)
    yy, xx = np.ogrid[:320, :320]
    image[(yy - 160) ** 2 + (xx - 160) ** 2 <= 45 ** 2] = (180, 180, 180)
    assert cv2.imwrite(str(source), image)
    original_bytes = source.read_bytes()

    manifest = build_bundle(source, tmp_path / "evidence")

    assert (tmp_path / "evidence" / "original.png").read_bytes() == original_bytes
    assert manifest["calibration"]["physical_validation"] is False
    assert manifest["roi"]["available"] is False
    assert manifest["candidate_count"]["verified"] is False
    assert manifest["candidate_count"]["count"] is not None
    assert all((tmp_path / "evidence" / item["file"]).is_file() for item in manifest["stages"].values())


def test_rejected_image_keeps_original_and_marks_unrun_stages_unavailable(tmp_path):
    import cv2

    source = tmp_path / "blank.png"
    assert cv2.imwrite(str(source), np.full((320, 320, 3), 127, dtype=np.uint8))

    manifest = build_bundle(source, tmp_path / "rejected-evidence")

    assert manifest["quality"]["status"] == "rejected"
    assert manifest["candidate_count"]["count"] is None
    assert all(stage["status"] == "unavailable" for stage in manifest["stages"].values())
