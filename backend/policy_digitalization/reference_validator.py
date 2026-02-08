"""Pass 3: Reference Data Validator — validates clinical codes against external databases."""

import re
from typing import Dict, Any, List

from backend.policy_digitalization.validator import ValidatedExtractionResult
from backend.models.policy_schema import DigitizedPolicy, CriterionProvenance, ExtractionConfidence
from backend.policy_digitalization.exceptions import ValidationError
from backend.config.logging_config import get_logger

logger = get_logger(__name__)


# Code format patterns
ICD10_PATTERN = re.compile(r'^[A-Z]\d{2}(\.\d{1,4})?$')
HCPCS_PATTERN = re.compile(r'^[A-Z]\d{4}$')
CPT_PATTERN = re.compile(r'^\d{5}$')
NDC_PATTERN = re.compile(r'^\d{5}-\d{4}-\d{2}$|^\d{11}$')
LOINC_PATTERN = re.compile(r'^\d{1,7}-\d$')


class ReferenceDataValidator:
    """Validates clinical codes in extracted data using format validation and MCP validators."""

    def __init__(self):
        logger.info("ReferenceDataValidator initialized")

    async def validate_codes(self, validated: ValidatedExtractionResult) -> DigitizedPolicy:
        """
        Validate clinical codes and build final DigitizedPolicy.

        Pass 3: Format validation for codes. MCP validators (ICD-10, NPI)
        can be used when available, but format validation is the baseline.
        """
        logger.info("Starting Pass 3 reference validation")

        data = validated.extracted_data
        provenances: Dict[str, CriterionProvenance] = {}
        code_results: Dict[str, Dict[str, bool]] = {}

        # Validate codes in each criterion
        for cid, criterion_data in data.get("atomic_criteria", {}).items():
            codes = criterion_data.get("clinical_codes", [])
            criterion_code_results = {}

            for code_entry in codes:
                system = code_entry.get("system", "")
                code = code_entry.get("code", "")
                valid = self._validate_code_format(system, code)
                criterion_code_results[f"{system}:{code}"] = valid
                if not valid:
                    logger.warning("Invalid code format", criterion=cid, system=system, code=code)

            code_results[cid] = criterion_code_results

            # Mark codes_validated
            if codes:
                all_valid = all(criterion_code_results.values())
                criterion_data["codes_validated"] = all_valid

            # Build provenance
            provenances[cid] = CriterionProvenance(
                criterion_id=cid,
                source_page=criterion_data.get("source_page"),
                source_section=criterion_data.get("source_section"),
                source_text_excerpt=criterion_data.get("source_text_excerpt", criterion_data.get("policy_text", "")),
                extraction_confidence=ExtractionConfidence(
                    criterion_data.get("extraction_confidence", "medium")
                ),
                validation_action="confirmed" if validated.validation_status == "valid" else "corrected",
                code_validation_results=criterion_code_results,
            )

        # Attempt MCP validation for ICD-10 codes (non-blocking)
        await self._mcp_validate_icd10(data, provenances)

        # Build DigitizedPolicy from validated data
        policy = self._build_policy(data, validated, provenances)

        logger.info(
            "Pass 3 complete",
            criteria_count=len(policy.atomic_criteria),
            provenances_count=len(policy.provenances),
        )

        return policy

    def _validate_code_format(self, system: str, code: str) -> bool:
        """Validate clinical code format by system."""
        if not code:
            return False
        system_upper = system.upper().replace("-", "")
        if system_upper in ("ICD10", "ICD10CM"):
            return bool(ICD10_PATTERN.match(code.upper()))
        elif system_upper == "HCPCS":
            return bool(HCPCS_PATTERN.match(code.upper()))
        elif system_upper == "CPT":
            return bool(CPT_PATTERN.match(code))
        elif system_upper == "NDC":
            return bool(NDC_PATTERN.match(code))
        elif system_upper == "LOINC":
            return bool(LOINC_PATTERN.match(code))
        # SNOMED, RxNorm — accept any non-empty string
        return True

    @staticmethod
    def _parse_dose_string(dose_str: str):
        """Parse '5 mg/kg' into (5.0, 'mg/kg') or (None, dose_str)."""
        import re as _re
        m = _re.match(r'^([\d.]+)\s*(.+)$', dose_str.strip())
        if m:
            try:
                return float(m.group(1)), m.group(2).strip()
            except ValueError:
                pass
        return None, dose_str

    def _map_dosing_dict(self, dr: Dict[str, Any], indication_name: str):
        """Map Gemini's dosing dict format to DosingRequirement fields."""
        from backend.models.policy_schema import DosingRequirement

        # Parse 'dose' field like '5 mg/kg' into dose_value + dose_unit
        dose_value, dose_unit = None, "as_prescribed"
        if "dose" in dr:
            dose_value, dose_unit = self._parse_dose_string(str(dr["dose"]))

        # Parse max_dose — may be a number or a string like '10 mg/kg every 4 weeks'
        max_dose = None
        max_dose_notes = ""
        raw_max = dr.get("max_dose")
        if raw_max is not None:
            if isinstance(raw_max, (int, float)):
                max_dose = float(raw_max)
            else:
                parsed_val, _ = self._parse_dose_string(str(raw_max))
                if parsed_val is not None:
                    max_dose = parsed_val
                else:
                    max_dose_notes = f"Max dose: {raw_max}"

        # Infer phase from keys or default
        phase = dr.get("phase", "all")
        if phase not in ("induction", "maintenance", "both", "all"):
            phase = "all"

        notes_parts = [dr.get("notes", ""), max_dose_notes]
        notes = "; ".join(p for p in notes_parts if p) or None

        return DosingRequirement(
            indication=dr.get("indication", indication_name),
            phase=phase,
            dose_value=dose_value,
            dose_unit=dr.get("dose_unit", dose_unit),
            route=dr.get("route", "IV"),
            frequency=dr.get("frequency", "as_prescribed"),
            max_dose=max_dose,
            max_dose_unit=dr.get("max_dose_unit"),
            notes=notes,
        )

    async def _mcp_validate_icd10(
        self, data: Dict[str, Any], provenances: Dict[str, CriterionProvenance]
    ):
        """Attempt to validate ICD-10 codes via MCP validator (best-effort)."""
        try:
            from backend.mcp.icd10_validator import get_icd10_validator
            validator = get_icd10_validator()

            icd10_codes = set()
            code_to_criteria = {}
            for cid, criterion_data in data.get("atomic_criteria", {}).items():
                for code_entry in criterion_data.get("clinical_codes", []):
                    if code_entry.get("system", "").upper().startswith("ICD"):
                        code = code_entry["code"]
                        icd10_codes.add(code)
                        code_to_criteria.setdefault(code, []).append(cid)

            if icd10_codes:
                result = await validator.validate_batch(list(icd10_codes))
                for code_info in result.codes:
                    for cid in code_to_criteria.get(code_info.code, []):
                        key = f"ICD-10:{code_info.code}"
                        if cid in provenances:
                            provenances[cid].code_validation_results[key] = code_info.is_valid

                logger.info(
                    "MCP ICD-10 validation complete",
                    total=len(icd10_codes),
                    valid=result.valid_count,
                    invalid=result.invalid_count,
                )
        except Exception as e:
            # MCP validation is best-effort — don't fail the pipeline
            logger.warning("MCP ICD-10 validation skipped", error=str(e))

    def _build_policy(
        self,
        data: Dict[str, Any],
        validated: ValidatedExtractionResult,
        provenances: Dict[str, CriterionProvenance],
    ) -> DigitizedPolicy:
        """Build DigitizedPolicy from validated extraction data."""
        from backend.models.policy_schema import (
            AtomicCriterion, CriterionGroup, IndicationCriteria,
            ExclusionCriteria, StepTherapyRequirement, ClinicalCode,
            DosingRequirement, CriterionType,
        )

        valid_criterion_types = {e.value for e in CriterionType}

        # Parse atomic criteria — tolerate individual failures
        atomic_criteria = {}
        for cid, cdata in data.get("atomic_criteria", {}).items():
            try:
                clinical_codes = [ClinicalCode(**c) for c in cdata.get("clinical_codes", [])]
                raw_type = cdata.get("criterion_type", "custom")
                if raw_type not in valid_criterion_types:
                    logger.warning("Unknown criterion_type, falling back to custom", criterion_id=cid, raw_type=raw_type)
                    raw_type = "custom"
                atomic_criteria[cid] = AtomicCriterion(
                    criterion_id=cdata.get("criterion_id", cid),
                    criterion_type=raw_type,
                    name=cdata.get("name", ""),
                    description=cdata.get("description", ""),
                    policy_text=cdata.get("policy_text", ""),
                    clinical_codes=clinical_codes,
                    comparison_operator=cdata.get("comparison_operator"),
                    threshold_value=cdata.get("threshold_value"),
                    threshold_value_upper=cdata.get("threshold_value_upper"),
                    threshold_unit=cdata.get("threshold_unit"),
                    allowed_values=cdata.get("allowed_values", []),
                    drug_names=cdata.get("drug_names", []),
                    drug_classes=cdata.get("drug_classes", []),
                    evidence_types=cdata.get("evidence_types", []),
                    is_required=cdata.get("is_required", True),
                    category=cdata.get("category", "documentation"),
                    source_section=cdata.get("source_section"),
                    source_page=cdata.get("source_page"),
                    source_text_excerpt=cdata.get("source_text_excerpt", ""),
                    extraction_confidence=cdata.get("extraction_confidence", "medium"),
                    validation_status=cdata.get("validation_status"),
                    patient_data_path=cdata.get("patient_data_path"),
                    evaluation_strategy=cdata.get("evaluation_strategy"),
                    codes_validated=cdata.get("codes_validated", False),
                    minimum_duration_days=cdata.get("minimum_duration_days"),
                )
            except Exception as e:
                logger.warning("Skipping unparseable criterion", criterion_id=cid, error=str(e))

        # Parse groups
        criterion_groups = {}
        for gid, gdata in data.get("criterion_groups", {}).items():
            try:
                criterion_groups[gid] = CriterionGroup(
                    group_id=gdata.get("group_id", gid),
                    name=gdata.get("name", ""),
                    description=gdata.get("description"),
                    operator=gdata.get("operator", "AND"),
                    criteria=gdata.get("criteria", []),
                    subgroups=gdata.get("subgroups", []),
                    negated=gdata.get("negated", False),
                )
            except Exception as e:
                logger.warning("Skipping unparseable group", group_id=gid, error=str(e))

        # Parse indications
        indications = []
        for idata in data.get("indications", []):
            try:
                ind_codes = [ClinicalCode(**c) for c in idata.get("indication_codes", [])]
                dosing = []
                ind_name = idata.get("indication_name", "unknown")
                for dr in idata.get("dosing_requirements", []):
                    if isinstance(dr, str):
                        # Gemini sometimes returns dosing as plain text strings
                        dosing.append(DosingRequirement(
                            indication=ind_name,
                            phase="all",
                            dose_unit="as_prescribed",
                            route="as_prescribed",
                            frequency="as_prescribed",
                            notes=dr,
                        ))
                    elif isinstance(dr, dict):
                        # Try direct construction first; if it fails, map Gemini's schema
                        try:
                            dosing.append(DosingRequirement(**dr))
                        except Exception:
                            dosing.append(self._map_dosing_dict(dr, ind_name))
                    else:
                        logger.warning("Unexpected dosing_requirements entry type", type=type(dr).__name__)
                indications.append(IndicationCriteria(
                    indication_id=idata.get("indication_id", ""),
                    indication_name=idata.get("indication_name", ""),
                    indication_codes=ind_codes,
                    initial_approval_criteria=idata.get("initial_approval_criteria", ""),
                    continuation_criteria=idata.get("continuation_criteria"),
                    initial_approval_duration_months=idata.get("initial_approval_duration_months", 6),
                    continuation_approval_duration_months=idata.get("continuation_approval_duration_months"),
                    dosing_requirements=dosing,
                    min_age_years=idata.get("min_age_years"),
                    max_age_years=idata.get("max_age_years"),
                ))
            except Exception as e:
                logger.warning("Skipping unparseable indication", indication=idata.get("indication_id", "unknown"), error=str(e))

        # Parse exclusions
        exclusions = []
        for e in data.get("exclusions", []):
            try:
                exclusions.append(ExclusionCriteria(
                    exclusion_id=e.get("exclusion_id", ""),
                    name=e.get("name", ""),
                    description=e.get("description", ""),
                    policy_text=e.get("policy_text", ""),
                    trigger_criteria=e.get("trigger_criteria", []),
                ))
            except Exception as exc:
                logger.warning("Skipping unparseable exclusion", exclusion=e.get("exclusion_id", "unknown"), error=str(exc))

        # Parse step therapy
        step_therapy = []
        for s in data.get("step_therapy_requirements", []):
            try:
                step_therapy.append(StepTherapyRequirement(
                    requirement_id=s.get("requirement_id", ""),
                    indication=s.get("indication", ""),
                    required_drugs=s.get("required_drugs", []),
                    required_drug_classes=s.get("required_drug_classes", []),
                    minimum_trials=s.get("minimum_trials", 1),
                    minimum_duration_days=s.get("minimum_duration_days"),
                    failure_required=s.get("failure_required", True),
                    intolerance_acceptable=s.get("intolerance_acceptable", True),
                    contraindication_acceptable=s.get("contraindication_acceptable", True),
                    documentation_requirements=s.get("documentation_requirements", []),
                ))
            except Exception as exc:
                logger.warning("Skipping unparseable step therapy", requirement=s.get("requirement_id", "unknown"), error=str(exc))

        # Parse medication codes
        med_codes = [ClinicalCode(**c) for c in data.get("medication_codes", [])]

        # Parse date
        def parse_date(d):
            if not d:
                return None
            try:
                from datetime import date as date_cls
                return date_cls.fromisoformat(d)
            except (ValueError, TypeError):
                return None

        # Determine quality
        if validated.quality_score >= 0.8:
            quality = "good"
        elif validated.quality_score >= 0.5:
            quality = "needs_review"
        else:
            quality = "poor"

        # effective_date is required — fall back to today if LLM didn't provide it
        effective = parse_date(data.get("effective_date"))
        if effective is None:
            from datetime import date as date_cls
            effective = date_cls.today()
            logger.warning("effective_date not in extraction; defaulting to today")

        return DigitizedPolicy(
            policy_id=data.get("policy_id", "UNKNOWN"),
            policy_number=data.get("policy_number", ""),
            policy_title=data.get("policy_title", ""),
            payer_name=data.get("payer_name", ""),
            medication_name=data.get("medication_name", ""),
            medication_brand_names=data.get("medication_brand_names", []),
            medication_generic_names=data.get("medication_generic_names", []),
            medication_codes=med_codes,
            effective_date=effective,
            last_revision_date=parse_date(data.get("last_revision_date")),
            atomic_criteria=atomic_criteria,
            criterion_groups=criterion_groups,
            indications=indications,
            exclusions=exclusions,
            step_therapy_requirements=step_therapy,
            required_specialties=data.get("required_specialties", []),
            consultation_allowed=data.get("consultation_allowed", True),
            safety_screenings=data.get("safety_screenings", []),
            extraction_pipeline_version="1.0",
            validation_model="claude",
            extraction_quality=quality,
            provenances=provenances,
        )
