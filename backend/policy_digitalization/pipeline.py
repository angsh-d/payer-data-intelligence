"""Policy Digitalization Pipeline — orchestrates multi-pass extraction.

Pass 1: Gemini extracts structured criteria from policy document
Pass 2: Claude validates extraction against original policy text
Pass 3: Reference data validation (clinical codes)
Store: Persist to PolicyCacheModel.parsed_criteria
"""

import json
from typing import Optional
from pathlib import Path

from pydantic import BaseModel, Field

from backend.models.policy_schema import DigitizedPolicy
from backend.policy_digitalization.extractor import GeminiPolicyExtractor, RawExtractionResult
from backend.policy_digitalization.validator import ClaudePolicyValidator, ValidatedExtractionResult
from backend.policy_digitalization.reference_validator import ReferenceDataValidator
from backend.policy_digitalization.policy_repository import get_policy_repository
from backend.policy_digitalization.exceptions import ExtractionError, PolicyNotFoundError
from backend.config.logging_config import get_logger
from backend.config.settings import get_settings

logger = get_logger(__name__)

def _load_medication_aliases() -> dict:
    """Load medication name aliases from config file."""
    config_path = Path("data/config/medication_aliases.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("aliases", {})
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Could not load medication aliases config", error=str(e))
        return {}

# Brand ↔ generic medication name aliases for policy file resolution.
# Loaded from data/config/medication_aliases.json — extensible without code changes.
MEDICATION_NAME_ALIASES = _load_medication_aliases()


class DigitalizationResult(BaseModel):
    """Result of the full digitalization pipeline."""
    policy: Optional[dict] = None  # DigitizedPolicy as dict for JSON serialization
    source_type: str = ""
    passes_completed: int = 0
    extraction_quality: str = ""
    validation_status: str = ""
    quality_score: float = 0.0
    corrections_count: int = 0
    criteria_count: int = 0
    indications_count: int = 0
    stored: bool = False
    cache_id: Optional[str] = None


class PolicyDigitalizationPipeline:
    """Orchestrates the 3-pass policy digitalization pipeline."""

    def __init__(self):
        self.extractor = GeminiPolicyExtractor()
        self.validator = ClaudePolicyValidator()
        self.reference_validator = ReferenceDataValidator()
        self.repository = get_policy_repository()
        logger.info("PolicyDigitalizationPipeline initialized")

    async def digitalize_policy(
        self,
        source: str,
        source_type: str = "text",  # "text" or "pdf"
        skip_validation: bool = False,
        payer_name: Optional[str] = None,
        medication_name: Optional[str] = None,
        skip_store: bool = False,
        version_hint: str = "",
    ) -> DigitalizationResult:
        """
        Run the full 3-pass pipeline.

        Args:
            source: Policy text or path to PDF
            source_type: "text" or "pdf"
            skip_validation: Skip Pass 2 (Claude validation) — useful for testing
            payer_name: Override payer name for storage key (ensures lookup consistency)
            medication_name: Override medication name for storage key
            skip_store: Skip storing the result in the repository
            version_hint: Directive for multi-version docs (e.g., extract only 2025 version)

        Returns:
            DigitalizationResult with the digitized policy
        """
        logger.info("Starting digitalization pipeline", source_type=source_type)

        # Pass 1: Extract
        if source_type == "pdf":
            raw = await self.extractor.extract_from_pdf(source, version_hint=version_hint)
            policy_text = self._load_policy_text_for_pdf(source)
        else:
            raw = await self.extractor.extract_from_text(source, version_hint=version_hint)
            policy_text = source

        passes_completed = 1

        # Guard against empty extraction
        if not raw.extracted_data.get("atomic_criteria") and not raw.extracted_data.get("indications"):
            raise ExtractionError(
                f"Pass 1 returned empty extraction (no criteria or indications). "
                f"Source length: {len(source)} chars, model: {raw.extraction_model}"
            )

        # Pass 2: Validate (unless skipped)
        if skip_validation:
            validated = ValidatedExtractionResult(
                extracted_data=raw.extracted_data,
                validation_status="skipped",
                quality_score=0.7,
            )
        else:
            validated = await self.validator.validate_extraction(raw, policy_text)
            passes_completed = 2

        # Pass 3: Reference validation + build DigitizedPolicy
        policy = await self.reference_validator.validate_codes(validated)
        passes_completed = 3

        # Add extraction metadata
        policy.extraction_timestamp = raw.extraction_timestamp
        policy.extraction_model = raw.extraction_model
        policy.source_document_hash = raw.source_hash

        # Override payer/medication names so the DB key matches the caller's lookup key
        if payer_name:
            policy.payer_name = payer_name
        if medication_name:
            policy.medication_name = medication_name

        # Store in repository (skip when caller handles storage, e.g. upload endpoint)
        cache_id = None
        if not skip_store:
            cache_id = await self.repository.store(policy)

        policy_dict = policy.model_dump(mode="json")

        logger.info(
            "Digitalization pipeline complete",
            policy_id=policy.policy_id,
            criteria=len(policy.atomic_criteria),
            indications=len(policy.indications),
            quality=policy.extraction_quality,
        )

        return DigitalizationResult(
            policy=policy_dict,
            source_type=source_type,
            passes_completed=passes_completed,
            extraction_quality=policy.extraction_quality or "",
            validation_status=validated.validation_status,
            quality_score=validated.quality_score,
            corrections_count=len(validated.corrections_applied),
            criteria_count=len(policy.atomic_criteria),
            indications_count=len(policy.indications),
            stored=not skip_store,
            cache_id=cache_id,
        )

    async def get_or_digitalize(
        self,
        payer_name: str,
        medication_name: str,
    ) -> DigitizedPolicy:
        """
        Load from cache or digitalize from file.

        First checks PolicyCacheModel for cached digitized policy.
        If not found, looks for pre-digitized JSON file, raw policy text,
        or PDF and digitalizes. Tries brand/generic name aliases when the
        primary medication name doesn't match any file.
        """
        # Try cache first
        cached = await self.repository.load(payer_name, medication_name)
        if cached:
            logger.info("Loaded digitized policy from cache", payer=payer_name, medication=medication_name)
            return cached

        # Sanitize keys — with path traversal protection
        import re
        payer_key = payer_name.lower().replace(" ", "_")
        med_key = medication_name.lower().replace(" ", "_")
        if not re.match(r'^[a-z0-9_-]+$', payer_key) or not re.match(r'^[a-z0-9_-]+$', med_key):
            raise PolicyNotFoundError(f"Invalid payer/medication name: {payer_name}/{medication_name}")

        policies_root = Path(get_settings().policies_dir).resolve()

        # Build list of medication keys to try (primary + brand/generic alias)
        med_keys = [med_key]
        alias = MEDICATION_NAME_ALIASES.get(med_key)
        if alias:
            med_keys.append(alias)

        for mk in med_keys:
            # Try pre-digitized JSON
            digitized_path = (policies_root / f"{payer_key}_{mk}_digitized.json").resolve()
            try:
                digitized_path.relative_to(policies_root)
            except ValueError:
                continue

            if digitized_path.exists():
                with open(digitized_path) as f:
                    data = json.load(f)
                policy = DigitizedPolicy(**data)
                await self.repository.store(policy)
                logger.info("Loaded from pre-digitized JSON and cached", path=str(digitized_path))
                return policy

            # Try raw policy text
            txt_path = (policies_root / f"{payer_key}_{mk}.txt").resolve()
            try:
                txt_path.relative_to(policies_root)
            except ValueError:
                continue

            if txt_path.exists():
                with open(txt_path) as f:
                    policy_text = f.read()
                result = await self.digitalize_policy(
                    policy_text, source_type="text",
                    payer_name=payer_name, medication_name=medication_name,
                )
                if result.policy:
                    return DigitizedPolicy(**result.policy)

            # Try PDF policy
            pdf_path = (policies_root / f"{payer_key}_{mk}.pdf").resolve()
            try:
                pdf_path.relative_to(policies_root)
            except ValueError:
                continue

            if pdf_path.exists():
                logger.info("Found PDF policy, running digitalization", path=str(pdf_path))
                result = await self.digitalize_policy(
                    str(pdf_path), source_type="pdf",
                    payer_name=payer_name, medication_name=medication_name,
                )
                if result.policy:
                    return DigitizedPolicy(**result.policy)

        raise PolicyNotFoundError(
            f"No policy found for {payer_name}/{medication_name}"
        )

    async def digitalize_versioned(
        self,
        source: str,
        source_type: str,
        payer_name: str,
        medication_name: str,
        version_label: str,
        version_year: Optional[int] = None,
        skip_validation: bool = False,
    ) -> DigitalizationResult:
        """
        Digitalize a specific version of a policy and store it with a version label.

        For multi-version documents (e.g., BCBS PDFs with 2024 and 2025 versions),
        pass version_year to instruct the LLM to extract only that version.

        Args:
            source: Policy text or path to PDF
            source_type: "text" or "pdf"
            payer_name: Payer name for storage key
            medication_name: Medication name for storage key
            version_label: Version label (e.g., "v1", "v2", "2024", "2025")
            version_year: If set, instructs LLM to extract only this year's version
            skip_validation: Skip Pass 2 Claude validation

        Returns:
            DigitalizationResult
        """
        version_hint = ""
        if version_year:
            version_hint = (
                f"This document contains multiple policy versions. "
                f"Extract ONLY the {version_year} policy version. "
                f"Ignore criteria, dates, and requirements from other versions."
            )

        result = await self.digitalize_policy(
            source=source,
            source_type=source_type,
            skip_validation=skip_validation,
            payer_name=payer_name,
            medication_name=medication_name,
            skip_store=True,
            version_hint=version_hint,
        )

        # Store as versioned entry
        if result.policy:
            from backend.models.policy_schema import DigitizedPolicy
            policy = DigitizedPolicy(**result.policy)
            cache_id = await self.repository.store_version(policy, version_label)
            result.stored = True
            result.cache_id = cache_id
            logger.info(
                "Versioned policy stored",
                payer=payer_name, medication=medication_name,
                version=version_label, year=version_year,
            )

        return result

    def _load_policy_text_for_pdf(self, pdf_path: str) -> str:
        """Load companion text file for a PDF (for validation pass)."""
        policies_root = Path(get_settings().policies_dir).resolve()
        text_path = Path(pdf_path).with_suffix(".txt").resolve()
        try:
            text_path.relative_to(policies_root)
        except ValueError:
            logger.warning("PDF companion text path outside policies dir", path=str(pdf_path))
            return "[Original policy text not available — validation based on extraction only]"
        if text_path.exists():
            with open(text_path) as f:
                return f.read()
        return "[Original policy text not available — validation based on extraction only]"


# Global instance
_pipeline: Optional[PolicyDigitalizationPipeline] = None


def get_digitalization_pipeline() -> PolicyDigitalizationPipeline:
    """Get or create global pipeline instance."""
    global _pipeline
    if _pipeline is None:
        _pipeline = PolicyDigitalizationPipeline()
    return _pipeline
