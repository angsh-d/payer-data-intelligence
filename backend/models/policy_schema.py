"""
Digitized Policy Schema - Atomic Criteria with Logical Operators

This module defines the schema for representing payer policies in a structured,
machine-readable format that enables deterministic patient qualification.

Design Principles:
- Atomic criteria: Each criterion tests ONE specific condition
- Logical composition: Complex rules built from atoms using AND/OR/NOT
- Clinical coding: ICD-10, HCPCS, CPT, NDC codes where applicable
- Explicit thresholds: Numeric comparisons are explicit (age >= 18, not "adult")
"""

from datetime import date
from typing import Dict, List, Optional, Union, Literal
from pydantic import BaseModel, Field
from enum import Enum


class ExtractionConfidence(str, Enum):
    """Confidence level of extracted criterion."""
    HIGH = "high"           # Explicitly stated, unambiguous
    MEDIUM = "medium"       # Implied or requires interpretation
    LOW = "low"             # Inferred, may be incorrect
    UNCONFIDENT = "unconfident"  # Flagged for human review


class CriterionCategory(str, Enum):
    """Category hierarchy for criterion types."""
    DEMOGRAPHICS = "demographics"
    DIAGNOSIS = "diagnosis"
    TREATMENT_HISTORY = "treatment_history"
    LAB_RESULTS = "lab_results"
    SAFETY = "safety"
    PRESCRIBER = "prescriber"
    DOCUMENTATION = "documentation"
    CONCURRENT_THERAPY = "concurrent_therapy"
    BIOMARKER = "biomarker"
    FUNCTIONAL_STATUS = "functional_status"
    STAGING = "staging"
    IMAGING = "imaging"
    GENETIC_TESTING = "genetic_testing"
    PROGRAM_ENROLLMENT = "program_enrollment"
    SITE_OF_CARE = "site_of_care"
    QUANTITY_LIMITS = "quantity_limits"
    FORMULARY = "formulary"


class PolicyType(str, Enum):
    """Type of payer policy."""
    MEDICAL_BENEFIT_PA = "medical_benefit_pa"
    PHARMACY_BENEFIT_PA = "pharmacy_benefit_pa"
    MEDICARE_LCD = "medicare_lcd"
    MEDICARE_NCD = "medicare_ncd"
    STEP_THERAPY_PROTOCOL = "step_therapy_protocol"
    FORMULARY_EXCEPTION = "formulary_exception"
    SITE_OF_CARE = "site_of_care"
    QUANTITY_LIMIT_EXCEPTION = "quantity_limit_exception"


class CriterionProvenance(BaseModel):
    """Tracks where a criterion was extracted from and validation status."""
    criterion_id: str
    source_page: Optional[int] = None
    source_section: Optional[str] = None
    source_text_excerpt: str = ""
    extraction_confidence: ExtractionConfidence = ExtractionConfidence.MEDIUM
    validation_action: Optional[str] = None       # confirmed/corrected/added
    validation_reasoning: Optional[str] = None
    code_validation_results: Dict[str, bool] = Field(default_factory=dict)


class ComparisonOperator(str, Enum):
    """Comparison operators for numeric/date criteria."""
    EQUALS = "eq"
    NOT_EQUALS = "ne"
    GREATER_THAN = "gt"
    GREATER_THAN_OR_EQUAL = "gte"
    LESS_THAN = "lt"
    LESS_THAN_OR_EQUAL = "lte"
    BETWEEN = "between"  # Inclusive range
    IN = "in"  # Value in list
    NOT_IN = "not_in"  # Value not in list


class LogicalOperator(str, Enum):
    """Logical operators for combining criteria."""
    AND = "AND"
    OR = "OR"
    NOT = "NOT"


class CriterionType(str, Enum):
    """Types of atomic criteria."""
    # Patient demographics
    AGE = "age"
    GENDER = "gender"

    # Clinical diagnosis
    DIAGNOSIS_CONFIRMED = "diagnosis_confirmed"
    DIAGNOSIS_SEVERITY = "diagnosis_severity"
    DISEASE_DURATION = "disease_duration"

    # Prior treatments / Step therapy
    PRIOR_TREATMENT_TRIED = "prior_treatment_tried"
    PRIOR_TREATMENT_FAILED = "prior_treatment_failed"
    PRIOR_TREATMENT_INTOLERANT = "prior_treatment_intolerant"
    PRIOR_TREATMENT_CONTRAINDICATED = "prior_treatment_contraindicated"
    PRIOR_TREATMENT_DURATION = "prior_treatment_duration"

    # Lab values
    LAB_VALUE = "lab_value"
    LAB_TEST_COMPLETED = "lab_test_completed"

    # Safety screenings
    SAFETY_SCREENING_COMPLETED = "safety_screening_completed"
    SAFETY_SCREENING_NEGATIVE = "safety_screening_negative"

    # Prescriber requirements
    PRESCRIBER_SPECIALTY = "prescriber_specialty"
    PRESCRIBER_CONSULTATION = "prescriber_consultation"

    # Clinical documentation
    DOCUMENTATION_PRESENT = "documentation_present"
    CLINICAL_MARKER_PRESENT = "clinical_marker_present"

    # Concurrent therapy
    CONCURRENT_THERAPY = "concurrent_therapy"
    NO_CONCURRENT_THERAPY = "no_concurrent_therapy"

    # Custom/Other
    CUSTOM = "custom"


