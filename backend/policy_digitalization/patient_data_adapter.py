"""Patient Data Adapter - Normalizes raw patient JSON for deterministic evaluation.

Converts raw patient data (like data/patients/david_c.json) into a flat,
evaluator-friendly NormalizedPatientData structure.
"""

from datetime import date, datetime
from typing import Dict, Any, List, Optional

from pydantic import BaseModel, Field


class NormalizedTreatment(BaseModel):
    """Normalized prior treatment record."""
    medication_name: str
    drug_class: Optional[str] = None
    duration_weeks: Optional[int] = None
    outcome: Optional[str] = None  # failed, intolerant, contraindicated, partial_response, inadequate_response, steroid_dependent
    adequate_trial: bool = False

class NormalizedLabResult(BaseModel):
    """Normalized lab result."""
    test_name: str
    loinc_code: Optional[str] = None
    value: Optional[float] = None
    unit: Optional[str] = None
    date: Optional[str] = None
    flag: Optional[str] = None  # H, L, null

class NormalizedScreening(BaseModel):
    """Normalized safety screening."""
    screening_type: str   # tb, hepatitis_b, hepatitis_c
    completed: bool
    result_negative: Optional[bool] = None
    date: Optional[str] = None

class NormalizedBiomarker(BaseModel):
    """Normalized biomarker result (cross-therapeutic)."""
    biomarker_name: str
    result: Optional[str] = None
    value: Optional[float] = None
    unit: Optional[str] = None
    positive: Optional[bool] = None

class NormalizedFunctionalScore(BaseModel):
    """Normalized functional/performance score."""
    score_type: str  # CDAI, ECOG, NYHA, EDSS, etc.
    score_value: Optional[float] = None
    interpretation: Optional[str] = None

class NormalizedImagingResult(BaseModel):
    """Normalized imaging result."""
    modality: str  # colonoscopy, MRI, CT, PET
    date: Optional[str] = None
    findings_summary: Optional[str] = None
    score_type: Optional[str] = None
    score_value: Optional[float] = None

class NormalizedGeneticTest(BaseModel):
    """Normalized genetic test result."""
    test_name: str
    gene: Optional[str] = None
    result: Optional[str] = None
    pathogenic: Optional[bool] = None

class NormalizedPatientData(BaseModel):
    """Flat, evaluator-friendly patient data."""
    patient_id: Optional[str] = None

    # Demographics
    age_years: Optional[int] = None
    gender: Optional[str] = None

    # Diagnosis
    diagnosis_codes: List[str] = Field(default_factory=list)
    disease_severity: Optional[str] = None

    # Treatment history
    prior_treatments: List[NormalizedTreatment] = Field(default_factory=list)

    # Lab results
    lab_results: List[NormalizedLabResult] = Field(default_factory=list)

    # Safety screenings
    completed_screenings: List[NormalizedScreening] = Field(default_factory=list)

    # Prescriber
    prescriber_specialty: Optional[str] = None
    prescriber_npi: Optional[str] = None

    # Cross-therapeutic extensions
    biomarkers: List[NormalizedBiomarker] = Field(default_factory=list)
    functional_scores: List[NormalizedFunctionalScore] = Field(default_factory=list)
    staging: Optional[Dict[str, Any]] = None
    imaging_results: List[NormalizedImagingResult] = Field(default_factory=list)
    genetic_tests: List[NormalizedGeneticTest] = Field(default_factory=list)
    program_enrollments: List[str] = Field(default_factory=list)
    site_of_care: Optional[str] = None
    insurance_formulary_tier: Optional[int] = None

    # Clinical markers — generic key-value store for evaluator lookups
    # Keys use lowercase snake_case. Examples:
    #   organ_function_adequate, ventilator_dependent, symptomatic,
    #   rems_enrolled, prior_gene_therapy, clinical_trial_enrollment,
    #   concurrent_risdiplam, disease_status, lines_of_therapy
    clinical_markers: Dict[str, Any] = Field(default_factory=dict)


