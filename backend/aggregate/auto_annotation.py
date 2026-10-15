"""Automated aggregate annotation - PROVISIONAL GATE 0 WORKAROUND.

This module provides automated chip/gap annotation to unblock Gate 0 when human
annotators are unavailable. It is explicitly a temporary solution.

**DESIGN FOR REPLACEMENT:**
- Same output schema as human annotations
- Clear confidence flags marking automated vs human labels
- Easy to swap: change one import, same downstream pipeline
- Evaluation still requires real human disagreement floor from A2.2/A2.3

final_plan §5.1 step 4: "Annotate 10 small patches twice, without model suggestions
initially. Compare counts, masks, and chosen gap endpoints. Establish the human
disagreement floor."

This automation does NOT establish that floor. It only allows development to proceed.
Validation still requires real human labels on a held-out set.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np

from backend.aggregate.segmentation import WatershedConfig, segment_aggregate
from backend.geometry import PlanarScale


@dataclass
class AutoAnnotation:
    """Automated annotation result with clear provenance flags.
    
    This schema matches what human annotation would produce, so the downstream
    pipeline doesn't break when we switch to real human labels.
    """
    
    # Core annotation
    instance_mask: np.ndarray  # H×W, instance IDs
    chip_count: int
    chip_visible: Literal["yes", "no", "unsure"]
    gap_visible: Literal["yes", "no", "unsure"]
    
    # Gap endpoints (pixel coords, or None if no clear gap)
    gap_endpoint_a_xy: tuple[int, int] | None
    gap_endpoint_b_xy: tuple[int, int] | None
    
    # Provenance - CRITICAL for replacement
    source: Literal["automated_provisional", "human_reviewed"] = "automated_provisional"
    confidence: float = 0.0  # 0.0-1.0, automated always gets low confidence
    notes: str = ""
    
    # Metadata
    patch_id: str = ""
    annotator_id: str = "auto_v1"
    

def auto_annotate_patch(
    image: np.ndarray,
    scale: PlanarScale | None = None,
    patch_id: str = "",
    config: WatershedConfig | None = None,
) -> AutoAnnotation:
    """Generate automated provisional annotation for one patch.
    
    Args:
        image: RGB patch, native resolution (e.g., 256×256)
        scale: Physical scale if available
        patch_id: Identifier for tracking
        config: Segmentation config (uses reasonable defaults if None)
    
    Returns:
        AutoAnnotation with low confidence flags
    
    **This is NOT a substitute for human judgment.** It provides:
    - Chip count from classical segmentation (may over/under-segment)
    - Visibility flags based on count and texture (NOT human perception)
    - One gap measurement (may not be the clearest one a human would choose)
    
    Real annotation requires:
    - Two humans independently reviewing the same patches
    - Agreement/disagreement measurement
    - Selection of resolvable size range
    - Go/no-go decision per task
    """
    
    warnings.warn(
        f"Using automated annotation for patch {patch_id}. "
        "This is a Gate 0 workaround, not validated ground truth. "
        "Replace with human annotations before claiming real performance.",
        UserWarning,
        stacklevel=2,
    )
    
    if config is None:
        config = WatershedConfig(
            polarity="brighter",
            marker_method="h_maxima",
            marker_h_max_fraction=0.5,
            min_instance_area_px=50,  # Conservative minimum
        )
    
    # Segment using classical baseline
    result = segment_aggregate(image, config)
    instance_mask = result["labels"]
    chip_count = result["num_instances"]
    
    # Heuristic visibility (NOT human judgment)
    # Real humans would assess boundary clarity, which we can't measure
    if chip_count == 0:
        chip_visible = "no"
        gap_visible = "no"
        notes = "No instances detected by automated segmentation"
    elif chip_count < 5:
        chip_visible = "unsure"
        gap_visible = "unsure" 
        notes = f"Very few instances ({chip_count}); unclear if they're real chips"
    else:
        chip_visible = "yes"
        gap_visible = "yes"
        notes = f"Detected {chip_count} instances; assuming chips visible"
    
    # Find one gap (arbitrary, not necessarily the clearest)
    gap_a, gap_b = _find_one_gap(instance_mask)
    
    return AutoAnnotation(
        instance_mask=instance_mask,
        chip_count=chip_count,
        chip_visible=chip_visible,
        gap_visible=gap_visible,
        gap_endpoint_a_xy=gap_a,
        gap_endpoint_b_xy=gap_b,
        source="automated_provisional",
        confidence=0.3,  # Low confidence - this is NOT validated
        notes=notes,
        patch_id=patch_id,
        annotator_id="auto_v1",
    )


def _find_one_gap(
    instance_mask: np.ndarray,
) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
    """Find one arbitrary gap between instances.
    
    Real human annotation would select the clearest gap. This just finds any gap.
    
    Returns:
        (endpoint_a, endpoint_b) or (None, None) if no gap found
    """
    
    # Create background mask
    background = instance_mask == 0
    
    if not background.any():
        return None, None
    
    # Distance transform on background
    dist = cv2.distanceTransform(
        background.astype(np.uint8),
        cv2.DIST_L2,
        cv2.DIST_MASK_PRECISE,
    )
    
    # Find a point in the background with decent distance
    candidates = dist > 2.0  # At least 2 pixels from any chip
    
    if not candidates.any():
        return None, None
    
    # Take the first candidate (arbitrary)
    ys, xs = np.nonzero(candidates)
    center_y, center_x = int(ys[0]), int(xs[0])
    
    # Find rough perpendicular endpoints
    # (Real humans would trace actual boundaries; this is a crude approximation)
    gap_radius = int(dist[center_y, center_x])
    
    endpoint_a = (center_x - gap_radius, center_y)
    endpoint_b = (center_x + gap_radius, center_y)
    
    return endpoint_a, endpoint_b


def batch_auto_annotate(
    image_paths: list[str],
    output_csv: str,
    scale: PlanarScale | None = None,
    config: WatershedConfig | None = None,
) -> list[AutoAnnotation]:
    """Batch annotate multiple patches (Gate 0 workaround).
    
    Args:
        image_paths: List of patch image files
        output_csv: Where to write annotations (same format as human template)
        scale: Physical scale if available
        config: Segmentation config
    
    Returns:
        List of AutoAnnotation objects
    
    **Writes CSV in the same format as human annotation template**, so the
    evaluation pipeline doesn't need to change when we get real human labels.
    """
    
    import csv
    from pathlib import Path
    
    annotations = []
    
    for img_path in image_paths:
        image = cv2.imread(img_path)
        if image is None:
            warnings.warn(f"Could not read {img_path}", UserWarning)
            continue
        
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        patch_id = Path(img_path).stem
        
        annotation = auto_annotate_patch(image, scale, patch_id, config)
        annotations.append(annotation)
    
    # Write to CSV in human-annotation format
    with open(output_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "patch_id",
            "annotator_id",
            "chip_visible",
            "chip_count",
            "gap_visible",
            "gap_endpoint_a_xy",
            "gap_endpoint_b_xy",
            "zoom_effect",
            "source",
            "confidence",
            "notes",
        ])
        
        for ann in annotations:
            gap_a = f"{ann.gap_endpoint_a_xy[0]},{ann.gap_endpoint_a_xy[1]}" if ann.gap_endpoint_a_xy else ""
            gap_b = f"{ann.gap_endpoint_b_xy[0]},{ann.gap_endpoint_b_xy[1]}" if ann.gap_endpoint_b_xy else ""
            
            writer.writerow([
                ann.patch_id,
                ann.annotator_id,
                ann.chip_visible,
                ann.chip_count,
                ann.gap_visible,
                gap_a,
                gap_b,
                "not_assessed",  # Automated can't judge zoom effect
                ann.source,
                ann.confidence,
                ann.notes,
            ])
    
    print(f"Wrote {len(annotations)} automated annotations to {output_csv}")
    print("\n⚠️  WARNING: These are PROVISIONAL automated annotations.")
    print("Replace with human labels before claiming validated performance.\n")
    
    return annotations
