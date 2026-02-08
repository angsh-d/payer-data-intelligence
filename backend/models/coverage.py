"""Coverage assessment models."""
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

from .enums import CoverageStatus


class CriterionAssessment(BaseModel):
    """Assessment of a single coverage criterion."""
    criterion_id: str = Field(..., description="Unique identifier for the criterion")
    criterion_name: str = Field(..., description="Name of the coverage criterion")
    criterion_description: str = Field(..., description="Description of what the criterion requires")
    is_met: bool = Field(..., description="Whether the criterion is currently met")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0-1)")
    supporting_evidence: List[str] = Field(default_factory=list, description="Evidence supporting the assessment")
    gaps: List[str] = Field(default_factory=list, description="Missing documentation or requirements")
    reasoning: str = Field(..., description="LLM reasoning for this assessment")


class DocumentationGap(BaseModel):
    """Identified gap in documentation."""
    gap_id: str = Field(..., description="Unique identifier for the gap")
    gap_type: str = Field(..., description="Type of documentation gap")
    description: str = Field(..., description="Description of what is missing")
    required_for: List[str] = Field(default_factory=list, description="Criteria this gap affects")
    priority: str = Field(..., description="Priority level: high, medium, low")
    suggested_action: str = Field(..., description="Recommended action to resolve gap")
    estimated_resolution_complexity: str = Field(default="medium", description="Complexity: simple, medium, complex")


class CoverageAssessment(BaseModel):
    """Complete coverage assessment for a payer."""
    assessment_id: str = Field(..., description="Unique identifier for this assessment")
    payer_name: str = Field(..., description="Name of the payer")
    policy_name: str = Field(..., description="Name of the policy document analyzed")
    medication_name: str = Field(..., description="Medication being assessed")
    assessment_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Overall status
    coverage_status: CoverageStatus = Field(..., description="Overall coverage status")
    approval_likelihood: float = Field(..., ge=0.0, le=1.0, description="Probability of approval (0-1)")
    approval_likelihood_reasoning: str = Field(..., description="Reasoning for likelihood score")

    # Criterion-level assessments
    criteria_assessments: List[CriterionAssessment] = Field(
        default_factory=list,
        description="Individual criterion assessments"
    )
    criteria_met_count: int = Field(default=0, description="Number of criteria met")
    criteria_total_count: int = Field(default=0, description="Total number of criteria")

    # Gaps and recommendations
    documentation_gaps: List[DocumentationGap] = Field(
        default_factory=list,
        description="Identified documentation gaps"
    )
    recommendations: List[str] = Field(
        default_factory=list,
        description="Recommendations for improving approval likelihood"
    )

    # Step therapy and alternatives
    step_therapy_required: bool = Field(default=False, description="Whether step therapy is required")
    step_therapy_options: List[str] = Field(default_factory=list, description="Step therapy drug options")
    step_therapy_satisfied: bool = Field(default=False, description="Whether step therapy is satisfied")

    # Raw data
    raw_policy_text: Optional[str] = Field(default=None, description="Raw policy text analyzed")
    llm_raw_response: Optional[Dict[str, Any]] = Field(default=None, description="Raw LLM response")

    def calculate_readiness_score(self) -> float:
        """Calculate documentation readiness score."""
        if self.criteria_total_count == 0:
            return 0.0
        base_score = self.criteria_met_count / self.criteria_total_count

        # Penalty for documentation gaps
        gap_penalty = len(self.documentation_gaps) * 0.05
        return max(0.0, min(1.0, base_score - gap_penalty))

    def get_critical_gaps(self) -> List[DocumentationGap]:
        """Get high-priority documentation gaps."""
        return [gap for gap in self.documentation_gaps if gap.priority.lower() == "high"]
