"""Route bin aggregation and coverage accounting for Ghost-Rider.

Implements:
- Configurable 50 m reporting bins (default).
- Grouping of duplicate / overlapping frames to mitigate stopped-vehicle bias.
- Factual sample counts, accepted counts, and strip area calculation.
- Median SQI and lower-tail score calculation.
- Honest coverage truth: unique_area is None when registration is unreliable.
- Unsampled stretch accounting: never fills missing stretches with Good/Bad.

Ownership: Backend & AWS AI
Reference: docs/final_plan.md (Section 12.1)
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from ..schemas import SegmentList, SegmentResult, SegmentSummary
from .coverage import compute_cumulative_distances, haversine_distance_m

logger = logging.getLogger("ghost_rider.routes.aggregation")


def calculate_median(values: List[float]) -> Optional[int]:
    """Calculate rounded median of integer/float values."""
    if not values:
        return None
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 1:
        return int(round(sorted_vals[mid]))
    return int(round((sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0))


def calculate_lower_tail(values: List[float]) -> Optional[int]:
    """Calculate lower-tail (p25 / p10) score when sample size is sufficient (n >= 3)."""
    if len(values) < 3:
        return None
    sorted_vals = sorted(values)
    # 25th percentile
    index = int(math.floor(0.25 * (len(sorted_vals) - 1)))
    return int(round(sorted_vals[index]))


def aggregate_route_segments(
    samples: List[SegmentResult],
    bin_length_m: float = 50.0,
    total_distance_override: Optional[float] = None,
    route_id: Optional[str] = None,
) -> SegmentList:
    """Aggregate a sequence of analyzed segment samples into 50m reporting bins.

    Args:
        samples: List of analyzed SegmentResult objects.
        bin_length_m: Reporting bin interval in meters (default 50m).
        total_distance_override: Optional total distance if known from vehicle odometer.
        route_id: Optional parent route or session identifier.

    Returns:
        SegmentList conforming to backend/schemas.py.
    """
    parent_route_id = route_id or (samples[0].route_id if samples and samples[0].route_id else "route-default")

    if not samples:
        return SegmentList(
            route_id=parent_route_id,
            segments=[],
            total_distance_m=0.0,
            coverage_percentage=0.0,
            unsampled_stretches=[],
        )

    # 1. Determine distance along route for each sample
    points: List[Tuple[float, float]] = []
    has_gps = False
    for s in samples:
        if s.gps and s.gps.lat is not None and s.gps.lon is not None:
            points.append((s.gps.lat, s.gps.lon))
            has_gps = True
        else:
            points.append((0.0, 0.0))

    if has_gps:
        distances = compute_cumulative_distances(points)
    else:
        # Fallback to nominal frame interval spacing (e.g. 5m per frame if unlocated)
        distances = [float(i * 5.0) for i in range(len(samples))]

    # 2. Pair each sample with its along-track distance
    sample_distances: List[Tuple[float, SegmentResult]] = []
    for dist, sample in zip(distances, samples):
        sample_distances.append((dist, sample))

    max_dist = max(distances) if distances else 0.0
    total_dist = max_dist if total_distance_override is None else max(max_dist, total_distance_override)
    if total_dist <= 0.0:
        total_dist = float(len(samples) * 5.0)

    # 3. Determine number of bins
    num_bins = max(1, int(math.ceil(total_dist / bin_length_m)))
    bins_data: Dict[int, List[Tuple[float, SegmentResult]]] = {i: [] for i in range(num_bins)}

    for dist, sample in sample_distances:
        bin_idx = min(int(dist // bin_length_m), num_bins - 1)
        bins_data[bin_idx].append((dist, sample))

    # 4. Build summaries per bin
    summaries: List[SegmentSummary] = []
    unsampled_stretches: List[Dict[str, float]] = []

    for bin_idx in range(num_bins):
        start_m = float(bin_idx * bin_length_m)
        end_m = float(min((bin_idx + 1) * bin_length_m, total_dist))
        items = bins_data[bin_idx]

        if not items:
            # Unsampled bin
            summaries.append(
                SegmentSummary(
                    segment_id=bin_idx + 1,
                    start_distance_m=start_m,
                    end_distance_m=end_m,
                    center_lat=None,
                    center_lon=None,
                    gps_accuracy_m=None,
                    simulated=False,
                    sample_count=0,
                    accepted_sample_count=0,
                    unique_area_m2=None,
                    strip_area_m2=0.0,
                    median_score=None,
                    lower_tail_score=None,
                    serious_defect_observed=False,
                    unknown_coverage=True,
                )
            )
            unsampled_stretches.append({"start_m": start_m, "end_m": end_m})
            continue

        # Group duplicate/overlapping frames to limit stopped-vehicle bias
        # Clustered if distance delta < 0.2m
        filtered_items: List[Tuple[float, SegmentResult]] = []
        last_d: Optional[float] = None
        for d, s in items:
            if last_d is not None and abs(d - last_d) < 0.2:
                # Near duplicate (vehicle likely stopped or slow crawl)
                continue
            filtered_items.append((d, s))
            last_d = d

        if not filtered_items:
            filtered_items = [items[0]]

        sample_count = len(items)
        accepted_samples = [s for _, s in items if s.quality and s.quality.status.value == "accepted"]
        accepted_count = len(accepted_samples)

        # Scores from accepted or reviewed samples
        scores: List[float] = []
        serious_defect = False
        strip_area = 0.0
        lats: List[float] = []
        lons: List[float] = []
        accuracies: List[float] = []
        is_simulated = False

        for _, s in filtered_items:
            if s.score and s.score.value is not None:
                scores.append(float(s.score.value))
            if s.score and s.score.severe_defect_flag:
                serious_defect = True
            if s.metrics and s.metrics.pothole_count and s.metrics.pothole_count > 0:
                serious_defect = True
            if s.observed_area and s.observed_area.observed_area_m2 is not None:
                strip_area += s.observed_area.observed_area_m2
            if s.gps:
                if s.gps.lat is not None and s.gps.lon is not None:
                    lats.append(s.gps.lat)
                    lons.append(s.gps.lon)
                if s.gps.accuracy_m is not None:
                    accuracies.append(s.gps.accuracy_m)
                if s.gps.simulated:
                    is_simulated = True

        median_val = calculate_median(scores)
        lower_tail_val = calculate_lower_tail(scores)
        center_lat = (sum(lats) / len(lats)) if lats else None
        center_lon = (sum(lons) / len(lons)) if lons else None
        avg_acc = (sum(accuracies) / len(accuracies)) if accuracies else None

        # Registration truth: unless dedicated registration algorithm runs, unique_area is None
        unique_area = None

        summaries.append(
            SegmentSummary(
                segment_id=bin_idx + 1,
                start_distance_m=start_m,
                end_distance_m=end_m,
                center_lat=center_lat,
                center_lon=center_lon,
                gps_accuracy_m=avg_acc,
                simulated=is_simulated,
                sample_count=sample_count,
                accepted_sample_count=accepted_count,
                unique_area_m2=unique_area,
                strip_area_m2=round(strip_area, 3),
                median_score=median_val,
                lower_tail_score=lower_tail_val,
                serious_defect_observed=serious_defect,
                unknown_coverage=accepted_count == 0,
            )
        )

    sampled_bins = sum(1 for s in summaries if not s.unknown_coverage)
    coverage_pct = round((sampled_bins / num_bins) * 100.0, 1) if num_bins > 0 else 0.0

    return SegmentList(
        route_id=parent_route_id,
        segments=summaries,
        total_distance_m=round(total_dist, 2),
        coverage_percentage=coverage_pct,
        unsampled_stretches=unsampled_stretches,
    )
