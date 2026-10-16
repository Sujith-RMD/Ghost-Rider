"""Amazon Bedrock Runtime Converse API integration for factual narration.

Adheres strictly to the final plan constraints:
- Uses Boto3 Bedrock Runtime Converse API with available model in approved AWS region.
- Supplies compact structured measurements and permitted interpretation reason codes only.
- Prohibits Bedrock from estimating counts, gaps, scale, scores, repair costs, or structural design.
- Validates every referenced fact against stored data.
- Caches results by (assessment_id, factual_input_hash).
- On timeout, schema failure, or missing AWS credentials, cleanly falls back to deterministic template.

Ownership: Backend & AWS AI
Reference: docs/final_plan.md (Section 12.3)
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from ..schemas import NarrativeStatus, ReportContent
from ..bedrock_models import promote_nova_model_id
from .template import build_factual_template

logger = logging.getLogger("ghost_rider.reports.bedrock")

DEFAULT_BEDROCK_REGION = os.getenv("AWS_REGION", "ap-southeast-2")
# ap-southeast-2 serves Amazon Nova through cross-region inference profiles; promote the
# bare default so the report path works without an explicit BEDROCK_MODEL_ID override.
DEFAULT_BEDROCK_MODEL_ID = promote_nova_model_id(
    os.getenv("BEDROCK_MODEL_ID", "amazon.nova-micro-v1:0"), DEFAULT_BEDROCK_REGION
) or "amazon.nova-micro-v1:0"
FALLBACK_BEDROCK_MODEL_ID = os.getenv("BEDROCK_FALLBACK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")

# In-memory LRU cache for factual report outputs: hash -> (ReportContent, model_id)
_NARRATIVE_CACHE: Dict[str, Tuple[ReportContent, str]] = {}


def is_bedrock_configured() -> bool:
    """Check if Bedrock client can be initialized with credentials or IAM role."""
    try:
        import boto3
        session = boto3.Session()
        creds = session.get_credentials()
        return creds is not None and bool(session.region_name or DEFAULT_BEDROCK_REGION)
    except Exception:
        return False


def get_bedrock_client(region: Optional[str] = None) -> Optional[Any]:
    """Obtain boto3 bedrock-runtime client."""
    try:
        import boto3
        target_region = region or DEFAULT_BEDROCK_REGION
        return boto3.client("bedrock-runtime", region_name=target_region)
    except Exception as exc:
        logger.debug("Could not initialize boto3 bedrock-runtime: %s", exc)
        return None


def _format_facts_for_prompt(assessment_id: str, facts: Dict[str, Any]) -> str:
    """Format compact structured facts into a concise, tamper-proof JSON string."""
    compact = {
        "assessment_id": assessment_id,
        "quality_status": facts.get("quality_status"),
        "quality_reasons": facts.get("quality_reasons", []),
        "scale_source": facts.get("scale_source", "unscaled"),
        "observed_area_m2": facts.get("observed_area_m2"),
        "sqi_score": facts.get("score_value"),
        "condition_rating": facts.get("score_status"),
        "pothole_count": facts.get("pothole_count", 0),
        "crack_total_area_m2": facts.get("crack_total_area_m2"),
        "chip_density_per_m2": facts.get("chip_density_per_m2"),
        "gap_median_mm": facts.get("gap_median_mm"),
        "severe_defect_flag": bool(facts.get("severe_defect_flag", False)),
        "grade_percent": facts.get("grade_percent"),
    }
    return json.dumps(compact, indent=2)


SYSTEM_PROMPT = """You are Ghost-Rider's Road Inspection Assistant.
Your sole job is to translate strictly verified pavement measurements into clear engineering inspection notes.

