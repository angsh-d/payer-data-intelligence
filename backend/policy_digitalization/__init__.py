"""Policy Digitalization Module.

Multi-pass extraction pipeline for converting payer policy documents
into structured, machine-readable criteria.
"""

from backend.policy_digitalization.exceptions import (
    ExtractionError,
    ValidationError,
    EvaluationError,
    PolicyNotFoundError,
)
from backend.policy_digitalization.differ import (
    PolicyDiffer,
    PolicyDiffResult,
    ChangeType,
)
from backend.policy_digitalization.impact_analyzer import (
    PolicyImpactAnalyzer,
    PolicyImpactReport,
    PatientImpact,
)

__all__ = [
    # Exceptions
    "ExtractionError",
    "ValidationError",
    "EvaluationError",
    "PolicyNotFoundError",
    # Differ
    "PolicyDiffer",
    "PolicyDiffResult",
    "ChangeType",
    # Impact
    "PolicyImpactAnalyzer",
    "PolicyImpactReport",
    "PatientImpact",
]
