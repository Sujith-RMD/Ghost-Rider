"""Ghost-Rider report generation and Bedrock narrative package.

Ownership: Backend & AWS AI
"""

from .bedrock import (
    DEFAULT_BEDROCK_MODEL_ID,
    generate_bedrock_narrative,
    is_bedrock_configured,
)
from .generator import (
    compute_factual_hash,
    extract_facts_from_sample,
    generate_report_for_assessment,
)
from .template import build_factual_template

__all__ = [
    "DEFAULT_BEDROCK_MODEL_ID",
    "generate_bedrock_narrative",
    "is_bedrock_configured",
    "compute_factual_hash",
    "extract_facts_from_sample",
    "generate_report_for_assessment",
    "build_factual_template",
]
