"""Response models for PDI API endpoints."""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel


class PolicyAnalysisResponse(BaseModel):
    """Response from policy analysis."""
    payer_name: str
    coverage_status: str
    approval_likelihood: float
    criteria_met: int
    criteria_total: int
    documentation_gaps: List[Dict[str, Any]]
    recommendations: List[str]
    step_therapy_required: bool
    step_therapy_satisfied: bool


class HealthCheckResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: str
    version: str
    components: Dict[str, bool]


class ErrorResponse(BaseModel):
    """Error response."""
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None
