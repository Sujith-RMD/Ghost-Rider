"""Measurement-core tests: scale, plane geometry, segmentation, features, record.

Consolidated from five modules plus a shared helpers file, so the whole core is
verified with one command rather than six files.

Synthetic fixtures with analytically known area and separation are used because
final plan section 13.4 states that synthetic geometric shapes are the right tool
for checking *arithmetic* correctness. They establish nothing about real pavement
accuracy; that requires the reviewed annotation pilot on admitted real imagery.

Run:
    python -m pytest tests/ml/test_measurement_core.py -q
"""

from __future__ import annotations

import json
import math

import cv2
import numpy as np
import pytest

from backend.aggregate import (
    GAP_METHOD_VERSION,
    TEX_METHOD_VERSION,
    MeasurementConfig,
    TextureStatistics,
    WatershedConfig,
    aggregate_coverage,
    count_density_per_m2,
    gap_statistics,
    instance_properties,
    measure_surface,
    particle_size_stats,
    renumber_labels,
    segment_aggregate,
    skeletonize_2d,
    texture_statistics,
)
from backend.aggregate.features import _glcm_features
from backend.geometry import (
    PlanarScale,
    ScaleSource,
    UnscaledError,
    apply_homography,
    equivalent_diameter_mm,
    invert_homography,
    local_scale,
    normalize_homography,
    plane_homography,
    polygon_area,
    project_points_to_plane,
)

# =============================================================================
# Synthetic fixtures (folded from the former tests/ml/helpers.py)
# =============================================================================


def synthetic_disks_image(
    height: int = 200,
    width: int = 200,
    background: int = 60,
    disk_value: int = 200,
    radius: int = 12,
    centers_yx: tuple[tuple[int, int], ...] = ((40, 40), (40, 140), (140, 40), (140, 140)),
) -> np.ndarray:
    """Flat-background image with bright circular "chips" of known radius."""
    image = np.full((height, width), background, dtype=np.uint8)
    yy, xx = np.mgrid[0:height, 0:width]
    for cy, cx in centers_yx:
        image[(yy - cy) ** 2 + (xx - cx) ** 2 <= radius * radius] = disk_value
    return image


def disk_labels(
    height: int = 200,
    width: int = 200,
    radius: int = 12,
    centers_yx: tuple[tuple[int, int], ...] = ((40, 40), (140, 140)),
) -> np.ndarray:
    """Label map with one instance per supplied disk centre."""
    labels = np.zeros((height, width), dtype=np.int32)
    yy, xx = np.mgrid[0:height, 0:width]
    for index, (cy, cx) in enumerate(centers_yx, start=1):
        labels[(yy - cy) ** 2 + (xx - cx) ** 2 <= radius * radius] = index
    return labels


def two_bar_labels(
    height: int = 200,
    width: int = 200,
    bar_a_rows: tuple[int, int] = (40, 60),
    bar_b_rows: tuple[int, int] = (70, 90),
) -> np.ndarray:
    """Two full-width bars, labelled 1 and 2, with a known vertical separation."""
    labels = np.zeros((height, width), dtype=np.int32)
    labels[bar_a_rows[0] : bar_a_rows[1], :] = 1
    labels[bar_b_rows[0] : bar_b_rows[1], :] = 2
    return labels


def single_bar_labels(
    height: int = 200,
    width: int = 200,
    bar_rows: tuple[int, int] = (80, 100),
) -> np.ndarray:
    """One full-width bar labelled 1, surrounded by open gap region."""
    labels = np.zeros((height, width), dtype=np.int32)
    labels[bar_rows[0] : bar_rows[1], :] = 1
    return labels


def _count(labels: np.ndarray) -> int:
    return int(np.count_nonzero(np.unique(labels) > 0))


# Shared constants. Values are identical to the per-module originals.
SCALE_1MM = PlanarScale.calibrated(1.0, 1.0, ScaleSource.SOURCE_CALIBRATED, "synthetic")
SCALE_HALF_MM = PlanarScale.calibrated(0.5, 0.5, ScaleSource.SOURCE_CALIBRATED, "synthetic")
UNSCALED = PlanarScale.unscaled(provenance="synthetic fixture with no scale")

RADIUS = 12
CENTERS = ((40, 40), (40, 140), (140, 40), (140, 140))
HEIGHT = WIDTH = 200
N_DISKS = len(CENTERS)

# Downward-looking camera at height 1.5 m with identity rotation.
FX = FY = 1000.0
CX, CY = 640.0, 360.0
HEIGHT_M = 1.5
K_DOWN = np.array([[FX, 0.0, CX], [0.0, FY, CY], [0.0, 0.0, 1.0]])
R_IDENTITY = np.eye(3)
T_DOWN = np.array([0.0, 0.0, HEIGHT_M])

# two_bar_labels() leaves a 10-row gap; the facing aggregate pixel rows are 59
# and 70, so the pixel-centre separation is 11 px.
EXPECTED_BAR_GAP_PX = 11


def _image() -> np.ndarray:
    return synthetic_disks_image(height=HEIGHT, width=WIDTH, radius=RADIUS, centers_yx=CENTERS)


def _full_valid() -> np.ndarray:
    return np.ones((HEIGHT, WIDTH), dtype=bool)


# =============================================================================
# 1. Planar scale: units, lineage, uncertainty, null-versus-zero
# =============================================================================


def test_unscaled_has_no_metric_area():
    scale = PlanarScale.unscaled(provenance="judge upload, no reference")
    assert scale.is_scaled is False
    assert scale.area_m2(10_000) is None
    assert scale.pixel_area_mm2 is None
    assert scale.equivalent_mm_per_px is None
    assert scale.relative_area_uncertainty() is None


def test_unscaled_must_not_carry_mm_per_px():
    with pytest.raises(ValueError):
        PlanarScale(
            sx_mm_per_px=1.0,
            sy_mm_per_px=1.0,
            source=ScaleSource.UNSCALED,
            provenance="contradictory",
        )


def test_unscaled_area_is_none_but_zero_is_measurable():
    assert PlanarScale.unscaled().area_m2(0) is None
    scaled = PlanarScale.calibrated(1.0, 1.0, ScaleSource.SOURCE_CALIBRATED, "d")
    # A measured empty region is 0.0, not None.
    assert scaled.area_m2(0) == 0.0


