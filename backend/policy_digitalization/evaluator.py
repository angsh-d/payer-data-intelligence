"""Deterministic Criteria Evaluator — NO LLM, pure logic.

Evaluates patient data against digitized policy criteria to produce
per-criterion verdicts (MET / NOT_MET / INSUFFICIENT_DATA / NOT_APPLICABLE).

Design principles:
- Pure function: no DB, no LLM, no side effects
- Same inputs always produce same outputs
- INSUFFICIENT_DATA != NOT_MET — missing data drives gap analysis, not denial
- Fully testable and auditable
"""

from enum import Enum
from typing import Dict, List, Optional, Callable, Tuple

from pydantic import BaseModel, Field

from backend.models.policy_schema import (
    DigitizedPolicy, AtomicCriterion, CriterionGroup, CriterionType,
    CriterionCategory, ComparisonOperator, LogicalOperator,
)
from backend.policy_digitalization.patient_data_adapter import NormalizedPatientData
from backend.policy_digitalization.exceptions import EvaluationError
from backend.config.logging_config import get_logger

logger = get_logger(__name__)


class CriterionVerdict(str, Enum):
    MET = "met"
    NOT_MET = "not_met"
    INSUFFICIENT_DATA = "insufficient_data"
    NOT_APPLICABLE = "not_applicable"


class CriterionEvaluation(BaseModel):
    criterion_id: str
    criterion_name: str
    verdict: CriterionVerdict
    confidence: float = 1.0
    evidence: List[str] = Field(default_factory=list)
    reasoning: str = ""
    is_required: bool = True


class GroupEvaluation(BaseModel):
    group_id: str
    operator: str  # AND, OR, NOT
    verdict: CriterionVerdict
    reasoning: str = ""
    criteria_results: List[CriterionEvaluation] = Field(default_factory=list)
    subgroup_results: List["GroupEvaluation"] = Field(default_factory=list)


class IndicationEvaluation(BaseModel):
    indication_id: str
    indication_name: str
    overall_verdict: CriterionVerdict
    approval_criteria_result: Optional[GroupEvaluation] = None
    criteria_met_count: int = 0
    criteria_total_count: int = 0
    unmet_criteria: List[CriterionEvaluation] = Field(default_factory=list)
    insufficient_criteria: List[CriterionEvaluation] = Field(default_factory=list)


class PolicyEvaluationResult(BaseModel):
    policy_id: str
    patient_id: str
    indication_evaluations: List[IndicationEvaluation] = Field(default_factory=list)
    exclusion_evaluations: List[CriterionEvaluation] = Field(default_factory=list)
    step_therapy_evaluation: Optional[Dict] = None
    overall_readiness: float = 0.0  # 0.0-1.0
    overall_verdict: CriterionVerdict = CriterionVerdict.INSUFFICIENT_DATA
    gaps: List[Dict] = Field(default_factory=list)


# --- Evaluator Registry ---

CriterionEvaluatorFn = Callable[[AtomicCriterion, NormalizedPatientData], CriterionEvaluation]

EVALUATOR_REGISTRY: Dict[str, CriterionEvaluatorFn] = {}


def register_evaluator(*criterion_types: str):
    """Decorator to register an evaluator function for one or more CriterionType values."""
    def decorator(fn: CriterionEvaluatorFn):
        for ct in criterion_types:
            EVALUATOR_REGISTRY[ct] = fn
        return fn
    return decorator


# --- Individual criterion evaluators ---

@register_evaluator(CriterionType.AGE)
def evaluate_age(criterion: AtomicCriterion, patient: NormalizedPatientData) -> CriterionEvaluation:
    if patient.age_years is None:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.INSUFFICIENT_DATA,
            reasoning="Patient age not available",
            is_required=criterion.is_required,
        )
    raw_threshold = criterion.threshold_value
    if raw_threshold is None:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.INSUFFICIENT_DATA,
            reasoning="No threshold defined in criterion",
            is_required=criterion.is_required,
        )
    threshold = _safe_float(raw_threshold)
    if threshold is None:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.INSUFFICIENT_DATA,
            reasoning=f"Non-numeric threshold value: {raw_threshold}",
            is_required=criterion.is_required,
        )
    met = _compare_numeric(patient.age_years, threshold, criterion.comparison_operator, criterion.threshold_value_upper)
    return CriterionEvaluation(
        criterion_id=criterion.criterion_id,
        criterion_name=criterion.name,
        verdict=CriterionVerdict.MET if met else CriterionVerdict.NOT_MET,
        evidence=[f"Patient age: {patient.age_years} years"],
        reasoning=f"Age {patient.age_years} {'meets' if met else 'does not meet'} {criterion.comparison_operator or 'gte'} {threshold}",
        is_required=criterion.is_required,
    )


@register_evaluator(CriterionType.GENDER)
def evaluate_gender(criterion: AtomicCriterion, patient: NormalizedPatientData) -> CriterionEvaluation:
    if not patient.gender:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.INSUFFICIENT_DATA,
            reasoning="Patient gender not available",
            is_required=criterion.is_required,
        )
    allowed = [v.lower() for v in criterion.allowed_values] if criterion.allowed_values else []
    if not allowed and criterion.threshold_value:
        allowed = [str(criterion.threshold_value).lower()]
    met = patient.gender.lower() in allowed if allowed else True
    return CriterionEvaluation(
        criterion_id=criterion.criterion_id,
        criterion_name=criterion.name,
        verdict=CriterionVerdict.MET if met else CriterionVerdict.NOT_MET,
        evidence=[f"Patient gender: {patient.gender}"],
        reasoning=f"Gender '{patient.gender}' {'is' if met else 'is not'} in allowed values {allowed}",
        is_required=criterion.is_required,
    )


@register_evaluator(CriterionType.DIAGNOSIS_CONFIRMED)
def evaluate_diagnosis_confirmed(criterion: AtomicCriterion, patient: NormalizedPatientData) -> CriterionEvaluation:
    if not patient.diagnosis_codes:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.INSUFFICIENT_DATA,
            reasoning="No diagnosis codes available",
            is_required=criterion.is_required,
        )
    # Check if any patient diagnosis code matches criterion's clinical codes
    criterion_codes = {c.code.upper().replace(".", "") for c in criterion.clinical_codes}
    patient_codes_normalized = {c.upper().replace(".", "") for c in patient.diagnosis_codes}

    # Match by exact or criterion-prefix (criterion K50 matches patient K5010)
    # Patient code must be at least as specific as criterion code (no reverse prefix)
    matched = False
    evidence = []
    for pc in patient.diagnosis_codes:
        pc_norm = pc.upper().replace(".", "")
        for cc in criterion_codes:
            if pc_norm == cc or pc_norm.startswith(cc):
                matched = True
                evidence.append(f"Diagnosis {pc} matches criterion code")
                break

    # If no clinical codes on criterion, try keyword matching against criterion description
    if not criterion_codes:
        desc_lower = criterion.description.lower()
        name_lower = criterion.name.lower()
        # Build keywords from patient's diagnosis codes and severity
        patient_context = " ".join(patient.diagnosis_codes).lower()
        if patient.disease_severity:
            patient_context += " " + patient.disease_severity.lower()
        # Check if criterion description keywords appear in diagnosis context or vice versa
        # Use the criterion name as key diagnostic term
        diag_keywords = [w for w in name_lower.replace("_", " ").split() if len(w) >= 4]
        if any(kw in patient_context for kw in diag_keywords):
            matched = True
            evidence = [f"Diagnosis keyword match: {criterion.name}"]
        else:
            return CriterionEvaluation(
                criterion_id=criterion.criterion_id,
                criterion_name=criterion.name,
                verdict=CriterionVerdict.INSUFFICIENT_DATA,
                evidence=[f"Criterion has no clinical codes; keyword match inconclusive"],
                reasoning="Cannot verify diagnosis without criterion clinical codes",
                is_required=criterion.is_required,
            )

    return CriterionEvaluation(
        criterion_id=criterion.criterion_id,
        criterion_name=criterion.name,
        verdict=CriterionVerdict.MET if matched else CriterionVerdict.NOT_MET,
        evidence=evidence,
        reasoning=f"Diagnosis {'confirmed' if matched else 'not confirmed'} against criterion codes",
        is_required=criterion.is_required,
    )


