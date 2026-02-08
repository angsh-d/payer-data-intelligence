"""Policy Assistant — conversational Q&A over digitized policies using Claude."""

import hashlib
import json
import uuid
from typing import Optional, Dict, Any, List

from backend.reasoning.llm_gateway import get_llm_gateway, LLMGateway
from backend.reasoning.prompt_loader import get_prompt_loader
from backend.models.enums import TaskCategory
from backend.policy_digitalization.policy_repository import get_policy_repository
from backend.storage.database import get_db
from backend.storage.models import PolicyCacheModel, PolicyQACacheModel
from backend.config.logging_config import get_logger

logger = get_logger(__name__)

# Semantic similarity threshold for cache hits
_SEMANTIC_SIMILARITY_THRESHOLD = 0.90


class PolicyAssistant:
    """Answers natural language questions about digitized policies."""

    async def query(
        self,
        question: str,
        payer_filter: Optional[str] = None,
        medication_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Query digitized policies with a natural language question.

        Uses semantic cache: embeds the question, searches DB for similar cached Q&A,
        and only calls Claude on a cache miss.

        Args:
            question: Natural language question
            payer_filter: Optional payer name filter
            medication_filter: Optional medication name filter

        Returns:
            Dictionary with answer, citations, policies_consulted, confidence
        """
        # Load matching policies
        policies_context = await self._build_policies_context(payer_filter, medication_filter)

        if not policies_context:
            return {
                "answer": "No digitized policies found matching the specified filters.",
                "citations": [],
                "policies_consulted": [],
                "confidence": 0.0,
            }

        gateway = get_llm_gateway()

        # Compute policy content hash for cache freshness
        policy_content_hash = hashlib.sha256(policies_context.encode()).hexdigest()

        # Try semantic cache lookup
        cached = await self._semantic_cache_lookup(
            gateway, question, payer_filter, medication_filter, policy_content_hash
        )
        if cached is not None:
            return cached

        # Cache miss — call Claude
        filter_parts = []
        if payer_filter:
            filter_parts.append(f"Payer: {payer_filter}")
        if medication_filter:
            filter_parts.append(f"Medication: {medication_filter}")
        filter_context = ", ".join(filter_parts) if filter_parts else "All policies"

        prompt_loader = get_prompt_loader()
        system_prompt = prompt_loader.load("policy_digitalization/policy_assistant_system.txt")
        query_prompt = prompt_loader.load(
            "policy_digitalization/policy_assistant_query.txt",
            {
                "policies_context": policies_context,
                "question": question,
                "filter_context": filter_context,
            },
        )

        result = await gateway.generate(
            task_category=TaskCategory.POLICY_QA,
            prompt=query_prompt,
            system_prompt=system_prompt,
            temperature=0.1,
            response_format="json",
        )

        # Parse response
        raw = result.get("response")
        if raw is None:
            parsed = {k: v for k, v in result.items() if k not in ("provider", "task_category")}
        else:
            try:
                if isinstance(raw, str):
                    parsed = json.loads(raw)
                else:
                    parsed = raw
            except (json.JSONDecodeError, TypeError):
                parsed = {
                    "answer": raw if isinstance(raw, str) else str(raw),
                    "citations": [],
                    "policies_consulted": [],
                    "confidence": 0.5,
                }

        response_data = {
            "answer": parsed.get("answer", ""),
            "citations": parsed.get("citations", []),
            "policies_consulted": parsed.get("policies_consulted", []),
            "confidence": parsed.get("confidence", 0.5),
            "provider": result.get("provider", "unknown"),
        }

        # Store in semantic cache (fire-and-forget — don't block the response)
        try:
            question_embedding = await gateway.embed(question)
            await self._store_in_cache(
                question, question_embedding, payer_filter, medication_filter,
                policy_content_hash, response_data,
            )
        except Exception as e:
            logger.warning("Failed to store Q&A in semantic cache", error=str(e))

        return response_data

    async def _semantic_cache_lookup(
        self,
        gateway: LLMGateway,
        question: str,
        payer_filter: Optional[str],
        medication_filter: Optional[str],
        policy_content_hash: str,
    ) -> Optional[Dict[str, Any]]:
        """Search DB for a semantically similar cached Q&A pair."""
        try:
            question_embedding = await gateway.embed(question)
        except Exception as e:
            logger.warning("Embedding failed, skipping semantic cache", error=str(e))
            return None

        from sqlalchemy import select, update

        try:
            async with get_db() as session:
                # Filter by exact context match + policy freshness
                stmt = (
                    select(PolicyQACacheModel)
                    .where(PolicyQACacheModel.policy_content_hash == policy_content_hash)
                )
                if payer_filter:
                    stmt = stmt.where(PolicyQACacheModel.payer_filter == payer_filter.lower())
                else:
                    stmt = stmt.where(PolicyQACacheModel.payer_filter.is_(None))
                if medication_filter:
                    stmt = stmt.where(PolicyQACacheModel.medication_filter == medication_filter.lower())
                else:
                    stmt = stmt.where(PolicyQACacheModel.medication_filter.is_(None))

                result = await session.execute(stmt)
                candidates = result.scalars().all()

                best_match = None
                best_score = 0.0
                for candidate in candidates:
                    score = LLMGateway.cosine_similarity(question_embedding, candidate.question_embedding)
                    if score >= _SEMANTIC_SIMILARITY_THRESHOLD and score > best_score:
                        best_score = score
                        best_match = candidate

                if best_match:
                    # Increment hit count
                    await session.execute(
                        update(PolicyQACacheModel)
                        .where(PolicyQACacheModel.id == best_match.id)
                        .values(hit_count=best_match.hit_count + 1)
                    )
                    logger.info(
                        "Semantic cache HIT",
                        similarity=round(best_score, 4),
                        cached_question=best_match.question_text[:80],
                        hit_count=best_match.hit_count + 1,
                    )
                    cached_response = best_match.response_data
                    cached_response["cache_hit"] = True
                    cached_response["similarity_score"] = round(best_score, 4)
                    return cached_response

        except Exception as e:
            logger.warning("Semantic cache lookup failed", error=str(e))

        return None

    async def _store_in_cache(
        self,
        question: str,
        question_embedding: List[float],
        payer_filter: Optional[str],
        medication_filter: Optional[str],
        policy_content_hash: str,
        response_data: Dict[str, Any],
    ) -> None:
        """Store a Q&A pair in the semantic cache."""
        async with get_db() as session:
            row = PolicyQACacheModel(
                id=str(uuid.uuid4()),
                question_text=question,
                question_embedding=question_embedding,
                payer_filter=payer_filter.lower() if payer_filter else None,
                medication_filter=medication_filter.lower() if medication_filter else None,
                policy_content_hash=policy_content_hash,
                response_data=response_data,
                hit_count=0,
            )
            session.add(row)
        logger.info("Q&A stored in semantic cache", question=question[:80])

    async def _build_policies_context(
        self,
        payer_filter: Optional[str],
        medication_filter: Optional[str],
    ) -> str:
        """Build serialized policy context for the LLM prompt."""
        from sqlalchemy import select

        async with get_db() as session:
            stmt = select(PolicyCacheModel).where(PolicyCacheModel.parsed_criteria.isnot(None))

            if payer_filter:
                stmt = stmt.where(PolicyCacheModel.payer_name == payer_filter.lower())
            if medication_filter:
                stmt = stmt.where(PolicyCacheModel.medication_name == medication_filter.lower())

            # Load all versions (not just latest) so Claude can compare versions
            stmt = stmt.order_by(PolicyCacheModel.payer_name, PolicyCacheModel.medication_name, PolicyCacheModel.cached_at.desc())
            result = await session.execute(stmt)
            entries = result.scalars().all()

        if not entries:
            return ""

        # Build context string — include all versions per policy (up to 3)
        context_parts = []
        version_count: Dict[str, int] = {}
        for entry in entries:
            key = f"{entry.payer_name}:{entry.medication_name}"
            version_count[key] = version_count.get(key, 0) + 1
            if version_count[key] > 3:
                continue  # Cap at 3 versions per policy to manage token usage

            criteria = entry.parsed_criteria
            if not criteria:
                continue

            context_parts.append(self._format_policy_entry(entry, criteria))

        return "\n---\n".join(context_parts)

    def _format_policy_entry(self, entry: PolicyCacheModel, criteria: dict) -> str:
        """Format a single policy entry for the LLM context."""
        # Header with brand/generic names
        brand_names = criteria.get("medication_brand_names", [])
        generic_names = criteria.get("medication_generic_names", [])
        part = f"### Policy: {entry.payer_name} - {entry.medication_name}"
        if brand_names:
            part += f" (brand: {', '.join(brand_names)})"
        if generic_names:
            part += f" (generic: {', '.join(generic_names)})"
        part += f"\n**Version:** {entry.policy_version}"
        effective_date = criteria.get("effective_date")
        last_revision = criteria.get("last_revision_date")
        if effective_date:
            part += f" | **Effective Date:** {effective_date}"
        if last_revision:
            part += f" | **Last Revised:** {last_revision}"
        part += "\n"

        # Atomic criteria summaries
        atomic = criteria.get("atomic_criteria", {})
        if atomic:
            part += f"\n**Criteria ({len(atomic)} total):**\n"
            for cid, crit in list(atomic.items())[:30]:  # Limit to avoid token overflow
                ctype = crit.get("criterion_type", "")
                desc = crit.get("description", "")
                part += f"- {cid}: [{ctype}] {desc}\n"

        # Step therapy
        step_therapy = criteria.get("step_therapy_requirements", [])
        if step_therapy:
            part += "\n**Step Therapy:**\n"
            for st in step_therapy:
                indication = st.get("indication", "All")
                drugs = st.get("required_drug_classes", [])
                part += f"- {indication}: {', '.join(drugs)}\n"

        # Exclusions
        exclusions = criteria.get("exclusions", [])
        if exclusions:
            part += "\n**Exclusions:**\n"
            for ex in exclusions:
                part += f"- {ex.get('description', ex.get('exclusion_id', ''))}\n"

        # Indications
        indications = criteria.get("indications", [])
        if indications:
            part += "\n**Indications:**\n"
            for ind in indications:
                name = ind.get("indication_name", "")
                codes = ind.get("indication_codes", [])
                code_str = ", ".join(c.get("code", "") for c in codes) if codes else ""
                part += f"- {name} {f'({code_str})' if code_str else ''}\n"

        return part


# Global instance
_policy_assistant: Optional[PolicyAssistant] = None


def get_policy_assistant() -> PolicyAssistant:
    """Get or create the global PolicyAssistant."""
    global _policy_assistant
    if _policy_assistant is None:
        _policy_assistant = PolicyAssistant()
    return _policy_assistant