class ClinicalCode(BaseModel):
    """A clinical code (ICD-10, HCPCS, CPT, NDC, etc.)."""
    system: Literal["ICD-10", "ICD-10-CM", "ICD-10-PCS", "HCPCS", "CPT", "NDC", "LOINC", "SNOMED", "RxNorm", "NPI"] = Field(
        ..., description="Code system"
    )
    code: str = Field(..., description="The code value")
    display: Optional[str] = Field(None, description="Human-readable display name")

    def __str__(self) -> str:
        return f"{self.system}:{self.code}"


class AtomicCriterion(BaseModel):
    """
    A single, indivisible criterion that tests ONE specific condition.

    Examples:
    - "Patient age >= 18 years"
    - "Diagnosis of Crohn's Disease (ICD-10: K50.x)"
    - "Prior trial of methotrexate for >= 3 months"
    - "TB screening completed with negative result"
    """
    criterion_id: str = Field(..., description="Unique identifier (e.g., 'CROHN_AGE_001')")
    criterion_type: CriterionType = Field(..., description="Type of criterion")

    # Human-readable
    name: str = Field(..., description="Short name (e.g., 'Age Requirement')")
    description: str = Field(..., description="Full description from policy")
    policy_text: str = Field(..., description="Exact text from policy document")

    # Clinical codes
    clinical_codes: List[ClinicalCode] = Field(
        default_factory=list,
        description="Applicable clinical codes (ICD-10, HCPCS, etc.)"
    )

    # For numeric comparisons
    comparison_operator: Optional[ComparisonOperator] = Field(
        None, description="Comparison operator for numeric criteria"
    )
    threshold_value: Optional[Union[int, float, str]] = Field(
        None, description="Threshold value for comparison"
    )
    threshold_value_upper: Optional[Union[int, float, str]] = Field(
        None, description="Upper bound for BETWEEN comparisons"
    )
    threshold_unit: Optional[str] = Field(
        None, description="Unit of measurement (years, months, days, mg/dL, etc.)"
    )

    # For list-based criteria (e.g., "one of these drugs")
    allowed_values: List[str] = Field(
        default_factory=list,
        description="Allowed values for IN/NOT_IN comparisons"
    )

    # For drug/treatment references
    drug_names: List[str] = Field(
        default_factory=list,
        description="Drug names if criterion involves medications"
    )
    drug_classes: List[str] = Field(
        default_factory=list,
        description="Drug classes (e.g., 'TNF inhibitor', 'conventional DMARD')"
    )

    # Evidence requirements
    evidence_types: List[str] = Field(
        default_factory=list,
        description="Types of evidence that can satisfy criterion"
    )

    # Metadata
    is_required: bool = Field(True, description="Whether criterion is mandatory")
    category: str = Field(..., description="Category (diagnosis, step_therapy, safety, prescriber, etc.)")
    criterion_category: Optional[CriterionCategory] = Field(None, description="Typed category for evaluator dispatch")
    source_section: Optional[str] = Field(None, description="Section in policy document")

    # Extraction provenance (populated by extraction pipeline)
    source_page: Optional[int] = Field(None, description="Page number in source document")
    source_text_excerpt: str = Field("", description="Exact text excerpt from policy document")
    extraction_confidence: ExtractionConfidence = Field(
        ExtractionConfidence.MEDIUM, description="Confidence of extraction"
    )
    validation_status: Optional[str] = Field(None, description="confirmed/corrected/added by validator")

    # Evaluation hints (guide deterministic evaluator)
    patient_data_path: Optional[str] = Field(None, description="JSONPath into patient data (e.g., 'demographics.age')")
    evaluation_strategy: Optional[str] = Field(
        None, description="Evaluator dispatch: numeric_compare, code_match, list_contains, boolean_check, date_compare"
    )
    codes_validated: bool = Field(False, description="Whether clinical codes have been validated against reference data")

    # Duration requirements for step therapy criteria
    minimum_duration_days: Optional[int] = Field(None, description="Minimum trial duration in days")