@register_evaluator(CriterionType.DIAGNOSIS_SEVERITY)
def evaluate_diagnosis_severity(criterion: AtomicCriterion, patient: NormalizedPatientData) -> CriterionEvaluation:
    if not patient.disease_severity:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.INSUFFICIENT_DATA,
            reasoning="Disease severity not documented",
            is_required=criterion.is_required,
        )
    # Check if patient severity matches allowed values or description keywords
    allowed = [v.lower() for v in criterion.allowed_values] if criterion.allowed_values else []
    severity_lower = patient.disease_severity.lower().replace("-", "_").replace(" ", "_")

    met = False
    if allowed:
        met = severity_lower in [a.replace("-", "_").replace(" ", "_") for a in allowed]
    else:
        # Check description keywords
        desc_lower = criterion.description.lower()
        if "moderate" in desc_lower and "moderate" in severity_lower:
            met = True
        elif "severe" in desc_lower and "severe" in severity_lower:
            met = True

    return CriterionEvaluation(
        criterion_id=criterion.criterion_id,
        criterion_name=criterion.name,
        verdict=CriterionVerdict.MET if met else CriterionVerdict.NOT_MET,
        evidence=[f"Disease severity: {patient.disease_severity}"],
        reasoning=f"Severity '{patient.disease_severity}' {'matches' if met else 'does not match'} criterion",
        is_required=criterion.is_required,
    )


@register_evaluator(CriterionType.PRIOR_TREATMENT_TRIED)
def evaluate_prior_treatment_tried(criterion: AtomicCriterion, patient: NormalizedPatientData) -> CriterionEvaluation:
    if not patient.prior_treatments:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.INSUFFICIENT_DATA,
            reasoning="No prior treatment history available",
            is_required=criterion.is_required,
        )
    matched = _find_treatment_match(criterion, patient)
    evidence = [f"Prior treatments: {[t.medication_name for t in patient.prior_treatments]}"]
    return CriterionEvaluation(
        criterion_id=criterion.criterion_id,
        criterion_name=criterion.name,
        verdict=CriterionVerdict.MET if matched else CriterionVerdict.NOT_MET,
        evidence=evidence,
        reasoning=f"Prior treatment {'found' if matched else 'not found'} matching criterion",
        is_required=criterion.is_required,
    )


@register_evaluator(CriterionType.PRIOR_TREATMENT_FAILED)
def evaluate_prior_treatment_failed(criterion: AtomicCriterion, patient: NormalizedPatientData) -> CriterionEvaluation:
    if not patient.prior_treatments:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.INSUFFICIENT_DATA,
            reasoning="No prior treatment history available",
            is_required=criterion.is_required,
        )

    desc_lower = criterion.description.lower()
    name_lower = criterion.name.lower()

    # --- Special case: "X or more lines of therapy" criteria ---
    # These check total treatment lines, not a specific drug failure
    import re
    lines_match = re.search(r'(\w+)\s+or more\s+(?:prior\s+)?lines?\s+of\s+(?:systemic\s+)?therapy', desc_lower)
    if not lines_match:
        lines_match = re.search(r'(?:at least|received)\s+(\w+)\s+(?:prior\s+)?lines?\s+of\s+(?:systemic\s+)?therapy', desc_lower)
    if lines_match:
        word_to_num = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
        required_lines_word = lines_match.group(1).lower()
        required_lines = word_to_num.get(required_lines_word)
        if required_lines is None:
            try:
                required_lines = int(required_lines_word)
            except ValueError:
                required_lines = None

        if required_lines is not None:
            actual_lines = patient.clinical_markers.get("lines_of_therapy")
            if actual_lines is not None:
                met = actual_lines >= required_lines
                return CriterionEvaluation(
                    criterion_id=criterion.criterion_id,
                    criterion_name=criterion.name,
                    verdict=CriterionVerdict.MET if met else CriterionVerdict.NOT_MET,
                    evidence=[f"Lines of therapy: {actual_lines} (required: {required_lines}+)"],
                    reasoning=f"{actual_lines} lines {'meets' if met else 'does not meet'} requirement of {required_lines}+",
                    is_required=criterion.is_required,
                )
            # Fall back to counting treatments
            actual_lines = len(patient.prior_treatments)
            met = actual_lines >= required_lines
            return CriterionEvaluation(
                criterion_id=criterion.criterion_id,
                criterion_name=criterion.name,
                verdict=CriterionVerdict.MET if met else CriterionVerdict.NOT_MET,
                evidence=[f"Prior treatments count: {actual_lines} (required: {required_lines}+)"],
                reasoning=f"{actual_lines} prior treatments {'meets' if met else 'does not meet'} {required_lines}+ requirement",
                is_required=criterion.is_required,
            )

    # --- Special case: "refractory to lenalidomide" ---
    if "refractory" in desc_lower and ("lenalidomide" in desc_lower or "revlimid" in desc_lower):
        refractory_to = patient.clinical_markers.get("refractory_to", [])
        if isinstance(refractory_to, list):
            for drug in refractory_to:
                if "lenalidomide" in drug.lower() or "revlimid" in drug.lower():
                    return CriterionEvaluation(
                        criterion_id=criterion.criterion_id,
                        criterion_name=criterion.name,
                        verdict=CriterionVerdict.MET,
                        evidence=[f"Refractory to: {drug}"],
                        reasoning=f"Patient is refractory to lenalidomide",
                        is_required=criterion.is_required,
                    )
        # Also check treatment outcomes
        for tx in patient.prior_treatments:
            if "lenalidomide" in tx.medication_name.lower() or "revlimid" in tx.medication_name.lower():
                if tx.outcome in ("failed", "inadequate_response", "partial_response"):
                    return CriterionEvaluation(
                        criterion_id=criterion.criterion_id,
                        criterion_name=criterion.name,
                        verdict=CriterionVerdict.MET,
                        evidence=[f"Lenalidomide: outcome={tx.outcome}"],
                        reasoning=f"Lenalidomide failure documented: {tx.outcome}",
                        is_required=criterion.is_required,
                    )
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.NOT_MET,
            reasoning="Lenalidomide refractoriness not documented",
            is_required=criterion.is_required,
        )

    # --- Special case: "NO prior gene therapy" phrased as prior_treatment_failed ---
    if "not previously received gene therapy" in desc_lower or "no prior" in name_lower.replace("_", " "):
        if criterion.drug_names:
            drug_names_lower = {d.lower() for d in criterion.drug_names}
            for tx in patient.prior_treatments:
                tx_lower = tx.medication_name.lower()
                for dn in drug_names_lower:
                    if dn in tx_lower or tx_lower in dn:
                        return CriterionEvaluation(
                            criterion_id=criterion.criterion_id,
                            criterion_name=criterion.name,
                            verdict=CriterionVerdict.NOT_MET,
                            evidence=[f"Patient received excluded drug: {tx.medication_name}"],
                            reasoning=f"Excluded therapy found: {tx.medication_name}",
                            is_required=criterion.is_required,
                        )
            # Check clinical markers
            prior_gt = patient.clinical_markers.get("prior_gene_therapy")
            if prior_gt is not None:
                met = not prior_gt
                return CriterionEvaluation(
                    criterion_id=criterion.criterion_id,
                    criterion_name=criterion.name,
                    verdict=CriterionVerdict.MET if met else CriterionVerdict.NOT_MET,
                    evidence=[f"Prior gene therapy: {prior_gt}"],
                    reasoning=f"Gene therapy {'not received' if met else 'previously received'}",
                    is_required=criterion.is_required,
                )
            return CriterionEvaluation(
                criterion_id=criterion.criterion_id,
                criterion_name=criterion.name,
                verdict=CriterionVerdict.MET,
                evidence=["No excluded drugs found in treatment history"],
                reasoning="None of the excluded drugs found in patient history",
                is_required=criterion.is_required,
            )

    # --- Standard treatment failure check ---
    tx = _get_matched_treatment(criterion, patient)
    if not tx:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.NOT_MET,
            reasoning="No matching treatment found in history",
            is_required=criterion.is_required,
        )
    # Check if the matched treatment failed
    failed_outcomes = {"failed", "inadequate_response", "partial_response", "steroid_dependent"}
    if tx.outcome in failed_outcomes:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.MET,
            evidence=[f"{tx.medication_name}: outcome={tx.outcome}"],
            reasoning=f"Treatment {tx.medication_name} failed with outcome: {tx.outcome}",
            is_required=criterion.is_required,
        )
    return CriterionEvaluation(
        criterion_id=criterion.criterion_id,
        criterion_name=criterion.name,
        verdict=CriterionVerdict.NOT_MET,
        evidence=[f"Treatment found but outcome not a failure: {tx.outcome if tx else 'unknown'}"],
        reasoning="Treatment was tried but failure not documented",
        is_required=criterion.is_required,
    )


