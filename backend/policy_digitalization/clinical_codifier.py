"""Pass 4: Clinical Codification & Consensus Validation.

Uses a dual-LLM consensus model:
  Pass 4A (Gemini): Extract clinical concepts → map to codes → expand hierarchies
  Pass 4B (Claude): Validate each proposed code → confirm/reject/modify

Consensus logic:
  - Both agree → CONFIRMED
  - Gemini proposed + Claude rejected → REJECTED (kept for audit)
  - Gemini proposed + Claude modified → use corrected code, CONFIRMED
  - Gemini proposed + Claude silent → REVIEW_NEEDED
  - Claude-only addition → REVIEW_NEEDED
  - Existing verbatim codes preserved with source=VERBATIM, status=CONFIRMED
    (not counted in total_proposed — they predate Pass 4)
"""

import json
from datetime import datetime, timezone
from typing import Optional

from backend.models.policy_schema import (
    ClinicalCode,
    DigitizedPolicy,
    EnrichedClinicalCode,
    CodificationMetadata,
    CodeSource,
    ConsensusStatus,
)
from backend.models.enums import TaskCategory
from backend.reasoning.llm_gateway import get_llm_gateway, LLMGateway
from backend.reasoning.prompt_loader import get_prompt_loader, PromptLoader
from backend.reasoning.json_utils import extract_json_from_text
from backend.policy_digitalization.exceptions import CodificationError
from backend.config.logging_config import get_logger

logger = get_logger(__name__)


