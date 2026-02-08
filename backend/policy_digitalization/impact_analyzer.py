"""Policy Impact Analyzer — assesses which active cases are affected by policy changes.

LLM-first approach: compares pre-computed CoverageAssessment objects (from Claude)
rather than running a deterministic evaluator. When pre-computed assessments are not
available, runs PolicyReasoner.assess_coverage() lazily against both policy versions.
"""

from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field

from backend.models.policy_schema import DigitizedPolicy
from backend.models.coverage import CoverageAssessment, CriterionAssessment
from backend.models.enums import CoverageStatus
from backend.policy_digitalization.differ import PolicyDiffResult
from backend.config.logging_config import get_logger

logger = get_logger(__name__)

# Coverage statuses that indicate approval/met
_POSITIVE_STATUSES = {
    CoverageStatus.COVERED,
    CoverageStatus.LIKELY_COVERED,
    CoverageStatus.REQUIRES_PA,
}

# Coverage statuses that indicate denial/not met
_NEGATIVE_STATUSES = {
    CoverageStatus.NOT_COVERED,
    CoverageStatus.REQUIRES_HUMAN_REVIEW,
}


class PatientImpact(BaseModel):
    patient_id: str
    case_id: Optional[str] = None
    patient_name: str = ""
    current_status: str = "unknown"
    projected_status: str = "unknown"
    current_likelihood: float = 0.0
    projected_likelihood: float = 0.0
    verdict_changed: bool = False
    affected_criteria: List[str] = Field(default_factory=list)
    risk_level: str = "no_impact"  # verdict_flip, at_risk, improved, no_impact
    recommended_action: str = "no action needed"
    criteria_detail: List[Dict[str, Any]] = Field(default_factory=list)


class PolicyImpactReport(BaseModel):
    diff: PolicyDiffResult
    total_active_cases: int = 0
    impacted_cases: int = 0
    verdict_flips: int = 0
    at_risk_cases: int = 0
    patient_impacts: List[PatientImpact] = Field(default_factory=list)
    action_items: List[str] = Field(default_factory=list)