@register_evaluator(CriterionType.PRIOR_TREATMENT_INTOLERANT)
def evaluate_prior_treatment_intolerant(criterion: AtomicCriterion, patient: NormalizedPatientData) -> CriterionEvaluation:
    if not patient.prior_treatments:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.INSUFFICIENT_DATA,
            reasoning="No prior treatment history available",
            is_required=criterion.is_required,
        )
    tx = _get_matched_treatment(criterion, patient)
    if tx and tx.outcome == "intolerant":
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.MET,
            evidence=[f"{tx.medication_name}: intolerant"],
            reasoning=f"Patient was intolerant to {tx.medication_name}",
            is_required=criterion.is_required,
        )
    return CriterionEvaluation(
        criterion_id=criterion.criterion_id,
        criterion_name=criterion.name,
        verdict=CriterionVerdict.NOT_MET,
        reasoning="Intolerance not documented for matched treatment",
        is_required=criterion.is_required,
    )


@register_evaluator(CriterionType.PRIOR_TREATMENT_CONTRAINDICATED)
def evaluate_prior_treatment_contraindicated(criterion: AtomicCriterion, patient: NormalizedPatientData) -> CriterionEvaluation:
    if not patient.prior_treatments:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.INSUFFICIENT_DATA,
            reasoning="No prior treatment history available",
            is_required=criterion.is_required,
        )
    tx = _get_matched_treatment(criterion, patient)
    if tx and tx.outcome == "contraindicated":
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.MET,
            evidence=[f"{tx.medication_name}: contraindicated"],
            reasoning=f"Contraindication documented for {tx.medication_name}",
            is_required=criterion.is_required,
        )
    return CriterionEvaluation(
        criterion_id=criterion.criterion_id,
        criterion_name=criterion.name,
        verdict=CriterionVerdict.NOT_MET,
        reasoning="Contraindication not documented for matched treatment",
        is_required=criterion.is_required,
    )


@register_evaluator(CriterionType.PRIOR_TREATMENT_DURATION)
def evaluate_prior_treatment_duration(criterion: AtomicCriterion, patient: NormalizedPatientData) -> CriterionEvaluation:
    if not patient.prior_treatments:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.INSUFFICIENT_DATA,
            reasoning="No prior treatment history available",
            is_required=criterion.is_required,
        )
    tx = _get_matched_treatment(criterion, patient)
    if not tx:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.NOT_MET,
            reasoning="No matching treatment found",
            is_required=criterion.is_required,
        )
    if tx.duration_weeks is None:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.INSUFFICIENT_DATA,
            reasoning=f"Duration not documented for {tx.medication_name}",
            is_required=criterion.is_required,
        )
    # Convert minimum_duration_days or threshold to weeks for comparison
    threshold_days = None
    if criterion.threshold_value:
        parsed = _safe_float(criterion.threshold_value)
        threshold_days = int(parsed) if parsed is not None else None
    min_days = criterion.minimum_duration_days or threshold_days
    if min_days is None:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.MET,
            evidence=[f"{tx.medication_name}: {tx.duration_weeks} weeks"],
            reasoning="No minimum duration specified; treatment documented",
            is_required=criterion.is_required,
        )
    # Convert days to weeks
    min_weeks = min_days / 7.0
    met = tx.duration_weeks >= min_weeks
    return CriterionEvaluation(
        criterion_id=criterion.criterion_id,
        criterion_name=criterion.name,
        verdict=CriterionVerdict.MET if met else CriterionVerdict.NOT_MET,
        evidence=[f"{tx.medication_name}: {tx.duration_weeks} weeks (required: {min_weeks:.0f} weeks)"],
        reasoning=f"Duration {tx.duration_weeks}w {'meets' if met else 'does not meet'} minimum {min_weeks:.0f}w",
        is_required=criterion.is_required,
    )


@register_evaluator(CriterionType.LAB_VALUE)
def evaluate_lab_value(criterion: AtomicCriterion, patient: NormalizedPatientData) -> CriterionEvaluation:
    if not patient.lab_results:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.INSUFFICIENT_DATA,
            reasoning="No lab results available",
            is_required=criterion.is_required,
        )
    # Find matching lab by name or LOINC code
    lab = _find_lab_result(criterion, patient)
    if not lab or lab.value is None:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.INSUFFICIENT_DATA,
            reasoning=f"Lab result '{criterion.name}' not found in patient data",
            is_required=criterion.is_required,
        )
    if criterion.threshold_value is None:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.MET,
            evidence=[f"{lab.test_name}: {lab.value} {lab.unit or ''}"],
            reasoning="Lab present; no threshold to compare",
            is_required=criterion.is_required,
        )
    threshold = _safe_float(criterion.threshold_value)
    if threshold is None:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.INSUFFICIENT_DATA,
            reasoning=f"Non-numeric threshold value: {criterion.threshold_value}",
            is_required=criterion.is_required,
        )
    met = _compare_numeric(lab.value, threshold, criterion.comparison_operator, criterion.threshold_value_upper)
    return CriterionEvaluation(
        criterion_id=criterion.criterion_id,
        criterion_name=criterion.name,
        verdict=CriterionVerdict.MET if met else CriterionVerdict.NOT_MET,
        evidence=[f"{lab.test_name}: {lab.value} {lab.unit or ''}"],
        reasoning=f"Lab {lab.test_name} = {lab.value} {'meets' if met else 'does not meet'} threshold {criterion.comparison_operator or 'gte'} {threshold}",
        is_required=criterion.is_required,
    )


@register_evaluator(CriterionType.LAB_TEST_COMPLETED)
def evaluate_lab_test_completed(criterion: AtomicCriterion, patient: NormalizedPatientData) -> CriterionEvaluation:
    if not patient.lab_results:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.INSUFFICIENT_DATA,
            reasoning="No lab results available",
            is_required=criterion.is_required,
        )
    lab = _find_lab_result(criterion, patient)
    met = lab is not None
    return CriterionEvaluation(
        criterion_id=criterion.criterion_id,
        criterion_name=criterion.name,
        verdict=CriterionVerdict.MET if met else CriterionVerdict.INSUFFICIENT_DATA,
        evidence=[f"Lab {lab.test_name} found" if lab else f"Lab '{criterion.name}' not found"],
        reasoning=f"Lab test {'completed' if met else 'not found'}",
        is_required=criterion.is_required,
    )


@register_evaluator(CriterionType.SAFETY_SCREENING_COMPLETED)
def evaluate_safety_screening_completed(criterion: AtomicCriterion, patient: NormalizedPatientData) -> CriterionEvaluation:
    if not patient.completed_screenings:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.INSUFFICIENT_DATA,
            reasoning="No screening data available",
            is_required=criterion.is_required,
        )
    screening = _find_screening(criterion, patient)
    if screening and screening.completed:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.MET,
            evidence=[f"Screening '{screening.screening_type}' completed"],
            reasoning=f"Safety screening {screening.screening_type} completed",
            is_required=criterion.is_required,
        )
    return CriterionEvaluation(
        criterion_id=criterion.criterion_id,
        criterion_name=criterion.name,
        verdict=CriterionVerdict.INSUFFICIENT_DATA if screening is None else CriterionVerdict.NOT_MET,
        reasoning=f"Screening {'not found' if screening is None else 'not completed'}",
        is_required=criterion.is_required,
    )


@register_evaluator(CriterionType.SAFETY_SCREENING_NEGATIVE)
def evaluate_safety_screening_negative(criterion: AtomicCriterion, patient: NormalizedPatientData) -> CriterionEvaluation:
    if not patient.completed_screenings:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.INSUFFICIENT_DATA,
            reasoning="No screening data available",
            is_required=criterion.is_required,
        )
    screening = _find_screening(criterion, patient)
    if screening and screening.completed and screening.result_negative:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.MET,
            evidence=[f"Screening '{screening.screening_type}' completed and negative"],
            reasoning=f"Safety screening {screening.screening_type} negative",
            is_required=criterion.is_required,
        )
    if screening and screening.completed and screening.result_negative is False:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.NOT_MET,
            evidence=[f"Screening '{screening.screening_type}' positive/not negative"],
            reasoning=f"Safety screening {screening.screening_type} not negative",
            is_required=criterion.is_required,
        )
    return CriterionEvaluation(
        criterion_id=criterion.criterion_id,
        criterion_name=criterion.name,
        verdict=CriterionVerdict.INSUFFICIENT_DATA,
        reasoning="Screening result not available",
        is_required=criterion.is_required,
    )