def test_require_scaled_raises_for_unscaled():
    with pytest.raises(UnscaledError):
        PlanarScale.unscaled(provenance="dashcam").require_scaled()


def test_area_from_pixels_matches_plan_formula():
    scale = PlanarScale.calibrated(1.0, 1.0, ScaleSource.SOURCE_CALIBRATED, "src")
    # 1000 px * 1 mm^2/px = 1000 mm^2 = 1e-3 m^2
    assert scale.area_m2(1000) == pytest.approx(1e-3, rel=1e-12)


def test_anisotropic_scale_multiplies_both_axes():
    scale = PlanarScale.calibrated(2.0, 3.0, ScaleSource.RIG_CALIBRATED, "rig-1")
    assert scale.pixel_area_mm2 == pytest.approx(6.0)
    assert scale.area_m2(100) == pytest.approx(600.0 / 1e6, rel=1e-12)


def test_downsample_doubles_mm_per_px_and_preserves_physical_area():
    original = PlanarScale.calibrated(1.0, 1.0, ScaleSource.SOURCE_CALIBRATED, "src")
    downsampled = original.resized(0.5, 0.5)
    assert downsampled.sx_mm_per_px == pytest.approx(2.0)
    assert downsampled.sy_mm_per_px == pytest.approx(2.0)
    # Halving each axis keeps a quarter of the pixels for the same physical
    # region, and each of those pixels is four times the area.
    assert downsampled.area_m2(100) == pytest.approx(original.area_m2(400), rel=1e-12)


def test_upsample_reduces_mm_per_px():
    original = PlanarScale.calibrated(2.0, 2.0, ScaleSource.SOURCE_CALIBRATED, "src")
    assert original.resized(4.0, 4.0).sx_mm_per_px == pytest.approx(0.5)


def test_resize_records_lineage():
    original = PlanarScale.calibrated(1.0, 1.0, ScaleSource.SOURCE_CALIBRATED, "GAPs 10m")
    resized = original.resized(0.5, 0.5)
    assert "GAPs 10m" in resized.provenance
    assert "resized" in resized.provenance


def test_resize_of_unscaled_stays_unscaled():
    assert PlanarScale.unscaled(provenance="upload").resized(0.5, 0.5).is_scaled is False


def test_cropping_preserves_scale():
    scale = PlanarScale.calibrated(0.91, 0.91, ScaleSource.SOURCE_CALIBRATED, "istd")
    assert scale.cropped().sx_mm_per_px == pytest.approx(0.91)
    assert scale.cropped().source is scale.source


def test_resize_rejects_non_positive_factors():
    scale = PlanarScale.calibrated(1.0, 1.0, ScaleSource.RIG_CALIBRATED, "rig")
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            scale.resized(bad, 1.0)


def test_calibrated_requires_positive_finite_values():
    for sx, sy in ((0.0, 1.0), (1.0, -2.0), (float("nan"), 1.0), (float("inf"), 1.0)):
        with pytest.raises(ValueError):
            PlanarScale.calibrated(sx, sy, ScaleSource.RIG_CALIBRATED, "rig")


def test_calibrated_rejects_unscaled_source():
    with pytest.raises(ValueError):
        PlanarScale.calibrated(1.0, 1.0, ScaleSource.UNSCALED, "rig")


def test_relative_area_uncertainty_adds_variances():
    scale = PlanarScale.calibrated(
        1.0,
        1.0,
        ScaleSource.RIG_CALIBRATED,
        "rig",
        rel_uncertainty_x=0.05,
        rel_uncertainty_y=0.05,
    )
    assert scale.relative_area_uncertainty() == pytest.approx(math.sqrt(0.005), rel=1e-12)


def test_relative_area_uncertainty_none_when_unreported():
    assert PlanarScale.calibrated(1.0, 1.0, ScaleSource.RIG_CALIBRATED, "rig").relative_area_uncertainty() is None


def test_negative_uncertainty_rejected():
    with pytest.raises(ValueError):
        PlanarScale.calibrated(
            1.0, 1.0, ScaleSource.RIG_CALIBRATED, "rig", rel_uncertainty_x=-0.1
        )


def test_area_rejects_negative_pixel_count():
    with pytest.raises(ValueError):
        PlanarScale.calibrated(1.0, 1.0, ScaleSource.RIG_CALIBRATED, "rig").area_m2(-5)


def test_equivalent_diameter_matches_circle_formula():
    assert equivalent_diameter_mm(100.0) == pytest.approx(2.0 * math.sqrt(100.0 / math.pi))
    assert equivalent_diameter_mm(0.0) == 0.0


def test_equivalent_diameter_rejects_bad_input():
    with pytest.raises(ValueError):
        equivalent_diameter_mm(-1.0)


def test_describe_carries_provenance_and_units():
    scale = PlanarScale.calibrated(
        0.5,
        0.5,
        ScaleSource.REFERENCE_MEASURED,
        "checkerboard 40 mm squares",
        rel_uncertainty_x=0.02,
        rel_uncertainty_y=0.02,
    )
    described = scale.describe()
    assert described["scale_source"] == "reference_measured"
    assert described["sx_mm_per_px"] == pytest.approx(0.5)
    assert described["equivalent_mm_per_px"] == pytest.approx(0.5)
    assert described["scale_provenance"] == "checkerboard 40 mm squares"
    assert described["relative_area_uncertainty"] == pytest.approx(math.sqrt(0.0008))


# =============================================================================
# 2. Road-plane homography: projection, local scale, polygon area
# =============================================================================


def test_plane_origin_maps_to_principal_point():
    mapped = apply_homography(plane_homography(K_DOWN, R_IDENTITY, T_DOWN), np.array([[0.0, 0.0]]))
    assert mapped[0, 0] == pytest.approx(CX, rel=1e-9)
    assert mapped[0, 1] == pytest.approx(CY, rel=1e-9)


def test_plane_point_maps_to_expected_pixel():
    expected_u = CX + FX * 1.0 / HEIGHT_M
    mapped = apply_homography(plane_homography(K_DOWN, R_IDENTITY, T_DOWN), np.array([[1.0, 0.0]]))
    assert mapped[0, 0] == pytest.approx(expected_u, rel=1e-9)
    assert mapped[0, 1] == pytest.approx(CY, rel=1e-9)