class PolicyImpactAnalyzer:
    """Analyzes impact of policy changes on active cases using LLM-first assessments."""

    async def analyze_impact(
        self,
        diff: PolicyDiffResult,
        old_policy: DigitizedPolicy,
        new_policy: DigitizedPolicy,
        active_cases: List[Dict[str, Any]],
        old_assessments: Optional[Dict[str, CoverageAssessment]] = None,
        new_assessments: Optional[Dict[str, CoverageAssessment]] = None,
    ) -> PolicyImpactReport:
        """
        Analyze impact of policy changes on active cases.

        When old_assessments/new_assessments are provided (keyed by patient_id),
        compares them directly — no LLM calls needed.

        When not provided, runs PolicyReasoner.assess_coverage() against both
        policy versions for each patient (lazy LLM evaluation).
        """
        logger.info("Analyzing policy impact", cases_count=len(active_cases))

        old_assessments = old_assessments or {}
        new_assessments = new_assessments or {}

        patient_impacts = []
        verdict_flips = 0
        at_risk = 0
        evaluated_count = 0

        for case in active_cases:
            patient_data = case.get("patient") or case.get("patient_data") or {}
            case_id = case.get("case_id")
            patient_id = patient_data.get("patient_id", case_id or "unknown")
            patient_name = self._get_patient_name(patient_data)

            if not patient_data:
                logger.debug("Skipping case with empty patient_data", case_id=case_id)
                continue

            evaluated_count += 1

            # Get or compute assessments for this patient
            old_assessment = old_assessments.get(patient_id)
            new_assessment = new_assessments.get(patient_id)

            if not old_assessment or not new_assessment:
                # Lazy LLM evaluation — run coverage assessment against both versions
                old_assessment, new_assessment = await self._lazy_assess(
                    patient_data, old_policy, new_policy, patient_id
                )

            if not old_assessment or not new_assessment:
                logger.warning("Could not assess patient", patient_id=patient_id)
                continue

            # Compare coverage statuses
            old_status = old_assessment.coverage_status
            new_status = new_assessment.coverage_status
            old_positive = old_status in _POSITIVE_STATUSES
            new_positive = new_status in _POSITIVE_STATUSES
            old_negative = old_status in _NEGATIVE_STATUSES
            new_negative = new_status in _NEGATIVE_STATUSES

            verdict_changed = old_status != new_status

            # Find criteria that flipped between versions
            affected_criteria, criteria_detail = self._compare_criteria_assessments(
                old_assessment, new_assessment, diff
            )

            # Classify risk based on coverage status changes and likelihood shifts
            likelihood_drop = old_assessment.approval_likelihood - new_assessment.approval_likelihood
            risk_level, recommended_action = self._classify_risk(
                old_status, new_status, old_positive, new_negative,
                affected_criteria, likelihood_drop, verdict_changed
            )

            if risk_level == "verdict_flip":
                verdict_flips += 1
            elif risk_level in ("at_risk", "improved"):
                at_risk += 1

            patient_impacts.append(PatientImpact(
                patient_id=patient_id,
                case_id=case_id,
                patient_name=patient_name,
                current_status=old_status.value,
                projected_status=new_status.value,
                current_likelihood=old_assessment.approval_likelihood,
                projected_likelihood=new_assessment.approval_likelihood,
                verdict_changed=verdict_changed,
                affected_criteria=affected_criteria,
                risk_level=risk_level,
                recommended_action=recommended_action,
                criteria_detail=criteria_detail,
            ))

        impacted = sum(1 for p in patient_impacts if p.risk_level != "no_impact")

        # Build action items
        action_items = []
        if verdict_flips > 0:
            action_items.append(
                f"URGENT: {verdict_flips} case(s) may flip from APPROVED to NOT MET under new policy"
            )
        if at_risk > 0:
            action_items.append(
                f"WARNING: {at_risk} case(s) at risk — gather additional documentation"
            )
        if diff.summary.breaking_changes > 0:
            action_items.append(
                f"Review {diff.summary.breaking_changes} breaking change(s) in policy"
            )

        report = PolicyImpactReport(
            diff=diff,
            total_active_cases=evaluated_count,
            impacted_cases=impacted,
            verdict_flips=verdict_flips,
            at_risk_cases=at_risk,
            patient_impacts=patient_impacts,
            action_items=action_items,
        )

        logger.info(
            "Impact analysis complete",
            total=len(active_cases),
            impacted=impacted,
            verdict_flips=verdict_flips,
            at_risk=at_risk,
        )

        return report

    def _classify_risk(
        self,
        old_status: CoverageStatus,
        new_status: CoverageStatus,
        old_positive: bool,
        new_negative: bool,
        affected_criteria: List[str],
        likelihood_drop: float,
        verdict_changed: bool,
    ) -> tuple:
        """Classify risk level and recommend action."""
        # Verdict flip: was positive, now negative
        if verdict_changed and old_positive and new_negative:
            return (
                "verdict_flip",
                "re-evaluate case immediately; prepare preemptive appeal",
            )

        # Improved: was negative, now positive
        if verdict_changed and not old_positive and not new_negative:
            return (
                "improved",
                "patient now meets criteria under new policy; submit PA",
            )

        # Significant likelihood drop (>0.2) even if status didn't change
        if likelihood_drop > 0.2 and affected_criteria:
            return (
                "at_risk",
                f"approval likelihood dropped by {likelihood_drop:.0%}; review {len(affected_criteria)} changed criteria",
            )

        # Criteria changed but overall status the same
        if verdict_changed:
            return (
                "at_risk",
                "coverage status changed between policy versions; review criteria",
            )

        if affected_criteria:
            return (
                "at_risk",
                "individual criteria changed though overall status stable; gather documentation for changed criteria",
            )

        return ("no_impact", "no action needed")

    def _get_patient_name(self, patient_data: Dict) -> str:
        """Extract patient name from data."""
        first = patient_data.get("first_name") or patient_data.get("demographics", {}).get("first_name", "")
        last = patient_data.get("last_name") or patient_data.get("demographics", {}).get("last_name", "")
        return f"{first} {last}".strip() or "Unknown"

    def _compare_criteria_assessments(
        self,
        old_assessment: CoverageAssessment,
        new_assessment: CoverageAssessment,
        diff: PolicyDiffResult,
    ) -> tuple:
        """Compare per-criterion assessments between two versions.

        Returns (affected_criterion_ids, criteria_detail_list).
        """
        # Build lookup maps: criterion_id -> CriterionAssessment
        old_map: Dict[str, CriterionAssessment] = {
            c.criterion_id: c for c in old_assessment.criteria_assessments
        }
        new_map: Dict[str, CriterionAssessment] = {
            c.criterion_id: c for c in new_assessment.criteria_assessments
        }

        # Get criterion IDs that changed in the policy diff
        all_changes = diff.criterion_changes + diff.step_therapy_changes + diff.exclusion_changes
        changed_criterion_ids = {
            c.criterion_id for c in all_changes
            if c.change_type.value != "unchanged"
        }

        affected = []
        criteria_detail = []
        all_cids = set(old_map.keys()) | set(new_map.keys())

        for cid in all_cids:
            old_c = old_map.get(cid)
            new_c = new_map.get(cid)

            # Criterion only in old (removed)
            if old_c and not new_c:
                affected.append(cid)
                criteria_detail.append({
                    "criterion_id": cid,
                    "criterion_name": old_c.criterion_name,
                    "change": "removed",
                    "old_met": old_c.is_met,
                    "new_met": None,
                    "confidence_change": -old_c.confidence,
                })
                continue

            # Criterion only in new (added)
            if new_c and not old_c:
                affected.append(cid)
                criteria_detail.append({
                    "criterion_id": cid,
                    "criterion_name": new_c.criterion_name,
                    "change": "added",
                    "old_met": None,
                    "new_met": new_c.is_met,
                    "confidence_change": new_c.confidence,
                })
                continue

            # Both exist — check for verdict flip or confidence change
            if old_c.is_met != new_c.is_met:
                affected.append(cid)
                criteria_detail.append({
                    "criterion_id": cid,
                    "criterion_name": old_c.criterion_name,
                    "change": "verdict_flip",
                    "old_met": old_c.is_met,
                    "new_met": new_c.is_met,
                    "confidence_change": new_c.confidence - old_c.confidence,
                })
            elif cid in changed_criterion_ids:
                # Policy criterion changed but verdict didn't flip yet
                confidence_delta = new_c.confidence - old_c.confidence
                if abs(confidence_delta) > 0.15:
                    affected.append(cid)
                    criteria_detail.append({
                        "criterion_id": cid,
                        "criterion_name": old_c.criterion_name,
                        "change": "confidence_shift",
                        "old_met": old_c.is_met,
                        "new_met": new_c.is_met,
                        "confidence_change": confidence_delta,
                    })

        return affected, criteria_detail

    async def _lazy_assess(
        self,
        patient_data: Dict[str, Any],
        old_policy: DigitizedPolicy,
        new_policy: DigitizedPolicy,
        patient_id: str,
    ) -> tuple:
        """Run PolicyReasoner against both policy versions when pre-computed assessments unavailable.

        Passes the version-specific DigitizedPolicy to each assessment call so
        Claude evaluates against the correct set of criteria for that version.
        """
        try:
            from backend.reasoning.policy_reasoner import get_policy_reasoner

            reasoner = get_policy_reasoner()
            payer = old_policy.payer_name
            med_info = {
                "medication_name": old_policy.medication_name,
            }

            old_result = await reasoner.assess_coverage(
                patient_info=patient_data,
                medication_info=med_info,
                payer_name=payer,
                digitized_policy=old_policy,
            )
            new_result = await reasoner.assess_coverage(
                patient_info=patient_data,
                medication_info=med_info,
                payer_name=payer,
                digitized_policy=new_policy,
            )
            return old_result, new_result
        except Exception as e:
            logger.error(
                "Lazy assessment failed for patient",
                patient_id=patient_id,
                error=str(e),
            )
            return None, None