@register_evaluator(CriterionType.PRESCRIBER_SPECIALTY)
def evaluate_prescriber_specialty(criterion: AtomicCriterion, patient: NormalizedPatientData) -> CriterionEvaluation:
    if not patient.prescriber_specialty:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.INSUFFICIENT_DATA,
            reasoning="Prescriber specialty not available",
            is_required=criterion.is_required,
        )
    allowed = [v.lower() for v in criterion.allowed_values] if criterion.allowed_values else []
    # Also check against drug_names/description for specialty keywords
    desc_lower = criterion.description.lower()
    specialty_lower = patient.prescriber_specialty.lower()

    met = False
    if allowed:
        met = specialty_lower in allowed
    else:
        # Extract specialty from description
        for keyword in ["gastroenterolog", "rheumatolog", "dermatolog", "neurolog", "oncolog"]:
            if keyword in desc_lower and keyword in specialty_lower:
                met = True
                break
        # Also check criterion name
        criterion_name_lower = criterion.name.lower()
        if not met:
            for keyword in ["gastroenterolog", "rheumatolog", "dermatolog", "neurolog", "oncolog"]:
                if keyword in criterion_name_lower and keyword in specialty_lower:
                    met = True
                    break

    return CriterionEvaluation(
        criterion_id=criterion.criterion_id,
        criterion_name=criterion.name,
        verdict=CriterionVerdict.MET if met else CriterionVerdict.NOT_MET,
        evidence=[f"Prescriber specialty: {patient.prescriber_specialty}"],
        reasoning=f"Specialty '{patient.prescriber_specialty}' {'matches' if met else 'does not match'} requirement",
        is_required=criterion.is_required,
    )


@register_evaluator(CriterionType.PRESCRIBER_CONSULTATION)
def evaluate_prescriber_consultation(criterion: AtomicCriterion, patient: NormalizedPatientData) -> CriterionEvaluation:
    """Evaluate prescriber consultation / attestation criteria.

    Many prescriber_consultation criteria are attestation-type requirements
    (e.g., CRS monitoring agreement, neurological toxicity monitoring) that
    cannot be verified from patient chart data.  For these we return
    INSUFFICIENT_DATA so they surface as documentation gaps rather than
    false NOT_MET verdicts.

    For consultation criteria that reference a specific specialty we can still
    check the prescriber specialty on file.
    """
    name_lower = criterion.name.lower()
    desc_lower = (criterion.description or "").lower()
    combined = f"{name_lower} {desc_lower}"

    # Attestation-type criteria — cannot be verified from patient data
    attestation_keywords = [
        "monitoring agreement", "monitoring plan", "attestation",
        "rems", "crs monitor", "neurotox", "neuro_tox",
        "neurological toxicity monitor", "cytokine release monitor",
    ]
    if any(kw in combined for kw in attestation_keywords):
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.INSUFFICIENT_DATA,
            evidence=[],
            reasoning="Attestation/monitoring agreement — requires provider documentation; cannot be verified from patient chart data",
            is_required=criterion.is_required,
        )

    # For specialty-based consultation criteria, delegate to specialty check
    return evaluate_prescriber_specialty(criterion, patient)


@register_evaluator(CriterionType.CLINICAL_MARKER_PRESENT)
def evaluate_clinical_marker(criterion: AtomicCriterion, patient: NormalizedPatientData) -> CriterionEvaluation:
    """Evaluate clinical marker presence using biomarkers, functional scores, and clinical_markers."""
    name_lower = criterion.name.lower()
    desc_lower = criterion.description.lower()
    combined = name_lower + " " + desc_lower
    allowed = [v.lower() for v in criterion.allowed_values] if criterion.allowed_values else []

    # --- Biomarker checks (HR, HER2, ER, PR, BCMA, PIK3CA, Ki-67) ---
    biomarker_keywords = {
        "hormone receptor": ["HR", "ER"],
        "hr-positive": ["HR", "ER"],
        "hr positive": ["HR", "ER"],
        "estrogen receptor": ["ER"],
        "progesterone receptor": ["PR"],
        "her2": ["HER2"],
        "bcma": ["BCMA"],
        "pik3ca": ["PIK3CA"],
        "ki-67": ["Ki-67"],
        "ki67": ["Ki-67"],
    }
    for keyword, marker_names in biomarker_keywords.items():
        if keyword in combined:
            for marker_name in marker_names:
                for bm in patient.biomarkers:
                    if bm.biomarker_name.upper() == marker_name.upper():
                        # Check if allowed_values match the result
                        if allowed:
                            met = bm.result and bm.result.lower() in allowed
                        else:
                            # Infer from criterion name: "Negative" in name means positive=False
                            if "negative" in name_lower:
                                met = bm.positive is False or (bm.result and bm.result.lower() == "negative")
                            elif "positive" in name_lower:
                                met = bm.positive is True or (bm.result and bm.result.lower() == "positive")
                            else:
                                met = bm.result is not None
                        return CriterionEvaluation(
                            criterion_id=criterion.criterion_id,
                            criterion_name=criterion.name,
                            verdict=CriterionVerdict.MET if met else CriterionVerdict.NOT_MET,
                            evidence=[f"{bm.biomarker_name}: {bm.result}"],
                            reasoning=f"Biomarker {bm.biomarker_name}={bm.result} {'matches' if met else 'does not match'} criterion",
                            is_required=criterion.is_required,
                        )
            # Biomarker keyword matched but not found in patient data
            return CriterionEvaluation(
                criterion_id=criterion.criterion_id,
                criterion_name=criterion.name,
                verdict=CriterionVerdict.INSUFFICIENT_DATA,
                reasoning=f"Biomarker data for '{keyword}' not available",
                is_required=criterion.is_required,
            )

    # --- Organ function ---
    if "organ function" in combined or "organ and bone marrow" in combined:
        adequate = patient.clinical_markers.get("organ_function_adequate")
        if adequate is not None:
            return CriterionEvaluation(
                criterion_id=criterion.criterion_id,
                criterion_name=criterion.name,
                verdict=CriterionVerdict.MET if adequate else CriterionVerdict.NOT_MET,
                evidence=[f"Organ function adequate: {adequate}"],
                reasoning=f"Organ function {'adequate' if adequate else 'not adequate'}",
                is_required=criterion.is_required,
            )

    # --- Ventilator dependence ---
    if "ventilator" in combined:
        vent = patient.clinical_markers.get("ventilator_dependent")
        if vent is not None:
            # "No Permanent Ventilator Dependence" means NOT ventilator dependent = MET
            met = not vent
            return CriterionEvaluation(
                criterion_id=criterion.criterion_id,
                criterion_name=criterion.name,
                verdict=CriterionVerdict.MET if met else CriterionVerdict.NOT_MET,
                evidence=[f"Ventilator dependent: {vent}"],
                reasoning=f"Ventilator dependent={vent}, criterion {'met' if met else 'not met'}",
                is_required=criterion.is_required,
            )

    # --- Symptomatic / Asymptomatic status ---
    if "symptomatic" in combined or "asymptomatic" in combined:
        symptom_status = patient.clinical_markers.get("symptom_status")
        if symptom_status:
            if "asymptomatic" in name_lower:
                met = symptom_status == "asymptomatic"
            elif "symptomatic" in name_lower:
                met = symptom_status == "symptomatic"
            else:
                met = symptom_status is not None
            return CriterionEvaluation(
                criterion_id=criterion.criterion_id,
                criterion_name=criterion.name,
                verdict=CriterionVerdict.MET if met else CriterionVerdict.NOT_MET,
                evidence=[f"Symptom status: {symptom_status}"],
                reasoning=f"Symptom status '{symptom_status}' {'matches' if met else 'does not match'} criterion",
                is_required=criterion.is_required,
            )

    # --- Performance status (ECOG) ---
    if "performance status" in combined or "ecog" in combined:
        for fs in patient.functional_scores:
            if fs.score_type.upper() == "ECOG":
                ecog_val = _safe_float(fs.score_value)
                if ecog_val is not None and criterion.threshold_value is not None:
                    threshold = _safe_float(criterion.threshold_value)
                    op = criterion.comparison_operator or ComparisonOperator.LESS_THAN_OR_EQUAL
                    met = _compare_numeric(ecog_val, op, threshold) if threshold is not None else True
                else:
                    met = True  # score documented, no threshold to compare
                return CriterionEvaluation(
                    criterion_id=criterion.criterion_id,
                    criterion_name=criterion.name,
                    verdict=CriterionVerdict.MET if met else CriterionVerdict.NOT_MET,
                    evidence=[f"ECOG: {fs.score_value}"],
                    reasoning=f"ECOG performance status {fs.score_value}" + (f" vs threshold {criterion.threshold_value}" if criterion.threshold_value else ""),
                    is_required=criterion.is_required,
                )

    # --- Disease progression ---
    if "no disease progression" in combined or "no progression" in combined:
        disease_status = patient.clinical_markers.get("disease_status", "")
        if disease_status:
            has_progression = "progress" in disease_status.lower()
            met = not has_progression
            return CriterionEvaluation(
                criterion_id=criterion.criterion_id,
                criterion_name=criterion.name,
                verdict=CriterionVerdict.MET if met else CriterionVerdict.NOT_MET,
                evidence=[f"Disease status: {disease_status}"],
                reasoning=f"Disease status '{disease_status}' {'shows' if has_progression else 'does not show'} progression",
                is_required=criterion.is_required,
            )

    # --- Clinical improvement/stabilization (SMA renewal) ---
    if "clinical improvement" in combined or "stabilization" in combined:
        # Check functional scores for motor assessments and compare to baseline if available
        for fs in patient.functional_scores:
            if fs.score_type.upper() in ("CHOP-INTEND", "HFMSE", "HINE", "ULM", "MFM32", "RULM"):
                # Check for baseline comparison if available
                baseline = patient.clinical_markers.get("hfmse_prior") or patient.clinical_markers.get("baseline_motor_score")
                score_val = _safe_float(fs.score_value)
                if baseline is not None and score_val is not None:
                    baseline_val = _safe_float(baseline)
                    if baseline_val is not None:
                        improved_or_stable = score_val >= baseline_val
                        return CriterionEvaluation(
                            criterion_id=criterion.criterion_id,
                            criterion_name=criterion.name,
                            verdict=CriterionVerdict.MET if improved_or_stable else CriterionVerdict.NOT_MET,
                            evidence=[f"{fs.score_type}: {fs.score_value} (baseline: {baseline})"],
                            reasoning=f"Motor score {fs.score_value} vs baseline {baseline}: {'stable/improved' if improved_or_stable else 'declined'}",
                            is_required=criterion.is_required,
                        )
                # No baseline available — score documented counts as met
                return CriterionEvaluation(
                    criterion_id=criterion.criterion_id,
                    criterion_name=criterion.name,
                    verdict=CriterionVerdict.MET,
                    evidence=[f"{fs.score_type}: {fs.score_value}"],
                    reasoning=f"Motor assessment documented: {fs.score_type}={fs.score_value}",
                    is_required=criterion.is_required,
                )

    # --- Endocrine resistance ---
    if "endocrine" in combined and "resist" in combined:
        # Check if patient had endocrine therapy failure
        for tx in patient.prior_treatments:
            if tx.drug_class and "endocrine" in tx.drug_class.lower():
                if tx.outcome in ("failed", "inadequate_response", "partial_response"):
                    return CriterionEvaluation(
                        criterion_id=criterion.criterion_id,
                        criterion_name=criterion.name,
                        verdict=CriterionVerdict.MET,
                        evidence=[f"Failed endocrine therapy: {tx.medication_name}"],
                        reasoning=f"Endocrine resistance documented: {tx.medication_name} outcome={tx.outcome}",
                        is_required=criterion.is_required,
                    )

    # Fallback: INSUFFICIENT_DATA
    return CriterionEvaluation(
        criterion_id=criterion.criterion_id,
        criterion_name=criterion.name,
        verdict=CriterionVerdict.INSUFFICIENT_DATA,
        reasoning=f"Clinical marker '{criterion.name}' requires manual verification",
        is_required=criterion.is_required,
    )


