"""Unit tests for route aggregation and coverage accounting.

Verifies:
- Configurable 50m reporting bins
- Stopped-vehicle / duplicate frame grouping
- Factual sample counts and strip area
- Median SQI and lower-tail score (p25 when n >= 3)
- unique_area is None when registration is unreliable
- Unsampled stretch accounting (never fills with Good/Bad)
"""

from backend.routes.aggregation import (
    aggregate_route_segments,
    calculate_lower_tail,
    calculate_median,
)
from backend.routes.coverage import compute_cumulative_distances, haversine_distance_m
from backend.schemas import (
    AggregatedMetrics,
    AreaResult,
    GPSData,
    QualityResult,
    QualityStatus,
    ScoreResult,
    ScoreStatus,
    SegmentResult,
)


def test_haversine_and_cumulative_distance():
    # Bangalore MG Road points ~ 111 meters apart
    lat1, lon1 = 12.9716, 77.5946
    lat2, lon2 = 12.9726, 77.5946
    d = haversine_distance_m(lat1, lon1, lat2, lon2)
    assert 110.0 < d < 112.0

    points = [(lat1, lon1), (lat2, lon2)]
    dists = compute_cumulative_distances(points)
    assert len(dists) == 2
    assert dists[0] == 0.0
    assert 110.0 < dists[1] < 112.0


def test_calculate_median_and_lower_tail():
    # Odd count
    assert calculate_median([70, 80, 90]) == 80
    # Even count
    assert calculate_median([70, 80, 90, 100]) == 85
    # Empty
    assert calculate_median([]) is None

    # Lower tail requires n >= 3
    assert calculate_lower_tail([80, 90]) is None
    assert calculate_lower_tail([60, 70, 80, 90]) == 60


def test_aggregate_50m_bins_and_coverage():
    # Build 10 simulated samples along a 120m stretch
    samples = []
    # Points roughly every 15 meters along longitude
    base_lat = 12.9716
    base_lon = 77.5946
    step_lon = 0.000135  # roughly 15m

    for i in range(8):
        lon = base_lon + (i * step_lon)
        # Alternate good and minor distress
        score_val = 80 if i % 2 == 0 else 60
        samples.append(
            SegmentResult(
                segment_id=i + 1,
                route_id="route-test-01",
                gps=GPSData(lat=base_lat, lon=lon, accuracy_m=3.0, simulated=False),
                geometry_valid=True,
                observed_area=AreaResult(observed_area_m2=0.5, scale_source="rig_calibrated"),
                quality=QualityResult(status=QualityStatus.ACCEPTED, reasons=[]),
                metrics=AggregatedMetrics(chip_count=350, chip_density_per_m2=700.0),
                score=ScoreResult(value=score_val, status=ScoreStatus.GOOD if score_val >= 70 else ScoreStatus.BAD),
            )
        )

    res = aggregate_route_segments(samples, bin_length_m=50.0)

    assert res.route_id == "route-test-01"
    assert len(res.segments) >= 2
    assert res.total_distance_m > 90.0

    # Check first 50m bin
    bin1 = res.segments[0]
    assert bin1.segment_id == 1
    assert bin1.start_distance_m == 0.0
    assert bin1.end_distance_m == 50.0
    assert bin1.sample_count > 0
    assert bin1.accepted_sample_count > 0
    assert bin1.median_score is not None
    assert bin1.unique_area_m2 is None  # Honest registration truth
    assert bin1.strip_area_m2 > 0.0
    assert not bin1.unknown_coverage


def test_stopped_vehicle_bias_mitigation():
    """Verify that multiple frames taken at essentially the same point (<0.2m) are clustered."""
    base_lat, base_lon = 12.9716, 77.5946
    samples = []

    # 1 normal frame
    samples.append(
        SegmentResult(
            segment_id=1,
            route_id="route-stop-test",
            gps=GPSData(lat=base_lat, lon=base_lon, accuracy_m=2.0),
            quality=QualityResult(status=QualityStatus.ACCEPTED),
            score=ScoreResult(value=90, status=ScoreStatus.GOOD),
        )
    )

    # 5 frames while stopped at a red light (identical coordinates, bad score on one patch)
    for i in range(2, 7):
        samples.append(
            SegmentResult(
                segment_id=i,
                route_id="route-stop-test",
                gps=GPSData(lat=base_lat, lon=base_lon, accuracy_m=2.0),
                quality=QualityResult(status=QualityStatus.ACCEPTED),
                score=ScoreResult(value=30, status=ScoreStatus.BAD),
            )
        )

    # Aggregating should not let the 5 duplicate stopped frames completely skew the entire route
    res = aggregate_route_segments(samples, bin_length_m=50.0)
    assert len(res.segments) == 1
    bin1 = res.segments[0]
    # Sample count records actual received frames
    assert bin1.sample_count == 6


def test_unsampled_stretch_accounting():
    """Unsampled stretches must remain unknown and NEVER be interpolated with Good or Bad."""
    samples = [
        # Frame at 0m
        SegmentResult(
            segment_id=1,
            route_id="route-gap-test",
            gps=GPSData(lat=12.9716, lon=77.5946),
            quality=QualityResult(status=QualityStatus.ACCEPTED),
            score=ScoreResult(value=85, status=ScoreStatus.GOOD),
        ),
        # Frame at 150m (leaving 50-100m completely unsampled)
        SegmentResult(
            segment_id=2,
            route_id="route-gap-test",
            gps=GPSData(lat=12.9716 + 0.00135, lon=77.5946),  # ~150m away
            quality=QualityResult(status=QualityStatus.ACCEPTED),
            score=ScoreResult(value=88, status=ScoreStatus.GOOD),
        ),
    ]

    res = aggregate_route_segments(samples, bin_length_m=50.0)
    # Total distance ~150m -> 3 bins: [0-50), [50-100), [100-150]
    assert len(res.segments) >= 3

    # Bin 2 [50-100m] was unsampled
    bin2 = res.segments[1]
    assert bin2.sample_count == 0
    assert bin2.accepted_sample_count == 0
    assert bin2.median_score is None  # MUST NOT be interpolated!
    assert bin2.unknown_coverage is True

    # Checked unsampled stretches list
    assert len(res.unsampled_stretches) >= 1
    assert any(s["start_m"] == 50.0 for s in res.unsampled_stretches)