def _calculate_age(dob_str: str) -> Optional[int]:
    """Calculate age from date of birth string."""
    try:
        dob = date.fromisoformat(dob_str)
        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        return age
    except (ValueError, TypeError):
        return None


def _normalize_outcome(raw_outcome: str) -> str:
    """Normalize treatment outcome to standard vocabulary.

    Preserves granular outcome types (inadequate_response, partial_response,
    steroid_dependent) since the evaluator checks for these explicitly.
    Normalizes oncology/neurology outcomes to evaluator-friendly values.
    """
    outcome_map = {
        "failed": "failed",
        "failure": "failed",
        "inadequate_response": "inadequate_response",
        "inadequate response": "inadequate_response",
        "partial_response": "partial_response",
        "partial response": "partial_response",
        "intolerant": "intolerant",
        "intolerance": "intolerant",
        "contraindicated": "contraindicated",
        "contraindication": "contraindicated",
        "steroid_dependent": "steroid_dependent",
        "steroid-dependent": "steroid_dependent",
        "steroid dependent": "steroid_dependent",
        # Oncology outcomes — map to evaluator's "failed" vocabulary
        "progressive_disease": "failed",
        "progressive_disease_on_therapy": "failed",
        "progressed": "failed",
        "complete_response_then_relapsed": "failed",
        "partial_response_then_relapsed": "failed",
        "partial_response_then_progressed": "failed",
        "minimal_response_then_progressed": "failed",
        "sustained_partial_response": "partial_response",
        "very_good_partial_response": "partial_response",
        "initial_improvement_then_decline": "failed",
        "failed_inadequate_response": "inadequate_response",
        # Intolerance variants
        "discontinued_adverse_effects": "intolerant",
    }
    normalized = (raw_outcome or "").lower().strip()
    return outcome_map.get(normalized, normalized)