def test_normalized_homography_has_unit_bottom_right():
    assert plane_homography(K_DOWN, R_IDENTITY, T_DOWN)[2, 2] == pytest.approx(1.0)


def test_local_scale_for_downward_camera_is_height_over_focal():
    scale = local_scale(plane_homography(K_DOWN, R_IDENTITY, T_DOWN), (CX, CY))
    # 1.5 m / 1000 px = 1.5 mm/px
    assert scale.min_mm_per_px == pytest.approx(1.5, rel=1e-9)
    assert scale.max_mm_per_px == pytest.approx(1.5, rel=1e-9)
    assert scale.mean_mm_per_px == pytest.approx(1.5, rel=1e-9)
    assert scale.anisotropy == pytest.approx(1.0, rel=1e-9)


def test_local_scale_is_uniform_for_a_similarity_homography():
    # H maps plane -> image with a factor of 2, so the inverse maps one image
    # pixel to 0.5 plane units. With mm_per_plane_unit=1.0 that is 0.5 mm/px.
    h = np.array([[2.0, 0.0, 10.0], [0.0, 2.0, -5.0], [0.0, 0.0, 1.0]])
    for point in ((0.0, 0.0), (100.0, 50.0), (500.0, 900.0)):
        scale = local_scale(h, point, mm_per_plane_unit=1.0)
        assert scale.min_mm_per_px == pytest.approx(0.5, rel=1e-9)
        assert scale.max_mm_per_px == pytest.approx(0.5, rel=1e-9)
        assert scale.anisotropy == pytest.approx(1.0, rel=1e-9)


def test_local_scale_recovers_anisotropic_axes():
    # One pixel spans 1/3 plane unit in x and 1/5 in y, so mm/px is 1/3 and 1/5.
    h = np.array([[3.0, 0.0, 0.0], [0.0, 5.0, 0.0], [0.0, 0.0, 1.0]])
    scale = local_scale(h, (10.0, 10.0), mm_per_plane_unit=1.0)
    assert scale.min_mm_per_px == pytest.approx(1.0 / 5.0, rel=1e-9)
    assert scale.max_mm_per_px == pytest.approx(1.0 / 3.0, rel=1e-9)
    assert scale.mean_mm_per_px == pytest.approx(np.sqrt(1.0 / 15.0), rel=1e-9)
    assert scale.anisotropy == pytest.approx(5.0 / 3.0, rel=1e-9)


def test_local_scale_varies_under_perspective():
    h = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.002, 0.0, 1.0]])
    near = local_scale(h, (100.0, 100.0))
    far = local_scale(h, (400.0, 100.0))
    assert near.mean_mm_per_px != pytest.approx(far.mean_mm_per_px, rel=1e-6)


def test_plane_units_conversion_is_applied():
    h = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    assert local_scale(h, (0.0, 0.0), mm_per_plane_unit=1000.0).mean_mm_per_px == pytest.approx(1000.0)
    assert local_scale(h, (0.0, 0.0), mm_per_plane_unit=1.0).mean_mm_per_px == pytest.approx(1.0)


def test_invert_round_trips_projection():
    h = plane_homography(K_DOWN, R_IDENTITY, T_DOWN)
    plane_points = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
    recovered = project_points_to_plane(h, apply_homography(h, plane_points))
    assert np.allclose(recovered, plane_points, atol=1e-9)


def test_polygon_area_of_unit_square_round_trip():
    h = plane_homography(K_DOWN, R_IDENTITY, T_DOWN)
    plane_square = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]])
    back_projected = project_points_to_plane(h, apply_homography(h, plane_square))
    # 1 m^2 = 1e6 mm^2
    assert polygon_area(back_projected) == pytest.approx(1.0, rel=1e-9)
    assert polygon_area(back_projected) * 1e6 == pytest.approx(1e6, rel=1e-9)


def test_polygon_area_is_orientation_independent():
    clockwise = np.array([[0.0, 0.0], [0.0, 2.0], [3.0, 2.0], [3.0, 0.0]])
    assert polygon_area(clockwise) == pytest.approx(6.0)


def test_polygon_area_rejects_degenerate_polygon():
    with pytest.raises(ValueError):
        polygon_area(np.array([[0.0, 0.0], [1.0, 1.0]]))


def test_horizon_point_is_rejected_not_silently_wrapped():
    h = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 0.0, 1.0]])
    with pytest.raises(ValueError):
        apply_homography(h, np.array([[-1.0, 0.0]]))


def test_zero_bottom_right_homography_cannot_be_normalized():
    with pytest.raises(ValueError):
        normalize_homography(np.zeros((3, 3)))


def test_singular_homography_rejected():
    singular = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 0.0, 1.0]])
    singular[1, :] = singular[0, :]  # rank deficient, H[2,2] still non-zero
    with pytest.raises(ValueError):
        invert_homography(singular)


def test_bad_camera_shapes_rejected():
    with pytest.raises(ValueError):
        plane_homography(np.eye(2), R_IDENTITY, T_DOWN)
    with pytest.raises(ValueError):
        plane_homography(K_DOWN, np.eye(2), T_DOWN)
    with pytest.raises(ValueError):
        plane_homography(K_DOWN, R_IDENTITY, np.zeros(2))


def test_apply_homography_validates_point_shape():
    with pytest.raises(ValueError):
        apply_homography(np.eye(3), np.zeros((3, 3)))


# =============================================================================
# 3. Classical aggregate segmentation
# =============================================================================


def test_counts_four_separated_disks():
    assert _count(segment_aggregate(synthetic_disks_image(radius=RADIUS, centers_yx=CENTERS))) == N_DISKS


def test_instance_diameters_are_close_to_ground_truth():
    labels = segment_aggregate(synthetic_disks_image(radius=RADIUS, centers_yx=CENTERS))
    for props in instance_properties(labels):
        assert props.equivalent_diameter_px == pytest.approx(2.0 * RADIUS, rel=0.15)


def test_instances_are_separated_by_expected_centroids():
    labels = segment_aggregate(synthetic_disks_image(radius=RADIUS, centers_yx=CENTERS))
    centroids = sorted(props.centroid_yx for props in instance_properties(labels))
    for (cy, cx), (ey, ex) in zip(centroids, sorted(CENTERS)):
        assert cy == pytest.approx(ey, abs=2.0)
        assert cx == pytest.approx(ex, abs=2.0)


