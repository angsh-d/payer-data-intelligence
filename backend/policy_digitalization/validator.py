"""Pass 2: Claude Policy Validator — validates extraction against original policy."""

import json
from typing import Dict, Any, List, Optional

from pydantic import BaseModel, Field

from backend.models.enums import TaskCategory
from backend.reasoning.llm_gateway import get_llm_gateway
from backend.reasoning.prompt_loader import get_prompt_loader
from backend.reasoning.json_utils import extract_json_from_text
from backend.policy_digitalization.extractor import RawExtractionResult
from backend.policy_digitalization.exceptions import ValidationError
from backend.config.logging_config import get_logger

logger = get_logger(__name__)


class ValidatedExtractionResult(BaseModel):
    """Result of Pass 2 validation."""
    extracted_data: Dict[str, Any]
    validation_status: str = "valid"  # valid, needs_corrections, major_issues
    quality_score: float = 0.0
    corrections_applied: List[Dict] = Field(default_factory=list)
    missing_criteria_added: List[Dict] = Field(default_factory=list)
    confidence_overrides: List[Dict] = Field(default_factory=list)
    overall_assessment: str = ""


class ClaudePolicyValidator:
    """Validates extraction using Claude (POLICY_REASONING — Claude only, no fallback)."""

    def __init__(self):
        self.llm_gateway = get_llm_gateway()
        self.prompt_loader = get_prompt_loader()
        logger.info("ClaudePolicyValidator initialized")

    async def validate_extraction(
        self,
        raw: RawExtractionResult,
        policy_text: str,
    ) -> ValidatedExtractionResult:
        """
        Validate Pass 1 extraction against original policy text.

        Uses POLICY_REASONING task category → Claude ONLY, no fallback.
        """
        logger.info("Starting Pass 2 validation")

        # Serialize extracted data for the prompt
        extracted_json = json.dumps(raw.extracted_data, indent=2, default=str)

        prompt = self.prompt_loader.load(
            "policy_digitalization/validation_pass2.txt",
            {
                "extracted_data": extracted_json,
                "policy_document": policy_text,
            }
        )

        result = await self.llm_gateway.generate(
            task_category=TaskCategory.POLICY_REASONING,
            prompt=prompt,
            temperature=0.1,
            response_format="json",
        )

        # Parse validation response
        if isinstance(result, str):
            validation_data = extract_json_from_text(result)
        elif isinstance(result, dict):
            if "content" in result and isinstance(result["content"], str):
                validation_data = extract_json_from_text(result["content"])
            else:
                validation_data = result
        else:
            raise ValidationError(f"Unexpected result type: {type(result)}")

        # Apply corrections to extracted data
        corrected_data = self._apply_corrections(raw.extracted_data, validation_data)

        logger.info(
            "Pass 2 validation complete",
            status=validation_data.get("validation_status", "unknown"),
            quality=validation_data.get("quality_score", 0),
            corrections=len(validation_data.get("corrections", [])),
            missing_added=len(validation_data.get("completeness", {}).get("missing_criteria", [])),
        )

        return ValidatedExtractionResult(
            extracted_data=corrected_data,
            validation_status=validation_data.get("validation_status", "valid"),
            quality_score=validation_data.get("quality_score", 0.0),
            corrections_applied=validation_data.get("corrections", []),
            missing_criteria_added=validation_data.get("completeness", {}).get("missing_criteria", []),
            confidence_overrides=validation_data.get("confidence_overrides", []),
            overall_assessment=validation_data.get("overall_assessment", ""),
        )

    # Fields that Claude validation is allowed to correct
    CORRECTABLE_FIELDS = {
        "name", "description", "policy_text", "threshold_value",
        "threshold_value_upper", "threshold_unit", "comparison_operator",
        "drug_names", "drug_classes", "allowed_values", "clinical_codes",
        "source_text_excerpt", "minimum_duration_days",
    }

    def _apply_corrections(
        self, extracted_data: Dict[str, Any], validation_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Apply validated corrections to extracted data."""
        import copy
        data = copy.deepcopy(extracted_data)

        # Apply field-level corrections
        for correction in validation_data.get("corrections", []):
            cid = correction.get("criterion_id")
            field = correction.get("field")
            new_value = correction.get("corrected_value")
            if field and field not in self.CORRECTABLE_FIELDS:
                logger.warning("Ignoring correction to non-correctable field", field=field, criterion=cid)
                continue
            if cid and field and new_value is not None and cid in data.get("atomic_criteria", {}):
                data["atomic_criteria"][cid][field] = new_value
                logger.info("Applied correction", criterion=cid, field=field)

        # Add missing criteria
        for missing in validation_data.get("completeness", {}).get("missing_criteria", []):
            cid = missing.get("criterion_id")
            if cid and cid not in data.get("atomic_criteria", {}):
                data.setdefault("atomic_criteria", {})[cid] = missing
                logger.info("Added missing criterion", criterion=cid)

        # Apply confidence overrides
        for override in validation_data.get("confidence_overrides", []):
            cid = override.get("criterion_id")
            new_conf = override.get("validated_confidence")
            if cid and new_conf is not None and cid in data.get("atomic_criteria", {}):
                data["atomic_criteria"][cid]["extraction_confidence"] = new_conf

        return data
