"""Deterministic factual report template for Ghost-Rider.

Used as the baseline report generator and as the strict fallback whenever
Bedrock is unreachable, times out, or returns unvalidated output.
Only uses stored structured measurements. Prohibits hallucinated numbers,
cost estimation, or structural sub-base prescriptions.

Ownership: Backend & AWS AI
Reference: docs/final_plan.md (Section 12.3)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..schemas import NarrativeStatus, QualityStatus, ReportContent, ScoreStatus

logger = logging.getLogger("ghost_rider.reports.template")


def build_factual_template(
    assessment_id: str,
    stored_facts: Dict[str, Any],
) -> ReportContent:
    """Build deterministic, fact-checked report content from stored structured facts.

    Args:
        assessment_id: ID of the sample, segment, or job.
        stored_facts: Normalized dictionary of stored measurements and statuses.

    Returns:
        ReportContent instance with factual_template_used=True.
    """
    quality_status = stored_facts.get("quality_status", QualityStatus.ACCEPTED.value)
    score_val = stored_facts.get("score_value")
    score_status = stored_facts.get("score_status", ScoreStatus.UNKNOWN.value)
    reasons = stored_facts.get("quality_reasons", [])
    scale_source = stored_facts.get("scale_source")
    observed_area = stored_facts.get("observed_area_m2")
    chip_count = stored_facts.get("chip_count")
    chip_density = stored_facts.get("chip_density_per_m2")
    gap_median = stored_facts.get("gap_median_mm")
    pothole_count = stored_facts.get("pothole_count", 0) or 0
    crack_area = stored_facts.get("crack_total_area_m2")
    severe_flag = bool(stored_facts.get("severe_defect_flag", False))
    grade_percent = stored_facts.get("grade_percent")

    summary_sentences: List[str] = []
    limitations: List[str] = []
    inspection_actions: List[str] = []
    evidence_refs: List[str] = [f"sample:{assessment_id}"]

    # 1. Image Quality & Domain Assessment
    if quality_status == QualityStatus.REJECTED.value:
        summary_sentences.append(
            f"Frame rejected during quality admission due to: {', '.join(reasons) or 'optical or surface defect'}."
        )
        limitations.append("Measurements suppressed due to input quality rejection.")
        inspection_actions.append("Recapture frame with proper lighting, stable focus, and approved downward angle.")
    elif quality_status == QualityStatus.LIMITED.value:
        summary_sentences.append(
            f"Frame assessed with limited confidence ({', '.join(reasons) or 'partial visibility'})."
        )
        limitations.append("Optical or geometric limitation prevents full metric validation.")
    else:
        summary_sentences.append("Frame verified and passed quality admission standards.")

    # 2. Geometry & Scale
    if not scale_source or scale_source == "unscaled":
        limitations.append("Input lacks physical metric calibration; physical dimensions (mm, m², count/m²) unavailable.")
    else:
        summary_sentences.append(
            f"Metric scale established via {scale_source}."
        )

    # 3. Surface Quality Index (SQI)
    if score_val is not None:
        summary_sentences.append(
            f"Surface Quality Index (SQI): {score_val}/100 ({score_status})."
        )
    else:
        summary_sentences.append(f"Condition rating status: {score_status} (numerical SQI withheld).")

    # 4. Distress Evidence
    if severe_flag or pothole_count > 0:
        evidence_refs.append(f"defect:severe_flag:{assessment_id}")
        summary_sentences.append("Severe surface deterioration detected in inspected area.")
        inspection_actions.append("Prioritize on-site physical walk-through inspection for localized structural pitting.")

    if pothole_count > 0:
        evidence_refs.append(f"defect:pothole_count:{pothole_count}")
        summary_sentences.append(f"Identified {pothole_count} visible pothole instance(s).")
        inspection_actions.append("Verify pothole depth and perimeter stability using manual road gauge.")

    if crack_area is not None and crack_area > 0.0:
        evidence_refs.append(f"defect:crack_area:{crack_area:.3f}m2")
        summary_sentences.append(f"Visible crack footprint covers {crack_area:.3f} m².")
        inspection_actions.append("Inspect crack propagation and check for moisture intrusion.")

    # 5. Aggregate Metrology
    if chip_count is not None and chip_density is not None:
        summary_sentences.append(
            f"Visible aggregate count: {chip_count} particles ({chip_density:.1f} chips/m²)."
        )
    if gap_median is not None:
        summary_sentences.append(f"Median adjacent-boundary chip spacing: {gap_median:.2f} mm.")

    # 6. Inclination / Grade
    if grade_percent is not None:
        summary_sentences.append(f"Measured supporting longitudinal grade: {grade_percent:.1f}%.")

    # 7. Standard Engineering Limitations
    limitations.append("Analysis based solely on visible RGB surface appearance; structural load capacity, sub-base condition, and water permeability are not measured.")
    limitations.append("No automatic structural reconstruction or repair cost claims are made.")

    if not inspection_actions:
        inspection_actions.append("Routine scheduled visual monitoring; no urgent localized defect flagged.")

    return ReportContent(
        summary=" ".join(summary_sentences),
        evidence_references=evidence_refs,
        limitations=limitations,
        inspection_actions=inspection_actions,
        narrative_status=NarrativeStatus.FALLBACK,
        factual_template_used=True,
    )