class ClinicalCodifier:
    """Dual-LLM clinical codification engine."""

    def __init__(
        self,
        llm_gateway: Optional[LLMGateway] = None,
        prompt_loader: Optional[PromptLoader] = None,
    ):
        self.gateway = llm_gateway or get_llm_gateway()
        self.prompt_loader = prompt_loader or get_prompt_loader()

    async def codify_policy(self, policy: DigitizedPolicy) -> DigitizedPolicy:
        """Run Pass 4 codification on a digitized policy.

        Args:
            policy: DigitizedPolicy from Pass 3

        Returns:
            The same DigitizedPolicy with enriched_codes populated (mutated in place)

        Raises:
            CodificationError: If Pass 4A (Gemini) fails
        """
        if not policy.atomic_criteria and not policy.indications:
            logger.info("Pass 4: Skipping — no criteria or indications to codify")
            return policy

        logger.info(
            "Pass 4: Starting clinical codification",
            policy_id=policy.policy_id,
            criteria=len(policy.atomic_criteria),
            indications=len(policy.indications),
        )

        codification_input = self._build_codification_input(policy)
        medication_context = self._build_medication_context(policy)

        # Pass 4A: Gemini proposes codes
        try:
            gemini_codes = await self._pass_4a_codify(codification_input, medication_context)
        except Exception as e:
            raise CodificationError(f"Pass 4A (Gemini codification) failed: {e}")

        # Pass 4B: Claude validates codes
        try:
            claude_verdicts = await self._pass_4b_validate(codification_input, medication_context, gemini_codes)
        except Exception as e:
            logger.warning("Pass 4B (Claude validation) failed, using Gemini codes as review_needed", error=str(e))
            claude_verdicts = None

        # Merge with consensus logic
        self._apply_consensus(policy, gemini_codes, claude_verdicts)

        logger.info(
            "Pass 4: Clinical codification complete",
            policy_id=policy.policy_id,
            confirmed=policy.codification_metadata.confirmed_codes if policy.codification_metadata else 0,
            review_needed=policy.codification_metadata.review_needed_codes if policy.codification_metadata else 0,
        )

        return policy

    def _build_codification_input(self, policy: DigitizedPolicy) -> str:
        """Serialize criteria and indications for LLM consumption."""
        criteria_list = []
        for cid, criterion in policy.atomic_criteria.items():
            existing_codes = [
                {"system": c.system, "code": c.code, "display": c.display}
                for c in criterion.clinical_codes
            ]
            criteria_list.append({
                "criterion_id": cid,
                "name": criterion.name,
                "description": criterion.description,
                "policy_text": criterion.policy_text[:2000],
                "category": criterion.category,
                "criterion_type": criterion.criterion_type.value,
                "drug_names": criterion.drug_names,
                "drug_classes": criterion.drug_classes,
                "existing_codes": existing_codes,
            })

        indications_list = []
        for indication in policy.indications:
            existing_codes = [
                {"system": c.system, "code": c.code, "display": c.display}
                for c in indication.indication_codes
            ]
            indications_list.append({
                "indication_id": indication.indication_id,
                "indication_name": indication.indication_name,
                "existing_codes": existing_codes,
            })

        return json.dumps({
            "criteria": criteria_list,
            "indications": indications_list,
        }, indent=2, default=str)

    def _build_medication_context(self, policy: DigitizedPolicy) -> str:
        """Build medication context string for the prompt."""
        return json.dumps({
            "medication_name": policy.medication_name,
            "brand_names": policy.medication_brand_names,
            "generic_names": policy.medication_generic_names,
            "existing_medication_codes": [
                {"system": c.system, "code": c.code, "display": c.display}
                for c in policy.medication_codes
            ],
        }, indent=2, default=str)

    async def _pass_4a_codify(self, codification_input: str, medication_context: str) -> dict:
        """Pass 4A: Gemini extracts and maps clinical codes."""
        prompt = self.prompt_loader.load(
            "policy_digitalization/clinical_codification.txt",
            {
                "codification_input": codification_input,
                "medication_context": medication_context,
            },
        )

        result = await self.gateway.generate(
            task_category=TaskCategory.CLINICAL_CODIFICATION,
            prompt=prompt,
            temperature=0.1,
            response_format="json",
        )

        parsed = self._parse_llm_response(result)

        # Validate expected structure
        if "criteria_codes" not in parsed and "indication_codes" not in parsed:
            raise CodificationError(
                "Pass 4A returned no codification data "
                f"(missing criteria_codes and indication_codes). Keys: {list(parsed.keys())}"
            )

        return parsed

    async def _pass_4b_validate(
        self, codification_input: str, medication_context: str, proposed_codes: dict
    ) -> dict:
        """Pass 4B: Claude validates Gemini's proposed codes."""
        prompt = self.prompt_loader.load(
            "policy_digitalization/codification_consensus.txt",
            {
                "codification_input": codification_input,
                "medication_context": medication_context,
                "proposed_codes": json.dumps(proposed_codes, indent=2, default=str),
            },
        )

        result = await self.gateway.generate(
            task_category=TaskCategory.POLICY_REASONING,
            prompt=prompt,
            temperature=0.0,
            response_format="json",
        )

        parsed = self._parse_llm_response(result)

        if "criteria_verdicts" not in parsed and "indication_verdicts" not in parsed:
            raise CodificationError(
                "Pass 4B returned no verdict data "
                f"(missing criteria_verdicts and indication_verdicts). Keys: {list(parsed.keys())}"
            )

        return parsed

    @staticmethod
    def _parse_llm_response(result: dict) -> dict:
        """Extract parsed JSON from an LLM gateway response."""
        raw_response = result.get("response")
        if raw_response is None:
            # Some providers return parsed JSON fields at top level
            return {k: v for k, v in result.items() if k not in ("provider", "task_category")}
        if isinstance(raw_response, str):
            return extract_json_from_text(raw_response)
        return raw_response

    def _apply_consensus(
        self,
        policy: DigitizedPolicy,
        gemini_codes: dict,
        claude_verdicts: Optional[dict],
    ) -> None:
        """Merge Gemini proposals with Claude verdicts using consensus logic.

        Mutates policy in place: sets enriched_codes on criteria/indications,
        appends to medication_codes, and sets codification_metadata.
        """
        stats = {
            "total_proposed": 0,
            "confirmed": 0,
            "review_needed": 0,
            "rejected": 0,
            "criteria_codified": 0,
            "indications_codified": 0,
        }

        # Build verdict lookup: entity_id → {system:code → verdict_dict}
        verdict_lookup = {}
        additional_lookup = {}
        if claude_verdicts:
            for cv in claude_verdicts.get("criteria_verdicts", []):
                cid = cv.get("criterion_id", "")
                verdict_lookup[cid] = {
                    f"{v.get('system', '')}:{v.get('code', '')}": v
                    for v in cv.get("code_verdicts", [])
                }
                additional_lookup[cid] = cv.get("additional_codes", [])

            for iv in claude_verdicts.get("indication_verdicts", []):
                iid = iv.get("indication_id", "")
                verdict_lookup[iid] = {
                    f"{v.get('system', '')}:{v.get('code', '')}": v
                    for v in iv.get("code_verdicts", [])
                }
                additional_lookup[iid] = iv.get("additional_codes", [])

        # Process criteria codes
        for cc in gemini_codes.get("criteria_codes", []):
            cid = cc.get("criterion_id", "")
            if cid not in policy.atomic_criteria:
                continue

            criterion = policy.atomic_criteria[cid]
            enriched = self._merge_codes_for_entity(
                cc.get("codes", []),
                verdict_lookup.get(cid, {}),
                additional_lookup.get(cid, []),
                criterion.clinical_codes,
                stats,
            )
            criterion.enriched_codes = enriched
            if enriched:
                stats["criteria_codified"] += 1

        # Process indication codes
        for ic in gemini_codes.get("indication_codes", []):
            iid = ic.get("indication_id", "")
            matching = [ind for ind in policy.indications if ind.indication_id == iid]
            if not matching:
                continue

            indication = matching[0]
            enriched = self._merge_codes_for_entity(
                ic.get("codes", []),
                verdict_lookup.get(iid, {}),
                additional_lookup.get(iid, []),
                indication.indication_codes,
                stats,
            )
            indication.enriched_codes = enriched
            if enriched:
                stats["indications_codified"] += 1

        # Process medication codes
        self._process_medication_codes(policy, gemini_codes, claude_verdicts, stats)

        policy.codification_metadata = CodificationMetadata(
            codification_timestamp=datetime.now(timezone.utc).isoformat(),
            codification_model_a="gemini",
            codification_model_b="claude" if claude_verdicts else None,
            total_codes_proposed=stats["total_proposed"],
            confirmed_codes=stats["confirmed"],
            review_needed_codes=stats["review_needed"],
            rejected_codes=stats["rejected"],
            criteria_codified=stats["criteria_codified"],
            indications_codified=stats["indications_codified"],
        )

    def _process_medication_codes(
        self,
        policy: DigitizedPolicy,
        gemini_codes: dict,
        claude_verdicts: Optional[dict],
        stats: dict,
    ) -> None:
        """Process medication-level codes from Gemini + Claude verdicts."""
        med_codes = gemini_codes.get("medication_codes", [])

        med_verdicts = {}
        med_additional = []
        if claude_verdicts and "medication_verdicts" in claude_verdicts:
            mv = claude_verdicts["medication_verdicts"]
            med_verdicts = {
                f"{v.get('system', '')}:{v.get('code', '')}": v
                for v in mv.get("code_verdicts", [])
            }
            med_additional = mv.get("additional_codes", [])

        # Build existing keys once, update as we add
        existing_code_keys = {f"{c.system}:{c.code}" for c in policy.medication_codes}

        for mc in med_codes:
            key = f"{mc.get('system', '')}:{mc.get('code', '')}"
            verdict = med_verdicts.get(key)
            consensus = self._resolve_consensus(mc, verdict)
            stats["total_proposed"] += 1
            stats[consensus.value] += 1

            # Resolve final code and display (handle modified verdicts)
            code_value = mc.get("code", "")
            if verdict and verdict.get("verdict") == "modified" and verdict.get("corrected_code"):
                code_value = verdict["corrected_code"]
                display = verdict.get("corrected_display") or mc.get("display")
            else:
                display = mc.get("display")

            new_key = f"{mc.get('system', '')}:{code_value}"
            if consensus != ConsensusStatus.REJECTED and new_key not in existing_code_keys:
                policy.medication_codes.append(ClinicalCode(
                    system=mc.get("system", "RxNorm"),
                    code=code_value,
                    display=display,
                ))
                existing_code_keys.add(new_key)

        # Process Claude-only additional medication codes
        for ac in med_additional:
            system = ac.get("system", "RxNorm")
            code_val = ac.get("code", "")
            key = f"{system}:{code_val}"
            if key in existing_code_keys:
                continue

            stats["total_proposed"] += 1
            stats["review_needed"] += 1
            policy.medication_codes.append(ClinicalCode(
                system=system,
                code=code_val,
                display=ac.get("display"),
            ))
            existing_code_keys.add(key)

    def _merge_codes_for_entity(
        self,
        proposed_codes: list,
        verdicts: dict,
        additional_codes: list,
        existing_clinical_codes: list,
        stats: dict,
    ) -> list:
        """Merge proposed codes with verdicts for a single criterion or indication.

        Verbatim codes (from existing clinical_codes) are preserved but NOT
        counted in stats — they predate Pass 4.
        """
        enriched = []

        # First, preserve existing verbatim codes (not counted in stats)
        existing_keys = set()
        for cc in existing_clinical_codes:
            key = f"{cc.system}:{cc.code}"
            existing_keys.add(key)
            enriched.append(EnrichedClinicalCode(
                system=cc.system,
                code=cc.code,
                display=cc.display,
                source=CodeSource.VERBATIM,
                consensus_status=ConsensusStatus.CONFIRMED,
                concept_text=cc.display or "",
            ))

        # Process Gemini-proposed codes
        for pc in proposed_codes:
            code_val = pc.get("code", "")
            system = pc.get("system", "ICD-10-CM")
            key = f"{system}:{code_val}"

            # Skip if already present as verbatim
            if key in existing_keys:
                continue

            stats["total_proposed"] += 1
            verdict = verdicts.get(key)
            consensus = self._resolve_consensus(pc, verdict)

            # If modified, use the corrected code
            final_code = code_val
            final_display = pc.get("display")
            if verdict and verdict.get("verdict") == "modified":
                final_code = verdict.get("corrected_code", code_val)
                final_display = verdict.get("corrected_display") or final_display
                consensus = ConsensusStatus.CONFIRMED

            stats[consensus.value] += 1

            source_str = pc.get("source", "inferred")
            try:
                source = CodeSource(source_str)
            except ValueError:
                source = CodeSource.INFERRED

            enriched.append(EnrichedClinicalCode(
                system=system,
                code=final_code,
                display=final_display,
                source=source,
                consensus_status=consensus,
                parent_code=pc.get("parent_code"),
                concept_text=pc.get("concept_text", ""),
            ))
            # Track both original and corrected keys to prevent duplicates
            existing_keys.add(key)
            if final_code != code_val:
                existing_keys.add(f"{system}:{final_code}")

        # Process Claude-only additional codes
        for ac in additional_codes:
            system = ac.get("system", "ICD-10-CM")
            code_val = ac.get("code", "")
            key = f"{system}:{code_val}"
            if key in existing_keys:
                continue

            stats["total_proposed"] += 1
            stats["review_needed"] += 1

            enriched.append(EnrichedClinicalCode(
                system=system,
                code=code_val,
                display=ac.get("display"),
                source=CodeSource.INFERRED,
                consensus_status=ConsensusStatus.REVIEW_NEEDED,
                concept_text=ac.get("concept_text", ""),
            ))
            existing_keys.add(key)

        return enriched

    @staticmethod
    def _resolve_consensus(proposed: dict, verdict: Optional[dict]) -> ConsensusStatus:
        """Determine consensus status from a proposed code and its verdict."""
        if verdict is None:
            return ConsensusStatus.REVIEW_NEEDED

        v = verdict.get("verdict", "").lower()
        if v == "confirmed":
            return ConsensusStatus.CONFIRMED
        elif v == "rejected":
            return ConsensusStatus.REJECTED
        elif v == "modified":
            return ConsensusStatus.CONFIRMED
        elif v == "uncertain":
            return ConsensusStatus.REVIEW_NEEDED
        else:
            return ConsensusStatus.REVIEW_NEEDED


# Global singleton
_codifier: Optional[ClinicalCodifier] = None


def get_clinical_codifier() -> ClinicalCodifier:
    """Get or create the global ClinicalCodifier instance."""
    global _codifier
    if _codifier is None:
        _codifier = ClinicalCodifier()
    return _codifier