def test_labels_start_at_one_and_are_contiguous():
    labels = segment_aggregate(synthetic_disks_image(radius=RADIUS, centers_yx=CENTERS))
    assert list(np.unique(labels[labels > 0])) == list(range(1, N_DISKS + 1))


def test_darker_polarity_supported():
    inverted = synthetic_disks_image(
        radius=RADIUS, centers_yx=CENTERS, background=200, disk_value=60
    )
    assert _count(segment_aggregate(inverted, WatershedConfig(polarity="darker"))) == N_DISKS


def test_uniform_image_yields_no_instances():
    assert _count(segment_aggregate(np.full((64, 64), 128, dtype=np.uint8))) == 0


def test_tiny_image_rejected():
    with pytest.raises(ValueError):
        segment_aggregate(np.zeros((2, 2), dtype=np.uint8))


def test_empty_image_rejected():
    with pytest.raises(ValueError):
        segment_aggregate(np.zeros((0, 0), dtype=np.uint8))


def test_three_channel_bgr_input_supported():
    gray = synthetic_disks_image(radius=RADIUS, centers_yx=CENTERS)
    assert _count(segment_aggregate(np.repeat(gray[:, :, None], 3, axis=2))) == N_DISKS


def test_invalid_polarity_rejected():
    with pytest.raises(ValueError):
        WatershedConfig(polarity="mixed")


def test_instances_below_the_declared_minimum_area_are_dropped():
    # Final plan section 7.3: count only particles above the validated minimum
    # size, and record that minimum. A radius-3 disk is ~29 px; a radius-12 disk
    # is ~441 px, so a 100 px minimum must keep the large one and drop the speck.
    image = synthetic_disks_image(height=200, width=200, radius=RADIUS, centers_yx=((70, 70),))
    yy, xx = np.mgrid[0:200, 0:200]
    image = image.copy()
    image[(yy - 70) ** 2 + (xx - 150) ** 2 <= 3 ** 2] = 190
    assert _count(segment_aggregate(image)) == 2

    kept = segment_aggregate(image, WatershedConfig(min_instance_area_px=100))
    assert _count(kept) == 1
    assert instance_properties(kept)[0].area_px > 100


def test_minimum_area_filter_changes_labels_but_not_measured_areas():
    # The filter removes instances; it must never rescale the ones it keeps.
    image = synthetic_disks_image(height=200, width=200, radius=RADIUS, centers_yx=((70, 70),))
    unfiltered = instance_properties(segment_aggregate(image))[0].area_px
    filtered = instance_properties(
        segment_aggregate(image, WatershedConfig(min_instance_area_px=100))
    )[0].area_px
    assert filtered == unfiltered


def test_negative_minimum_area_rejected():
    with pytest.raises(ValueError):
        WatershedConfig(min_instance_area_px=-1)


def test_thin_binder_joint_between_touching_chips_is_preserved():
    # Two tangent radius-12 chips with a 2 px dark joint along the contact line.
    # The joint is the *only* evidence that these are two particles (final plan
    # section 6.3: split touching particles only when a boundary is visible), so
    # no clean-up step may bridge it.
    image = synthetic_disks_image(
        height=120, width=200, radius=RADIUS, centers_yx=((60, 70), (60, 94)),
        background=60, disk_value=200,
    )
    image = image.copy()
    image[:, 81:83] = 60
    assert _count(segment_aggregate(image)) == 2


def test_small_thresholding_holes_inside_a_chip_are_filled():
    # The close step existed to remove holes caused by thresholding. Filling
    # interior holes directly keeps that behaviour without merging neighbours.
    clean = synthetic_disks_image(height=200, width=200, radius=RADIUS, centers_yx=((70, 70),))
    holed = clean.copy()
    yy, xx = np.mgrid[0:200, 0:200]
    holed[(yy - 70) ** 2 + (xx - 70) ** 2 <= 1 ** 2] = 60  # 5 px interior hole
    clean_area = instance_properties(segment_aggregate(clean))[0].area_px
    holed_area = instance_properties(segment_aggregate(holed))[0].area_px
    assert holed_area == pytest.approx(clean_area, rel=0.02)


def test_hole_filling_is_bounded_by_its_area_limit():
    # A dark patch larger than the limit is a real background region, not a
    # thresholding hole, so it must survive.
    holed = synthetic_disks_image(height=200, width=200, radius=RADIUS, centers_yx=((70, 70),))
    yy, xx = np.mgrid[0:200, 0:200]
    big_hole = (yy - 70) ** 2 + (xx - 70) ** 2 <= 6 ** 2  # 113 px
    holed = holed.copy()
    holed[big_hole] = 60
    labels = segment_aggregate(holed, WatershedConfig(hole_fill_max_area_px=16))
    assert int(np.count_nonzero(labels == 0)) > 100


def test_negative_hole_fill_limit_rejected():
    with pytest.raises(ValueError):
        WatershedConfig(hole_fill_max_area_px=-1)


def test_invalid_marker_method_rejected():
    with pytest.raises(ValueError):
        WatershedConfig(marker_method="kmeans")


def test_marker_h_max_fraction_out_of_range_rejected():
    with pytest.raises(ValueError):
        WatershedConfig(marker_h_max_fraction=1.0)


def test_relative_h_maxima_is_the_default_marker_method():
    assert WatershedConfig().marker_method == "h_maxima"


def test_disconnected_regions_are_never_stolen_by_another_basin():
    # cv2.watershed floods through the *background*, not just the foreground, so
    # with a single global call one component can swallow another that is fully
    # separate. Measured: both markers were placed correctly at (50,1) and (80,0),
    # yet the output was ONE instance of 7920 px - a silent under-count that would
    # hit real imagery wherever chips form separate blobs.
    image = np.full((200, 200), 60, dtype=np.uint8)
    image[40:60, :] = 200
    image[70:90, :] = 200
    labels = segment_aggregate(image)
    assert _count(labels) == 2
    areas = sorted(props.area_px for props in instance_properties(labels))
    # each bar is 20 x 200 = 4000 px; a single-marker component is labelled
    # directly, so nothing is eaten by a ridge line
    assert all(3800 < area <= 4000 for area in areas), areas