def _calculate_duration_weeks(start_date_str: Optional[str], end_date_str: Optional[str]) -> Optional[int]:
    """Calculate duration in weeks from start and end date strings."""
    if not start_date_str or not end_date_str:
        return None
    try:
        start = date.fromisoformat(start_date_str)
        end = date.fromisoformat(end_date_str)
        delta = (end - start).days
        return max(1, delta // 7) if delta > 0 else None
    except (ValueError, TypeError):
        return None


def normalize_patient_data(raw: Dict[str, Any]) -> NormalizedPatientData:
    """
    Normalize raw patient JSON into evaluator-friendly format.

    Handles the structure from data/patients/*.json files across all
    therapeutic areas (GI, oncology, hematology, neurology).
    """
    result = NormalizedPatientData()

    result.patient_id = raw.get("patient_id")

    # Demographics
    demographics = raw.get("demographics", {})
    if demographics.get("date_of_birth"):
        result.age_years = _calculate_age(demographics["date_of_birth"])
    elif demographics.get("age"):
        result.age_years = demographics["age"]
    result.gender = (demographics.get("gender") or "").lower() or None

    # Diagnoses
    for dx in raw.get("diagnoses", []):
        code = dx.get("icd10_code")
        if code:
            result.diagnosis_codes.append(code)

    # Disease activity
    disease_activity = raw.get("disease_activity", {})
    result.disease_severity = disease_activity.get("disease_severity")

    # --- Prior treatments (enhanced for oncology) ---
    _extract_treatments(raw, result)

    # --- Lab results — flatten all panels ---
    _extract_lab_results(raw, result)

    # --- Safety screenings (biologic + viral panels) ---
    _extract_screenings(raw, result)

    # Prescriber
    prescriber = raw.get("prescriber", {})
    result.prescriber_specialty = prescriber.get("specialty")
    result.prescriber_npi = prescriber.get("npi")

    # --- Functional scores (all therapeutic areas) ---
    _extract_functional_scores(disease_activity, raw, result)

    # --- Biomarkers (tumor markers, BCMA, etc.) ---
    _extract_biomarkers(raw, result)

    # --- Genetic tests (SMN1/SMN2, etc.) ---
    _extract_genetic_tests(raw, result)

    # --- Imaging / procedures ---
    _extract_imaging(raw, result)

    # --- Clinical markers (organ function, disease flags, therapy flags) ---
    _extract_clinical_markers(raw, disease_activity, result)

    # --- Staging ---
    _extract_staging(disease_activity, result)

    # Site of care
    med_request = raw.get("medication_request", {})
    result.site_of_care = med_request.get("site_of_care")

    # REMS enrollment
    if prescriber.get("rems_certified_facility"):
        result.clinical_markers["rems_enrolled"] = True

    return result


def _extract_treatments(raw: Dict[str, Any], result: NormalizedPatientData) -> None:
    """Extract and normalize prior treatments from patient data."""
    for tx in raw.get("prior_treatments", []):
        # Calculate duration_weeks from dates if not directly provided
        duration_weeks = tx.get("duration_weeks")
        if duration_weeks is None and tx.get("duration_months"):
            duration_weeks = int(tx["duration_months"] * 4.33)
        if duration_weeks is None:
            duration_weeks = _calculate_duration_weeks(
                tx.get("start_date"), tx.get("end_date")
            )

        result.prior_treatments.append(NormalizedTreatment(
            medication_name=tx.get("medication_name", ""),
            drug_class=tx.get("drug_class"),
            duration_weeks=duration_weeks,
            outcome=_normalize_outcome(tx.get("outcome", "")),
            adequate_trial=tx.get("adequate_trial", False),
        ))

        # If treatment has component drug classes, add synthetic entries
        # so the evaluator can match by class (e.g., "Anti-CD20 monoclonal antibody")
        _add_component_treatments(tx, result)


def _add_component_treatments(tx: Dict[str, Any], result: NormalizedPatientData) -> None:
    """Add synthetic treatment entries for component drug classes in combination regimens."""
    outcome = _normalize_outcome(tx.get("outcome", ""))
    # Map boolean flags to drug class entries
    class_flags = {
        "contains_anti_cd20": "Anti-CD20 monoclonal antibody",
        "contains_anthracycline": "Anthracycline",
        "contains_proteasome_inhibitor": "Proteasome inhibitor",
        "contains_immunomodulatory_agent": "Immunomodulatory agent",
        "contains_anti_cd38": "Anti-CD38 monoclonal antibody",
    }
    for flag, drug_class in class_flags.items():
        if tx.get(flag):
            # Only add if not already present
            exists = any(
                t.drug_class and t.drug_class.lower() == drug_class.lower()
                for t in result.prior_treatments
            )
            if not exists:
                result.prior_treatments.append(NormalizedTreatment(
                    medication_name=tx.get("medication_name", ""),
                    drug_class=drug_class,
                    outcome=outcome,
                    adequate_trial=tx.get("adequate_trial", False),
                ))

    # BTK inhibitor flag
    if tx.get("is_btk_inhibitor"):
        exists = any(
            t.drug_class and "btk" in t.drug_class.lower()
            for t in result.prior_treatments
        )
        if not exists:
            result.prior_treatments.append(NormalizedTreatment(
                medication_name=tx.get("medication_name", ""),
                drug_class="BTK inhibitor",
                outcome=outcome,
                adequate_trial=tx.get("adequate_trial", False),
            ))

    # Gene therapy flag
    if tx.get("is_gene_therapy"):
        exists = any(
            t.drug_class and "gene therapy" in t.drug_class.lower()
            for t in result.prior_treatments
        )
        if not exists:
            result.prior_treatments.append(NormalizedTreatment(
                medication_name=tx.get("medication_name", ""),
                drug_class="Gene Therapy",
                outcome=outcome,
            ))

    # Individual components list (e.g., R-CHOP has Rituximab, Cyclophosphamide, etc.)
    for component in tx.get("components", []):
        component_lower = component.lower()
        if "rituximab" in component_lower or "anti-cd20" in component_lower:
            exists = any(
                t.drug_class and "anti-cd20" in t.drug_class.lower()
                for t in result.prior_treatments
            )
            if not exists:
                result.prior_treatments.append(NormalizedTreatment(
                    medication_name="Rituximab",
                    drug_class="Anti-CD20 monoclonal antibody",
                    outcome=outcome,
                ))
        if "doxorubicin" in component_lower or "anthracycline" in component_lower:
            exists = any(
                t.drug_class and "anthracycline" in t.drug_class.lower()
                for t in result.prior_treatments
            )
            if not exists:
                result.prior_treatments.append(NormalizedTreatment(
                    medication_name="Doxorubicin",
                    drug_class="Anthracycline",
                    outcome=outcome,
                ))


def _extract_lab_results(raw: Dict[str, Any], result: NormalizedPatientData) -> None:
    """Extract and flatten lab results from all panels."""
    lab_data = raw.get("laboratory_results", {})
    panels = lab_data.get("panels", {})
    for panel_name, panel in panels.items():
        for lab in panel.get("results", []):
            value = lab.get("value")
            if isinstance(value, str):
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    value = None
            result.lab_results.append(NormalizedLabResult(
                test_name=lab.get("test", ""),
                value=value if isinstance(value, (int, float)) else None,
                unit=lab.get("unit"),
                date=lab_data.get("collection_date"),
                flag=lab.get("flag"),
            ))


def _extract_screenings(raw: Dict[str, Any], result: NormalizedPatientData) -> None:
    """Extract safety screenings from both biologic and viral screening panels."""
    # Original biologic screening structure
    screening_data = raw.get("pre_biologic_screening", {})
    tb = screening_data.get("tuberculosis_screening", {})
    if tb:
        result.completed_screenings.append(NormalizedScreening(
            screening_type="tb",
            completed=(tb.get("status") or "").upper() == "COMPLETE",
            result_negative=(tb.get("result") or "").lower() == "negative",
        ))

    hep_b = screening_data.get("hepatitis_b_screening", {})
    if hep_b:
        result.completed_screenings.append(NormalizedScreening(
            screening_type="hepatitis_b",
            completed=(hep_b.get("status") or "").upper() == "COMPLETE",
            result_negative=hep_b.get("cleared_for_biologic", False),
        ))

    hep_c = screening_data.get("hepatitis_c_screening", {})
    if hep_c:
        result.completed_screenings.append(NormalizedScreening(
            screening_type="hepatitis_c",
            completed=(hep_c.get("status") or "").upper() == "COMPLETE",
            result_negative=(hep_c.get("result") or "").lower() in ("non-reactive", "negative"),
        ))

    # Viral screening panel (oncology/hematology patients)
    viral = raw.get("laboratory_results", {}).get("panels", {}).get("viral_screening", {})
    for lab in viral.get("results", []):
        test_name = (lab.get("test") or "").lower()
        value = (str(lab.get("value")) or "").lower()
        is_negative = value in ("negative", "non-reactive", "not detected")

        if "hbsag" in test_name or "hepatitis b surface" in test_name:
            if not any(s.screening_type == "hepatitis_b" for s in result.completed_screenings):
                result.completed_screenings.append(NormalizedScreening(
                    screening_type="hepatitis_b",
                    completed=True,
                    result_negative=is_negative,
                ))
        elif "anti-hbc" in test_name or "hepatitis b core" in test_name:
            pass  # hep B already covered by HBsAg above
        elif "hcv" in test_name or "hepatitis c" in test_name:
            if not any(s.screening_type == "hepatitis_c" for s in result.completed_screenings):
                result.completed_screenings.append(NormalizedScreening(
                    screening_type="hepatitis_c",
                    completed=True,
                    result_negative=is_negative,
                ))
        elif "hiv" in test_name:
            result.completed_screenings.append(NormalizedScreening(
                screening_type="hiv",
                completed=True,
                result_negative=is_negative,
            ))

    # Anti-AAV9 panel (gene therapy patients)
    aav9 = raw.get("laboratory_results", {}).get("panels", {}).get("anti_aav9", {})
    for lab in aav9.get("results", []):
        test_name = (lab.get("test") or "").lower()
        if "anti-aav9" in test_name:
            result.completed_screenings.append(NormalizedScreening(
                screening_type="anti_aav9",
                completed=True,
                result_negative=(str(lab.get("value")) or "").lower() in ("negative", "< 1:50"),
            ))


def _extract_functional_scores(
    disease_activity: Dict[str, Any],
    raw: Dict[str, Any],
    result: NormalizedPatientData,
) -> None:
    """Extract functional/performance scores from disease activity data."""
    if disease_activity.get("cdai_score") is not None:
        result.functional_scores.append(NormalizedFunctionalScore(
            score_type="CDAI",
            score_value=disease_activity["cdai_score"],
            interpretation=disease_activity.get("cdai_interpretation"),
        ))

    if disease_activity.get("ecog_performance_status") is not None:
        result.functional_scores.append(NormalizedFunctionalScore(
            score_type="ECOG",
            score_value=float(disease_activity["ecog_performance_status"]),
            interpretation=disease_activity.get("ecog_interpretation"),
        ))

    if disease_activity.get("chop_intend_score") is not None:
        result.functional_scores.append(NormalizedFunctionalScore(
            score_type="CHOP-INTEND",
            score_value=float(disease_activity["chop_intend_score"]),
            interpretation=disease_activity.get("chop_intend_interpretation"),
        ))

    if disease_activity.get("hfmse_score") is not None:
        result.functional_scores.append(NormalizedFunctionalScore(
            score_type="HFMSE",
            score_value=float(disease_activity["hfmse_score"]),
        ))


def _extract_biomarkers(raw: Dict[str, Any], result: NormalizedPatientData) -> None:
    """Extract tumor biomarkers and other biomarker data."""
    tumor = raw.get("tumor_biomarkers", {})
    if not tumor:
        return

    # ER status
    er = tumor.get("estrogen_receptor", {})
    if er:
        status = er.get("status", "").lower()
        result.biomarkers.append(NormalizedBiomarker(
            biomarker_name="HR",  # Hormone Receptor (ER+PR combined)
            result=status,
            positive=status == "positive",
        ))
        result.biomarkers.append(NormalizedBiomarker(
            biomarker_name="ER",
            result=status,
            positive=status == "positive",
        ))

    # PR status
    pr = tumor.get("progesterone_receptor", {})
    if pr:
        status = pr.get("status", "").lower()
        result.biomarkers.append(NormalizedBiomarker(
            biomarker_name="PR",
            result=status,
            positive=status == "positive",
        ))

    # HER2 status
    her2 = tumor.get("her2_status", {})
    if her2:
        status = (her2.get("overall_status") or her2.get("status") or "").lower()
        result.biomarkers.append(NormalizedBiomarker(
            biomarker_name="HER2",
            result=status,
            positive=status == "positive",
        ))

    # PIK3CA mutation
    pik3ca = tumor.get("pik3ca_mutation", {})
    if pik3ca:
        status = pik3ca.get("status", "").lower()
        result.biomarkers.append(NormalizedBiomarker(
            biomarker_name="PIK3CA",
            result=status,
            positive=status in ("positive", "detected"),
        ))

    # Ki-67
    ki67 = tumor.get("ki67")
    if ki67 is not None:
        if isinstance(ki67, dict):
            ki67_val = ki67.get("value")
        elif isinstance(ki67, str):
            ki67_val = ki67.replace("%", "").strip()
        else:
            ki67_val = ki67
        try:
            ki67_float = float(ki67_val) if ki67_val is not None else None
        except (ValueError, TypeError):
            ki67_float = None
        result.biomarkers.append(NormalizedBiomarker(
            biomarker_name="Ki-67",
            result=str(ki67_val),
            value=ki67_float,
            unit="%",
        ))

    # BCMA expression (from bone marrow biopsy)
    procedures = raw.get("procedures", {})
    bm_biopsy = procedures.get("bone_marrow_biopsy", {})
    if bm_biopsy:
        bcma = bm_biopsy.get("bcma_expression", bm_biopsy.get("flow_cytometry", {}).get("bcma_expression"))
        if bcma:
            result.biomarkers.append(NormalizedBiomarker(
                biomarker_name="BCMA",
                result=str(bcma) if isinstance(bcma, str) else "positive",
                positive=True,
            ))


def _extract_genetic_tests(raw: Dict[str, Any], result: NormalizedPatientData) -> None:
    """Extract genetic test results (SMN1/SMN2, etc.)."""
    genetic = raw.get("genetic_testing", {})
    if not genetic:
        return

    # Confirmatory testing (SMA patients) — try multiple nesting paths
    confirm = genetic.get("confirmatory_testing", {})
    results_data = confirm.get("results", {})
    if not results_data:
        # Try initial_testing path (aiden_f structure)
        initial = genetic.get("initial_testing", {})
        results_data = initial.get("results", {})
    if not results_data:
        # Try direct results (non-nested structure)
        results_data = genetic.get("results", {})

    smn1_copies = results_data.get("smn1_exon_7_copies")
    if smn1_copies is not None:
        result.genetic_tests.append(NormalizedGeneticTest(
            test_name="SMN1 Exon 7 Copy Number",
            gene="SMN1",
            result=str(smn1_copies),
            pathogenic=smn1_copies == 0,
        ))
        # Also add as lab result for lab_value evaluator matching
        result.lab_results.append(NormalizedLabResult(
            test_name="SMN1 Deletion",
            value=float(smn1_copies),
            unit="copies",
        ))

    smn2_copies = results_data.get("smn2_copy_number")
    if smn2_copies is not None:
        result.genetic_tests.append(NormalizedGeneticTest(
            test_name="SMN2 Copy Number",
            gene="SMN2",
            result=str(smn2_copies),
        ))
        result.lab_results.append(NormalizedLabResult(
            test_name="SMN2 Copy Number",
            value=float(smn2_copies),
            unit="copies",
        ))

    # Mutation type
    mutation_type = results_data.get("smn1_mutation_type")
    if mutation_type:
        result.genetic_tests.append(NormalizedGeneticTest(
            test_name="SMN1 Mutation Type",
            gene="SMN1",
            result=mutation_type,
            pathogenic=True,
        ))

    # Newborn screening
    nbs = genetic.get("newborn_screening", {})
    if nbs and nbs.get("result"):
        result.genetic_tests.append(NormalizedGeneticTest(
            test_name="Newborn Screening SMA",
            gene="SMN1",
            result=nbs["result"],
            pathogenic="positive" in nbs["result"].lower(),
        ))


def _extract_imaging(raw: Dict[str, Any], result: NormalizedPatientData) -> None:
    """Extract imaging and procedure results."""
    procedures = raw.get("procedures", {})

    colonoscopy = procedures.get("colonoscopy", {})
    if colonoscopy:
        endo_score = colonoscopy.get("endoscopic_score", {})
        result.imaging_results.append(NormalizedImagingResult(
            modality="colonoscopy",
            date=colonoscopy.get("procedure_date"),
            findings_summary=colonoscopy.get("impression"),
            score_type=endo_score.get("score_type"),
            score_value=endo_score.get("score_value"),
        ))

    pet_ct = procedures.get("pet_ct", {})
    if pet_ct:
        result.imaging_results.append(NormalizedImagingResult(
            modality="PET/CT",
            date=pet_ct.get("procedure_date"),
            findings_summary=pet_ct.get("findings"),
        ))

    echo = procedures.get("echocardiogram", {})
    if echo:
        result.imaging_results.append(NormalizedImagingResult(
            modality="echocardiogram",
            date=echo.get("procedure_date"),
            findings_summary=echo.get("findings"),
        ))


def _extract_clinical_markers(
    raw: Dict[str, Any],
    disease_activity: Dict[str, Any],
    result: NormalizedPatientData,
) -> None:
    """Extract clinical markers into the generic key-value store."""
    markers = result.clinical_markers
    clinical_history = raw.get("clinical_history", {})

    # Organ function assessment
    organ = raw.get("organ_function_assessment", {})
    if organ:
        acceptable_statuses = {"adequate", "borderline", "normal", "acceptable"}
        all_adequate = all(
            v.get("status", "").lower() in acceptable_statuses
            for v in organ.values()
            if isinstance(v, dict)
        )
        markers["organ_function_adequate"] = all_adequate

    # Ventilator status
    if "ventilator_dependent" in disease_activity:
        markers["ventilator_dependent"] = disease_activity["ventilator_dependent"]

    # Symptomatic status
    symptom_status = disease_activity.get("symptom_status", "").lower()
    if symptom_status:
        markers["symptomatic"] = symptom_status == "symptomatic"
        markers["asymptomatic"] = symptom_status == "asymptomatic"
        markers["symptom_status"] = symptom_status

    # Disease status (relapsed/refractory, etc.)
    disease_status = disease_activity.get("disease_status", "")
    if disease_status:
        markers["disease_status"] = disease_status

    # Lines of therapy completed
    lines = disease_activity.get("lines_of_therapy_completed")
    if lines is not None:
        markers["lines_of_therapy"] = lines

    # Refractory status
    refractory_to = disease_activity.get("refractory_to", [])
    if refractory_to:
        markers["refractory_to"] = refractory_to

    # Clinical history boolean flags
    for flag in [
        "prior_gene_therapy", "prior_car_t_therapy", "prior_spinraza",
        "concurrent_risdiplam", "clinical_trial_enrollment",
        "prior_cdk4_6_inhibitor",
    ]:
        if flag in clinical_history:
            markers[flag] = clinical_history[flag]

    # SMA-specific
    if disease_activity.get("sma_type"):
        markers["sma_type"] = disease_activity["sma_type"]
    if disease_activity.get("hfmse_prior") is not None:
        markers["hfmse_prior"] = disease_activity["hfmse_prior"]

    # Blastoid variant (MCL)
    if "blastoid_variant" in disease_activity:
        markers["blastoid_variant"] = disease_activity["blastoid_variant"]

    # Endocrine resistance (breast cancer)
    tumor = raw.get("tumor_biomarkers", {})
    if tumor.get("pik3ca_mutation", {}).get("status", "").lower() in ("positive", "detected"):
        markers["pik3ca_mutated"] = True

    # LHRH/testicular suppression (male breast cancer) — only if treatment is ongoing/completed
    for tx in raw.get("prior_treatments", []):
        if tx.get("is_lhrh_agonist"):
            outcome = (tx.get("outcome") or "").lower()
            # Discontinued/intolerant means NOT suppressed
            if outcome not in ("discontinued_adverse_effects", "intolerant", "discontinued"):
                markers["male_testicular_suppression"] = True
                break
    # Also check current medications field
    if raw.get("concurrent_medications"):
        for med in raw["concurrent_medications"]:
            med_name = (med.get("medication_name") or "").lower() if isinstance(med, dict) else str(med).lower()
            if any(k in med_name for k in ["goserelin", "leuprolide", "lhrh", "gnrh"]):
                markers["male_testicular_suppression"] = True


def _extract_staging(disease_activity: Dict[str, Any], result: NormalizedPatientData) -> None:
    """Extract disease staging information."""
    staging = {}
    if disease_activity.get("stage"):
        staging["stage"] = disease_activity["stage"]
    if disease_activity.get("ann_arbor_stage"):
        staging["ann_arbor_stage"] = disease_activity["ann_arbor_stage"]
    if disease_activity.get("iss_stage"):
        staging["iss_stage"] = disease_activity["iss_stage"]
    if disease_activity.get("revised_iss_stage"):
        staging["revised_iss_stage"] = disease_activity["revised_iss_stage"]
    if staging:
        result.staging = staging
