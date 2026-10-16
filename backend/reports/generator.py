"""Report generator coordinating factual extraction, hashing, Bedrock, and templates.

Ownership: Backend & AWS AI
Reference: docs/final_plan.md (Section 11.4, 12.3)
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from ..schemas import NarrativeStatus, ReportContent, ReportResult, SegmentResult
from .bedrock import generate_bedrock_narrative
from .template import build_factual_template

logger = logging.getLogger("ghost_rider.reports.generator")


def compute_factual_hash(assessment_id: str, facts: Dict[str, Any]) -> str:
    """Compute SHA-256 hash of normalized factual measurements for caching and validation."""
    serialized = json.dumps(
        {
            "assessment_id": assessment_id,
            "quality_status": facts.get("quality_status"),
            "quality_reasons": sorted(facts.get("quality_reasons", [])),
            "scale_source": facts.get("scale_source"),
            "observed_area_m2": facts.get("observed_area_m2"),
            "score_value": facts.get("score_value"),
            "score_status": facts.get("score_status"),
            "pothole_count": facts.get("pothole_count"),
            "crack_total_area_m2": facts.get("crack_total_area_m2"),
            "chip_count": facts.get("chip_count"),
            "chip_density_per_m2": facts.get("chip_density_per_m2"),
            "gap_median_mm": facts.get("gap_median_mm"),
            "severe_defect_flag": facts.get("severe_defect_flag"),
            "grade_percent": facts.get("grade_percent"),
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def extract_facts_from_sample(sample: SegmentResult) -> Dict[str, Any]:
    """Extract normalized factual dictionary from a SegmentResult model."""
    facts: Dict[str, Any] = {
        "assessment_id": sample.sample_id or str(sample.segment_id),
        "quality_status": sample.quality.status.value if sample.quality else "limited",
        "quality_reasons": sample.quality.reasons if sample.quality else ["quality_not_measured"],
        "scale_source": sample.observed_area.scale_source if sample.observed_area else "unscaled",
        "observed_area_m2": sample.observed_area.observed_area_m2 if sample.observed_area else None,
        "score_value": sample.score.value if sample.score else None,
        "score_status": sample.score.status.value if sample.score else "unknown",
        "severe_defect_flag": sample.score.severe_defect_flag if sample.score else False,
        "chip_count": sample.metrics.chip_count if sample.metrics else None,
        "chip_density_per_m2": sample.metrics.chip_density_per_m2 if sample.metrics else None,
        "gap_median_mm": sample.metrics.gap_median_mm if sample.metrics else None,
        "pothole_count": sample.metrics.pothole_count if sample.metrics else None,
        "crack_total_area_m2": sample.metrics.crack_total_area_m2 if sample.metrics else None,
        "grade_percent": sample.grade.grade_percent if sample.grade else None,
    }
    return facts


def generate_report_for_assessment(
    assessment_id: str,
    stored_facts: Dict[str, Any],
    include_narrative: bool = False,
    model_id: Optional[str] = None,
) -> ReportResult:
    """Generate a full factual report, using Bedrock if requested and configured.

    Returns:
        ReportResult instance conforming to backend/schemas.py.
    """
    report_id = str(uuid.uuid4())
    generated_at = datetime.now(timezone.utc).isoformat()
    factual_hash = compute_factual_hash(assessment_id, stored_facts)

    bedrock_model_id: Optional[str] = None
    if include_narrative:
        content, bedrock_model_id = generate_bedrock_narrative(
            assessment_id=assessment_id,
            stored_facts=stored_facts,
            factual_input_hash=factual_hash,
            model_id=model_id,
        )
    else:
        content = build_factual_template(assessment_id, stored_facts)
        content.narrative_status = NarrativeStatus.NOT_REQUESTED
        content.factual_template_used = False

    return ReportResult(
        report_id=report_id,
        assessment_id=assessment_id,
        content=content,
        generated_at=generated_at,
        bedrock_model_id=bedrock_model_id,
        factual_input_hash=factual_hash,
    )
