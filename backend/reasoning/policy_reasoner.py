"""Policy Reasoner - Analyzes payer policies using LLM."""
import json
from typing import Dict, Any, Optional
from pathlib import Path

from backend.models.coverage import CoverageAssessment, CriterionAssessment, DocumentationGap
from backend.models.enums import CoverageStatus
from backend.reasoning.prompt_loader import get_prompt_loader
from backend.reasoning.llm_gateway import get_llm_gateway
from backend.reasoning.rubric_loader import get_rubric_loader
from backend.policy_digitalization.exceptions import PolicyNotFoundError
from backend.config.logging_config import get_logger
from backend.config.settings import get_settings

logger = get_logger(__name__)


class PolicyReasoner:
    """
    Analyzes payer policies to assess coverage eligibility.
    Uses LLM for policy reasoning - Claude for clinical accuracy.
    """

    def __init__(self, policies_dir: Optional[Path] = None):
        """
        Initialize the Policy Reasoner.

        Args:
            policies_dir: Directory containing policy documents
        """
        self.policies_dir = policies_dir or Path(get_settings().policies_dir)
        self.prompt_loader = get_prompt_loader()
        self.llm_gateway = get_llm_gateway()
        self.rubric_loader = get_rubric_loader()
        logger.info(
            "Policy Reasoner initialized",
            policies_dir=str(self.policies_dir)
        )

    def load_policy(self, payer_name: str, medication_name: str) -> str:
        """
        Load a policy document for a payer/medication combination.

        Tries brand/generic name aliases when the primary medication name
        doesn't match any file. Returns a placeholder when only a PDF exists
        (digitized criteria are passed separately via the policy criteria structure).

        Args:
            payer_name: Name of the payer (e.g., "cigna", "uhc")
            medication_name: Name of the medication

        Returns:
            Policy document text
        """
        from backend.policy_digitalization.pipeline import MEDICATION_NAME_ALIASES

        payer_key = payer_name.lower().replace(" ", "_")
        med_key = medication_name.lower().replace(" ", "_")
        policies_root = self.policies_dir.resolve()

        # Build list of medication keys to try (primary + brand/generic alias)
        med_keys = [med_key]
        alias = MEDICATION_NAME_ALIASES.get(med_key)
        if alias:
            med_keys.append(alias)

        # Try .txt files with each medication key
        for mk in med_keys:
            policy_path = (self.policies_dir / f"{payer_key}_{mk}.txt").resolve()
            try:
                policy_path.relative_to(policies_root)
            except ValueError:
                continue
            if policy_path.exists():
                with open(policy_path, "r", encoding="utf-8") as f:
                    return f.read()

        # Try generic payer policy
        policy_path = (self.policies_dir / f"{payer_key}.txt").resolve()
        try:
            policy_path.relative_to(policies_root)
            if policy_path.exists():
                with open(policy_path, "r", encoding="utf-8") as f:
                    return f.read()
        except ValueError:
            pass

        # Check if a PDF-only policy exists (digitized criteria passed separately)
        for mk in med_keys:
            pdf_path = (self.policies_dir / f"{payer_key}_{mk}.pdf").resolve()
            try:
                pdf_path.relative_to(policies_root)
            except ValueError:
                continue
            if pdf_path.exists():
                logger.info(
                    "Policy available as PDF only — digitized criteria passed separately",
                    payer=payer_name, medication=medication_name, pdf=str(pdf_path),
                )
                return (
                    f"[Policy for {payer_name}/{medication_name} is available as PDF only. "
                    f"Raw policy text not available for direct inclusion. Use the "
                    f"digitized policy criteria structure below for evaluation.]"
                )

        logger.error("Policy file not found", payer=payer_name, medication=medication_name)
        raise FileNotFoundError(
            f"Policy not found for {payer_name}/{medication_name}"
        )

    async def assess_coverage(
        self,
        patient_info: Dict[str, Any],
        medication_info: Dict[str, Any],
        payer_name: str,
        digitized_policy: Optional[Any] = None,
    ) -> CoverageAssessment:
        """
        Assess coverage eligibility for a patient/medication/payer combination.

        Passes digitized policy criteria structure to Claude so it evaluates
        each criterion by ID, producing per-criterion assessments.

        Args:
            patient_info: Patient demographic and clinical data
            medication_info: Medication request details
            payer_name: Name of the payer
            digitized_policy: Optional pre-loaded DigitizedPolicy to use instead
                of loading from cache (used for version-specific impact analysis)

        Returns:
            Complete coverage assessment
        """
        logger.info(
            "Assessing coverage",
            payer=payer_name,
            medication=medication_info.get("medication_name")
        )

        # Load policy document
        policy_text = self.load_policy(
            payer_name=payer_name,
            medication_name=medication_info.get("medication_name", "unknown")
        )

        # Load digitized policy criteria structure for Claude
        policy_criteria_context = ""
        if digitized_policy:
            # Use the provided digitized policy (version-specific)
            policy_criteria_context = self._format_policy_criteria(digitized_policy)
            logger.info(
                "Using provided digitized policy for assessment",
                payer=payer_name,
                version=getattr(digitized_policy, 'version', 'unknown'),
            )
        else:
            try:
                from backend.policy_digitalization.pipeline import get_digitalization_pipeline
                pipeline = get_digitalization_pipeline()
                digitized_policy = await pipeline.get_or_digitalize(
                    payer_name, medication_info.get("medication_name", "unknown")
                )
                policy_criteria_context = self._format_policy_criteria(digitized_policy)
            except (FileNotFoundError, PolicyNotFoundError):
                logger.info("No digitized policy available, Claude will work from raw policy text", payer=payer_name)
            except Exception as e:
                logger.error(
                    "Failed to load digitized policy, Claude will work from raw policy text",
                    error=str(e), error_type=type(e).__name__, payer=payer_name,
                )

        if not policy_criteria_context:
            policy_criteria_context = (
                "[No structured policy criteria available. "
                "Evaluate coverage based on the raw policy document above. "
                "Generate criterion_id values for each requirement you identify.]"
            )

        # Load decision rubric for this payer
        rubric = self.rubric_loader.load(payer_name=payer_name)
        rubric_context = rubric.to_prompt_context()

        # Build prompt with rubric context and policy criteria
        prompt = self.prompt_loader.load(
            "policy_analysis/coverage_assessment.txt",
            {
                "patient_info": patient_info,
                "medication_info": medication_info,
                "policy_document": policy_text,
                "decision_rubric": rubric_context,
                "policy_criteria": policy_criteria_context,
            }
        )

        # Get system prompt
        system_prompt = self.prompt_loader.load("system/clinical_reasoning_base.txt")

        # Analyze with LLM
        result = await self.llm_gateway.analyze_policy(
            prompt=prompt,
            system_prompt=system_prompt
        )

        # Parse response into CoverageAssessment (pass digitized policy for criterion_id validation)
        assessment = self._parse_assessment(
            result=result,
            payer_name=payer_name,
            policy_text=policy_text,
            medication_name=medication_info.get("medication_name", "unknown"),
            digitized_policy=digitized_policy,
        )

        logger.info(
            "Coverage assessment complete",
            payer=payer_name,
            status=assessment.coverage_status.value,
            likelihood=assessment.approval_likelihood
        )

        return assessment

    def _format_policy_criteria(self, digitized_policy) -> str:
        """Format digitized policy criteria as structured context for the LLM prompt.

        Includes atomic criteria (with IDs, types, clinical thresholds, duration
        requirements), exclusion criteria, criterion groups, and indications so
        Claude can evaluate each criterion by its exact ID.
        """
        lines = []

        # Indications
        if digitized_policy.indications:
            lines.append("### Covered Indications")
            for ind in digitized_policy.indications:
                codes_str = ""
                if ind.indication_codes:
                    codes_str = " (" + ", ".join(
                        f"{c.system}:{c.code}" for c in ind.indication_codes
                    ) + ")"
                lines.append(f"- **{ind.indication_name}**{codes_str}")
                if ind.initial_approval_criteria:
                    lines.append(f"  Initial approval criteria group: {ind.initial_approval_criteria}")
                if ind.min_age_years is not None or ind.max_age_years is not None:
                    age_str = ""
                    if ind.min_age_years is not None:
                        age_str += f">= {ind.min_age_years}"
                    if ind.max_age_years is not None:
                        age_str += f"{' and ' if age_str else ''}<= {ind.max_age_years}"
                    lines.append(f"  Age restriction: {age_str} years")

        # Criterion Groups (hierarchy)
        if digitized_policy.criterion_groups:
            lines.append("\n### Criterion Groups (Logical Structure)")
            for gid, group in digitized_policy.criterion_groups.items():
                operator = getattr(group, 'operator', getattr(group, 'logical_operator', 'AND'))
                criteria_list = ", ".join(group.criteria) if group.criteria else "none"
                subgroups = ", ".join(group.subgroups) if group.subgroups else ""
                lines.append(f"- **{gid}** ({group.name}): operator={operator}, criteria=[{criteria_list}]"
                             + (f", subgroups=[{subgroups}]" if subgroups else ""))

        # Atomic Criteria (the items Claude must evaluate)
        if digitized_policy.atomic_criteria:
            lines.append("\n### Atomic Criteria to Evaluate")
            lines.append("Evaluate EACH of the following criteria against the patient data.")
            lines.append("You MUST use the exact criterion_id shown for each criterion in your response.")
            for cid, criterion in digitized_policy.atomic_criteria.items():
                required_tag = " [REQUIRED]" if getattr(criterion, 'is_required', True) else " [OPTIONAL]"
                confidence_tag = ""
                ext_conf = getattr(criterion, 'extraction_confidence', None)
                if ext_conf and str(ext_conf) in ('low', 'unconfident'):
                    confidence_tag = f" [EXTRACTION: {ext_conf}]"

                lines.append(f"\n**criterion_id: {cid}**{required_tag}{confidence_tag}")
                lines.append(f"  Name: {criterion.name}")
                lines.append(f"  Type: {criterion.criterion_type}")
                lines.append(f"  Category: {criterion.category}")
                lines.append(f"  Description: {criterion.description}")
                if criterion.policy_text:
                    lines.append(f"  Policy Text: \"{criterion.policy_text}\"")
                if criterion.clinical_codes:
                    codes = ", ".join(f"{c.system}:{c.code}" for c in criterion.clinical_codes)
                    lines.append(f"  Clinical Codes: {codes}")
                if hasattr(criterion, 'drug_names') and criterion.drug_names:
                    lines.append(f"  Drug Names: {', '.join(criterion.drug_names)}")
                if hasattr(criterion, 'drug_classes') and criterion.drug_classes:
                    lines.append(f"  Drug Classes: {', '.join(criterion.drug_classes)}")
                if hasattr(criterion, 'allowed_values') and criterion.allowed_values:
                    lines.append(f"  Allowed Values: {', '.join(criterion.allowed_values)}")

                # Numeric thresholds (including range comparisons)
                threshold = getattr(criterion, 'threshold_value', None)
                if threshold is not None:
                    op = getattr(criterion, 'comparison_operator', '')
                    unit = getattr(criterion, 'threshold_unit', '') or ''
                    upper = getattr(criterion, 'threshold_value_upper', None)
                    if upper is not None:
                        lines.append(f"  Threshold: {threshold} to {upper} {unit}".strip())
                    else:
                        lines.append(f"  Threshold: {op} {threshold} {unit}".strip())

                # Duration requirements (critical for step therapy)
                min_duration = getattr(criterion, 'minimum_duration_days', None)
                if min_duration is not None:
                    lines.append(f"  Minimum Duration: {min_duration} days")

                # Evidence types that satisfy this criterion
                evidence_types = getattr(criterion, 'evidence_types', None)
                if evidence_types:
                    lines.append(f"  Acceptable Evidence: {', '.join(evidence_types)}")

        # Exclusion Criteria (conditions that explicitly disqualify coverage)
        if digitized_policy.exclusions:
            lines.append("\n### Exclusion Criteria (Disqualifying Conditions)")
            lines.append("If ANY of the following exclusions apply, flag them in your assessment:")
            for excl in digitized_policy.exclusions:
                lines.append(f"\n**exclusion_id: {excl.exclusion_id}**")
                lines.append(f"  Name: {excl.name}")
                lines.append(f"  Description: {excl.description}")
                if excl.policy_text:
                    lines.append(f"  Policy Text: \"{excl.policy_text}\"")
                if excl.trigger_criteria:
                    lines.append(f"  Triggered by criteria: {', '.join(excl.trigger_criteria)}")

        # Step Therapy Requirements (summary for cross-reference)
        if digitized_policy.step_therapy_requirements:
            lines.append("\n### Step Therapy Requirements")
            for st in digitized_policy.step_therapy_requirements:
                lines.append(f"\n**{st.requirement_id}** (Indication: {st.indication})")
                if st.required_drugs:
                    lines.append(f"  Required drugs: {', '.join(st.required_drugs)}")
                if st.required_drug_classes:
                    lines.append(f"  Required drug classes: {', '.join(st.required_drug_classes)}")
                lines.append(f"  Minimum trials: {st.minimum_trials}")
                if st.minimum_duration_days:
                    lines.append(f"  Minimum trial duration: {st.minimum_duration_days} days")
                lines.append(f"  Failure required: {st.failure_required}, Intolerance acceptable: {st.intolerance_acceptable}, Contraindication exempts: {st.contraindication_acceptable}")

        return "\n".join(lines)

    def _parse_assessment(
        self,
        result: Dict[str, Any],
        payer_name: str,
        policy_text: str,
        medication_name: str,
        digitized_policy=None,
    ) -> CoverageAssessment:
        """Parse LLM response into CoverageAssessment with criterion_id validation."""
        from uuid import uuid4

        # Validate the LLM returned usable data
        if not result.get("criteria_assessments") and not result.get("coverage_status"):
            logger.error(
                "LLM returned no usable assessment data",
                payer=payer_name,
                keys=list(result.keys()),
            )
            raise ValueError(f"LLM response missing required assessment fields for {payer_name}")

        # Build set of known criterion_ids from digitized policy for validation
        known_criterion_ids = set()
        if digitized_policy and hasattr(digitized_policy, 'atomic_criteria'):
            known_criterion_ids = set(digitized_policy.atomic_criteria.keys())

        # Parse criteria assessments with ID validation
        criteria = []
        raw_criteria = result.get("criteria_assessments", [])
        matched_ids = set()
        for c in raw_criteria:
            cid = c.get("criterion_id", "")

            # Validate criterion_id against known policy criteria
            if known_criterion_ids and cid:
                if cid in known_criterion_ids:
                    matched_ids.add(cid)
                else:
                    logger.warning(
                        "LLM returned unknown criterion_id — not in digitized policy",
                        criterion_id=cid,
                        payer=payer_name,
                        criterion_name=c.get("criterion_name", ""),
                    )

            # Use provided ID or generate fallback (with warning)
            if not cid:
                cid = str(uuid4())
                logger.warning(
                    "LLM returned criterion without criterion_id, generated fallback",
                    payer=payer_name,
                    criterion_name=c.get("criterion_name", "Unknown"),
                )

            criteria.append(CriterionAssessment(
                criterion_id=cid,
                criterion_name=c.get("criterion_name", "Unknown"),
                criterion_description=c.get("criterion_description", ""),
                is_met=c.get("is_met", False),
                confidence=c.get("confidence", 0.5),
                supporting_evidence=c.get("supporting_evidence", []),
                gaps=c.get("gaps", []),
                reasoning=c.get("reasoning", "")
            ))

        # Enforce coverage of known criteria — downgrade status if too many are missing
        if known_criterion_ids:
            missing_from_response = known_criterion_ids - matched_ids
            if missing_from_response:
                missing_pct = len(missing_from_response) / len(known_criterion_ids)
                logger.warning(
                    "LLM did not evaluate all policy criteria",
                    payer=payer_name,
                    missing_criterion_ids=sorted(missing_from_response),
                    evaluated_count=len(matched_ids),
                    total_policy_criteria=len(known_criterion_ids),
                    missing_pct=f"{missing_pct:.0%}",
                )
                # Check if any REQUIRED criteria were missed
                required_missing = []
                if digitized_policy and hasattr(digitized_policy, 'atomic_criteria'):
                    for mid in missing_from_response:
                        crit = digitized_policy.atomic_criteria.get(mid)
                        if crit and getattr(crit, 'is_required', True):
                            required_missing.append(mid)
                if required_missing:
                    logger.error(
                        "REQUIRED policy criteria not evaluated by LLM — flagging as incomplete",
                        payer=payer_name,
                        required_missing=sorted(required_missing),
                    )
                    # Add missing required criteria as NOT MET with zero confidence
                    for mid in required_missing:
                        crit = digitized_policy.atomic_criteria[mid]
                        criteria.append(CriterionAssessment(
                            criterion_id=mid,
                            criterion_name=crit.name,
                            criterion_description=f"[NOT EVALUATED BY AI] {crit.description}",
                            is_met=False,
                            confidence=0.0,
                            supporting_evidence=[],
                            gaps=["Criterion was not evaluated by AI — requires manual review"],
                            reasoning="This criterion was not included in the AI assessment response. Marked as not met pending human review.",
                        ))

        # Parse documentation gaps
        gaps = []
        raw_gaps = result.get("documentation_gaps", [])
        for g in raw_gaps:
            gaps.append(DocumentationGap(
                gap_id=g.get("gap_id", str(uuid4())),
                gap_type=g.get("gap_type", "other"),
                description=g.get("description", ""),
                required_for=g.get("required_for", []),
                priority=g.get("priority", "medium"),
                suggested_action=g.get("suggested_action", "")
            ))

        # Map coverage status with conservative decision model
        status_str = result.get("coverage_status", "unknown")
        coverage_status = self._apply_conservative_status_mapping(
            status_str,
            result.get("approval_likelihood", 0.5)
        )

        # Validate and sanitize approval_likelihood from LLM
        raw_likelihood = result.get("approval_likelihood", 0.5)
        approval_likelihood = self._validate_approval_likelihood(
            raw_likelihood, criteria, payer_name, digitized_policy=digitized_policy,
        )

        return CoverageAssessment(
            assessment_id=str(uuid4()),
            payer_name=payer_name,
            policy_name=f"{payer_name} Policy",
            medication_name=medication_name,
            coverage_status=coverage_status,
            approval_likelihood=approval_likelihood,
            approval_likelihood_reasoning=result.get("approval_likelihood_reasoning", ""),
            criteria_assessments=criteria,
            criteria_met_count=sum(1 for c in criteria if c.is_met),
            criteria_total_count=len(criteria),
            documentation_gaps=gaps,
            recommendations=result.get("recommendations", []),
            step_therapy_required=result.get("step_therapy_required", False),
            step_therapy_options=result.get("step_therapy_options", []),
            step_therapy_satisfied=result.get("step_therapy_satisfied", False),
            raw_policy_text=policy_text,
            llm_raw_response=result
        )

    def _validate_approval_likelihood(
        self,
        raw_likelihood: float,
        criteria: list,
        payer_name: str,
        digitized_policy=None,
    ) -> float:
        """
        Validate and cross-check LLM-provided approval_likelihood against
        deterministic criteria results. Caps values that contradict met/unmet
        criteria counts to prevent hallucinated high-confidence scores.

        Args:
            raw_likelihood: Raw likelihood float from LLM (0.0-1.0)
            criteria: List of parsed CriterionAssessment objects
            payer_name: Payer name for logging
            digitized_policy: Optional digitized policy for exclusion detection

        Returns:
            Validated likelihood clamped to [0.0, 1.0]
        """
        # Ensure within valid range
        likelihood = max(0.0, min(1.0, float(raw_likelihood)))

        if not criteria:
            return likelihood

        # --- Hard-block exclusion detection ---
        # If any exclusion criterion is triggered (is_met=True on an exclusion),
        # this is a hard block — approval likelihood must be aggressively floored.
        exclusion_ids = set()
        if digitized_policy and hasattr(digitized_policy, 'exclusions') and digitized_policy.exclusions:
            exclusion_ids = {e.exclusion_id for e in digitized_policy.exclusions}
            # Also check trigger_criteria — atomic criteria that act as exclusions
            for excl in digitized_policy.exclusions:
                if excl.trigger_criteria:
                    exclusion_ids.update(excl.trigger_criteria)

        triggered_exclusions = [
            c for c in criteria
            if c.criterion_id in exclusion_ids and c.is_met and c.confidence >= 0.7
        ]
        if triggered_exclusions:
            hard_block_cap = 0.15
            if likelihood > hard_block_cap:
                logger.warning(
                    "Approval likelihood hard-capped: exclusion criterion triggered",
                    payer=payer_name,
                    raw_likelihood=raw_likelihood,
                    capped_likelihood=hard_block_cap,
                    triggered_exclusions=[c.criterion_id for c in triggered_exclusions],
                )
                return hard_block_cap

        met_count = sum(1 for c in criteria if c.is_met)
        total_count = len(criteria)
        met_ratio = met_count / total_count if total_count > 0 else 0.0

        # Flag and cap if LLM claims high likelihood but few criteria are met
        if likelihood > 0.85 and met_ratio < 0.5:
            capped = met_ratio + 0.1  # Cap near the actual met ratio
            logger.warning(
                "Approval likelihood capped: LLM claimed high confidence but "
                "fewer than half criteria met",
                payer=payer_name,
                raw_likelihood=raw_likelihood,
                capped_likelihood=capped,
                met_count=met_count,
                total_count=total_count,
            )
            return capped

        # Mid-range cross-validation: likelihood 0.5-0.85 with met_ratio < 0.35
        if likelihood > 0.5 and met_ratio < 0.35:
            capped = max(met_ratio + 0.15, 0.3)
            logger.warning(
                "Approval likelihood capped: moderate confidence contradicts "
                "low criteria met ratio",
                payer=payer_name,
                raw_likelihood=raw_likelihood,
                capped_likelihood=capped,
                met_ratio=met_ratio,
                met_count=met_count,
                total_count=total_count,
            )
            return capped

        # Flag if LLM claims very low likelihood but most criteria are met
        if likelihood < 0.2 and met_ratio > 0.8:
            floored = max(likelihood, 0.5)
            logger.warning(
                "Approval likelihood raised: LLM claimed very low confidence but "
                "most criteria are met",
                payer=payer_name,
                raw_likelihood=raw_likelihood,
                adjusted_likelihood=floored,
                met_count=met_count,
                total_count=total_count,
            )
            return floored

        return likelihood

    def _apply_conservative_status_mapping(
        self,
        status_str: str,
        approval_likelihood: float
    ) -> CoverageStatus:
        """
        Apply conservative decision model to coverage status.

        Following Anthropic's prior-auth-review-skill pattern:
        - AI should NEVER recommend DENY
        - NOT_COVERED maps to REQUIRES_HUMAN_REVIEW
        - Low confidence also triggers human review

        Args:
            status_str: Raw status string from LLM
            approval_likelihood: Confidence score 0.0-1.0

        Returns:
            Mapped CoverageStatus (conservative)
        """
        # Try to parse the status
        try:
            coverage_status = CoverageStatus(status_str.lower())
        except ValueError:
            # Unknown status - requires human review
            logger.warning(
                "Unknown coverage status from LLM",
                status=status_str,
                mapping_to="requires_human_review"
            )
            return CoverageStatus.REQUIRES_HUMAN_REVIEW

        # CRITICAL: Apply conservative mapping
        # AI should NEVER recommend denial - map to human review
        if coverage_status == CoverageStatus.NOT_COVERED:
            logger.info(
                "Conservative mapping: NOT_COVERED -> REQUIRES_HUMAN_REVIEW",
                original_status=status_str,
                reason="AI cannot recommend denial - human must decide"
            )
            return CoverageStatus.REQUIRES_HUMAN_REVIEW

        # Low confidence also triggers human review
        if approval_likelihood < 0.3:
            logger.info(
                "Conservative mapping: Low confidence -> REQUIRES_HUMAN_REVIEW",
                original_status=status_str,
                likelihood=approval_likelihood,
                reason="Low approval likelihood requires human review"
            )
            return CoverageStatus.REQUIRES_HUMAN_REVIEW

        # Borderline cases get PEND instead of denial
        if coverage_status == CoverageStatus.UNKNOWN and approval_likelihood < 0.5:
            logger.info(
                "Conservative mapping: UNKNOWN with low likelihood -> REQUIRES_HUMAN_REVIEW",
                original_status=status_str,
                likelihood=approval_likelihood
            )
            return CoverageStatus.REQUIRES_HUMAN_REVIEW

        # Log passthrough for audit trail
        logger.debug(
            "Coverage status preserved",
            original=status_str,
            result=coverage_status.value,
            likelihood=approval_likelihood
        )

        return coverage_status

    async def identify_gaps(
        self,
        case_summary: Dict[str, Any],
        coverage_assessment: CoverageAssessment,
        available_documents: list
    ) -> list:
        """
        Identify documentation gaps in a case.

        Args:
            case_summary: Summary of the case
            coverage_assessment: Previous coverage assessment
            available_documents: List of available documentation

        Returns:
            List of documentation gaps
        """
        prompt = self.prompt_loader.load(
            "policy_analysis/gap_identification.txt",
            {
                "case_summary": case_summary,
                "coverage_assessment": coverage_assessment.model_dump(),
                "available_documents": available_documents
            }
        )

        result = await self.llm_gateway.analyze_policy(prompt=prompt)

        gaps = []
        for g in result.get("gaps", []):
            gaps.append(DocumentationGap(
                gap_id=g.get("gap_id", ""),
                gap_type=g.get("gap_type", "other"),
                description=g.get("description", ""),
                required_for=g.get("required_for_criteria", []),
                priority=g.get("impact_on_approval", "medium"),
                suggested_action=g.get("suggested_resolution", {}).get("action", ""),
                estimated_resolution_complexity=g.get("suggested_resolution", {}).get(
                    "estimated_complexity", "medium"
                )
            ))

        return gaps


# Global instance
_policy_reasoner: Optional[PolicyReasoner] = None


def get_policy_reasoner() -> PolicyReasoner:
    """Get or create the global Policy Reasoner instance."""
    global _policy_reasoner
    if _policy_reasoner is None:
        _policy_reasoner = PolicyReasoner()
    return _policy_reasoner
