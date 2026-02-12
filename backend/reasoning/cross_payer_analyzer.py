"""Cross-Payer Analyzer — compare coverage criteria for a medication across multiple payers.

Uses Claude to semantically compare policy criteria, identify gaps, and surface
coverage differences that matter to medical affairs teams.
"""

import json
from typing import Dict, Any, Optional, List

from backend.reasoning.llm_gateway import get_llm_gateway
from backend.reasoning.prompt_loader import get_prompt_loader
from backend.models.enums import TaskCategory
from backend.storage.database import get_db
from backend.storage.models import PolicyCacheModel
from backend.config.logging_config import get_logger

logger = get_logger(__name__)


class CrossPayerAnalyzer:
    """Compare coverage criteria across payers for the same medication."""

    async def analyze(
        self,
        medication: str,
        payers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Run cross-payer comparison analysis for a medication.

        Args:
            medication: Medication name (canonical, lowercase)
            payers: Optional list of payer names to compare. If None, compares all available.

        Returns:
            Comparison analysis with per-payer criteria, differences, and recommendations
        """
        from sqlalchemy import select

        medication_lower = medication.lower()

        # Load all policies for this medication
        async with get_db() as session:
            stmt = (
                select(PolicyCacheModel)
                .where(PolicyCacheModel.medication_name == medication_lower)
                .where(PolicyCacheModel.parsed_criteria.isnot(None))
                .order_by(PolicyCacheModel.cached_at.desc())
            )
            result = await session.execute(stmt)
            all_entries = result.scalars().all()

        if not all_entries:
            # Try alias resolution
            from backend.policy_digitalization.pipeline import MEDICATION_NAME_ALIASES
            alias = MEDICATION_NAME_ALIASES.get(medication_lower)
            if alias:
                async with get_db() as session:
                    stmt = (
                        select(PolicyCacheModel)
                        .where(PolicyCacheModel.medication_name == alias)
                        .where(PolicyCacheModel.parsed_criteria.isnot(None))
                        .order_by(PolicyCacheModel.cached_at.desc())
                    )
                    result = await session.execute(stmt)
                    all_entries = result.scalars().all()

        if not all_entries:
            return {
                "medication": medication,
                "error": f"No digitized policies found for {medication}",
                "payers_compared": [],
            }

        # Deduplicate: keep latest version per payer
        payer_policies: Dict[str, PolicyCacheModel] = {}
        for entry in all_entries:
            if payers and entry.payer_name not in [p.lower() for p in payers]:
                continue
            if entry.payer_name not in payer_policies:
                payer_policies[entry.payer_name] = entry

        if len(payer_policies) < 2:
            return {
                "medication": medication,
                "error": "Need at least 2 payers for cross-payer comparison",
                "payers_compared": list(payer_policies.keys()),
            }

        # Build context for each payer
        payer_contexts = []
        for payer_name, entry in payer_policies.items():
            criteria = entry.parsed_criteria or {}
            ctx = self._format_payer_criteria(payer_name, criteria)
            payer_contexts.append(ctx)

        combined_context = "\n\n===\n\n".join(payer_contexts)

        # Call Claude for semantic comparison
        prompt_loader = get_prompt_loader()
        prompt = prompt_loader.load(
            "policy_analysis/cross_payer_comparison.txt",
            {
                "medication": medication,
                "payer_count": len(payer_policies),
                "payer_names": ", ".join(payer_policies.keys()),
                "policies_context": combined_context,
            },
        )

        gateway = get_llm_gateway()
        result = await gateway.generate(
            task_category=TaskCategory.POLICY_QA,
            prompt=prompt,
            temperature=0.1,
            response_format="json",
        )

        # Parse response
        from backend.reasoning.json_utils import extract_json_from_text
        raw = result.get("response")
        if raw is None:
            parsed = {k: v for k, v in result.items() if k not in ("provider", "task_category")}
        else:
            try:
                parsed = extract_json_from_text(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                parsed = {"summary": str(raw)}

        parsed["medication"] = medication
        parsed["payers_compared"] = list(payer_policies.keys())
        parsed["provider"] = result.get("provider", "unknown")

        logger.info(
            "Cross-payer analysis complete",
            medication=medication,
            payers=list(payer_policies.keys()),
        )

        return parsed

    def _format_payer_criteria(self, payer_name: str, criteria: dict) -> str:
        """Format a payer's criteria for comparison context with full detail."""
        parts = [f"## Payer: {payer_name.upper()}"]

        indications = criteria.get("indications", [])
        if indications:
            parts.append(f"\n### Covered Indications ({len(indications)})")
            for ind in indications:
                age_range = ""
                min_age = ind.get("min_age_years")
                max_age = ind.get("max_age_years")
                if min_age is not None:
                    age_range = f", age >= {min_age}"
                if max_age is not None:
                    age_range += f", age <= {max_age}"
                parts.append(
                    f"- {ind.get('indication_id', '')}: {ind.get('indication_name', '')}{age_range}"
                )

        atomic = criteria.get("atomic_criteria", {})
        if atomic:
            parts.append(f"\n### Atomic Criteria ({len(atomic)} total)")
            for cid, crit in atomic.items():
                desc = crit.get("description", "")
                cat = crit.get("category", "")
                ctype = crit.get("criterion_type", "")
                required = "Required" if crit.get("is_required") else "Optional"
                indication_id = crit.get("indication_id", "")

                line = f"- {cid} [{cat}/{ctype}, {required}]"
                if indication_id:
                    line += f" (indication: {indication_id})"
                line += f": {desc}"

                # Include thresholds
                threshold = crit.get("threshold_value")
                if threshold is not None:
                    comp = crit.get("comparison_operator", "")
                    unit = crit.get("threshold_unit", "")
                    line += f" | threshold: {comp} {threshold} {unit}".strip()

                # Include drug classes
                drug_classes = crit.get("drug_classes", [])
                if drug_classes:
                    line += f" | drug_classes: {drug_classes}"

                parts.append(line)

        step_therapy = criteria.get("step_therapy_requirements", [])
        if step_therapy:
            parts.append("\n### Step Therapy")
            for st in step_therapy:
                indication = st.get("indication", "All")
                drugs = st.get("required_drug_classes", [])
                min_failures = st.get("minimum_failures", "")
                min_duration = st.get("minimum_duration", "")
                line = f"- {indication}: {', '.join(drugs)}"
                if min_failures:
                    line += f" | min_failures: {min_failures}"
                if min_duration:
                    line += f" | min_duration: {min_duration}"
                parts.append(line)

        exclusions = criteria.get("exclusions", [])
        if exclusions:
            parts.append("\n### Exclusions")
            for ex in exclusions:
                eid = ex.get("exclusion_id", "")
                desc = ex.get("description", "")
                prefix = f"{eid}: " if eid else ""
                parts.append(f"- {prefix}{desc}")

        return "\n".join(parts)


# Global instance
_analyzer: Optional[CrossPayerAnalyzer] = None


def get_cross_payer_analyzer() -> CrossPayerAnalyzer:
    """Get or create the global CrossPayerAnalyzer."""
    global _analyzer
    if _analyzer is None:
        _analyzer = CrossPayerAnalyzer()
    return _analyzer
