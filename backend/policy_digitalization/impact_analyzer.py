"""Policy Impact Analyzer — assesses which active cases are affected by policy changes.

LLM-first approach: runs authoritative v1 assessment via PolicyReasoner, then
projects v2 using a single LLM call that receives the v1 results + explicit diff
changes + v2 criteria. This ensures removed barriers produce positive impact.
"""

import json
from typing import Dict, List, Optional, Any

from pydantic import BaseModel, Field

from backend.models.policy_schema import DigitizedPolicy
from backend.models.coverage import CoverageAssessment, CriterionAssessment
from backend.models.enums import CoverageStatus, TaskCategory
from backend.policy_digitalization.differ import PolicyDiffResult, ChangeType
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
        improved = 0
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
                # v1 authoritative assessment + LLM-projected v2
                old_assessment, new_assessment = await self._lazy_assess(
                    patient_data, old_policy, new_policy, patient_id, diff
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
            elif risk_level == "improved":
                improved += 1
            elif risk_level == "at_risk":
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
        if improved > 0:
            action_items.append(
                f"POSITIVE: {improved} case(s) improved under new policy — review for PA submission"
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
            improved=improved,
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

        # Significant likelihood gain (>0.15) — patient outlook improved
        likelihood_gain = -likelihood_drop  # positive when likelihood increased
        if likelihood_gain > 0.15 and affected_criteria:
            return (
                "improved",
                f"approval likelihood improved by {likelihood_gain:.0%}; review removed barriers and consider submitting PA",
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
        diff: PolicyDiffResult,
    ) -> tuple:
        """Authoritative v1 assessment + LLM-projected v2.

        1. Runs PolicyReasoner against v1 (full LLM evaluation — authoritative baseline).
        2. Projects v2 via a single LLM call that receives v1 results + diff + v2 criteria.
        """
        try:
            from backend.reasoning.policy_reasoner import get_policy_reasoner

            reasoner = get_policy_reasoner()
            payer = old_policy.payer_name
            med_info = {
                "medication_name": old_policy.medication_name,
            }

            # Step 1: Authoritative v1 assessment
            old_result = await reasoner.assess_coverage(
                patient_info=patient_data,
                medication_info=med_info,
                payer_name=payer,
                digitized_policy=old_policy,
            )

            # Step 2: Project v2 from v1 + diff
            new_result = await self._project_v2_assessment(
                v1_assessment=old_result,
                diff=diff,
                new_policy=new_policy,
                patient_data=patient_data,
                patient_id=patient_id,
            )

            return old_result, new_result
        except Exception as e:
            logger.error(
                "Assessment failed for patient",
                patient_id=patient_id,
                error=str(e),
            )
            return None, None

    async def _project_v2_assessment(
        self,
        v1_assessment: CoverageAssessment,
        diff: PolicyDiffResult,
        new_policy: DigitizedPolicy,
        patient_data: Dict[str, Any],
        patient_id: str,
    ) -> CoverageAssessment:
        """Project v2 coverage by applying diff to v1 results via LLM."""
        from backend.reasoning.policy_reasoner import get_policy_reasoner
        from backend.reasoning.llm_gateway import get_llm_gateway
        from backend.reasoning.prompt_loader import get_prompt_loader

        # Collect all changes across criterion, step therapy, and exclusion changes
        all_changes = diff.criterion_changes + diff.step_therapy_changes + diff.exclusion_changes
        has_meaningful_changes = any(
            c.change_type.value in ("added", "removed", "modified")
            for c in all_changes
        )

        # Short-circuit: no meaningful changes → return copy of v1
        if not has_meaningful_changes:
            logger.info("No meaningful diff changes, returning v1 as projected v2", patient_id=patient_id)
            return v1_assessment.model_copy(deep=True)

        # Format inputs for the projection prompt
        v1_criteria_text = self._format_v1_criteria_for_projection(v1_assessment)
        removed_text, added_text, modified_text, unchanged_ids_text = self._format_diff_for_projection(
            diff, v1_assessment, new_policy
        )

        # Get v2 criteria structure
        reasoner = get_policy_reasoner()
        v2_criteria_text = reasoner._format_policy_criteria(new_policy)

        # Load and populate prompt
        prompt_loader = get_prompt_loader()
        prompt = prompt_loader.load(
            "policy_analysis/impact_projection.txt",
            {
                "patient_info": json.dumps(patient_data, indent=2, default=str),
                "v1_coverage_status": v1_assessment.coverage_status.value,
                "v1_approval_likelihood": str(v1_assessment.approval_likelihood),
                "v1_criteria_met_count": str(v1_assessment.criteria_met_count),
                "v1_criteria_total_count": str(v1_assessment.criteria_total_count),
                "v1_criteria_assessments": v1_criteria_text,
                "removed_criteria": removed_text,
                "added_criteria": added_text,
                "modified_criteria": modified_text,
                "unchanged_criteria_ids": unchanged_ids_text,
                "v2_policy_criteria": v2_criteria_text,
            },
        )

        # Call LLM for projection
        gateway = get_llm_gateway()
        llm_result = await gateway.generate(
            task_category=TaskCategory.POLICY_REASONING,
            prompt=prompt,
            temperature=0.0,
            response_format="json",
        )

        logger.info(
            "V2 projection LLM call complete",
            patient_id=patient_id,
            provider=llm_result.get("provider", "unknown"),
        )

        return self._parse_projected_assessment(llm_result, v1_assessment, patient_id)

    def _format_v1_criteria_for_projection(self, v1_assessment: CoverageAssessment) -> str:
        """Format v1 per-criterion assessments as structured text for the projection prompt."""
        lines = []
        for c in v1_assessment.criteria_assessments:
            lines.append(f"- {c.criterion_id}: {c.criterion_name}")
            lines.append(f"  is_met: {str(c.is_met).lower()} | confidence: {c.confidence}")
            if c.supporting_evidence:
                lines.append(f"  evidence: {'; '.join(c.supporting_evidence[:3])}")
            if c.gaps:
                lines.append(f"  gaps: {'; '.join(c.gaps[:3])}")
            lines.append(f"  reasoning: {c.reasoning}")
        return "\n".join(lines) if lines else "No criteria assessments available."

    def _format_diff_for_projection(
        self,
        diff: PolicyDiffResult,
        v1_assessment: CoverageAssessment,
        new_policy: DigitizedPolicy,
    ) -> tuple:
        """Categorize diff changes and format for the projection prompt.

        Returns (removed_text, added_text, modified_text, unchanged_ids_text).
        """
        # Build v1 assessment lookup
        v1_map: Dict[str, CriterionAssessment] = {
            c.criterion_id: c for c in v1_assessment.criteria_assessments
        }

        all_changes = diff.criterion_changes + diff.step_therapy_changes + diff.exclusion_changes

        removed_lines = []
        added_lines = []
        modified_lines = []
        unchanged_ids = []

        for change in all_changes:
            cid = change.criterion_id

            if change.change_type == ChangeType.REMOVED:
                v1_c = v1_map.get(cid)
                met_status = "PASSED (is_met=true)" if (v1_c and v1_c.is_met) else "FAILED (is_met=false)"
                removed_lines.append(f"- {cid}: {change.criterion_name}")
                removed_lines.append(f"  Patient v1 status: {met_status}")
                if v1_c:
                    removed_lines.append(f"  v1 reasoning: {v1_c.reasoning}")

            elif change.change_type == ChangeType.ADDED:
                added_lines.append(f"- {cid}: {change.criterion_name}")
                added_lines.append(f"  Severity: {change.severity}")
                # Include full criterion details from new_policy
                ac = new_policy.atomic_criteria.get(cid)
                if ac:
                    added_lines.append(f"  Description: {ac.description}")
                    added_lines.append(f"  Type: {ac.criterion_type}")
                    added_lines.append(f"  Required: {ac.is_required}")
                    if ac.threshold_value is not None:
                        op = getattr(ac, 'comparison_operator', '')
                        unit = getattr(ac, 'threshold_unit', '') or ''
                        added_lines.append(f"  Threshold: {op} {ac.threshold_value} {unit}".strip())
                elif change.new_value:
                    added_lines.append(f"  Details: {json.dumps(change.new_value, default=str)}")

            elif change.change_type == ChangeType.MODIFIED:
                modified_lines.append(f"- {cid}: {change.criterion_name}")
                modified_lines.append(f"  Severity: {change.severity}")
                for fc in change.field_changes:
                    modified_lines.append(f"  {fc.field_name}: {fc.old} → {fc.new}")

            elif change.change_type == ChangeType.UNCHANGED:
                unchanged_ids.append(cid)

        removed_text = "\n".join(removed_lines) if removed_lines else "None — no criteria were removed."
        added_text = "\n".join(added_lines) if added_lines else "None — no criteria were added."
        modified_text = "\n".join(modified_lines) if modified_lines else "None — no criteria were modified."
        unchanged_text = ", ".join(unchanged_ids) if unchanged_ids else "None — all criteria changed."

        return removed_text, added_text, modified_text, unchanged_text

    def _parse_projected_assessment(
        self,
        llm_result: Dict[str, Any],
        v1_assessment: CoverageAssessment,
        patient_id: str,
    ) -> CoverageAssessment:
        """Parse LLM projection response into a CoverageAssessment."""
        from uuid import uuid4

        # Extract JSON from response
        raw = llm_result.get("response")
        if raw is None:
            # Already parsed as dict
            data = llm_result
        elif isinstance(raw, str):
            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            data = json.loads(clean)
        elif isinstance(raw, dict):
            data = raw
        else:
            data = llm_result

        # Parse projected status with conservative mapping
        status_str = data.get("projected_coverage_status", "requires_human_review")
        try:
            coverage_status = CoverageStatus(status_str.lower())
        except ValueError:
            coverage_status = CoverageStatus.REQUIRES_HUMAN_REVIEW

        # Conservative: never recommend denial
        if coverage_status == CoverageStatus.NOT_COVERED:
            coverage_status = CoverageStatus.REQUIRES_HUMAN_REVIEW

        # Parse criteria assessments (excluding removed criteria)
        criteria = []
        for c in data.get("criteria_assessments", []):
            source = c.get("projection_source", "unknown")
            # Skip removed criteria that may have leaked through
            if source == "removed":
                continue
            criteria.append(CriterionAssessment(
                criterion_id=c.get("criterion_id", str(uuid4())),
                criterion_name=c.get("criterion_name", "Unknown"),
                criterion_description=c.get("reasoning", ""),
                is_met=c.get("is_met", False),
                confidence=c.get("confidence", 0.5),
                supporting_evidence=c.get("supporting_evidence", []),
                gaps=c.get("gaps", []),
                reasoning=c.get("reasoning", ""),
            ))

        met_count = sum(1 for c in criteria if c.is_met)

        # Store impact_summary in llm_raw_response for downstream consumers
        impact_summary = data.get("impact_summary", {})

        # Parse projected likelihood from LLM
        projected_likelihood = float(data.get("projected_approval_likelihood", v1_assessment.approval_likelihood))
        projected_likelihood = max(0.0, min(1.0, projected_likelihood))

        # ── Programmatic enforcement: likelihood MUST reflect v2 criteria reality ──
        # Compute v2 met_ratio from the projected criteria (not v1)
        v2_total = len(criteria) if criteria else 1
        v2_met_ratio = met_count / v2_total

        # If LLM returned likelihood that contradicts the v2 met_ratio, recalculate
        # based on actual projected criteria results (same logic as PolicyReasoner)
        if projected_likelihood > 0.85 and v2_met_ratio < 0.5:
            projected_likelihood = min(projected_likelihood, v2_met_ratio + 0.1)
            logger.warning(
                "Projected likelihood capped: high confidence but low v2 met_ratio",
                patient_id=patient_id, raw=data.get("projected_approval_likelihood"),
                capped=projected_likelihood, v2_met_ratio=v2_met_ratio,
            )
        elif projected_likelihood < 0.2 and v2_met_ratio > 0.8:
            projected_likelihood = max(projected_likelihood, 0.5)

        # CRITICAL: If failed barriers were removed, likelihood MUST exceed v1
        removed_barriers = impact_summary.get("removed_barriers", [])
        if removed_barriers:
            v1_likelihood = v1_assessment.approval_likelihood
            if projected_likelihood <= v1_likelihood:
                # Calculate floor: v1 + proportional boost per removed barrier
                # Each removed failed barrier lifts likelihood by a fraction of
                # the remaining gap to 1.0
                gap_to_full = 1.0 - v1_likelihood
                boost_per_barrier = gap_to_full * 0.15  # 15% of remaining gap per barrier
                total_boost = len(removed_barriers) * boost_per_barrier
                floor = min(v1_likelihood + max(total_boost, 0.08), 0.95)
                logger.warning(
                    "Enforcing likelihood increase for removed barriers",
                    patient_id=patient_id,
                    v1_likelihood=v1_likelihood,
                    llm_projected=projected_likelihood,
                    enforced_floor=floor,
                    removed_barriers=removed_barriers,
                )
                projected_likelihood = floor

        # Also reconcile likelihood with v2 met_ratio: if most v2 criteria are met,
        # likelihood should reflect that (not be dragged down by stale v1 value)
        if v2_met_ratio >= 0.7 and projected_likelihood < 0.5:
            reconciled = v2_met_ratio * 0.85
            logger.warning(
                "Reconciling low projected likelihood with high v2 met_ratio",
                patient_id=patient_id, projected=projected_likelihood,
                reconciled=reconciled, v2_met_ratio=v2_met_ratio,
            )
            projected_likelihood = reconciled

        projected_likelihood = max(0.0, min(1.0, projected_likelihood))

        assessment = CoverageAssessment(
            assessment_id=str(uuid4()),
            payer_name=v1_assessment.payer_name,
            policy_name=v1_assessment.policy_name,
            medication_name=v1_assessment.medication_name,
            coverage_status=coverage_status,
            approval_likelihood=projected_likelihood,
            approval_likelihood_reasoning=data.get("projection_reasoning", ""),
            criteria_assessments=criteria,
            criteria_met_count=met_count,
            criteria_total_count=len(criteria),
            documentation_gaps=v1_assessment.documentation_gaps,
            recommendations=v1_assessment.recommendations,
            step_therapy_required=v1_assessment.step_therapy_required,
            step_therapy_options=v1_assessment.step_therapy_options,
            step_therapy_satisfied=v1_assessment.step_therapy_satisfied,
            raw_policy_text=v1_assessment.raw_policy_text,
            llm_raw_response={"impact_summary": impact_summary, "projection_data": data},
        )

        logger.info(
            "Parsed projected v2 assessment",
            patient_id=patient_id,
            v1_status=v1_assessment.coverage_status.value,
            v2_status=coverage_status.value,
            v1_likelihood=v1_assessment.approval_likelihood,
            v2_likelihood=projected_likelihood,
            net_impact=impact_summary.get("net_impact", "unknown"),
        )

        return assessment
