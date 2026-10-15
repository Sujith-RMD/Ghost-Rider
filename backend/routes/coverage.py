"""Geospatial distance and coverage truth calculation for routes.

Ownership: Backend & AWS AI
Reference: docs/final_plan.md (Section 12.1)
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

EARTH_RADIUS_M = 6371000.0


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two GPS points in meters."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return EARTH_RADIUS_M * c


def compute_cumulative_distances(
    points: List[Tuple[float, float]],
) -> List[float]:
    """Compute cumulative distance along a traveled GPS polyline.

    Args:
        points: List of (lat, lon) coordinates in sequence order.

    Returns:
        List of cumulative distances in meters starting from 0.0.
    """
    if not points:
        return []

    distances = [0.0]
    total = 0.0
    for i in range(1, len(points)):
        step = haversine_distance_m(
            points[i - 1][0], points[i - 1][1],
            points[i][0], points[i][1],
        )
        total += step
        distances.append(total)

    return distances
