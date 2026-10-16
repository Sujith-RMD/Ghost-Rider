"""Unit tests for Bedrock integration and factual reporting.

Verifies:
- Factual input hashing determinism
- Deterministic factual template generation
- Fact-checking and rejection of prohibited repair cost/reconstruction claims
- Graceful degradation to template fallback on Bedrock absence or errors
"""

from unittest.mock import MagicMock, patch

from backend.reports.bedrock import (
    _parse_and_validate_bedrock_json,
    generate_bedrock_narrative,
)
from backend.reports.generator import compute_factual_hash, generate_report_for_assessment
from backend.reports.template import build_factual_template
from backend.schemas import NarrativeStatus, QualityStatus, ScoreStatus


def test_factual_input_hash_determinism():
    facts = {
        "quality_status": "accepted",
        "score_value": 78,
        "score_status": "Good",
        "pothole_count": 0,
        "chip_density_per_m2": 450.0,
    }
    h1 = compute_factual_hash("sample-01", facts)
    h2 = compute_factual_hash("sample-01", facts)
    assert h1 == h2
    assert len(h1) == 64

    # Changing a single fact alters the hash
    facts2 = dict(facts, score_value=79)
    assert compute_factual_hash("sample-01", facts2) != h1


def test_deterministic_factual_template():
    facts = {
        "quality_status": QualityStatus.ACCEPTED.value,
        "score_value": 82,
        "score_status": ScoreStatus.GOOD.value,
        "scale_source": "rig_calibrated",
        "observed_area_m2": 0.5,
        "chip_count": 410,
        "chip_density_per_m2": 820.0,
        "gap_median_mm": 1.25,
        "pothole_count": 0,
        "severe_defect_flag": False,
    }
    report = build_factual_template("sample-100", facts)

    assert report.factual_template_used is True
    assert "Surface Quality Index (SQI): 82/100" in report.summary
    assert "820.0 chips/m²" in report.summary
    assert len(report.limitations) >= 2
    assert any("load capacity" in lim.lower() for lim in report.limitations)
    assert len(report.inspection_actions) >= 1


def test_bedrock_output_fact_checking():
    facts = {"assessment_id": "test-1", "crack_total_area_m2": 0.2}

    # Valid response
    valid_json = """{
        "summary": "Pavement surface shows localized longitudinal cracking.",
        "evidence_references": ["sample:test-1"],
        "limitations": ["Visual RGB only"],
        "inspection_actions": ["Manual walk-through check"]
    }"""
    parsed = _parse_and_validate_bedrock_json(valid_json, "test-1", facts)
    assert parsed is not None
    assert "localized longitudinal cracking" in parsed["summary"]

    # Prohibited claim: cost estimation
    prohibited_cost_json = """{
        "summary": "This repair will cost approximately 50000 rupees.",
        "evidence_references": ["sample:test-1"],
        "limitations": [],
        "inspection_actions": ["Pay contractor"]
    }"""
    parsed_bad = _parse_and_validate_bedrock_json(prohibited_cost_json, "test-1", facts)
    assert parsed_bad is None  # Must reject hallucinated cost estimates!

    # Prohibited claim: sub-base demolition
    prohibited_subbase_json = """{
        "summary": "Sub-base reconstruction required immediately.",
        "evidence_references": ["sample:test-1"],
        "limitations": [],
        "inspection_actions": ["Excavate road base"]
    }"""
    parsed_bad2 = _parse_and_validate_bedrock_json(prohibited_subbase_json, "test-1", facts)
    assert parsed_bad2 is None


def test_bedrock_rejects_unsupported_distress_action_and_reference():
    facts = {"quality_status": "limited", "pothole_count": None, "crack_total_area_m2": None}
    unsupported = """{
        "summary": "The condition rating is unknown.",
        "evidence_references": ["sample:test-1"],
        "limitations": ["Scale missing"],
        "inspection_actions": ["Confirm pothole edge stability"]
    }"""
    assert _parse_and_validate_bedrock_json(unsupported, "test-1", facts) is None

    invented_reference = unsupported.replace("Confirm pothole edge stability", "Review the source image").replace("sample:test-1", "sample:other")
    assert _parse_and_validate_bedrock_json(invented_reference, "test-1", facts) is None

    invented_number = invented_reference.replace("sample:other", "sample:test-1").replace("unknown", "72/100")
    assert _parse_and_validate_bedrock_json(invented_number, "test-1", facts) is None

    invented_absence = invented_reference.replace("sample:other", "sample:test-1").replace("The condition rating is unknown.", "No defect identifications are available.")
    assert _parse_and_validate_bedrock_json(invented_absence, "test-1", facts) is None


def test_generate_report_fallback_when_bedrock_unconfigured():
    facts = {
        "quality_status": "accepted",
        "score_value": 75,
        "score_status": "Good",
    }
    # When Bedrock is not configured, requesting narrative gracefully falls back
    report = generate_report_for_assessment("sample-200", facts, include_narrative=True)

    assert report.assessment_id == "sample-200"
    assert report.content.factual_template_used is True
    assert report.content.narrative_status == NarrativeStatus.FALLBACK
    assert report.bedrock_model_id is None
    assert report.factual_input_hash is not None
