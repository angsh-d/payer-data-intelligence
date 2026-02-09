"""Policy Differ — compares two DigitizedPolicy versions."""

import json
from enum import Enum
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from backend.models.policy_schema import DigitizedPolicy, AtomicCriterion
from backend.config.logging_config import get_logger

logger = get_logger(__name__)


class ChangeType(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    MOVED = "moved"
    UNCHANGED = "unchanged"


class FieldChange(BaseModel):
    field_name: str
    old: Optional[str] = None
    new: Optional[str] = None


class CriterionChange(BaseModel):
    criterion_id: str
    criterion_name: str
    change_type: ChangeType
    old_value: Optional[Dict] = None
    new_value: Optional[Dict] = None
    field_changes: List[FieldChange] = Field(default_factory=list)
    severity: str = "minor"  # breaking, material, minor, cosmetic
    human_summary: str = ""


class IndicationChange(BaseModel):
    indication_id: str
    indication_name: str
    change_type: ChangeType
    field_changes: List[FieldChange] = Field(default_factory=list)
    severity: str = "minor"


class PolicyDiffSummary(BaseModel):
    total_criteria_old: int = 0
    total_criteria_new: int = 0
    added_count: int = 0
    removed_count: int = 0
    modified_count: int = 0
    unchanged_count: int = 0
    breaking_changes: int = 0
    material_changes: int = 0
    severity_assessment: str = "low_impact"


class PolicyDiffResult(BaseModel):
    old_version: str = ""
    new_version: str = ""
    policy_id: str = ""
    payer: str = ""
    medication: str = ""
    diff_timestamp: str = ""
    summary: PolicyDiffSummary = Field(default_factory=PolicyDiffSummary)
    indication_changes: List[IndicationChange] = Field(default_factory=list)
    step_therapy_changes: List[CriterionChange] = Field(default_factory=list)
    exclusion_changes: List[CriterionChange] = Field(default_factory=list)
    criterion_changes: List[CriterionChange] = Field(default_factory=list)


class PolicyDiffer:
    """Compares two DigitizedPolicy versions and produces a structured diff."""

    async def diff(self, old: DigitizedPolicy, new: DigitizedPolicy) -> PolicyDiffResult:
        """Diff two policy versions using LLM-powered semantic matching."""
        from datetime import datetime, timezone

        criterion_changes = await self._diff_criteria(old.atomic_criteria, new.atomic_criteria)
        indication_changes = self._diff_indications(old.indications, new.indications)
        step_therapy_changes = self._diff_step_therapy(old.step_therapy_requirements, new.step_therapy_requirements)
        exclusion_changes = self._diff_exclusions(old.exclusions, new.exclusions)

        # Build summary — aggregate all change types including indications
        all_changes = criterion_changes + step_therapy_changes + exclusion_changes
        added = sum(1 for c in all_changes if c.change_type == ChangeType.ADDED)
        removed = sum(1 for c in all_changes if c.change_type == ChangeType.REMOVED)
        modified = sum(1 for c in all_changes if c.change_type == ChangeType.MODIFIED)
        unchanged = sum(1 for c in all_changes if c.change_type == ChangeType.UNCHANGED)
        breaking = sum(1 for c in all_changes if c.severity == "breaking")
        material = sum(1 for c in all_changes if c.severity == "material")
        # Also count indication changes (different model type but same severity/change_type fields)
        added += sum(1 for c in indication_changes if c.change_type == ChangeType.ADDED)
        removed += sum(1 for c in indication_changes if c.change_type == ChangeType.REMOVED)
        modified += sum(1 for c in indication_changes if c.change_type == ChangeType.MODIFIED)
        breaking += sum(1 for c in indication_changes if c.severity == "breaking")
        material += sum(1 for c in indication_changes if c.severity == "material")

        if breaking > 0:
            severity_assessment = "high_impact"
        elif material > 0:
            severity_assessment = "moderate_impact"
        else:
            severity_assessment = "low_impact"

        summary = PolicyDiffSummary(
            total_criteria_old=len(old.atomic_criteria),
            total_criteria_new=len(new.atomic_criteria),
            added_count=added,
            removed_count=removed,
            modified_count=modified,
            unchanged_count=unchanged,
            breaking_changes=breaking,
            material_changes=material,
            severity_assessment=severity_assessment,
        )

        return PolicyDiffResult(
            old_version=old.version or "old",
            new_version=new.version or "new",
            policy_id=new.policy_id,
            payer=new.payer_name,
            medication=new.medication_name,
            diff_timestamp=datetime.now(timezone.utc).isoformat(),
            summary=summary,
            indication_changes=indication_changes,
            step_therapy_changes=step_therapy_changes,
            exclusion_changes=exclusion_changes,
            criterion_changes=criterion_changes,
        )

    async def _llm_match_criteria(
        self,
        unmatched_old: Dict[str, AtomicCriterion],
        unmatched_new: Dict[str, AtomicCriterion],
    ) -> Tuple[List[Tuple[str, str]], List[str], List[str]]:
        """Use LLM to semantically match criteria with different IDs.

        Returns (matched_pairs, truly_added_ids, truly_removed_ids).
        """
        if not unmatched_old or not unmatched_new:
            return [], list(unmatched_new.keys()), list(unmatched_old.keys())

        from backend.reasoning.llm_gateway import get_llm_gateway
        from backend.reasoning.prompt_loader import get_prompt_loader
        from backend.models.enums import TaskCategory

        def _criterion_summary(c: AtomicCriterion) -> dict:
            return {
                "id": c.criterion_id if hasattr(c, 'criterion_id') else '',
                "name": c.name,
                "description": c.description or '',
                "criterion_type": c.criterion_type or '',
                "category": c.category or '',
                "policy_text": c.policy_text or '',
                "is_required": c.is_required,
            }

        old_summaries = {oid: _criterion_summary(oc) for oid, oc in unmatched_old.items()}
        new_summaries = {nid: _criterion_summary(nc) for nid, nc in unmatched_new.items()}

        try:
            prompt_loader = get_prompt_loader()
            prompt = prompt_loader.load(
                "policy_digitalization/criteria_matching.txt",
                {
                    "old_criteria": json.dumps(old_summaries, indent=2),
                    "new_criteria": json.dumps(new_summaries, indent=2),
                },
            )

            gateway = get_llm_gateway()
            llm_result = await gateway.generate(
                task_category=TaskCategory.POLICY_REASONING,
                prompt=prompt,
                temperature=0.1,
                response_format="json",
            )

            raw = llm_result.get("response")
            if raw is None and "matched_pairs" in llm_result:
                mapping = llm_result
            elif isinstance(raw, str):
                clean = raw.strip()
                if clean.startswith("```"):
                    clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                mapping = json.loads(clean)
            elif isinstance(raw, dict):
                mapping = raw
            else:
                mapping = {}
            logger.info("LLM criteria mapping parsed", matched_count=len(mapping.get("matched_pairs", [])), added_count=len(mapping.get("truly_added", [])), removed_count=len(mapping.get("truly_removed", [])))

            matched: List[Tuple[str, str]] = []
            used_old: set = set()
            used_new: set = set()

            for pair in mapping.get("matched_pairs", []):
                oid = pair.get("old_id", "")
                nid = pair.get("new_id", "")
                if oid in unmatched_old and nid in unmatched_new and oid not in used_old and nid not in used_new:
                    matched.append((oid, nid))
                    used_old.add(oid)
                    used_new.add(nid)
                    logger.info(
                        "LLM-matched criteria",
                        old_id=oid, new_id=nid,
                        old_name=unmatched_old[oid].name,
                        new_name=unmatched_new[nid].name,
                        confidence=pair.get("confidence", "?"),
                        reasoning=pair.get("reasoning", ""),
                    )

            truly_added = [nid for nid in unmatched_new if nid not in used_new]
            truly_removed = [oid for oid in unmatched_old if oid not in used_old]

            logger.info(
                "LLM criteria matching complete",
                matched=len(matched),
                truly_added=len(truly_added),
                truly_removed=len(truly_removed),
            )
            return matched, truly_added, truly_removed

        except Exception as e:
            logger.error("LLM criteria matching failed, treating all as added/removed", error=str(e))
            return [], list(unmatched_new.keys()), list(unmatched_old.keys())

    async def _diff_criteria(
        self, old_criteria: Dict[str, AtomicCriterion], new_criteria: Dict[str, AtomicCriterion]
    ) -> List[CriterionChange]:
        """Diff atomic criteria between two versions using LLM-powered semantic matching."""
        changes = []
        old_ids = set(old_criteria.keys())
        new_ids = set(new_criteria.keys())

        exact_match_ids = old_ids & new_ids
        unmatched_old = {cid: old_criteria[cid] for cid in old_ids - new_ids}
        unmatched_new = {cid: new_criteria[cid] for cid in new_ids - old_ids}

        llm_pairs, truly_added, truly_removed = await self._llm_match_criteria(unmatched_old, unmatched_new)

        for cid in truly_added:
            c = new_criteria[cid]
            severity = "breaking" if c.is_required else "material"
            changes.append(CriterionChange(
                criterion_id=cid,
                criterion_name=c.name,
                change_type=ChangeType.ADDED,
                new_value=c.model_dump(mode="json") if hasattr(c, 'model_dump') else {},
                severity=severity,
                human_summary=f"New {'required' if c.is_required else 'optional'} criterion added: {c.name}",
            ))

        for cid in truly_removed:
            c = old_criteria[cid]
            changes.append(CriterionChange(
                criterion_id=cid,
                criterion_name=c.name,
                change_type=ChangeType.REMOVED,
                old_value=c.model_dump(mode="json") if hasattr(c, 'model_dump') else {},
                severity="material",
                human_summary=f"Criterion removed: {c.name}",
            ))

        all_pairs: List[Tuple[str, str]] = [(cid, cid) for cid in exact_match_ids] + llm_pairs

        for old_id, new_id in all_pairs:
            old_c = old_criteria[old_id]
            new_c = new_criteria[new_id]
            field_changes = self._compare_criterion_fields(old_c, new_c)

            display_id = new_id
            if not field_changes:
                changes.append(CriterionChange(
                    criterion_id=display_id,
                    criterion_name=new_c.name,
                    change_type=ChangeType.UNCHANGED,
                ))
            else:
                severity = self._classify_change_severity(field_changes, old_c, new_c)
                summary_parts = []
                for fc in field_changes:
                    summary_parts.append(f"{fc.field_name}: {fc.old} -> {fc.new}")
                changes.append(CriterionChange(
                    criterion_id=display_id,
                    criterion_name=new_c.name,
                    change_type=ChangeType.MODIFIED,
                    old_value=old_c.model_dump(mode="json") if hasattr(old_c, 'model_dump') else {},
                    new_value=new_c.model_dump(mode="json") if hasattr(new_c, 'model_dump') else {},
                    field_changes=field_changes,
                    severity=severity,
                    human_summary="; ".join(summary_parts),
                ))

        return changes

    def _compare_criterion_fields(self, old: AtomicCriterion, new: AtomicCriterion) -> List[FieldChange]:
        """Compare individual fields of two criteria."""
        changes = []
        fields_to_compare = [
            "threshold_value", "threshold_value_upper", "comparison_operator",
            "threshold_unit", "is_required", "criterion_type",
        ]
        for field in fields_to_compare:
            old_val = getattr(old, field, None)
            new_val = getattr(new, field, None)
            # Normalize enums to strings for comparison
            old_str = old_val.value if hasattr(old_val, 'value') else str(old_val) if old_val is not None else None
            new_str = new_val.value if hasattr(new_val, 'value') else str(new_val) if new_val is not None else None
            if old_str != new_str:
                changes.append(FieldChange(field_name=field, old=old_str, new=new_str))

        # Compare clinical codes
        old_codes = sorted([f"{c.system}:{c.code}" for c in old.clinical_codes])
        new_codes = sorted([f"{c.system}:{c.code}" for c in new.clinical_codes])
        if old_codes != new_codes:
            changes.append(FieldChange(
                field_name="clinical_codes",
                old=",".join(old_codes),
                new=",".join(new_codes),
            ))

        # Compare drug names/classes
        if sorted(old.drug_names) != sorted(new.drug_names):
            changes.append(FieldChange(
                field_name="drug_names",
                old=",".join(sorted(old.drug_names)),
                new=",".join(sorted(new.drug_names)),
            ))
        if sorted(old.drug_classes) != sorted(new.drug_classes):
            changes.append(FieldChange(
                field_name="drug_classes",
                old=",".join(sorted(old.drug_classes)),
                new=",".join(sorted(new.drug_classes)),
            ))

        return changes

    def _classify_change_severity(
        self, field_changes: List[FieldChange], old: AtomicCriterion, new: AtomicCriterion
    ) -> str:
        """Classify severity of changes. Returns max severity across all field changes."""
        severity_rank = {"cosmetic": 0, "minor": 1, "material": 2, "breaking": 3}
        max_severity = "minor"

        for fc in field_changes:
            field_severity = "minor"

            # Threshold tightening = breaking
            if fc.field_name == "threshold_value" and (old.comparison_operator or new.comparison_operator):
                try:
                    old_val = float(fc.old) if fc.old and fc.old != "None" else None
                    new_val = float(fc.new) if fc.new and fc.new != "None" else None
                    # Use new operator (governs the new requirement); fall back to old
                    effective_op = new.comparison_operator or old.comparison_operator
                    op = effective_op.value if hasattr(effective_op, 'value') else str(effective_op)
                    if old_val is None and new_val is not None:
                        # Adding a threshold where none existed = breaking
                        field_severity = "breaking"
                    elif old_val is not None and new_val is not None:
                        if op in ("gte", "gt") and new_val > old_val:
                            field_severity = "breaking"
                        elif op in ("lte", "lt") and new_val < old_val:
                            field_severity = "breaking"
                except (ValueError, TypeError):
                    pass

            # is_required changed to True = breaking
            elif fc.field_name == "is_required" and fc.new == "True" and fc.old == "False":
                field_severity = "breaking"

            # Description-only or cosmetic changes
            elif fc.field_name in ("description", "policy_text", "name"):
                field_severity = "cosmetic"

            # Code changes are material
            elif fc.field_name in ("clinical_codes", "drug_names", "drug_classes"):
                field_severity = "material"

            if severity_rank.get(field_severity, 1) > severity_rank.get(max_severity, 1):
                max_severity = field_severity

        return max_severity

    def _diff_indications(self, old_indications, new_indications) -> List[IndicationChange]:
        """Diff indications."""
        changes = []
        old_map = {i.indication_id: i for i in old_indications}
        new_map = {i.indication_id: i for i in new_indications}

        for iid in set(new_map.keys()) - set(old_map.keys()):
            changes.append(IndicationChange(
                indication_id=iid,
                indication_name=new_map[iid].indication_name,
                change_type=ChangeType.ADDED,
                severity="material",
            ))

        for iid in set(old_map.keys()) - set(new_map.keys()):
            changes.append(IndicationChange(
                indication_id=iid,
                indication_name=old_map[iid].indication_name,
                change_type=ChangeType.REMOVED,
                severity="breaking",
            ))

        for iid in set(old_map.keys()) & set(new_map.keys()):
            old_i = old_map[iid]
            new_i = new_map[iid]
            fc = []
            if old_i.initial_approval_criteria != new_i.initial_approval_criteria:
                fc.append(FieldChange(field_name="initial_approval_criteria",
                                      old=old_i.initial_approval_criteria,
                                      new=new_i.initial_approval_criteria))
            if old_i.initial_approval_duration_months != new_i.initial_approval_duration_months:
                fc.append(FieldChange(field_name="initial_approval_duration_months",
                                      old=str(old_i.initial_approval_duration_months),
                                      new=str(new_i.initial_approval_duration_months)))
            if fc:
                changes.append(IndicationChange(
                    indication_id=iid,
                    indication_name=new_i.indication_name,
                    change_type=ChangeType.MODIFIED,
                    field_changes=fc,
                    severity="material",
                ))

        return changes

    def _diff_step_therapy(self, old_st, new_st) -> List[CriterionChange]:
        """Diff step therapy requirements."""
        changes = []
        old_map = {s.requirement_id: s for s in old_st}
        new_map = {s.requirement_id: s for s in new_st}

        for rid in set(new_map.keys()) - set(old_map.keys()):
            changes.append(CriterionChange(
                criterion_id=rid,
                criterion_name=f"Step Therapy: {new_map[rid].indication}",
                change_type=ChangeType.ADDED,
                severity="breaking",
                human_summary=f"New step therapy requirement added for {new_map[rid].indication}",
            ))

        for rid in set(old_map.keys()) - set(new_map.keys()):
            changes.append(CriterionChange(
                criterion_id=rid,
                criterion_name=f"Step Therapy: {old_map[rid].indication}",
                change_type=ChangeType.REMOVED,
                severity="material",
                human_summary=f"Step therapy requirement removed for {old_map[rid].indication}",
            ))

        for rid in set(old_map.keys()) & set(new_map.keys()):
            old_s = old_map[rid]
            new_s = new_map[rid]
            fc = []
            if old_s.minimum_trials != new_s.minimum_trials:
                fc.append(FieldChange(field_name="minimum_trials",
                                      old=str(old_s.minimum_trials), new=str(new_s.minimum_trials)))
            if sorted(old_s.required_drugs) != sorted(new_s.required_drugs):
                fc.append(FieldChange(field_name="required_drugs",
                                      old=",".join(old_s.required_drugs), new=",".join(new_s.required_drugs)))
            if sorted(old_s.required_drug_classes) != sorted(new_s.required_drug_classes):
                fc.append(FieldChange(field_name="required_drug_classes",
                                      old=",".join(old_s.required_drug_classes), new=",".join(new_s.required_drug_classes)))
            if old_s.minimum_duration_days != new_s.minimum_duration_days:
                fc.append(FieldChange(field_name="minimum_duration_days",
                                      old=str(old_s.minimum_duration_days), new=str(new_s.minimum_duration_days)))
            if old_s.failure_required != new_s.failure_required:
                fc.append(FieldChange(field_name="failure_required",
                                      old=str(old_s.failure_required), new=str(new_s.failure_required)))
            if old_s.intolerance_acceptable != new_s.intolerance_acceptable:
                fc.append(FieldChange(field_name="intolerance_acceptable",
                                      old=str(old_s.intolerance_acceptable), new=str(new_s.intolerance_acceptable)))
            if old_s.contraindication_acceptable != new_s.contraindication_acceptable:
                fc.append(FieldChange(field_name="contraindication_acceptable",
                                      old=str(old_s.contraindication_acceptable), new=str(new_s.contraindication_acceptable)))
            if sorted(old_s.documentation_requirements) != sorted(new_s.documentation_requirements):
                fc.append(FieldChange(field_name="documentation_requirements",
                                      old=",".join(old_s.documentation_requirements), new=",".join(new_s.documentation_requirements)))
            if fc:
                # Breaking only if requirements tightened (not loosened)
                severity = "material"
                for f in fc:
                    if f.field_name in ("minimum_trials", "minimum_duration_days"):
                        try:
                            old_num = float(f.old) if f.old and f.old != "None" else 0
                            new_num = float(f.new) if f.new and f.new != "None" else 0
                            if new_num > old_num:  # Tightened
                                severity = "breaking"
                                break
                        except (ValueError, TypeError):
                            severity = "breaking"
                            break
                    elif f.field_name == "failure_required" and f.new == "True" and f.old == "False":
                        severity = "breaking"
                        break
                    elif f.field_name == "intolerance_acceptable" and f.new == "False" and f.old == "True":
                        severity = "breaking"
                        break
                    elif f.field_name == "contraindication_acceptable" and f.new == "False" and f.old == "True":
                        severity = "breaking"
                        break
                changes.append(CriterionChange(
                    criterion_id=rid,
                    criterion_name=f"Step Therapy: {new_s.indication}",
                    change_type=ChangeType.MODIFIED,
                    field_changes=fc,
                    severity=severity,
                    human_summary="; ".join(f"{f.field_name}: {f.old} -> {f.new}" for f in fc),
                ))

        return changes

    def _diff_exclusions(self, old_excl, new_excl) -> List[CriterionChange]:
        """Diff exclusion criteria."""
        changes = []
        old_map = {e.exclusion_id: e for e in old_excl}
        new_map = {e.exclusion_id: e for e in new_excl}

        for eid in set(new_map.keys()) - set(old_map.keys()):
            changes.append(CriterionChange(
                criterion_id=eid,
                criterion_name=new_map[eid].name,
                change_type=ChangeType.ADDED,
                severity="breaking",
                human_summary=f"New exclusion added: {new_map[eid].name}",
            ))

        for eid in set(old_map.keys()) - set(new_map.keys()):
            changes.append(CriterionChange(
                criterion_id=eid,
                criterion_name=old_map[eid].name,
                change_type=ChangeType.REMOVED,
                severity="material",
                human_summary=f"Exclusion removed: {old_map[eid].name}",
            ))

        # Check for modifications in shared exclusions
        for eid in set(old_map.keys()) & set(new_map.keys()):
            old_e = old_map[eid]
            new_e = new_map[eid]
            fc = []
            if old_e.name != new_e.name:
                fc.append(FieldChange(field_name="name", old=old_e.name, new=new_e.name))
            if old_e.description != new_e.description:
                fc.append(FieldChange(field_name="description", old=old_e.description, new=new_e.description))
            if old_e.policy_text != new_e.policy_text:
                fc.append(FieldChange(field_name="policy_text", old=old_e.policy_text, new=new_e.policy_text))
            if sorted(old_e.trigger_criteria) != sorted(new_e.trigger_criteria):
                fc.append(FieldChange(
                    field_name="trigger_criteria",
                    old=",".join(sorted(old_e.trigger_criteria)),
                    new=",".join(sorted(new_e.trigger_criteria)),
                ))
            if fc:
                changes.append(CriterionChange(
                    criterion_id=eid,
                    criterion_name=new_e.name,
                    change_type=ChangeType.MODIFIED,
                    field_changes=fc,
                    severity="breaking" if any(f.field_name == "trigger_criteria" for f in fc) else "material",
                    human_summary="; ".join(f"{f.field_name} changed" for f in fc),
                ))

        return changes