RULES:
1. DO NOT invent, hallucinate, or recalculate any numbers, scores, dimensions, or particle counts.
2. DO NOT estimate repair costs, financial budgets, or prescribe structural sub-base reconstruction.
3. Recommend human review of the source image. Name crack or pothole inspection only when the corresponding input measurement is positive; null means unavailable.
4. Do not write numeric quantities in prose. The application renders measured numbers directly from stored facts.
5. Use exactly one evidence reference: "sample:<assessment_id>" from the input. Clearly state engineering limitations.
6. Null measurements mean unmeasured. Do not claim that no defects or measurements exist; other evidence may be present outside these fields.
7. Output ONLY a valid JSON object matching this exact schema:
{
  "summary": "Concise 2-3 sentence factual summary rendered from the input facts",
  "evidence_references": ["sample:<assessment_id>"],
  "limitations": ["Limitation 1", ...],
  "inspection_actions": ["Action 1", ...]
}
Do not include markdown fences (```json), explanations, or preamble. Return ONLY the raw JSON string."""


def generate_bedrock_narrative(
    assessment_id: str,
    stored_facts: Dict[str, Any],
    factual_input_hash: str,
    model_id: Optional[str] = None,
) -> Tuple[ReportContent, Optional[str]]:
    """Generate fact-checked narrative using Bedrock Runtime Converse API.

    Returns:
        (ReportContent, bedrock_model_id_used)
    """
    # 1. Check cache first
    cache_key = f"{assessment_id}:{factual_input_hash}"
    if cache_key in _NARRATIVE_CACHE:
        cached_content, cached_model = _NARRATIVE_CACHE[cache_key]
        logger.info("Bedrock narrative served from cache for %s", assessment_id)
        return cached_content, cached_model

    client = get_bedrock_client()
    if client is None:
        logger.warning("Bedrock client unavailable; falling back to deterministic template")
        fallback = build_factual_template(assessment_id, stored_facts)
        return fallback, None

    active_model_id = model_id or DEFAULT_BEDROCK_MODEL_ID
    prompt_facts = _format_facts_for_prompt(assessment_id, stored_facts)

    try:
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "text": f"Generate inspection findings and actions for the following road assessment data:\n{prompt_facts}"
                    }
                ],
            }
        ]

        logger.info("Calling Bedrock Converse API with model %s for %s", active_model_id, assessment_id)
        response = client.converse(
            modelId=active_model_id,
            messages=messages,
            system=[{"text": SYSTEM_PROMPT}],
            inferenceConfig={
                "maxTokens": 800,
                "temperature": 0.1,  # Low temperature for factual precision
                "topP": 0.9,
            },
        )

        output_message = response.get("output", {}).get("message", {})
        contents = output_message.get("content", [])
        text_response = ""
        for c in contents:
            if "text" in c:
                text_response += c["text"]

        # 2. Parse and validate Bedrock JSON output
        parsed_json = _parse_and_validate_bedrock_json(text_response, assessment_id, stored_facts)
        if parsed_json is None:
            logger.warning("Bedrock output failed validation; using factual template fallback")
            fallback = build_factual_template(assessment_id, stored_facts)
            return fallback, active_model_id

        # 3. Construct validated ReportContent
        report_content = ReportContent(
            summary=parsed_json["summary"],
            evidence_references=parsed_json["evidence_references"],
            limitations=parsed_json["limitations"],
            inspection_actions=parsed_json["inspection_actions"],
            narrative_status=NarrativeStatus.GENERATED,
            factual_template_used=False,
        )

        # 4. Cache valid output
        if len(_NARRATIVE_CACHE) > 500:
            _NARRATIVE_CACHE.clear()
        _NARRATIVE_CACHE[cache_key] = (report_content, active_model_id)

        return report_content, active_model_id

    except Exception as exc:
        logger.warning("Bedrock call failed for %s (%s: %s); degrading to factual template",
                       assessment_id, type(exc).__name__, exc)
        fallback = build_factual_template(assessment_id, stored_facts)
        return fallback, None


def _parse_and_validate_bedrock_json(
    raw_text: str,
    assessment_id: str,
    stored_facts: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Clean and validate JSON response from Bedrock."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except Exception as exc:
        logger.debug("Failed to decode Bedrock response as JSON: %s. Response was: %r", exc, raw_text[:200])
        return None

    if not isinstance(data, dict):
        return None

    summary = str(data.get("summary") or "").strip()
    if not summary:
        return None

    # Check for hallucinated structural repair claims or cost estimates
    lower_summary = summary.lower()
    prohibited_keywords = ["dollars", "rupees", "cost estimation", "sub-base reconstruction", "demolition"]
    if any(k in lower_summary for k in prohibited_keywords):
        logger.warning("Bedrock response contained prohibited keywords; rejecting")
        return None

    evidence_refs = data.get("evidence_references")
    if evidence_refs != [f"sample:{assessment_id}"]:
        return None

    limitations = data.get("limitations") or []
    if not isinstance(limitations, list):
        limitations = [str(limitations)]

    inspection_actions = data.get("inspection_actions") or []
    if not isinstance(inspection_actions, list):
        inspection_actions = [str(inspection_actions)]

    prose = " ".join([summary, *map(str, limitations), *map(str, inspection_actions)]).lower()
    if re.search(r"\d", prose):
        return None
    if re.search(r"\bno\b.{0,50}\b(?:defects?|damage|distress|cracks?|potholes?|measurements?)\b", prose):
        return None
    if not stored_facts.get("pothole_count") and re.search(r"\bpotholes?\b|\bpitting\b", prose):
        return None
    if not stored_facts.get("crack_total_area_m2") and re.search(r"\bcracks?\b|\bcracking\b|\bfissures?\b", prose):
        return None

    return {
        "summary": summary,
        "evidence_references": [str(r) for r in evidence_refs],
        "limitations": [str(l) for l in limitations],
        "inspection_actions": [str(a) for a in inspection_actions],
    }
