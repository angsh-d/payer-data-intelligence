"""Gemini client for general tasks - primary model with Azure fallback."""
import json
from typing import Dict, Any, Optional, List

from google import genai
from google.genai import types
from google.api_core.exceptions import (
    GoogleAPIError,
    ServiceUnavailable,
    TooManyRequests,
    DeadlineExceeded,
)
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from backend.config.settings import get_settings
from backend.config.logging_config import get_logger
from backend.reasoning.json_utils import extract_json_from_text

logger = get_logger(__name__)


class GeminiError(Exception):
    """Error in Gemini API call."""
    pass


class GeminiClient:
    """
    Gemini client for general tasks.
    Used as primary model for non-policy-reasoning tasks.
    Falls back to Azure OpenAI if Gemini fails.
    """

    def __init__(self):
        """Initialize the Gemini client."""
        settings = get_settings()
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model_name = settings.gemini_model
        self.max_output_tokens = settings.gemini_max_output_tokens
        logger.info("Gemini client initialized", model=self.model_name)

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type((
            GoogleAPIError, ServiceUnavailable, TooManyRequests,
            DeadlineExceeded, ConnectionError, TimeoutError,
        )),
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
        Generate content using Gemini.

        Args:
            prompt: The generation prompt
            system_prompt: Optional system instruction
            temperature: Temperature for generation
            response_format: Expected format ("json" or "text")

        Returns:
            Generated response

        Raises:
            GeminiError: If generation fails
        """
        logger.info("Generating with Gemini", model=self.model_name)

        try:
            config = types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=self.max_output_tokens,
                system_instruction=system_prompt if system_prompt else None,
            )

            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )

            if not response.text:
                raise GeminiError("Empty response from Gemini")

            response_text = response.text
            usage_meta = getattr(response, 'usage_metadata', None)
            input_tokens = getattr(usage_meta, 'prompt_token_count', 0) if usage_meta else 0
            output_tokens = getattr(usage_meta, 'candidates_token_count', 0) if usage_meta else 0
            logger.debug(
                "Gemini response received",
                length=len(response_text),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

            usage = {"input_tokens": input_tokens, "output_tokens": output_tokens, "model": self.model_name}

            if response_format == "json":
                parsed = self._extract_json(response_text)
                parsed["_usage"] = usage
                return parsed
            else:
                return {"response": response_text, "_usage": usage}

        except Exception as e:
            logger.error("Gemini generation failed", error=str(e))
            raise GeminiError(f"Gemini generation failed: {e}") from e

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
    ):
        """
        Stream content generation from Gemini, yielding text chunks.

        Yields:
            String chunks of the response as they arrive
        """
        logger.info("Streaming with Gemini", model=self.model_name)

        try:
            config = types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=self.max_output_tokens,
                system_instruction=system_prompt if system_prompt else None,
            )

            async for chunk in self.client.aio.models.generate_content_stream(
                model=self.model_name,
                contents=prompt,
                config=config,
            ):
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error("Gemini streaming failed", error=str(e))
            raise GeminiError(f"Gemini streaming failed: {e}") from e

    async def summarize(self, text: str, max_length: int = 500) -> str:
        """
        Summarize text using Gemini.

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
            notification_type: Type of notification (provider, patient, etc.)
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

    async def embed(self, text: str, task_type: str = "SEMANTIC_SIMILARITY") -> List[float]:
        """
        Generate an embedding vector for the given text using Gemini embedding model.

        Args:
            text: Text to embed
            task_type: Embedding task type (SEMANTIC_SIMILARITY, RETRIEVAL_QUERY, etc.)

        Returns:
            List of 768 floats (embedding vector)
        """
        try:
            result = await self.client.aio.models.embed_content(
                model="gemini-embedding-001",
                contents=text,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=768,
                ),
            )
            return result.embeddings[0].values
        except Exception as e:
            logger.error("Gemini embedding failed", error=str(e))
            raise GeminiError(f"Gemini embedding failed: {e}") from e

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Extract JSON from response text using shared utility."""
        return extract_json_from_text(text)

    async def health_check(self) -> bool:
        """Check if Gemini API is accessible."""
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents="Reply with 'ok'",
                config=types.GenerateContentConfig(max_output_tokens=10),
            )
            return "ok" in response.text.lower()
        except Exception as e:
            logger.error("Gemini health check failed", error=str(e))
            return False
