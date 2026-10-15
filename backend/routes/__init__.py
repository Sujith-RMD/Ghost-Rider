"""Ghost-Rider route aggregation and coverage accounting package.

Ownership: Backend & AWS AI
"""

from .aggregation import (
    aggregate_route_segments,
    calculate_lower_tail,
    calculate_median,
)
from .coverage import (
    compute_cumulative_distances,
    haversine_distance_m,
)

__all__ = [
    "aggregate_route_segments",
    "calculate_median",
    "calculate_lower_tail",
    "compute_cumulative_distances",
    "haversine_distance_m",
]
