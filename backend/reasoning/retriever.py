"""RAG Retriever — chunk, embed, and retrieve policy content for context-aware LLM calls.

Integrates with PolicyEmbeddingModel for vector storage and
Gemini embedding API for 768-dim embedding generation.
"""

import uuid
import json
from typing import Optional, List, Dict, Any

from backend.reasoning.llm_gateway import get_llm_gateway, LLMGateway
from backend.storage.database import get_db
from backend.storage.models import PolicyEmbeddingModel
from backend.config.logging_config import get_logger

logger = get_logger(__name__)

# Chunk configuration
CHUNK_SIZE = 1500  # Characters per chunk
CHUNK_OVERLAP = 200  # Overlap between adjacent chunks
MIN_CHUNK_SIZE = 100  # Ignore chunks smaller than this


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Split text into overlapping chunks for embedding.

    Uses paragraph boundaries when possible, falling back to
    sentence boundaries, then character-level splitting.
    """
    if len(text) <= chunk_size:
        return [text] if len(text) >= MIN_CHUNK_SIZE else []

    # Split by paragraphs first
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= chunk_size:
            current_chunk += ("\n\n" if current_chunk else "") + para
        else:
            if current_chunk and len(current_chunk) >= MIN_CHUNK_SIZE:
                chunks.append(current_chunk)
            # If a single paragraph is too large, split it by sentences
            if len(para) > chunk_size:
                sentences = para.replace(". ", ".\n").split("\n")
                sub_chunk = ""
                for sent in sentences:
                    if len(sub_chunk) + len(sent) + 1 <= chunk_size:
                        sub_chunk += (" " if sub_chunk else "") + sent
                    else:
                        if sub_chunk and len(sub_chunk) >= MIN_CHUNK_SIZE:
                            chunks.append(sub_chunk)
                        sub_chunk = sent
                if sub_chunk and len(sub_chunk) >= MIN_CHUNK_SIZE:
                    current_chunk = sub_chunk
                else:
                    current_chunk = ""
            else:
                current_chunk = para

    if current_chunk and len(current_chunk) >= MIN_CHUNK_SIZE:
        chunks.append(current_chunk)

    # Add overlap between chunks
    if overlap > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_tail = chunks[i - 1][-overlap:]
            overlapped.append(prev_tail + " " + chunks[i])
        chunks = overlapped

    return chunks


class PolicyRetriever:
    """Handles chunking, embedding, and retrieval of policy content."""

    def __init__(self):
        self.gateway: LLMGateway = get_llm_gateway()

    async def index_policy(
        self,
        payer_name: str,
        medication_name: str,
        policy_text: str,
        policy_version: Optional[str] = None,
    ) -> int:
        """
        Chunk and embed a policy document, storing embeddings in the database.

        Args:
            payer_name: Payer identifier
            medication_name: Medication identifier
            policy_text: Full policy text to index
            policy_version: Optional version label

        Returns:
            Number of chunks indexed
        """
        payer = payer_name.lower()
        medication = medication_name.lower()

        # Delete existing embeddings for this policy/version
        from sqlalchemy import delete
        async with get_db() as session:
            stmt = delete(PolicyEmbeddingModel).where(
                PolicyEmbeddingModel.payer_name == payer,
                PolicyEmbeddingModel.medication_name == medication,
            )
            if policy_version:
                stmt = stmt.where(PolicyEmbeddingModel.policy_version == policy_version)
            await session.execute(stmt)

        # Chunk the text
        chunks = chunk_text(policy_text)
        if not chunks:
            logger.warning("No chunks generated from policy text", length=len(policy_text))
            return 0

        # Embed and store each chunk
        indexed = 0
        for i, chunk in enumerate(chunks):
            try:
                embedding = await self.gateway.embed(chunk, task_type="RETRIEVAL_DOCUMENT")
                async with get_db() as session:
                    row = PolicyEmbeddingModel(
                        id=str(uuid.uuid4()),
                        payer_name=payer,
                        medication_name=medication,
                        policy_version=policy_version,
                        chunk_index=i,
                        chunk_text=chunk,
                        embedding=embedding,
                    )
                    session.add(row)
                indexed += 1
            except Exception as e:
                logger.warning("Failed to embed chunk", chunk_index=i, error=str(e))
                continue

        logger.info(
            "Policy indexed for RAG",
            payer=payer, medication=medication,
            version=policy_version, chunks=indexed,
        )
        return indexed

    async def retrieve(
        self,
        query: str,
        payer_filter: Optional[str] = None,
        medication_filter: Optional[str] = None,
        top_k: int = 5,
        similarity_threshold: float = 0.70,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve the most relevant policy chunks for a query.

        Args:
            query: Search query
            payer_filter: Optional payer filter
            medication_filter: Optional medication filter
            top_k: Number of top results to return
            similarity_threshold: Minimum similarity score

        Returns:
            List of dicts with chunk_text, similarity, payer, medication, version
        """
        from sqlalchemy import select

        try:
            query_embedding = await self.gateway.embed(query, task_type="RETRIEVAL_QUERY")
        except Exception as e:
            logger.warning("Query embedding failed", error=str(e))
            return []

        async with get_db() as session:
            stmt = select(PolicyEmbeddingModel)
            if payer_filter:
                stmt = stmt.where(PolicyEmbeddingModel.payer_name == payer_filter.lower())
            if medication_filter:
                stmt = stmt.where(PolicyEmbeddingModel.medication_name == medication_filter.lower())
            stmt = stmt.limit(200)  # Scan limit

            result = await session.execute(stmt)
            all_chunks = result.scalars().all()

        # Score and rank
        scored = []
        for chunk in all_chunks:
            score = LLMGateway.cosine_similarity(query_embedding, chunk.embedding)
            if score >= similarity_threshold:
                scored.append({
                    "chunk_text": chunk.chunk_text,
                    "similarity": round(score, 4),
                    "payer": chunk.payer_name,
                    "medication": chunk.medication_name,
                    "version": chunk.policy_version,
                    "chunk_index": chunk.chunk_index,
                })

        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:top_k]

    async def index_digitized_policy(
        self,
        payer_name: str,
        medication_name: str,
        parsed_criteria: Dict[str, Any],
        policy_version: Optional[str] = None,
    ) -> int:
        """
        Index a digitized (structured) policy by serializing criteria into text chunks.

        This is called after the 3-pass pipeline completes.

        Args:
            payer_name: Payer identifier
            medication_name: Medication identifier
            parsed_criteria: The parsed_criteria JSON from PolicyCacheModel
            policy_version: Optional version label

        Returns:
            Number of chunks indexed
        """
        # Serialize criteria into text format for embedding
        text_parts = []

        # Atomic criteria
        atomic = parsed_criteria.get("atomic_criteria", {})
        for cid, crit in atomic.items():
            desc = crit.get("description", "")
            ctype = crit.get("criterion_type", "")
            policy_text = crit.get("policy_text", "")
            text_parts.append(f"Criterion {cid} [{ctype}]: {desc}\nPolicy Text: {policy_text}")

        # Indications
        for ind in parsed_criteria.get("indications", []):
            name = ind.get("indication_name", "")
            text_parts.append(f"Indication: {name}")

        # Step therapy
        for st in parsed_criteria.get("step_therapy_requirements", []):
            indication = st.get("indication", "All")
            drugs = st.get("required_drug_classes", [])
            text_parts.append(f"Step Therapy for {indication}: {', '.join(drugs)}")

        # Exclusions
        for ex in parsed_criteria.get("exclusions", []):
            text_parts.append(f"Exclusion: {ex.get('description', '')}")

        full_text = "\n\n".join(text_parts)
        return await self.index_policy(payer_name, medication_name, full_text, policy_version)


# Global instance
_retriever: Optional[PolicyRetriever] = None


def get_policy_retriever() -> PolicyRetriever:
    """Get or create the global PolicyRetriever."""
    global _retriever
    if _retriever is None:
        _retriever = PolicyRetriever()
    return _retriever