@register_evaluator(CriterionType.DOCUMENTATION_PRESENT)
def evaluate_documentation(criterion: AtomicCriterion, patient: NormalizedPatientData) -> CriterionEvaluation:
    """Evaluate documentation presence using available patient data."""
    name_lower = criterion.name.lower()
    desc_lower = criterion.description.lower()
    combined = name_lower + " " + desc_lower

    # REMS facility enrollment
    if "rems" in combined:
        rems = patient.clinical_markers.get("rems_enrolled")
        if rems is not None:
            return CriterionEvaluation(
                criterion_id=criterion.criterion_id,
                criterion_name=criterion.name,
                verdict=CriterionVerdict.MET if rems else CriterionVerdict.NOT_MET,
                evidence=[f"REMS enrolled: {rems}"],
                reasoning=f"REMS enrollment {'confirmed' if rems else 'not confirmed'}",
                is_required=criterion.is_required,
            )

    # Baseline motor milestone score
    if "motor milestone" in combined or "motor assessment" in combined:
        allowed_scores = [v.upper() for v in criterion.allowed_values] if criterion.allowed_values else []
        for fs in patient.functional_scores:
            if fs.score_type.upper() in allowed_scores or fs.score_type.upper() in (
                "CHOP-INTEND", "HFMSE", "HINE", "ULM", "MFM32", "RULM",
            ):
                return CriterionEvaluation(
                    criterion_id=criterion.criterion_id,
                    criterion_name=criterion.name,
                    verdict=CriterionVerdict.MET,
                    evidence=[f"Motor score documented: {fs.score_type}={fs.score_value}"],
                    reasoning=f"Baseline motor score available: {fs.score_type}",
                    is_required=criterion.is_required,
                )

    # Generic documentation check — can't deterministically verify
    return CriterionEvaluation(
        criterion_id=criterion.criterion_id,
        criterion_name=criterion.name,
        verdict=CriterionVerdict.INSUFFICIENT_DATA,
        reasoning="Documentation presence requires manual verification",
        is_required=criterion.is_required,
    )


@register_evaluator(CriterionType.DISEASE_DURATION)
def evaluate_disease_duration(criterion: AtomicCriterion, patient: NormalizedPatientData) -> CriterionEvaluation:
    # Disease duration typically not in structured patient data
    return CriterionEvaluation(
        criterion_id=criterion.criterion_id,
        criterion_name=criterion.name,
        verdict=CriterionVerdict.INSUFFICIENT_DATA,
        reasoning="Disease duration requires clinical notes review",
        is_required=criterion.is_required,
    )


