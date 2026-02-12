"""Appeal Strategy Agent — analyzes denials and generates appeal strategies.

Uses Claude for clinical accuracy in appeal reasoning. Supports:
- Denial analysis with weakness identification
- Appeal strategy generation with clinical evidence citations
- Peer-to-peer talking points
- Appeal letter drafting
"""

from typing import Dict, Any, Optional, List

from backend.reasoning.llm_gateway import get_llm_gateway
from backend.reasoning.prompt_loader import get_prompt_loader
from backend.models.enums import TaskCategory
from backend.config.logging_config import get_logger

logger = get_logger(__name__)


class AppealAgent:
    """Generates appeal strategies and letters for PA denials."""

    async def generate_strategy(
        self,
        denial_context: Dict[str, Any],
        patient_info: Dict[str, Any],
        payer_name: str,
        medication_name: str,
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive appeal strategy for a denial.

        Args:
            denial_context: Denial details (reason, date, reference number)
            patient_info: Patient clinical and demographic data
            payer_name: Payer that issued the denial
            medication_name: Medication that was denied

        Returns:
            Appeal strategy with arguments, evidence, and recommendations
        """
        # Load policy context
        policy_text = ""
        try:
            from backend.reasoning.policy_reasoner import get_policy_reasoner
            reasoner = get_policy_reasoner()
            policy_text = reasoner.load_policy(payer_name, medication_name)
        except FileNotFoundError:
            policy_text = f"[Policy document not available for {payer_name}/{medication_name}]"

        # Load digitized criteria for structured context
        digitized_context = ""
        try:
            from backend.policy_digitalization.pipeline import get_digitalization_pipeline
            pipeline = get_digitalization_pipeline()
            policy = await pipeline.get_or_digitalize(payer_name, medication_name)
            if policy and policy.atomic_criteria:
                criteria_lines = []
                for cid, crit in policy.atomic_criteria.items():
                    criteria_lines.append(f"- {cid}: {crit.name} ({crit.criterion_type}) — {crit.description}")
                digitized_context = "\n".join(criteria_lines)
        except Exception as e:
            logger.debug("Could not load digitized policy for appeal", error=str(e))

        if digitized_context:
            policy_text += f"\n\n## Digitized Criteria\n{digitized_context}"

        prompt_loader = get_prompt_loader()
        prompt = prompt_loader.load(
            "appeals/appeal_strategy.txt",
            {
                "denial_details": denial_context,
                "patient_profile": patient_info,
                "policy_document": policy_text,
                "original_request": denial_context.get("original_request", {}),
                "available_documentation": denial_context.get("available_documentation", []),
            },
        )

        gateway = get_llm_gateway()
        result = await gateway.generate(
            task_category=TaskCategory.APPEAL_STRATEGY,
            prompt=prompt,
            temperature=0.1,
            response_format="json",
        )

        # Clean up internal keys
        result.pop("_usage", None)
        result["payer"] = payer_name
        result["medication"] = medication_name

        logger.info(
            "Appeal strategy generated",
            payer=payer_name, medication=medication_name,
            success_likelihood=result.get("success_likelihood"),
        )

        return result

    async def draft_letter(
        self,
        appeal_strategy: Dict[str, Any],
        patient_info: Dict[str, Any],
        denial_context: Dict[str, Any],
        payer_name: str,
        medication_name: str,
    ) -> str:
        """
        Draft a formal appeal letter based on the strategy.

        Args:
            appeal_strategy: Previously generated appeal strategy
            patient_info: Patient information
            denial_context: Denial details
            payer_name: Payer name
            medication_name: Medication name

        Returns:
            Formatted appeal letter text
        """
        policy_text = ""
        try:
            from backend.reasoning.policy_reasoner import get_policy_reasoner
            reasoner = get_policy_reasoner()
            policy_text = reasoner.load_policy(payer_name, medication_name)
        except FileNotFoundError:
            pass

        prompt_loader = get_prompt_loader()
        prompt = prompt_loader.load(
            "appeals/appeal_letter_draft.txt",
            {
                "appeal_context": appeal_strategy,
                "patient_info": patient_info,
                "denial_details": denial_context,
                "policy_reference": policy_text[:3000] if policy_text else "[Not available]",
                "clinical_evidence": appeal_strategy.get("appeal_strategy", {}).get("clinical_evidence", []),
            },
        )

        gateway = get_llm_gateway()
        result = await gateway.generate(
            task_category=TaskCategory.APPEAL_DRAFTING,
            prompt=prompt,
            temperature=0.3,
            response_format="text",
        )

        letter_text = result.get("response", "")
        logger.info("Appeal letter drafted", payer=payer_name, medication=medication_name, length=len(letter_text))
        return letter_text


# Global instance
_appeal_agent: Optional[AppealAgent] = None


def get_appeal_agent() -> AppealAgent:
    """Get or create the global AppealAgent."""
    global _appeal_agent
    if _appeal_agent is None:
        _appeal_agent = AppealAgent()
    return _appeal_agent
