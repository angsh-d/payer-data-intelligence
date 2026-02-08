"""Request models for PDI API endpoints."""
from typing import Dict, Any
from pydantic import BaseModel, Field


class AnalyzePoliciesRequest(BaseModel):
    """Request for policy analysis."""
    patient_info: Dict[str, Any] = Field(..., description="Patient information")
    medication_info: Dict[str, Any] = Field(..., description="Medication details")
    payer_name: str = Field(..., description="Payer to analyze")
