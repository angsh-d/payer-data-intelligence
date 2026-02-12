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

        Uses criterion_name matching to reconcile criteria whose IDs changed
        between versions (e.g. PRESCRIBER_SPECIALTY → PRESCRIBER_SPEC).
        Without this, renamed criteria appear as remove+add instead of unchanged.

        Returns (affected_criterion_ids, criteria_detail_list).
        """
        # Build lookup maps: criterion_id -> CriterionAssessment
        old_map: Dict[str, CriterionAssessment] = {
            c.criterion_id: c for c in old_assessment.criteria_assessments
        }
        new_map: Dict[str, CriterionAssessment] = {
            c.criterion_id: c for c in new_assessment.criteria_assessments
        }

        # Build name-based mapping to reconcile IDs that changed between versions.
        # old_to_new[old_id] = new_id when criterion names match but IDs differ.
        old_name_to_id: Dict[str, str] = {}
        for c in old_assessment.criteria_assessments:
            name = (c.criterion_name or "").strip().lower()
            if name:
                old_name_to_id[name] = c.criterion_id

        new_name_to_id: Dict[str, str] = {}
        for c in new_assessment.criteria_assessments:
            name = (c.criterion_name or "").strip().lower()
            if name:
                new_name_to_id[name] = c.criterion_id

        old_to_new: Dict[str, str] = {}
        new_to_old: Dict[str, str] = {}

        # Unmatched old IDs (not directly in new_map)
        unmatched_old = {oid for oid in old_map if oid not in new_map}
        unmatched_new = {nid for nid in new_map if nid not in old_map}

        # Pass 1: exact name match
        for old_name, old_id in old_name_to_id.items():
            if old_id in unmatched_old and old_name in new_name_to_id:
                new_id = new_name_to_id[old_name]
                if new_id in unmatched_new:
                    old_to_new[old_id] = new_id
                    new_to_old[new_id] = old_id
                    unmatched_old.discard(old_id)
                    unmatched_new.discard(new_id)

        # Pass 2: fuzzy name match — one name contains the other
        if unmatched_old and unmatched_new:
            for old_id in list(unmatched_old):
                old_c = old_map[old_id]
                old_name = (old_c.criterion_name or "").strip().lower()
                if not old_name:
                    continue
                best_new_id = None
                for new_id in unmatched_new:
                    new_c = new_map[new_id]
                    new_name = (new_c.criterion_name or "").strip().lower()
                    if not new_name:
                        continue
                    if old_name in new_name or new_name in old_name:
                        best_new_id = new_id
                        break
                if best_new_id:
                    old_to_new[old_id] = best_new_id
                    new_to_old[best_new_id] = old_id
                    unmatched_old.discard(old_id)
                    unmatched_new.discard(best_new_id)

        # Get criterion IDs that changed in the policy diff
        all_changes = diff.criterion_changes + diff.step_therapy_changes + diff.exclusion_changes
        changed_criterion_ids = {
            c.criterion_id for c in all_changes
            if c.change_type.value != "unchanged"
        }

        affected = []
        criteria_detail = []

        # Track which new IDs we've already compared (via name-matched pairs)
        matched_new_ids: set = set()
        processed_old_ids: set = set()

        # First pass: process old criteria
        for old_id, old_c in old_map.items():
            processed_old_ids.add(old_id)

            # Direct match: same ID in both versions
            new_c = new_map.get(old_id)
            matched_new_id = old_id

            # Name-based match: ID renamed between versions
            if not new_c and old_id in old_to_new:
                matched_new_id = old_to_new[old_id]
                new_c = new_map.get(matched_new_id)

            if new_c:
                matched_new_ids.add(matched_new_id)
                # Both exist — compare
                if old_c.is_met != new_c.is_met:
                    affected.append(matched_new_id)
                    criteria_detail.append({
                        "criterion_id": matched_new_id,
                        "criterion_name": new_c.criterion_name or old_c.criterion_name,
                        "change": "verdict_flip",
                        "old_met": old_c.is_met,
                        "new_met": new_c.is_met,
                        "confidence_change": new_c.confidence - old_c.confidence,
                    })
                elif matched_new_id in changed_criterion_ids or old_id in changed_criterion_ids:
                    confidence_delta = new_c.confidence - old_c.confidence
                    if abs(confidence_delta) > 0.15:
                        affected.append(matched_new_id)
                        criteria_detail.append({
                            "criterion_id": matched_new_id,
                            "criterion_name": new_c.criterion_name or old_c.criterion_name,
                            "change": "confidence_shift",
                            "old_met": old_c.is_met,
                            "new_met": new_c.is_met,
                            "confidence_change": confidence_delta,
                        })
            else:
                # Truly removed (no match by ID or name)
                affected.append(old_id)
                criteria_detail.append({
                    "criterion_id": old_id,
                    "criterion_name": old_c.criterion_name,
                    "change": "removed",
                    "old_met": old_c.is_met,
                    "new_met": None,
                    "confidence_change": -old_c.confidence,
                })

        # Second pass: new criteria not matched to any old one
        for new_id, new_c in new_map.items():
            if new_id in matched_new_ids or new_id in processed_old_ids:
                continue
            if new_id in new_to_old:
                continue  # Already handled via name match
            affected.append(new_id)
            criteria_detail.append({
                "criterion_id": new_id,
                "criterion_name": new_c.criterion_name,
                "change": "added",
                "old_met": None,
                "new_met": new_c.is_met,
                "confidence_change": new_c.confidence,
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