class CriterionGroup(BaseModel):
    """
    A group of criteria combined with a logical operator.
    Enables building complex rules like:
    - (A AND B AND C)
    - (A OR B)
    - (A AND (B OR C))
    """
    group_id: str = Field(..., description="Unique identifier for this group")
    name: str = Field(..., description="Descriptive name")
    description: Optional[str] = Field(None, description="What this group represents")

    operator: LogicalOperator = Field(..., description="How to combine items in this group")

    # Can contain atomic criteria or nested groups
    criteria: List[str] = Field(
        default_factory=list,
        description="IDs of atomic criteria in this group"
    )
    subgroups: List[str] = Field(
        default_factory=list,
        description="IDs of nested criterion groups"
    )

    # For NOT operator (applies to first criterion/subgroup only)
    negated: bool = Field(False, description="Whether this entire group is negated")


class DosingRequirement(BaseModel):
    """Dosing requirements from policy."""
    indication: str = Field(..., description="Indication this dosing applies to")
    phase: Literal["induction", "maintenance", "both", "all"] = Field(
        ..., description="Treatment phase"
    )
    dose_value: Optional[float] = Field(None, description="Dose amount")
    dose_unit: str = Field(..., description="Dose unit (mg, mg/kg, etc.)")
    route: str = Field(..., description="Administration route (IV, SC, etc.)")
    frequency: str = Field(..., description="Dosing frequency")
    max_dose: Optional[float] = Field(None, description="Maximum single dose")
    max_dose_unit: Optional[str] = Field(None, description="Max dose unit")
    notes: Optional[str] = Field(None, description="Additional dosing notes")


class IndicationCriteria(BaseModel):
    """Coverage criteria for a specific indication."""
    indication_id: str = Field(..., description="Unique ID (e.g., 'CROHN_DISEASE')")
    indication_name: str = Field(..., description="Indication name")
    indication_codes: List[ClinicalCode] = Field(
        default_factory=list,
        description="ICD-10 codes for this indication"
    )

    # Approval criteria
    initial_approval_criteria: str = Field(
        ..., description="ID of root criterion group for initial approval"
    )
    continuation_criteria: Optional[str] = Field(
        None, description="ID of root criterion group for continuation/renewal"
    )

    # Approval duration
    initial_approval_duration_months: int = Field(
        ..., description="Duration of initial approval in months"
    )
    continuation_approval_duration_months: Optional[int] = Field(
        None, description="Duration of continuation approval in months"
    )

    # Dosing
    dosing_requirements: List[DosingRequirement] = Field(
        default_factory=list,
        description="Dosing requirements for this indication"
    )

    # Age restrictions
    min_age_years: Optional[int] = Field(None, description="Minimum age requirement")
    max_age_years: Optional[int] = Field(None, description="Maximum age requirement")


class ExclusionCriteria(BaseModel):
    """Conditions that explicitly exclude coverage."""
    exclusion_id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Name of exclusion")
    description: str = Field(..., description="Description of exclusion condition")
    policy_text: str = Field(..., description="Exact text from policy")

    # What triggers exclusion
    trigger_criteria: List[str] = Field(
        default_factory=list,
        description="Criterion IDs that trigger this exclusion"
    )


class StepTherapyRequirement(BaseModel):
    """Step therapy / prior authorization requirements."""
    requirement_id: str = Field(..., description="Unique identifier")
    indication: str = Field(..., description="Indication this applies to")

    # Required prior treatments
    required_drugs: List[str] = Field(
        default_factory=list,
        description="Specific drugs that must be tried"
    )
    required_drug_classes: List[str] = Field(
        default_factory=list,
        description="Drug classes that must be tried"
    )

    # How many must be tried
    minimum_trials: int = Field(1, description="Minimum number of drugs to try")

    # Duration requirements
    minimum_duration_days: Optional[int] = Field(
        None, description="Minimum trial duration in days"
    )

    # Acceptable outcomes
    failure_required: bool = Field(True, description="Must demonstrate treatment failure")
    intolerance_acceptable: bool = Field(True, description="Intolerance counts as trial")
    contraindication_acceptable: bool = Field(True, description="Contraindication exempts trial")

    # Documentation
    documentation_requirements: List[str] = Field(
        default_factory=list,
        description="Required documentation for step therapy"
    )