@register_evaluator(CriterionType.NO_CONCURRENT_THERAPY)
def evaluate_no_concurrent_therapy(criterion: AtomicCriterion, patient: NormalizedPatientData) -> CriterionEvaluation:
    """Evaluate that patient is NOT on a specific therapy.

    Checks:
    1. criterion.drug_names against prior_treatments and clinical_markers
    2. Keyword matching for gene therapy, risdiplam, clinical trials
    """
    name_lower = criterion.name.lower()
    desc_lower = criterion.description.lower()
    combined = name_lower + " " + desc_lower
    markers = patient.clinical_markers

    # --- No prior gene therapy ---
    if "gene therapy" in combined:
        # Check clinical_markers flag
        prior_gt = markers.get("prior_gene_therapy")
        prior_cart = markers.get("prior_car_t_therapy")
        if prior_gt is not None or prior_cart is not None:
            has_gene_therapy = bool(prior_gt) or bool(prior_cart)
            # Also check if any specific drug was received
            if criterion.drug_names:
                drug_names_lower = {d.lower() for d in criterion.drug_names}
                for tx in patient.prior_treatments:
                    if tx.medication_name.lower() in drug_names_lower:
                        has_gene_therapy = True
                        break
                    for dn in drug_names_lower:
                        if dn in tx.medication_name.lower() or tx.medication_name.lower() in dn:
                            has_gene_therapy = True
                            break
            met = not has_gene_therapy
            return CriterionEvaluation(
                criterion_id=criterion.criterion_id,
                criterion_name=criterion.name,
                verdict=CriterionVerdict.MET if met else CriterionVerdict.NOT_MET,
                evidence=[f"Prior gene therapy: {has_gene_therapy}"],
                reasoning=f"Gene therapy {'not received' if met else 'previously received'}",
                is_required=criterion.is_required,
            )

    # --- No concurrent risdiplam ---
    if "risdiplam" in combined:
        concurrent = markers.get("concurrent_risdiplam")
        if concurrent is not None:
            met = not concurrent
            return CriterionEvaluation(
                criterion_id=criterion.criterion_id,
                criterion_name=criterion.name,
                verdict=CriterionVerdict.MET if met else CriterionVerdict.NOT_MET,
                evidence=[f"Concurrent risdiplam: {concurrent}"],
                reasoning=f"Risdiplam {'not being used' if met else 'currently in use'}",
                is_required=criterion.is_required,
            )

    # --- No clinical trial enrollment ---
    if "clinical trial" in combined:
        enrolled = markers.get("clinical_trial_enrollment")
        if enrolled is not None:
            met = not enrolled
            return CriterionEvaluation(
                criterion_id=criterion.criterion_id,
                criterion_name=criterion.name,
                verdict=CriterionVerdict.MET if met else CriterionVerdict.NOT_MET,
                evidence=[f"Clinical trial enrollment: {enrolled}"],
                reasoning=f"Clinical trial {'not enrolled' if met else 'currently enrolled'}",
                is_required=criterion.is_required,
            )

    # --- Generic drug name exclusion check ---
    if criterion.drug_names:
        drug_names_lower = {d.lower() for d in criterion.drug_names}
        for tx in patient.prior_treatments:
            tx_name_lower = tx.medication_name.lower()
            # Skip treatments with clearly-ended outcomes (completed/failed/discontinued)
            if tx.outcome in ("failed", "completed", "inadequate_response", "intolerant", "discontinued_adverse_effects"):
                continue
            for dn in drug_names_lower:
                if dn in tx_name_lower or tx_name_lower in dn:
                    return CriterionEvaluation(
                        criterion_id=criterion.criterion_id,
                        criterion_name=criterion.name,
                        verdict=CriterionVerdict.NOT_MET,
                        evidence=[f"Patient on excluded therapy: {tx.medication_name}"],
                        reasoning=f"Excluded therapy {tx.medication_name} found (outcome: {tx.outcome or 'unknown'})",
                        is_required=criterion.is_required,
                    )
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.MET,
            evidence=[f"No excluded therapies found in current treatment"],
            reasoning="None of the excluded drugs found in active/ongoing treatment",
            is_required=criterion.is_required,
        )

    return CriterionEvaluation(
        criterion_id=criterion.criterion_id,
        criterion_name=criterion.name,
        verdict=CriterionVerdict.INSUFFICIENT_DATA,
        reasoning="Concurrent therapy status requires clinical review",
        is_required=criterion.is_required,
    )


@register_evaluator(CriterionType.CONCURRENT_THERAPY)
def evaluate_concurrent_therapy(criterion: AtomicCriterion, patient: NormalizedPatientData) -> CriterionEvaluation:
    """Evaluate that patient IS on a specific concurrent therapy.

    Used for requirements like 'must be on combination therapy with X'.
    """
    name_lower = criterion.name.lower()
    desc_lower = criterion.description.lower()
    combined = name_lower + " " + desc_lower
    markers = patient.clinical_markers

    # --- Male testicular suppression ---
    if "testicular" in combined or "steroidogenesis" in combined:
        # For female patients, this criterion is not applicable
        if patient.gender and patient.gender.lower() == "female":
            return CriterionEvaluation(
                criterion_id=criterion.criterion_id,
                criterion_name=criterion.name,
                verdict=CriterionVerdict.NOT_APPLICABLE,
                evidence=["Patient is female — male suppression not applicable"],
                reasoning="Male testicular suppression not applicable to female patients",
                is_required=criterion.is_required,
            )
        # For male patients, check marker
        suppression = markers.get("male_testicular_suppression")
        if suppression is not None:
            return CriterionEvaluation(
                criterion_id=criterion.criterion_id,
                criterion_name=criterion.name,
                verdict=CriterionVerdict.MET if suppression else CriterionVerdict.NOT_MET,
                evidence=[f"Male testicular suppression: {suppression}"],
                reasoning=f"Testicular suppression {'confirmed' if suppression else 'not confirmed'}",
                is_required=criterion.is_required,
            )

    # --- Combination therapy (aromatase inhibitor or fulvestrant) ---
    if "combination" in combined or "aromatase" in combined or "fulvestrant" in combined:
        # Check prior treatments for combination agents — only match if drug/class matches
        combo_keywords = ["aromatase", "fulvestrant", "letrozole", "anastrozole", "exemestane", "inavolisib"]
        for tx in patient.prior_treatments:
            tx_lower = tx.medication_name.lower()
            tx_class = (tx.drug_class or "").lower()
            for kw in combo_keywords:
                if kw in tx_lower or kw in tx_class:
                    return CriterionEvaluation(
                        criterion_id=criterion.criterion_id,
                        criterion_name=criterion.name,
                        verdict=CriterionVerdict.MET,
                        evidence=[f"Combination therapy with {tx.medication_name}"],
                        reasoning=f"Patient receiving combination therapy with {tx.medication_name}",
                        is_required=criterion.is_required,
                    )

    return CriterionEvaluation(
        criterion_id=criterion.criterion_id,
        criterion_name=criterion.name,
        verdict=CriterionVerdict.INSUFFICIENT_DATA,
        reasoning="Concurrent therapy status requires clinical review",
        is_required=criterion.is_required,
    )


@register_evaluator(CriterionType.CUSTOM)
def evaluate_custom(criterion: AtomicCriterion, patient: NormalizedPatientData) -> CriterionEvaluation:
    return CriterionEvaluation(
        criterion_id=criterion.criterion_id,
        criterion_name=criterion.name,
        verdict=CriterionVerdict.INSUFFICIENT_DATA,
        reasoning="Custom criterion requires manual evaluation",
        is_required=criterion.is_required,
    )


# --- Helper functions ---

def _safe_float(value) -> Optional[float]:
    """Safely convert a value to float, returning None on failure."""
    import math
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return None
        return result
    except (ValueError, TypeError):
        return None


def _compare_numeric(
    value: float,
    threshold: float,
    operator: Optional[ComparisonOperator],
    upper_bound: Optional[float] = None,
) -> bool:
    """Compare a numeric value against a threshold using the specified operator."""
    if operator is None or operator == ComparisonOperator.GREATER_THAN_OR_EQUAL:
        return value >= threshold
    elif operator == ComparisonOperator.GREATER_THAN:
        return value > threshold
    elif operator == ComparisonOperator.LESS_THAN:
        return value < threshold
    elif operator == ComparisonOperator.LESS_THAN_OR_EQUAL:
        return value <= threshold
    elif operator == ComparisonOperator.EQUALS:
        return abs(value - threshold) < 1e-9
    elif operator == ComparisonOperator.NOT_EQUALS:
        return abs(value - threshold) >= 1e-9
    elif operator == ComparisonOperator.BETWEEN:
        if upper_bound is None:
            return value >= threshold  # No upper bound, degrade to GTE
        upper = _safe_float(upper_bound)
        if upper is None:
            return value >= threshold  # Unparseable upper bound, degrade to GTE
        return threshold <= value <= upper
    elif operator == ComparisonOperator.IN:
        # IN: check if value equals any of: threshold, upper_bound
        targets = [threshold]
        if upper_bound is not None:
            parsed = _safe_float(upper_bound)
            if parsed is not None:
                targets.append(parsed)
        return value in targets
    elif operator == ComparisonOperator.NOT_IN:
        targets = [threshold]
        if upper_bound is not None:
            parsed = _safe_float(upper_bound)
            if parsed is not None:
                targets.append(parsed)
        return value not in targets
    return value >= threshold  # Default to gte


def _find_treatment_match(criterion: AtomicCriterion, patient: NormalizedPatientData) -> bool:
    """Check if any patient treatment matches criterion's drug requirements."""
    return _get_matched_treatment(criterion, patient) is not None


