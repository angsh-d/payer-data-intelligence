"""Azure OpenAI client - fallback for general tasks."""
import json
from typing import Dict, Any, Optional

from openai import AsyncAzureOpenAI, APIConnectionError, RateLimitError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from backend.config.settings import get_settings
from backend.config.logging_config import get_logger

logger = get_logger(__name__)


class AzureOpenAIError(Exception):
    """Error in Azure OpenAI API call."""
    pass


class AzureOpenAIClient:
    """
    Azure OpenAI client for general tasks.
    Used as fallback when Gemini fails.
    """

    def __init__(self):
        """Initialize the Azure OpenAI client."""
        settings = get_settings()
        self.client = AsyncAzureOpenAI(
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            azure_endpoint=settings.azure_openai_endpoint,
            timeout=180.0
        )
        self.deployment = settings.azure_openai_deployment
        self.max_tokens = settings.azure_max_output_tokens
        logger.info("Azure OpenAI client initialized", deployment=self.deployment)

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type((APIConnectionError, RateLimitError)),
        reraise=True
    )
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        response_format: str = "text"
    ) -> Dict[str, Any]:
        """
        Generate content using Azure OpenAI.

        Args:
            prompt: The generation prompt
            system_prompt: Optional system instruction
            temperature: Temperature for generation
            response_format: Expected format ("json" or "text")

        Returns:
            Generated response

        Raises:
            AzureOpenAIError: If generation fails
        """
        logger.info("Generating with Azure OpenAI", deployment=self.deployment)

        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            # Build request params - some models (gpt-5-mini) don't support temperature
            request_params = {
                "model": self.deployment,
                "messages": messages,
                "max_completion_tokens": self.max_tokens,
            }
            if response_format == "json":
                request_params["response_format"] = {"type": "json_object"}
            # Only set temperature if not using a model that doesn't support it
            if "mini" not in self.deployment.lower():
                request_params["temperature"] = temperature

            response = await self.client.chat.completions.create(**request_params)

            if not response.choices:
                raise AzureOpenAIError("No choices in Azure OpenAI response")
            response_text = response.choices[0].message.content
            if not response_text:
                raise AzureOpenAIError("Empty response from Azure OpenAI")

            logger.debug("Azure OpenAI response received", length=len(response_text))

            if response_format == "json":
                parsed = json.loads(response_text)
                return parsed
            else:
                return {"response": response_text}

        except json.JSONDecodeError as e:
            logger.error("Failed to parse Azure OpenAI response as JSON", error=str(e))
            raise AzureOpenAIError(f"Invalid JSON response: {e}") from e
        except Exception as e:
            logger.error("Azure OpenAI generation failed", error=str(e))
            raise AzureOpenAIError(f"Azure OpenAI generation failed: {e}") from e

    async def summarize(self, text: str, max_length: int = 500) -> str:
        """
        Summarize text using Azure OpenAI.

        Args:
            text: Text to summarize
            max_length: Maximum summary length

        Returns:
            Summary text
        """
        from backend.reasoning.prompt_loader import get_prompt_loader
        prompt = get_prompt_loader().load(
            "general/summarize.txt",
            {"max_length": max_length, "text": text}
        )

        result = await self.generate(prompt, temperature=0.2, response_format="text")
        return result.get("response", "")

    async def extract_data(
        self,
        text: str,
        extraction_schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Extract structured data from text.

        Args:
            text: Text to extract from
            extraction_schema: JSON schema defining what to extract

        Returns:
            Extracted data matching schema
        """
        from backend.reasoning.prompt_loader import get_prompt_loader
        prompt = get_prompt_loader().load(
            "general/extract_data.txt",
            {"extraction_schema": extraction_schema, "text": text}
        )

        result = await self.generate(prompt, temperature=0.1, response_format="json")
        return result

    async def draft_notification(
        self,
        notification_type: str,
        context: Dict[str, Any]
    ) -> str:
        """
        Draft a notification message.

        Args:
            notification_type: Type of notification
            context: Context for the notification

        Returns:
            Drafted notification text
        """
        from backend.reasoning.prompt_loader import get_prompt_loader
        prompt = get_prompt_loader().load(
            "general/draft_notification.txt",
            {"notification_type": notification_type, "context": context}
        )

        result = await self.generate(prompt, temperature=0.3, response_format="text")
        return result.get("response", "")

    async def health_check(self) -> bool:
        """Check if Azure OpenAI API is accessible."""
        try:
            response = await self.client.chat.completions.create(
                model=self.deployment,
                messages=[{"role": "user", "content": "Reply with 'ok'"}],
                max_completion_tokens=10
            )
            content = response.choices[0].message.content if response.choices else None
            return bool(content) and "ok" in content.lower()
        except Exception as e:
            logger.error("Azure OpenAI health check failed", error=str(e))
            return False