def test_the_segmentation_version_changed_when_the_basin_rule_changed():
    # Splitting basins per connected component changes measured output, so the
    # version moves rather than silently re-using agg-classical-v2.
    assert WatershedConfig().config_version == "agg-classical-v3"


def _chain_image(joints: bool) -> np.ndarray:
    """Three radius-15 chips in a row, optionally separated by visible joints.

    Centres are 30 px apart, so the contact lines fall at x = 85 and x = 115.
    """
    image = np.full((120, 260), 60, dtype=np.uint8)
    yy, xx = np.mgrid[0:120, 0:260]
    for cx in (70, 100, 130):
        image[(yy - 60) ** 2 + (xx - cx) ** 2 <= 15 ** 2] = 200
    if joints:
        image = image.copy()
        image[:, 84:86] = 60
        image[:, 114:116] = 60
    return image


def test_a_chain_with_visible_joints_is_split_into_three_chips():
    assert _count(segment_aggregate(_chain_image(joints=True))) == 3


def test_a_uniform_elongated_region_stays_one_instance_instead_of_fragmenting():
    # A flat region produces a distance-transform *plateau*. The legacy greedy NMS
    # seeding put a marker every marker_min_distance_px along the plateau -
    # measured on this exact 20x120 bar it returned 26 fragments. Relative
    # h-maxima see one connected plateau and report one region, which is what a
    # region with no visible internal boundary actually is (final plan section 6.3).
    image = np.full((200, 200), 60, dtype=np.uint8)
    image[90:110, 40:160] = 200
    assert _count(segment_aggregate(image)) == 1
    legacy = segment_aggregate(image, WatershedConfig(marker_method="nms"))
    assert _count(legacy) == 26


def test_hole_fill_limit_must_stay_below_the_minimum_particle_area():
    # Otherwise a hole-filling step would swallow the smallest particles the
    # configuration claims to be able to resolve.
    with pytest.raises(ValueError):
        WatershedConfig(min_instance_area_px=10, hole_fill_max_area_px=20)


def test_instance_properties_flags_border_contact():
    labels = disk_labels(height=60, width=60, radius=10, centers_yx=((10, 10), (40, 40)))
    props = {p.instance_id: p for p in instance_properties(labels)}
    assert props[1].touches_border is True
    assert props[2].touches_border is False


def test_instance_properties_area_matches_label_pixel_count():
    labels = disk_labels(height=60, width=60, radius=10, centers_yx=((30, 30),))
    props = instance_properties(labels)
    assert len(props) == 1
    assert props[0].area_px == int(np.count_nonzero(labels == 1))


def test_instance_properties_on_empty_labels_is_empty():
    assert instance_properties(np.zeros((10, 10), dtype=np.int32)) == []


def test_renumber_labels_compacts_gaps():
    labels = np.zeros((4, 4), dtype=np.int32)
    labels[0, 0] = 7
    labels[3, 3] = 3
    renumbered = renumber_labels(labels)
    assert sorted(np.unique(renumbered)) == [0, 1, 2]
    assert renumbered[0, 0] == 2  # 7 was the larger of the two, so it maps second
    assert renumbered[3, 3] == 1


def test_renumber_labels_handles_all_background():
    assert renumber_labels(np.zeros((3, 3), dtype=np.int32)).max() == 0


def test_instance_properties_rejects_non_2d():
    with pytest.raises(ValueError):
        instance_properties(np.zeros((2, 2, 3), dtype=np.int32))


# =============================================================================
# 4. Physical features: density, coverage, particle size, skeleton, gaps
# =============================================================================


def test_count_density_is_count_over_measured_area():
    assert count_density_per_m2(10, 0.5) == pytest.approx(20.0)


def test_zero_count_over_measured_area_is_a_measured_zero():
    assert count_density_per_m2(0, 0.5) == 0.0


def test_count_density_is_null_when_area_is_unavailable():
    assert count_density_per_m2(10, None) is None
    assert count_density_per_m2(0, None) is None


def test_count_density_is_null_for_a_zero_denominator():
    assert count_density_per_m2(4, 0.0) is None


def test_count_density_rejects_negative_area():
    with pytest.raises(ValueError):
        count_density_per_m2(4, -0.1)


def test_coverage_uses_the_union_over_the_eligible_area():
    labels = np.zeros((10, 10), dtype=np.int32)
    labels[0:5, 0:5] = 1
    labels[0:5, 5:10] = 2
    eligible = np.zeros((10, 10), dtype=bool)
    eligible[0:5, :] = True
    assert aggregate_coverage(labels, eligible) == pytest.approx(1.0)
    assert aggregate_coverage(labels, np.ones((10, 10), dtype=bool)) == pytest.approx(0.5)


def test_coverage_excludes_aggregate_outside_the_eligible_mask():
    labels = np.zeros((10, 10), dtype=np.int32)
    labels[0:5, 0:5] = 1
    labels[5:10, 5:10] = 2
    eligible = np.zeros((10, 10), dtype=bool)
    eligible[0:5, :] = True
    # Only instance 1 lies in the eligible area: 25 px of 50 px.
    assert aggregate_coverage(labels, eligible) == pytest.approx(0.5)


def test_coverage_is_null_when_the_eligible_area_is_empty():
    assert aggregate_coverage(np.zeros((4, 4), dtype=np.int32), np.zeros((4, 4), dtype=bool)) is None


def test_coverage_rejects_shape_mismatch():
    with pytest.raises(ValueError):
        aggregate_coverage(np.zeros((4, 4), dtype=np.int32), np.zeros((5, 5), dtype=bool))


def test_particle_size_reports_pixel_and_metric_medians():
    labels = disk_labels(height=100, width=100, radius=10, centers_yx=((50, 50),))
    stats = particle_size_stats(labels, SCALE_1MM)
    assert stats["scale_available"] is True
    assert stats["count_considered"] == 1
    # A 10 px radius disk has area ~314 px^2 -> equivalent diameter ~20 px.
    assert stats["diameter_px"]["median"] == pytest.approx(20.0, rel=0.1)
    assert stats["diameter_mm"]["median"] == pytest.approx(stats["diameter_px"]["median"], rel=1e-9)


def test_particle_size_returns_nulls_without_scale():
    labels = disk_labels(height=100, width=100, radius=10, centers_yx=((50, 50),))
    stats = particle_size_stats(labels, UNSCALED)
    assert stats["scale_available"] is False
    assert stats["diameter_mm"]["median"] is None
    assert stats["diameter_px"]["median"] is not None