def _get_matched_treatment(criterion: AtomicCriterion, patient: NormalizedPatientData):
    """Find the first matching treatment from patient history.

    Matching priority:
    1. Exact drug name match against criterion.drug_names
    2. Exact drug class match against criterion.drug_classes
    3. Substring match in criterion description/name (min 4 chars to avoid false positives)
    """
    drug_names_lower = {d.lower() for d in criterion.drug_names}
    drug_classes_lower = {d.lower() for d in criterion.drug_classes}
    desc_lower = criterion.description.lower()
    name_lower = criterion.name.lower()

    for tx in patient.prior_treatments:
        tx_name_lower = tx.medication_name.lower()
        tx_class_lower = (tx.drug_class or "").lower()

        # Match by drug name (exact)
        if tx_name_lower in drug_names_lower:
            return tx
        # Check if any criterion drug name contains or is contained by treatment name
        for dn in drug_names_lower:
            if dn in tx_name_lower or tx_name_lower in dn:
                return tx
        # Match by drug class (exact)
        if tx_class_lower and tx_class_lower in drug_classes_lower:
            return tx
        # Substring match in description/name — require minimum 4 chars to avoid false positives
        if len(tx_name_lower) >= 4 and (tx_name_lower in desc_lower or tx_name_lower in name_lower):
            return tx
        # Match drug class words in description — require minimum 4 chars per keyword
        if tx_class_lower:
            for keyword in tx_class_lower.split():
                if len(keyword) >= 4 and keyword in desc_lower:
                    return tx
    return None


def _find_lab_result(criterion: AtomicCriterion, patient: NormalizedPatientData):
    """Find a matching lab result by test name or LOINC code."""
    # Check LOINC codes first (most precise)
    criterion_loinc = {c.code for c in criterion.clinical_codes if c.system == "LOINC"}
    for lab in patient.lab_results:
        if lab.loinc_code and lab.loinc_code in criterion_loinc:
            return lab

    # Then check by name
    name_lower = criterion.name.lower()
    desc_lower = criterion.description.lower()
    # Meaningful keywords (skip common noise words)
    noise_words = {"test", "level", "value", "result", "lab", "blood", "serum", "plasma", "the", "and", "for", "with"}
    for lab in patient.lab_results:
        lab_name_lower = lab.test_name.lower()
        # Exact match (handles short names like CRP, ESR, TSH)
        if lab_name_lower == name_lower:
            return lab
        # Direct name containment (if test name is specific enough — min 4 chars to avoid false positives)
        if len(lab_name_lower) >= 4 and (lab_name_lower in name_lower or lab_name_lower in desc_lower):
            return lab
        if len(name_lower) >= 4 and name_lower in lab_name_lower:
            return lab
        # Short lab names (< 4 chars like CRP, ESR) — check exact word boundary match
        if len(lab_name_lower) < 4 and lab_name_lower.isalpha():
            if lab_name_lower in name_lower.split() or lab_name_lower in desc_lower.split():
                return lab
        # Keyword matching — require at least one meaningful keyword match
        criterion_keywords = {kw for kw in name_lower.split() if len(kw) >= 4 and kw not in noise_words}
        if criterion_keywords:
            lab_tokens = set(lab_name_lower.split())
            if criterion_keywords & lab_tokens:
                return lab
    return None


def _find_screening(criterion: AtomicCriterion, patient: NormalizedPatientData):
    """Find a matching screening by type keywords."""
    name_lower = criterion.name.lower()
    desc_lower = criterion.description.lower()
    combined = name_lower + " " + desc_lower

    for screening in patient.completed_screenings:
        st_lower = screening.screening_type.lower()
        if st_lower in combined:
            return screening
        # Common mappings
        if "tb" in combined and st_lower == "tb":
            return screening
        if "tuberculosis" in combined and st_lower == "tb":
            return screening
        if "hepatitis b" in combined and st_lower == "hepatitis_b":
            return screening
        if "hepatitis c" in combined and st_lower == "hepatitis_c":
            return screening
        if "hep b" in combined and st_lower == "hepatitis_b":
            return screening
        if "hep c" in combined and st_lower == "hepatitis_c":
            return screening
    return None


# --- Group and Policy evaluation ---

def evaluate_group(
    group: CriterionGroup,
    policy: DigitizedPolicy,
    patient: NormalizedPatientData,
    _visited: Optional[set] = None,
) -> GroupEvaluation:
    """Evaluate a criterion group recursively with cycle detection."""
    if _visited is None:
        _visited = set()
    if group.group_id in _visited:
        return GroupEvaluation(
            group_id=group.group_id,
            operator=group.operator.value if isinstance(group.operator, LogicalOperator) else str(group.operator),
            verdict=CriterionVerdict.INSUFFICIENT_DATA,
            reasoning="Circular group reference detected",
        )
    _visited.add(group.group_id)

    criteria_results = []
    for cid in group.criteria:
        criterion = policy.get_criterion(cid)
        if criterion:
            criteria_results.append(evaluate_criterion(criterion, patient))

    subgroup_results = []
    for sg_id in group.subgroups:
        sg = policy.get_group(sg_id)
        if sg:
            subgroup_results.append(evaluate_group(sg, policy, patient, _visited))

    # Allow diamond-pattern DAGs: discard after evaluation so other paths can visit this group
    _visited.discard(group.group_id)

    # Combine verdicts based on operator
    all_verdicts = [r.verdict for r in criteria_results] + [r.verdict for r in subgroup_results]
    verdict = _combine_verdicts(all_verdicts, group.operator, group.negated)

    return GroupEvaluation(
        group_id=group.group_id,
        operator=group.operator.value if isinstance(group.operator, LogicalOperator) else str(group.operator),
        verdict=verdict,
        criteria_results=criteria_results,
        subgroup_results=subgroup_results,
    )


def _combine_verdicts(
    verdicts: List[CriterionVerdict],
    operator: LogicalOperator,
    negated: bool = False,
) -> CriterionVerdict:
    """Combine verdicts using logical operator."""
    if not verdicts:
        return CriterionVerdict.NOT_APPLICABLE

    # NOT_APPLICABLE should be transparent to logical operators
    effective = [v for v in verdicts if v != CriterionVerdict.NOT_APPLICABLE]
    if not effective:
        return CriterionVerdict.NOT_APPLICABLE

    op = operator.value if isinstance(operator, LogicalOperator) else str(operator).upper()

    if op == "AND":
        if all(v == CriterionVerdict.MET for v in effective):
            result = CriterionVerdict.MET
        elif any(v == CriterionVerdict.NOT_MET for v in effective):
            result = CriterionVerdict.NOT_MET
        else:
            result = CriterionVerdict.INSUFFICIENT_DATA
    elif op == "OR":
        if any(v == CriterionVerdict.MET for v in effective):
            result = CriterionVerdict.MET
        elif all(v == CriterionVerdict.NOT_MET for v in effective):
            result = CriterionVerdict.NOT_MET
        else:
            result = CriterionVerdict.INSUFFICIENT_DATA
    elif op == "NOT":
        child = verdicts[0] if verdicts else CriterionVerdict.NOT_APPLICABLE
        if child == CriterionVerdict.MET:
            result = CriterionVerdict.NOT_MET
        elif child == CriterionVerdict.NOT_MET:
            result = CriterionVerdict.MET
        else:
            result = child
    else:
        result = CriterionVerdict.INSUFFICIENT_DATA

    if negated:
        if result == CriterionVerdict.MET:
            result = CriterionVerdict.NOT_MET
        elif result == CriterionVerdict.NOT_MET:
            result = CriterionVerdict.MET

    return result


def evaluate_criterion(criterion: AtomicCriterion, patient: NormalizedPatientData) -> CriterionEvaluation:
    """Evaluate a single criterion using the registry."""
    evaluator = EVALUATOR_REGISTRY.get(criterion.criterion_type)
    if evaluator is None:
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.INSUFFICIENT_DATA,
            reasoning=f"No evaluator registered for type '{criterion.criterion_type}'",
            is_required=criterion.is_required,
        )
    try:
        return evaluator(criterion, patient)
    except Exception as exc:
        logger.warning(
            "Criterion evaluation failed",
            criterion_id=criterion.criterion_id,
            error=str(exc),
        )
        return CriterionEvaluation(
            criterion_id=criterion.criterion_id,
            criterion_name=criterion.name,
            verdict=CriterionVerdict.INSUFFICIENT_DATA,
            reasoning=f"Evaluation error: {type(exc).__name__}",
            is_required=criterion.is_required,
        )


