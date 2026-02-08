"""Claude client for policy reasoning - NO FALLBACK."""
import json
from typing import Dict, Any, Optional

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from backend.config.settings import get_settings
from backend.config.logging_config import get_logger
from backend.reasoning.json_utils import extract_json_from_text

logger = get_logger(__name__)


class ClaudePolicyReasoningError(Exception):
    """Error in Claude policy reasoning - critical, no fallback allowed."""
    pass


class ClaudePAClient:
    """
    Claude client specialized for prior authorization policy reasoning.

    CRITICAL: This client has NO FALLBACK. If Claude fails, the error propagates.
    This is intentional for clinical accuracy - we cannot substitute with less
    capable models for policy reasoning tasks.
    """

    def __init__(self):
        """Initialize the Claude PA client."""
        settings = get_settings()
        self.client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=180.0
        )
        self.model = settings.claude_model
        self.max_tokens = settings.claude_max_output_tokens
        logger.info("Claude PA client initialized", model=self.model)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((anthropic.APIConnectionError, anthropic.RateLimitError)),
        reraise=True
    )
    async def _make_api_call(self, temperature: float, system: str, prompt: str):
        """Inner method that tenacity retries on transient errors."""
        return await self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": prompt}]
        )

    async def analyze_policy(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        response_format: str = "json"
    ) -> Dict[str, Any]:
        """
        Analyze a policy using Claude.

        CRITICAL: No fallback. Errors propagate.

        Args:
            prompt: The analysis prompt with all context
            system_prompt: Optional system prompt override
            temperature: Temperature for generation (default: 0.0 for deterministic clinical reasoning)
            response_format: Expected response format ("json" or "text")

        Returns:
            Parsed response from Claude

        Raises:
            ClaudePolicyReasoningError: If analysis fails
        """
        logger.info("Starting policy analysis with Claude", model=self.model)

        from backend.reasoning.prompt_loader import get_prompt_loader
        default_system = get_prompt_loader().load("system/clinical_reasoning_base.txt")

        try:
            message = await self._make_api_call(
                temperature=temperature,
                system=system_prompt or default_system,
                prompt=prompt
            )

            if not message.content:
                raise ClaudePolicyReasoningError("Empty response from Claude (no content blocks)")

            response_text = message.content[0].text
            logger.debug("Claude response received", length=len(response_text))

            if response_format == "json":
                parsed = self._extract_json(response_text)
                return parsed
            else:
                return {"response": response_text}

        except anthropic.APIConnectionError as e:
            logger.error("Claude API connection error", error=str(e))
            raise ClaudePolicyReasoningError(f"Claude API connection failed: {e}") from e
        except anthropic.RateLimitError as e:
            logger.error("Claude rate limit exceeded", error=str(e))
            raise ClaudePolicyReasoningError(f"Claude rate limit exceeded: {e}") from e
        except anthropic.APIStatusError as e:
            logger.error("Claude API error", status_code=e.status_code, error=str(e))
            raise ClaudePolicyReasoningError(f"Claude API error ({e.status_code}): {e}") from e
        except json.JSONDecodeError as e:
            logger.error("Failed to parse Claude response as JSON", error=str(e))
            raise ClaudePolicyReasoningError(f"Invalid JSON response from Claude: {e}") from e
        except Exception as e:
            logger.error("Unexpected error in Claude policy analysis", error=str(e))
            raise ClaudePolicyReasoningError(f"Policy analysis failed: {e}") from e

    async def generate_appeal_strategy(
        self,
        denial_context: Dict[str, Any],
        patient_info: Dict[str, Any],
        policy_text: str
    ) -> Dict[str, Any]:
        """
        Generate an appeal strategy using Claude.

        CRITICAL: No fallback. Clinical accuracy required.

        Args:
            denial_context: Information about the denial
            patient_info: Patient clinical information
            policy_text: Relevant policy text

        Returns:
            Appeal strategy recommendations
        """
        from backend.reasoning.prompt_loader import get_prompt_loader

        prompt_loader = get_prompt_loader()
        prompt = prompt_loader.load(
            "appeals/appeal_strategy.txt",
            {
                "denial_details": denial_context,
                "patient_profile": patient_info,
                "policy_document": policy_text,
                "original_request": denial_context.get("original_request", {}),
                "available_documentation": denial_context.get("available_documentation", [])
            }
        )

        return await self.analyze_policy(prompt, response_format="json")

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Extract JSON from response text using shared utility."""
        return extract_json_from_text(text)

    async def health_check(self) -> bool:
        """Check if Claude API is accessible."""
        try:
            message = await self.client.messages.create(
                model=self.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "Reply with 'ok'"}]
            )
            return bool(message.content) and "ok" in message.content[0].text.lower()
        except Exception as e:
            logger.error("Claude health check failed", error=str(e))
            return False