def test_particle_size_declares_excluded_below_minimum():
    labels = disk_labels(height=100, width=100, radius=10, centers_yx=((50, 50),))
    stats = particle_size_stats(labels, SCALE_1MM, min_diameter_px=40.0)
    assert stats["count_considered"] == 0
    assert stats["excluded_below_min_size"] == 1
    assert stats["diameter_px"]["median"] is None


def test_particle_size_rejects_negative_minimum():
    labels = disk_labels(height=60, width=60, radius=5, centers_yx=((30, 30),))
    with pytest.raises(ValueError):
        particle_size_stats(labels, SCALE_1MM, min_diameter_px=-1.0)


def test_skeletonize_thins_a_filled_square():
    square = np.zeros((21, 21), dtype=bool)
    square[5:16, 5:16] = True
    skeleton = skeletonize_2d(square)
    assert skeleton.sum() < square.sum()
    assert skeleton.sum() > 0
    assert skeleton.dtype == bool


def test_skeletonize_leaves_a_single_pixel_line_unchanged():
    line = np.zeros((11, 11), dtype=bool)
    line[5, :] = True
    assert np.array_equal(skeletonize_2d(line), line)


def test_skeletonize_empty_input_is_empty():
    assert skeletonize_2d(np.zeros((5, 5), dtype=bool)).sum() == 0


def test_skeletonize_matches_scikit_image_exactly():
    # scikit-image was approved as an ML dependency (D4) and is the reference
    # implementation (J8/D6). Adopting it means our thinning must *be* scikit-
    # image's, not a look-alike: the local Zhang-Suen differed from it by up to
    # 303 pixels on a 96x96 noise mask, which silently changes medial sites.
    from skimage.morphology import skeletonize

    rng = np.random.default_rng(7)
    cases = [
        np.eye(40, 40, dtype=bool),
        rng.random((64, 64)) < 0.25,
        (rng.random((96, 96)) < 0.35),
    ]
    for case in cases:
        assert np.array_equal(
            skeletonize_2d(case), np.asarray(skeletonize(case), dtype=bool)
        )


def test_gap_method_version_bumped_when_the_skeleton_changed():
    # Adopting scikit-image's thinning changed measured site counts on dense
    # fixtures (n 353 -> 347, median 37.88 -> 37.16 px) even though the canonical
    # 11 px bar fixture is unaffected, so the method version had to move.
    assert GAP_METHOD_VERSION == "gap-medial-v2"


def test_gap_between_two_bars_matches_known_separation():
    stats = gap_statistics(two_bar_labels(), SCALE_HALF_MM, min_gap_px=3.0)
    assert stats.sample_count > 50
    assert stats.median_px == pytest.approx(EXPECTED_BAR_GAP_PX, abs=1.0)
    assert stats.median_mm == pytest.approx(EXPECTED_BAR_GAP_PX * 0.5, abs=0.6)
    assert stats.config_version == GAP_METHOD_VERSION
    assert stats.method == "medial_axis_opposing_distinct_instances"


def test_gap_iqr_and_p90_are_ordered():
    stats = gap_statistics(two_bar_labels(), SCALE_1MM, min_gap_px=3.0)
    assert stats.iqr_mm is not None
    assert stats.p90_mm is not None
    assert 0.0 <= stats.iqr_mm
    assert stats.p90_mm >= stats.median_mm


def test_gap_ignores_single_isolated_particle():
    # With only one particle there is no opposing *distinct* instance, so no
    # site may qualify: this is the plan's protection against counting an open
    # background region as a chip gap.
    stats = gap_statistics(single_bar_labels(), SCALE_1MM, min_gap_px=3.0)
    assert stats.sample_count == 0
    assert stats.median_px is None
    assert stats.limitation is not None


def test_gap_without_instances_reports_a_limitation():
    stats = gap_statistics(np.zeros((50, 50), dtype=np.int32), SCALE_1MM)
    assert stats.sample_count == 0
    assert stats.limitation == "no_aggregate_instances_detected"


def test_gap_is_pixel_only_without_scale():
    stats = gap_statistics(two_bar_labels(), UNSCALED, min_gap_px=3.0)
    assert stats.sample_count > 0
    assert stats.median_px == pytest.approx(EXPECTED_BAR_GAP_PX, abs=1.0)
    assert stats.median_mm is None
    assert stats.iqr_mm is None
    assert stats.p90_mm is None
    assert stats.limitation is not None


def test_gap_respects_the_declared_minimum_reportable_width():
    stats = gap_statistics(two_bar_labels(), SCALE_1MM, min_gap_px=20.0)
    assert stats.sample_count == 0
    assert stats.median_px is None
    assert stats.limitation is not None


def test_gap_rejects_a_subpixel_minimum():
    with pytest.raises(ValueError):
        gap_statistics(two_bar_labels(), SCALE_1MM, min_gap_px=0.5)


def test_gap_respects_ignore_mask():
    labels = two_bar_labels()
    ignore = np.ones(labels.shape, dtype=bool)  # nothing eligible for gap measurement
    stats = gap_statistics(labels, SCALE_1MM, ignore_mask=ignore, min_gap_px=3.0)
    assert stats.sample_count == 0
    assert stats.limitation is not None


def test_gap_rejects_shape_mismatch():
    with pytest.raises(ValueError):
        gap_statistics(two_bar_labels(), SCALE_1MM, ignore_mask=np.zeros((5, 5), dtype=bool))


# =============================================================================
# 5. Versioned measurement record
# =============================================================================


def test_scaled_record_reports_metric_areas_and_density():
    record = measure_surface(_image(), _full_valid(), SCALE_1MM)
    # ROI = valid mask eroded by the 4 px margin -> 192 x 192 px.
    expected_roi_area = (HEIGHT - 8) * (WIDTH - 8) / 1_000_000.0
    assert record.eligible_area_m2 == pytest.approx(expected_roi_area, rel=1e-9)
    assert record.observed_area_m2 == pytest.approx(HEIGHT * WIDTH / 1_000_000.0, rel=1e-9)
    assert record.n_instances_in_roi == N_DISKS
    assert record.count_density_per_m2 == pytest.approx(N_DISKS / expected_roi_area, rel=1e-9)
    assert record.min_measurable_diameter_mm == pytest.approx(3.0)
    assert record.min_measurable_gap_mm == pytest.approx(3.0)