class DigitizedPolicy(BaseModel):
    """
    Complete digitized representation of a payer policy.

    This structure enables:
    1. Deterministic patient qualification
    2. Gap analysis (what criteria are not met)
    3. Documentation checklists
    4. Appeal strategy generation
    """
    # Policy identification
    policy_id: str = Field(..., description="Unique policy identifier (e.g., 'CIGNA_IP0660')")
    policy_number: str = Field(..., description="Official policy number")
    policy_title: str = Field(..., description="Official policy title")
    payer_name: str = Field(..., description="Payer organization name")

    # Medication covered
    medication_name: str = Field(..., description="Primary medication name")
    medication_brand_names: List[str] = Field(
        default_factory=list,
        description="Brand names covered"
    )
    medication_generic_names: List[str] = Field(
        default_factory=list,
        description="Generic names covered"
    )
    medication_codes: List[ClinicalCode] = Field(
        default_factory=list,
        description="HCPCS, NDC codes for the medication"
    )

    # Effective dates
    effective_date: date = Field(..., description="Policy effective date")
    last_revision_date: Optional[date] = Field(None, description="Last revision date")

    # Building blocks
    atomic_criteria: Dict[str, AtomicCriterion] = Field(
        default_factory=dict,
        description="All atomic criteria, keyed by criterion_id"
    )
    criterion_groups: Dict[str, CriterionGroup] = Field(
        default_factory=dict,
        description="All criterion groups, keyed by group_id"
    )

    # Indications and their criteria
    indications: List[IndicationCriteria] = Field(
        default_factory=list,
        description="Coverage criteria by indication"
    )

    # Exclusions
    exclusions: List[ExclusionCriteria] = Field(
        default_factory=list,
        description="Explicit exclusion conditions"
    )

    # Step therapy
    step_therapy_requirements: List[StepTherapyRequirement] = Field(
        default_factory=list,
        description="Step therapy requirements"
    )

    # Specialist requirements
    required_specialties: List[str] = Field(
        default_factory=list,
        description="Specialties that can prescribe"
    )
    consultation_allowed: bool = Field(
        True, description="Whether consultation with specialist is acceptable"
    )

    # Safety requirements (accepts both simple strings and rich screening objects)
    safety_screenings: List[Union[str, Dict]] = Field(
        default_factory=list,
        description="Required safety screenings"
    )

    # Policy type and version
    policy_type: PolicyType = Field(PolicyType.MEDICAL_BENEFIT_PA, description="Type of payer policy")
    version: Optional[str] = Field(None, description="Policy version label (e.g., 'v1', '2024-Q3')")

    # Metadata
    extraction_timestamp: Optional[str] = Field(None, description="When policy was digitized")
    extraction_model: Optional[str] = Field(None, description="Model used for extraction")
    source_document_hash: Optional[str] = Field(None, description="Hash of source document")

    # Pipeline metadata (populated by multi-pass pipeline)
    extraction_pipeline_version: Optional[str] = Field(None, description="Version of extraction pipeline")
    validation_model: Optional[str] = Field(None, description="Model used for validation pass")
    extraction_quality: Optional[str] = Field(None, description="good / needs_review / poor")
    provenances: Dict[str, CriterionProvenance] = Field(
        default_factory=dict, description="Provenance per criterion_id"
    )

    def get_criterion(self, criterion_id: str) -> Optional[AtomicCriterion]:
        """Get an atomic criterion by ID."""
        return self.atomic_criteria.get(criterion_id)

    def get_group(self, group_id: str) -> Optional[CriterionGroup]:
        """Get a criterion group by ID."""
        return self.criterion_groups.get(group_id)

    def get_indication(self, indication_name: str) -> Optional[IndicationCriteria]:
        """Get indication criteria by name."""
        for indication in self.indications:
            if indication.indication_name.lower() == indication_name.lower():
                return indication
        return None

    def get_all_criteria_for_indication(self, indication_name: str) -> List[AtomicCriterion]:
        """Get all atomic criteria applicable to an indication."""
        indication = self.get_indication(indication_name)
        if not indication:
            return []

        criteria_ids = set()
        self._collect_criteria_ids(indication.initial_approval_criteria, criteria_ids)

        return [self.atomic_criteria[cid] for cid in criteria_ids if cid in self.atomic_criteria]

    def _collect_criteria_ids(self, group_id: str, collected: set, visited: Optional[set] = None):
        """Recursively collect all criterion IDs from a group with cycle detection."""
        if visited is None:
            visited = set()
        if group_id in visited:
            return
        visited.add(group_id)

        group = self.criterion_groups.get(group_id)
        if not group:
            return

        for cid in group.criteria:
            collected.add(cid)

        for subgroup_id in group.subgroups:
            self._collect_criteria_ids(subgroup_id, collected, visited)