def evaluate_step_therapy(
    policy: DigitizedPolicy,
    patient: NormalizedPatientData,
) -> Dict:
    """Evaluate step therapy requirements."""
    if not policy.step_therapy_requirements:
        return {"required": False, "satisfied": True, "details": []}

    results = []
    all_satisfied = True
    for req in policy.step_therapy_requirements:
        # Check how many required drugs/classes have been tried and failed
        drugs_tried = 0
        drugs_failed = 0
        drug_details = []

        required_items = req.required_drugs + req.required_drug_classes

        for item in required_items:
            item_lower = item.lower()
            item_matched = False
            for tx in patient.prior_treatments:
                if item_matched:
                    break
                tx_name_lower = tx.medication_name.lower()
                tx_class_lower = (tx.drug_class or "").lower()
                if item_lower in tx_name_lower or item_lower in tx_class_lower:
                    drugs_tried += 1
                    item_matched = True
                    if tx.outcome in ("failed", "inadequate_response", "partial_response", "steroid_dependent"):
                        drugs_failed += 1
                        drug_details.append({
                            "drug": tx.medication_name,
                            "outcome": tx.outcome,
                            "duration_weeks": tx.duration_weeks,
                            "adequate_trial": tx.adequate_trial,
                        })
                    elif tx.outcome in ("intolerant",) and req.intolerance_acceptable:
                        drugs_failed += 1
                        drug_details.append({
                            "drug": tx.medication_name,
                            "outcome": tx.outcome,
                            "acceptable": True,
                        })
                    elif tx.outcome in ("contraindicated",) and req.contraindication_acceptable:
                        drugs_failed += 1
                        drug_details.append({
                            "drug": tx.medication_name,
                            "outcome": tx.outcome,
                            "acceptable": True,
                        })

        satisfied = drugs_failed >= req.minimum_trials
        if not satisfied:
            all_satisfied = False

        results.append({
            "requirement_id": req.requirement_id,
            "indication": req.indication,
            "minimum_trials": req.minimum_trials,
            "drugs_tried": drugs_tried,
            "drugs_failed": drugs_failed,
            "satisfied": satisfied,
            "details": drug_details,
        })

    return {
        "required": True,
        "satisfied": all_satisfied,
        "details": results,
    }


def evaluate_policy(
    policy: DigitizedPolicy,
    patient: NormalizedPatientData,
) -> PolicyEvaluationResult:
    """
    Evaluate a patient against a digitized policy.

    Returns a PolicyEvaluationResult with per-criterion verdicts,
    group evaluations, indication assessments, and gap analysis.
    """
    indication_evaluations = []

    # If the policy has defined indications, use them
    indications_to_eval = list(policy.indications)

    # If no indications defined, synthesize one from root approval groups
    if not indications_to_eval:
        from backend.models.policy_schema import IndicationCriteria
        root_group_id = _find_root_approval_group(policy)
        if root_group_id:
            indications_to_eval.append(IndicationCriteria(
                indication_id="AUTO_INITIAL",
                indication_name=f"{policy.medication_name} - Initial Approval",
                initial_approval_criteria=root_group_id,
                initial_approval_duration_months=12,
            ))

    for indication in indications_to_eval:
        # Evaluate the root criteria group
        root_group_id = indication.initial_approval_criteria
        root_group = policy.get_group(root_group_id)

        group_result = None
        if root_group:
            group_result = evaluate_group(root_group, policy, patient)

        # Collect all criteria evaluations for this indication
        all_criteria = _collect_all_criteria_evals(group_result) if group_result else []
        met_count = sum(1 for c in all_criteria if c.verdict == CriterionVerdict.MET)
        total_count = len(all_criteria)
        unmet = [c for c in all_criteria if c.verdict == CriterionVerdict.NOT_MET]
        insufficient = [c for c in all_criteria if c.verdict == CriterionVerdict.INSUFFICIENT_DATA]

        overall = group_result.verdict if group_result else CriterionVerdict.INSUFFICIENT_DATA

        indication_evaluations.append(IndicationEvaluation(
            indication_id=indication.indication_id,
            indication_name=indication.indication_name,
            overall_verdict=overall,
            approval_criteria_result=group_result,
            criteria_met_count=met_count,
            criteria_total_count=total_count,
            unmet_criteria=unmet,
            insufficient_criteria=insufficient,
        ))

    # Evaluate exclusions
    exclusion_evaluations = []
    for excl in policy.exclusions:
        for trigger_id in excl.trigger_criteria:
            criterion = policy.get_criterion(trigger_id)
            if criterion:
                eval_result = evaluate_criterion(criterion, patient)
                exclusion_evaluations.append(eval_result)

    # Evaluate step therapy
    step_therapy_result = evaluate_step_therapy(policy, patient)

    # Calculate overall readiness
    all_evals = []
    for ie in indication_evaluations:
        all_evals.extend(_collect_all_criteria_evals(ie.approval_criteria_result))

    total = len(all_evals)
    met = sum(1 for e in all_evals if e.verdict == CriterionVerdict.MET)
    overall_readiness = met / total if total > 0 else 0.0

    # Determine overall verdict
    if indication_evaluations:
        # Find best matching indication
        best_verdict = CriterionVerdict.NOT_MET
        has_real_evaluation = False
        for ie in indication_evaluations:
            if ie.overall_verdict == CriterionVerdict.MET:
                best_verdict = CriterionVerdict.MET
                has_real_evaluation = True
                break
            elif ie.overall_verdict == CriterionVerdict.INSUFFICIENT_DATA:
                best_verdict = CriterionVerdict.INSUFFICIENT_DATA
                has_real_evaluation = True
            elif ie.overall_verdict == CriterionVerdict.NOT_MET:
                has_real_evaluation = True
        if not has_real_evaluation:
            best_verdict = CriterionVerdict.NOT_APPLICABLE
        overall_verdict = best_verdict
    else:
        overall_verdict = CriterionVerdict.INSUFFICIENT_DATA

    # Build gaps
    gaps = []
    for ie in indication_evaluations:
        for ic in ie.insufficient_criteria:
            gaps.append({
                "criterion_id": ic.criterion_id,
                "criterion_name": ic.criterion_name,
                "indication": ie.indication_name,
                "gap_type": "insufficient_data",
                "action": f"Obtain documentation for: {ic.criterion_name}",
            })
        for uc in ie.unmet_criteria:
            if uc.is_required:
                gaps.append({
                    "criterion_id": uc.criterion_id,
                    "criterion_name": uc.criterion_name,
                    "indication": ie.indication_name,
                    "gap_type": "not_met",
                    "action": f"Address unmet criterion: {uc.criterion_name}",
                })

    # Note: Exclusion and step therapy evaluations are reported in the result
    # but do NOT override the overall verdict. The digitized policy exclusion
    # trigger criteria have ambiguous semantics (positive-check criteria like
    # "NO_ACTIVE_INFECTION" evaluating to MET means patient is CLEAR, not excluded).
    # Step therapy matching may also miss valid treatments due to name matching
    # limitations. Both are surfaced in gaps for human review instead.
    if step_therapy_result and not step_therapy_result.get("satisfied", True):
        gaps.append({
            "criterion_id": "STEP_THERAPY",
            "criterion_name": "Step Therapy Requirements",
            "indication": "step_therapy",
            "gap_type": "step_therapy_review",
            "action": "Review step therapy: " + step_therapy_result.get("reason", "requirements may not be fully satisfied"),
        })

    return PolicyEvaluationResult(
        policy_id=policy.policy_id,
        patient_id=patient.patient_id or "unknown",
        indication_evaluations=indication_evaluations,
        exclusion_evaluations=exclusion_evaluations,
        step_therapy_evaluation=step_therapy_result,
        overall_readiness=round(overall_readiness, 3),
        overall_verdict=overall_verdict,
        gaps=gaps,
    )


def _find_root_approval_group(policy: DigitizedPolicy) -> Optional[str]:
    """Find the root initial approval group in a policy that has no indications.

    Looks for groups named like 'INITIAL_APPROVAL', 'INITIAL_APPROVAL_GROUP', etc.
    """
    approval_keywords = ["initial_approval", "approval_group", "root"]
    for gid, group in policy.criterion_groups.items():
        gid_lower = gid.lower()
        for kw in approval_keywords:
            if kw in gid_lower:
                return gid
    # Fallback: return the group with the most criteria/subgroups
    if policy.criterion_groups:
        best_gid = max(
            policy.criterion_groups,
            key=lambda gid: len(policy.criterion_groups[gid].criteria) + len(policy.criterion_groups[gid].subgroups),
        )
        return best_gid
    return None


def _collect_all_criteria_evals(group_result: Optional[GroupEvaluation]) -> List[CriterionEvaluation]:
    """Recursively collect all CriterionEvaluation from a group result."""
    if group_result is None:
        return []
    results = list(group_result.criteria_results)
    for sg in group_result.subgroup_results:
        results.extend(_collect_all_criteria_evals(sg))
    return results