def test_unscaled_record_keeps_pixel_counts_but_nulls_metric_values():
    record = measure_surface(_image(), _full_valid(), UNSCALED)
    assert record.n_instances_in_roi == N_DISKS
    assert record.count_density_per_m2 is None
    assert record.eligible_area_m2 is None
    assert record.observed_area_m2 is None
    assert record.min_measurable_diameter_mm is None
    assert record.particle_size["diameter_mm"]["median"] is None
    # Coverage is a ratio of pixel counts, so it remains available unscaled.
    assert record.coverage_fraction is not None
    assert "unscaled_geometry_metric_values_unavailable" in record.limitations


def test_zero_count_over_a_known_area_is_zero_not_null():
    record = measure_surface(_image(), _full_valid(), SCALE_1MM, MeasurementConfig(min_diameter_px=40.0))
    assert record.n_instances_in_roi == 0
    assert record.count_density_per_m2 == 0.0
    assert record.particle_size["excluded_below_min_size"] == N_DISKS


def test_roi_margin_excludes_instances_whose_centroid_is_outside():
    valid = _full_valid()
    valid[0:60, :] = False  # top strip is not usable road surface
    record = measure_surface(_image(), valid, SCALE_1MM)
    # Only the two bottom disks keep their centroids inside the eroded ROI.
    assert record.n_instances_in_roi == 2
    # All four are still detected in the frame, which is why the ROI rule matters.
    assert record.n_instances_total == N_DISKS


def test_distress_area_is_reported_separately_from_the_texture_denominator():
    distress = np.zeros((HEIGHT, WIDTH), dtype=bool)
    distress[0:10, :] = True
    record = measure_surface(_image(), _full_valid(), SCALE_1MM, distress_mask=distress)
    assert record.distress_area_m2 == pytest.approx(200 * 10 / 1_000_000.0, rel=1e-9)
    # Excluding the distress strip from texture must shrink the texture
    # denominator without removing the damage measurement.
    assert record.eligible_area_m2 < record.observed_area_m2
    assert record.n_instances_in_roi == N_DISKS


def test_ignore_area_is_reported_and_excluded_from_eligible_area():
    ignore = np.zeros((HEIGHT, WIDTH), dtype=bool)
    ignore[:, 0:20] = True
    record = measure_surface(_image(), _full_valid(), SCALE_1MM, ignore_mask=ignore)
    assert record.ignored_area_m2 == pytest.approx(200 * 20 / 1_000_000.0, rel=1e-9)
    assert record.eligible_area_m2 is not None
    assert record.eligible_area_m2 < record.observed_area_m2


def test_record_describes_versions_and_scale_provenance():
    record = measure_surface(_image(), _full_valid(), SCALE_1MM)
    described = record.describe()
    assert described["config_version"] == "measure-v1"
    assert described["segmentation_version"] == "agg-classical-v3"
    assert described["geometry"]["scale_source"] == "source_calibrated"
    assert described["gap"]["config_version"] == "gap-medial-v2"
    assert described["areas_m2"]["texture_eligible"] == record.eligible_area_m2


def test_record_is_json_serializable():
    assert "count_density_per_m2" in json.dumps(measure_surface(_image(), _full_valid(), SCALE_1MM).describe())


def test_unscaled_record_is_json_serializable_with_nulls():
    payload = json.loads(json.dumps(measure_surface(_image(), _full_valid(), UNSCALED).describe()))
    assert payload["count_density_per_m2"] is None
    assert payload["areas_m2"]["texture_eligible"] is None


def test_no_valid_surface_is_reported_as_a_limitation():
    record = measure_surface(_image(), np.zeros((HEIGHT, WIDTH), dtype=bool), SCALE_1MM)
    assert record.n_instances_in_roi == 0
    assert "no_texture_eligible_area" in record.limitations
    assert record.eligible_area_m2 == 0.0


def test_mask_shape_mismatch_rejected():
    with pytest.raises(ValueError):
        measure_surface(_image(), np.ones((10, 10), dtype=bool), SCALE_1MM)


def test_scale_must_be_a_planar_scale():
    with pytest.raises(TypeError):
        measure_surface(_image(), _full_valid(), 0.5)  # type: ignore[arg-type]


def test_bgr_image_is_accepted():
    bgr = np.repeat(_image()[:, :, None], 3, axis=2)
    assert measure_surface(bgr, _full_valid(), SCALE_1MM).n_instances_in_roi == N_DISKS

# =============================================================================
# D7 -” fixed-scale texture proxies (final plan section 7.3)
# =============================================================================


def _scaled(mm_per_px: float = 1.0) -> PlanarScale:
    return PlanarScale.calibrated(
        sx_mm_per_px=mm_per_px,
        sy_mm_per_px=mm_per_px,
        source=ScaleSource.RIG_CALIBRATED,
        provenance=f"test {mm_per_px} mm/px",
    )


def _flat() -> np.ndarray:
    return np.full((128, 128), 128, dtype=np.uint8)


def _checker() -> np.ndarray:
    yy, xx = np.indices((128, 128))
    return (((xx + yy) % 2) * 255).astype(np.uint8)


