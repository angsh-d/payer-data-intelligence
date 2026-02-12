"""LLM Gateway for task-based model routing."""
import json
import math
import time
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List

from backend.models.enums import TaskCategory, LLMProvider
from backend.config.logging_config import get_logger
from backend.reasoning.claude_pa_client import ClaudePAClient, ClaudePolicyReasoningError
from backend.reasoning.gemini_client import GeminiClient, GeminiError
from backend.reasoning.openai_client import AzureOpenAIClient, AzureOpenAIError

logger = get_logger(__name__)

# Provider name → enum mapping
_PROVIDER_MAP = {
    "claude": LLMProvider.CLAUDE,
    "gemini": LLMProvider.GEMINI,
    "azure_openai": LLMProvider.AZURE_OPENAI,
}

# Task category name → enum mapping
_TASK_MAP = {cat.value: cat for cat in TaskCategory}


def _load_task_model_routing() -> Dict[TaskCategory, List[LLMProvider]]:
    """Load task-to-model routing from config file.

    Falls back to default Claude-first clinical routing if config unavailable.
    """
    config_path = Path("data/config/llm_routing.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        routing = {}
        for task_name, providers in data.get("routing", {}).items():
            task_cat = _TASK_MAP.get(task_name)
            if task_cat is None:
                logger.warning("Unknown task category in routing config", task=task_name)
                continue
            provider_list = [_PROVIDER_MAP[p] for p in providers if p in _PROVIDER_MAP]
            if provider_list:
                routing[task_cat] = provider_list
        logger.info("LLM routing loaded from config", tasks=len(routing))
        return routing
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        logger.warning("Could not load LLM routing config, using defaults", error=str(e))
        return {
            TaskCategory.POLICY_REASONING: [LLMProvider.CLAUDE, LLMProvider.AZURE_OPENAI],
            TaskCategory.APPEAL_STRATEGY: [LLMProvider.CLAUDE, LLMProvider.AZURE_OPENAI],
            TaskCategory.APPEAL_DRAFTING: [LLMProvider.GEMINI, LLMProvider.AZURE_OPENAI],
            TaskCategory.SUMMARY_GENERATION: [LLMProvider.GEMINI, LLMProvider.AZURE_OPENAI],
            TaskCategory.DATA_EXTRACTION: [LLMProvider.GEMINI, LLMProvider.AZURE_OPENAI],
            TaskCategory.NOTIFICATION: [LLMProvider.GEMINI, LLMProvider.AZURE_OPENAI],
            TaskCategory.POLICY_QA: [LLMProvider.CLAUDE],
        }


# Task to model routing — loaded from data/config/llm_routing.json
TASK_MODEL_ROUTING = _load_task_model_routing()


class LLMGatewayError(Exception):
    """Error from LLM Gateway."""
    pass


class LLMGateway:
    """
    Central gateway for LLM requests with task-based routing.

    Routes requests to appropriate models based on task category:
    - Policy reasoning → Claude (primary) → Azure OpenAI (fallback)
    - Appeal strategy → Claude (primary) → Azure OpenAI (fallback)
    - General tasks → Gemini (primary) → Azure OpenAI (fallback)
    """

    def __init__(self):
        """Initialize the LLM Gateway with all clients."""
        self._claude_client: Optional[ClaudePAClient] = None
        self._gemini_client: Optional[GeminiClient] = None
        self._azure_client: Optional[AzureOpenAIClient] = None
        logger.info("LLM Gateway initialized")

    @property
    def claude_client(self) -> ClaudePAClient:
        """Lazy-load Claude client."""
        if self._claude_client is None:
            self._claude_client = ClaudePAClient()
        return self._claude_client

    @property
    def gemini_client(self) -> GeminiClient:
        """Lazy-load Gemini client."""
        if self._gemini_client is None:
            self._gemini_client = GeminiClient()
        return self._gemini_client

    @property
    def azure_client(self) -> AzureOpenAIClient:
        """Lazy-load Azure OpenAI client."""
        if self._azure_client is None:
            self._azure_client = AzureOpenAIClient()
        return self._azure_client

    async def generate(
        self,
        task_category: TaskCategory,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        response_format: str = "text"
    ) -> Dict[str, Any]:
        """
        Generate content using the appropriate model for the task.

        Args:
            task_category: Category of task for routing
            prompt: The generation prompt
            system_prompt: Optional system instruction
            temperature: Temperature for generation
            response_format: Expected format ("json" or "text")

        Returns:
            Generated response with metadata

        Raises:
            LLMGatewayError: If all configured providers fail for the task
        """
        providers = TASK_MODEL_ROUTING.get(task_category, [LLMProvider.GEMINI, LLMProvider.AZURE_OPENAI])

        logger.info(
            "Routing LLM request",
            task_category=task_category.value,
            providers=[p.value for p in providers]
        )

        last_error = None

        for provider in providers:
            try:
                start_time = time.monotonic()
                result = await self._call_provider(
                    provider=provider,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    response_format=response_format
                )
                latency_ms = int((time.monotonic() - start_time) * 1000)
                result["provider"] = provider.value
                result["task_category"] = task_category.value

                # Record LLM metrics asynchronously
                usage = result.pop("_usage", None)
                if usage:
                    await self._record_metrics(
                        provider=provider.value,
                        model=usage.get("model", "unknown"),
                        task_category=task_category.value,
                        input_tokens=usage.get("input_tokens", 0),
                        output_tokens=usage.get("output_tokens", 0),
                        latency_ms=latency_ms,
                    )

                return result

            except (ClaudePolicyReasoningError, GeminiError, AzureOpenAIError) as e:
                last_error = e
                logger.warning(
                    "Provider failed, trying fallback",
                    provider=provider.value,
                    error=str(e)
                )
                continue

            except Exception as e:
                last_error = e
                logger.error(
                    "Unexpected error from provider",
                    provider=provider.value,
                    error=str(e)
                )
                continue

        # All providers failed
        raise LLMGatewayError(
            f"All providers failed for task {task_category.value}: {last_error}"
        )

    async def _call_provider(
        self,
        provider: LLMProvider,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        response_format: str
    ) -> Dict[str, Any]:
        """Call a specific provider."""
        if provider == LLMProvider.CLAUDE:
            return await self.claude_client.analyze_policy(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                response_format=response_format
            )
        elif provider == LLMProvider.GEMINI:
            return await self.gemini_client.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                response_format=response_format
            )
        elif provider == LLMProvider.AZURE_OPENAI:
            return await self.azure_client.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                response_format=response_format
            )
        else:
            raise ValueError(f"Unknown provider: {provider}")

    async def analyze_policy(
        self,
        prompt: str,
        system_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze policy using Claude for clinical accuracy.

        Uses temperature=0.0 for deterministic clinical reasoning.

        Args:
            prompt: Policy analysis prompt
            system_prompt: Optional system instruction

        Returns:
            Policy analysis result
        """
        return await self.generate(
            task_category=TaskCategory.POLICY_REASONING,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.0,  # Deterministic for policy reasoning
            response_format="json"
        )

    async def generate_appeal_strategy(
        self,
        denial_context: Dict[str, Any],
        patient_info: Dict[str, Any],
        policy_text: str
    ) -> Dict[str, Any]:
        """
        Generate appeal strategy using Claude for clinical accuracy.

        Args:
            denial_context: Denial information
            patient_info: Patient data
            policy_text: Policy document

        Returns:
            Appeal strategy
        """
        return await self.claude_client.generate_appeal_strategy(
            denial_context=denial_context,
            patient_info=patient_info,
            policy_text=policy_text
        )

    async def draft_appeal_letter(
        self,
        appeal_context: Dict[str, Any]
    ) -> str:
        """
        Draft an appeal letter using Gemini with Azure fallback.

        Args:
            appeal_context: Context for the appeal

        Returns:
            Draft appeal letter text
        """
        from backend.reasoning.prompt_loader import get_prompt_loader

        prompt_loader = get_prompt_loader()
        prompt = prompt_loader.load(
            "appeals/appeal_letter_draft.txt",
            appeal_context
        )

        result = await self.generate(
            task_category=TaskCategory.APPEAL_DRAFTING,
            prompt=prompt,
            temperature=0.4,
            response_format="text"
        )
        return result.get("response", "")

    async def summarize(self, text: str, max_length: int = 500) -> str:
        """Summarize text using Gemini with Azure fallback."""
        from backend.reasoning.prompt_loader import get_prompt_loader
        prompt = get_prompt_loader().load(
            "general/summarize.txt",
            {"max_length": max_length, "text": text}
        )
        result = await self.generate(
            task_category=TaskCategory.SUMMARY_GENERATION,
            prompt=prompt,
            temperature=0.2,
            response_format="text"
        )
        return result.get("response", "")

    async def generate_stream(
        self,
        task_category: TaskCategory,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
    ):
        """
        Stream content generation, yielding text chunks.

        Routes to the primary provider for the task category.
        Falls back to non-streaming if streaming is not available.

        Yields:
            String chunks of the response as they arrive
        """
        providers = TASK_MODEL_ROUTING.get(task_category, [LLMProvider.GEMINI])
        primary = providers[0] if providers else LLMProvider.GEMINI

        logger.info("Streaming LLM request", task_category=task_category.value, provider=primary.value)

        if primary == LLMProvider.CLAUDE:
            async for chunk in self.claude_client.analyze_policy_stream(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
            ):
                yield chunk
        elif primary == LLMProvider.GEMINI:
            async for chunk in self.gemini_client.generate_stream(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
            ):
                yield chunk
        else:
            # Azure OpenAI fallback — no streaming, yield full response
            result = await self.azure_client.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=temperature,
                response_format="text",
            )
            yield result.get("response", "")

    async def embed(self, text: str, task_type: str = "SEMANTIC_SIMILARITY") -> List[float]:
        """Generate an embedding vector via Gemini embedding model."""
        return await self.gemini_client.embed(text, task_type=task_type)

    @staticmethod
    def cosine_similarity(a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0

    async def _record_metrics(
        self,
        provider: str,
        model: str,
        task_category: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
    ) -> None:
        """Record LLM usage metrics to the database."""
        try:
            from backend.storage.database import get_db
            from backend.storage.models import LLMMetricsModel

            # Estimate cost (approximate pricing per 1K tokens)
            cost_map = {
                "claude": {"input": 0.003, "output": 0.015},
                "gemini": {"input": 0.00025, "output": 0.001},
                "azure_openai": {"input": 0.005, "output": 0.015},
            }
            rates = cost_map.get(provider, {"input": 0.001, "output": 0.002})
            estimated_cost = (input_tokens / 1000 * rates["input"]) + (output_tokens / 1000 * rates["output"])

            async with get_db() as session:
                session.add(LLMMetricsModel(
                    id=str(uuid.uuid4()),
                    provider=provider,
                    model=model,
                    task_category=task_category,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    estimated_cost_usd=f"{estimated_cost:.6f}",
                ))
            logger.debug(
                "LLM metrics recorded",
                provider=provider, model=model,
                input_tokens=input_tokens, output_tokens=output_tokens,
                latency_ms=latency_ms, cost=f"${estimated_cost:.6f}",
            )
        except Exception as e:
            # Don't let metrics recording failures break the main flow
            logger.warning("Failed to record LLM metrics", error=str(e))

    async def get_metrics_summary(self) -> Dict[str, Any]:
        """Get aggregated LLM usage metrics."""
        from sqlalchemy import select, func
        from backend.storage.database import get_db
        from backend.storage.models import LLMMetricsModel

        try:
            async with get_db() as session:
                # Per-provider aggregates
                stmt = (
                    select(
                        LLMMetricsModel.provider,
                        func.count().label("total_calls"),
                        func.sum(LLMMetricsModel.input_tokens).label("total_input_tokens"),
                        func.sum(LLMMetricsModel.output_tokens).label("total_output_tokens"),
                        func.avg(LLMMetricsModel.latency_ms).label("avg_latency_ms"),
                    )
                    .group_by(LLMMetricsModel.provider)
                )
                result = await session.execute(stmt)
                provider_stats = [
                    {
                        "provider": row.provider,
                        "total_calls": row.total_calls,
                        "total_input_tokens": row.total_input_tokens or 0,
                        "total_output_tokens": row.total_output_tokens or 0,
                        "avg_latency_ms": int(row.avg_latency_ms or 0),
                    }
                    for row in result.all()
                ]

                # Per-task category aggregates
                stmt2 = (
                    select(
                        LLMMetricsModel.task_category,
                        func.count().label("total_calls"),
                        func.sum(LLMMetricsModel.input_tokens).label("total_input_tokens"),
                        func.sum(LLMMetricsModel.output_tokens).label("total_output_tokens"),
                    )
                    .group_by(LLMMetricsModel.task_category)
                )
                result2 = await session.execute(stmt2)
                task_stats = [
                    {
                        "task_category": row.task_category,
                        "total_calls": row.total_calls,
                        "total_input_tokens": row.total_input_tokens or 0,
                        "total_output_tokens": row.total_output_tokens or 0,
                    }
                    for row in result2.all()
                ]

                # Total estimated cost
                stmt3 = select(func.count().label("total")).select_from(LLMMetricsModel)
                total_row = (await session.execute(stmt3)).one()

            return {
                "by_provider": provider_stats,
                "by_task": task_stats,
                "total_calls": total_row.total,
            }
        except Exception as e:
            logger.error("Failed to get metrics summary", error=str(e))
            return {"by_provider": [], "by_task": [], "total_calls": 0, "error": str(e)}

    async def health_check(self) -> Dict[str, bool]:
        """Check health of all providers."""
        results = {}

        try:
            results["claude"] = await self.claude_client.health_check()
        except Exception:
            results["claude"] = False

        try:
            results["gemini"] = await self.gemini_client.health_check()
        except Exception:
            results["gemini"] = False

        try:
            results["azure_openai"] = await self.azure_client.health_check()
        except Exception:
            results["azure_openai"] = False

        return results


# Global instance
_llm_gateway: Optional[LLMGateway] = None


def get_llm_gateway() -> LLMGateway:
    """Get or create the global LLM Gateway instance."""
    global _llm_gateway
    if _llm_gateway is None:
        _llm_gateway = LLMGateway()
    return _llm_gateway
