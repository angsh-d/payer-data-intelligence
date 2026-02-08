"""Pass 1: Gemini Policy Extractor — extracts structured criteria from policy documents."""

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

from pydantic import BaseModel, Field

from backend.models.enums import TaskCategory
from backend.reasoning.llm_gateway import get_llm_gateway
from backend.reasoning.prompt_loader import get_prompt_loader
from backend.reasoning.json_utils import extract_json_from_text
from backend.policy_digitalization.exceptions import ExtractionError
from backend.config.logging_config import get_logger

logger = get_logger(__name__)


class RawExtractionResult(BaseModel):
    """Result of Pass 1 extraction."""
    extracted_data: Dict[str, Any]
    source_hash: str
    source_type: str  # "pdf" or "text"
    extraction_model: Optional[str] = None
    extraction_timestamp: str = ""
    sections_identified: list = Field(default_factory=list)


class GeminiPolicyExtractor:
    """Extracts structured policy criteria using Gemini (DATA_EXTRACTION task category)."""

    def __init__(self):
        self.llm_gateway = get_llm_gateway()
        self.prompt_loader = get_prompt_loader()
        logger.info("GeminiPolicyExtractor initialized")

    async def extract_from_text(
        self, policy_text: str, policy_id: str = "UNKNOWN", version_hint: str = ""
    ) -> RawExtractionResult:
        """
        Extract structured criteria from policy text.

        Uses DATA_EXTRACTION task category → Gemini primary, Azure fallback.

        Args:
            policy_text: Raw policy text to extract from
            policy_id: Identifier for the policy
            version_hint: Optional directive for multi-version documents (e.g.,
                "This document contains multiple policy versions. Extract ONLY
                the 2025 policy version.")
        """
        logger.info("Starting Pass 1 extraction from text", policy_id=policy_id, text_length=len(policy_text))

        doc_hash = hashlib.sha256(policy_text.encode()).hexdigest()[:16]

        prompt = self.prompt_loader.load(
            "policy_digitalization/extraction_pass1.txt",
            {"policy_document": policy_text, "version_hint": version_hint}
        )

        result = await self.llm_gateway.generate(
            task_category=TaskCategory.DATA_EXTRACTION,
            prompt=prompt,
            temperature=0.1,
            response_format="json",
        )

        # The gateway returns parsed dict or raw text
        if isinstance(result, str):
            extracted_data = extract_json_from_text(result)
        elif isinstance(result, dict):
            # Check if the actual data is nested under a key
            if "content" in result and isinstance(result["content"], str):
                extracted_data = extract_json_from_text(result["content"])
            elif "atomic_criteria" in result:
                extracted_data = result
            else:
                extracted_data = result
        else:
            raise ExtractionError(f"Unexpected result type from LLM: {type(result)}")

        logger.info(
            "Pass 1 extraction complete",
            criteria_count=len(extracted_data.get("atomic_criteria", {})),
            groups_count=len(extracted_data.get("criterion_groups", {})),
            indications_count=len(extracted_data.get("indications", [])),
        )

        return RawExtractionResult(
            extracted_data=extracted_data,
            source_hash=doc_hash,
            source_type="text",
            extraction_model="gemini",
            extraction_timestamp=datetime.now(timezone.utc).isoformat(),
            sections_identified=extracted_data.get("sections_identified", []),
        )

    async def extract_from_pdf(self, pdf_path: str, version_hint: str = "") -> RawExtractionResult:
        """
        Extract structured criteria from a PDF policy document.

        Uploads PDF to Gemini for extraction.

        Args:
            pdf_path: Path to the PDF file
            version_hint: Optional directive for multi-version documents
        """
        from google import genai
        from google.genai import types
        from backend.config.settings import get_settings

        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise ExtractionError(f"Policy PDF not found: {pdf_path}")

        logger.info("Starting Pass 1 extraction from PDF", path=str(pdf_path))

        # Calculate hash
        sha256 = hashlib.sha256()
        with open(pdf_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        doc_hash = sha256.hexdigest()[:16]

        # Upload PDF via async Gemini client
        settings = get_settings()
        client = genai.Client(api_key=settings.gemini_api_key)
        uploaded_file = await client.aio.files.upload(file=str(pdf_path))

        prompt = self.prompt_loader.load(
            "policy_digitalization/extraction_pass1.txt",
            {"policy_document": "[PDF DOCUMENT ATTACHED]", "version_hint": version_hint}
        )

        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=[uploaded_file, prompt],
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=65536,
            ),
        )

        extracted_data = extract_json_from_text(response.text)

        logger.info(
            "Pass 1 PDF extraction complete",
            criteria_count=len(extracted_data.get("atomic_criteria", {})),
        )

        return RawExtractionResult(
            extracted_data=extracted_data,
            source_hash=doc_hash,
            source_type="pdf",
            extraction_model=settings.gemini_model,
            extraction_timestamp=datetime.now(timezone.utc).isoformat(),
            sections_identified=extracted_data.get("sections_identified", []),
        )