def _stripes(period_px: int = 4) -> np.ndarray:
    """Exact integer-period square wave, constant along y.

    An exact period (not a sine with an irrational period) makes the expected
    co-occurrence behaviour predictable: a shift of ``period_px`` is in phase,
    ``period_px / 2`` is exactly out of phase, and a quarter period is
    orthogonal.
    """
    yy, xx = np.indices((128, 128))
    return (((xx % period_px) < (period_px // 2)) * 255).astype(np.uint8)


def _noise() -> np.ndarray:
    return (np.random.default_rng(7).random((128, 128)) * 255).astype(np.uint8)


def test_flat_texture_has_zero_contrast_and_full_homogeneity():
    result = texture_statistics(_flat(), _scaled())
    assert result.glcm_contrast_mm == 0.0
    assert result.glcm_homogeneity_mm == 1.0
    assert result.gradient_energy_mm == 0.0
    # Perfectly flat -> every LBP code is uniform
    assert result.lbp_uniformity_mm == 1.0


def test_checker_has_high_contrast_and_low_homogeneity():
    result = texture_statistics(_checker(), _scaled())
    assert result.glcm_contrast_mm > 1000.0
    assert result.glcm_homogeneity_mm < 1.0
    # Two equally likely level pairs -> energy exactly 0.5
    assert abs(result.glcm_energy_mm - 0.5) < 1e-9
    # A checkerboard is never an LBP-uniform code
    assert result.lbp_uniformity_mm == 0.0


def test_sobel_is_a_null_operator_at_nyquist_and_that_is_recorded():
    # A 3x3 Sobel is exactly zero on a checkerboard. The metric must report the
    # zero rather than hide it, because a near-pixel-scale surface could read as
    # "smooth" when it is in fact the most textured case.
    result = texture_statistics(_checker(), _scaled())
    assert result.gradient_energy_mm == 0.0
    assert result.limitation is None  # not an error, a genuine property of the operator


def test_glcm_phase_response_matches_the_exact_period():
    # Per-direction co-occurrence behaviour on the square wave. Measured before
    # being asserted, so these are recorded facts rather than hoped-for values.
    square = _stripes(4)
    angles = (0.0, np.pi / 4, np.pi / 2, 3 * np.pi / 4)
    x_dir = lambda d: _glcm_features(square, (d,), angles)["correlation"][0, 0]

    assert x_dir(1) == pytest.approx(0.0, abs=0.05)   # quarter period -> orthogonal
    assert x_dir(2) == pytest.approx(-1.0, abs=1e-9)  # half period -> antiphase
    assert x_dir(3) == pytest.approx(0.0, abs=0.05)   # three quarters -> orthogonal
    assert x_dir(4) == pytest.approx(1.0, abs=1e-9)   # full period -> in phase
    assert x_dir(6) == pytest.approx(-1.0, abs=1e-9)  # 1.5 periods -> antiphase
    assert x_dir(8) == pytest.approx(1.0, abs=1e-9)   # 2 periods -> in phase


def test_glcm_reports_perfect_correlation_when_the_axis_is_constant():
    # The square wave does not vary along y, so every pair is (v, v) and the
    # GLCM is purely diagonal. That is a degenerate but correct +1.
    square = _stripes(4)
    angles = (0.0, np.pi / 4, np.pi / 2, 3 * np.pi / 4)
    for d in (1, 2, 4, 8):
        assert _glcm_features(square, (d,), angles)["correlation"][0, 2] == pytest.approx(
            1.0, abs=1e-9
        )


def test_public_api_ranks_in_phase_above_antiphase():
    # Averaged over four directions, a full-period offset must still score
    # above a half-period offset. The per-direction values are verified
    # separately; this checks the aggregate behaves sensibly.
    in_phase = texture_statistics(_stripes(4), _scaled(), distances_mm=(4.0,))
    antiphase = texture_statistics(_stripes(4), _scaled(), distances_mm=(2.0,))
    assert (
        in_phase.glcm_correlation_mm > antiphase.glcm_correlation_mm
    )


def test_noise_has_high_contrast_but_near_zero_correlation():
    result = texture_statistics(_noise(), _scaled())
    assert result.glcm_contrast_mm > 100.0
    assert abs(result.glcm_correlation_mm) < 0.1


def test_unscaled_returns_all_none_and_never_a_fabricated_number():
    result = texture_statistics(_noise(), PlanarScale.unscaled("no calibration"))
    assert result.glcm_contrast_mm is None
    assert result.glcm_homogeneity_mm is None
    assert result.glcm_energy_mm is None
    assert result.glcm_correlation_mm is None
    assert result.gradient_energy_mm is None
    assert result.lbp_uniformity_mm is None
    assert result.limitation is not None


def test_unscaled_none_is_not_zero():
    # Null-vs-zero discipline (final plan section 2): a missing scale must not
    # be mistaken for a measured zero.
    result = texture_statistics(_flat(), PlanarScale.unscaled(""))
    assert result.glcm_contrast_mm is None
    assert result.glcm_contrast_mm != 0.0


def test_colour_and_grey_paths_agree():
    grey = _stripes()
    bgr = cv2.cvtColor(grey, cv2.COLOR_GRAY2BGR)
    a = texture_statistics(grey, _scaled()).describe()
    b = texture_statistics(bgr, _scaled()).describe()
    for key in (
        "glcm_contrast_mm",
        "glcm_homogeneity_mm",
        "glcm_energy_mm",
        "glcm_correlation_mm",
        "gradient_energy_mm",
        "lbp_uniformity_mm",
    ):
        assert a[key] == b[key]


def test_same_pixel_offset_gives_same_value_across_scales():
    # The invariant: a physical offset quantises to a whole pixel count, so a
    # request that resolves to the *same* offset must produce the *same* value
    # regardless of the declared scale.
    fine = _scaled(1.0)
    coarse = _scaled(2.0)
    for target_px in (1, 2, 3, 4, 6, 8):
        mm_at_1 = float(target_px)
        mm_at_2 = float(target_px * 2)
        v1 = texture_statistics(
            _stripes(), fine, distances_mm=(mm_at_1,)
        ).describe()["glcm_correlation_mm"]
        v2 = texture_statistics(
            _stripes(), coarse, distances_mm=(mm_at_2,)
        ).describe()["glcm_correlation_mm"]
        assert v1 == v2


def test_anisotropic_scale_is_accepted():
    scale = PlanarScale.calibrated(
        1.0, 3.0, ScaleSource.RIG_CALIBRATED, "anisotropic"
    )
    result = texture_statistics(_stripes(), scale)
    assert result.glcm_contrast_mm is not None


def test_deterministic_for_repeated_calls():
    a = texture_statistics(_stripes(), _scaled()).describe()
    b = texture_statistics(_stripes(), _scaled()).describe()
    assert a == b


def test_rejects_non_finite_and_bad_shapes():
    with pytest.raises(ValueError):
        texture_statistics(np.array([[np.nan, 1.0], [2.0, 3.0]]), _scaled())
    with pytest.raises(ValueError):
        texture_statistics(np.zeros((4, 4, 5), dtype=np.uint8), _scaled())


def test_version_string_travels_with_the_result():
    result = texture_statistics(_flat(), _scaled())
    assert result.config_version == TEX_METHOD_VERSION
    assert result.method == "fixed_scale_glcm_gradient_lbp"
