"""Agent Orchestrator — plan-execute-reflect loop for agentic policy analysis.

Wraps LLM calls with:
- Planning: Determine what analysis steps are needed
- Tool use: Invoke tools (search, lookup, compare) autonomously
- Self-correction: Re-run extraction if validation finds critical issues
- Confidence scoring: Escalate to human review when confidence is low
"""

import json
from typing import Dict, Any, Optional, List, Callable, Awaitable

from backend.reasoning.llm_gateway import get_llm_gateway, LLMGateway
from backend.reasoning.tools import execute_tool, TOOL_DEFINITIONS, ToolResult
from backend.reasoning.prompt_loader import get_prompt_loader
from backend.models.enums import TaskCategory
from backend.config.logging_config import get_logger

logger = get_logger(__name__)

# Maximum reasoning iterations before forcing a result
MAX_ITERATIONS = 5

# Confidence threshold below which we flag for human review
CONFIDENCE_ESCALATION_THRESHOLD = 0.6

# If Pass 2 validation finds more than this many critical corrections, re-run Pass 1
CRITICAL_CORRECTIONS_RERUN_THRESHOLD = 3


class AgentStep:
    """A single step in the agent's reasoning trace."""

    def __init__(self, step_type: str, content: str, tool_name: Optional[str] = None,
                 tool_result: Optional[ToolResult] = None):
        self.step_type = step_type  # "plan", "tool_call", "reflection", "answer"
        self.content = content
        self.tool_name = tool_name
        self.tool_result = tool_result

    def to_dict(self) -> Dict[str, Any]:
        d = {"type": self.step_type, "content": self.content}
        if self.tool_name:
            d["tool"] = self.tool_name
        if self.tool_result:
            d["tool_success"] = self.tool_result.success
        return d


class AgentResult:
    """Result of an agent orchestration run."""

    def __init__(self, answer: Any, steps: List[AgentStep], confidence: float = 1.0,
                 needs_human_review: bool = False, iterations: int = 0):
        self.answer = answer
        self.steps = steps
        self.confidence = confidence
        self.needs_human_review = needs_human_review
        self.iterations = iterations

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "confidence": self.confidence,
            "needs_human_review": self.needs_human_review,
            "iterations": self.iterations,
            "reasoning_trace": [s.to_dict() for s in self.steps],
        }


class AgentOrchestrator:
    """Orchestrates multi-step agentic reasoning with tool use."""

    def __init__(self):
        self.gateway: LLMGateway = get_llm_gateway()
        self.prompt_loader = get_prompt_loader()

    async def run(
        self,
        task: str,
        context: str = "",
        task_category: TaskCategory = TaskCategory.POLICY_QA,
        available_tools: Optional[List[str]] = None,
        on_step: Optional[Callable[[AgentStep], Awaitable[None]]] = None,
    ) -> AgentResult:
        """
        Run the agent loop: plan → execute tools → reflect → answer.

        Args:
            task: The user's question or task description
            context: Additional context (policy text, patient data, etc.)
            task_category: LLM routing category
            available_tools: Which tools the agent may use (None = all)
            on_step: Optional callback for each reasoning step (for streaming progress)

        Returns:
            AgentResult with answer, confidence, and reasoning trace
        """
        steps: List[AgentStep] = []
        tool_outputs: List[str] = []
        iterations = 0

        # Filter available tools
        tools = TOOL_DEFINITIONS
        if available_tools:
            tools = [t for t in tools if t["name"] in available_tools]

        tools_description = "\n".join(
            f"- {t['name']}: {t['description']}" for t in tools
        )

        # Phase 1: Plan
        plan_prompt = self.prompt_loader.load(
            "system/agent_planning.txt",
            {
                "task": task,
                "context": context[:4000] if context else "No additional context.",
                "available_tools": tools_description,
            },
        )

        plan_result = await self.gateway.generate(
            task_category=task_category,
            prompt=plan_prompt,
            temperature=0.1,
            response_format="json",
        )

        plan_data = plan_result if isinstance(plan_result, dict) else {}
        plan_text = plan_data.get("plan", plan_data.get("response", str(plan_data)))
        tool_calls = plan_data.get("tool_calls", [])
        if isinstance(plan_text, list):
            plan_text = "\n".join(str(s) for s in plan_text)

        plan_step = AgentStep("plan", str(plan_text))
        steps.append(plan_step)
        if on_step:
            await on_step(plan_step)

        # Phase 2: Execute tool calls from the plan
        for tc in tool_calls[:5]:  # Cap at 5 tool calls per iteration
            tool_name = tc.get("tool") or tc.get("name", "")
            tool_params = tc.get("parameters") or tc.get("params", {})

            if not tool_name or tool_name not in [t["name"] for t in tools]:
                continue

            result = await execute_tool(tool_name, tool_params)
            tool_step = AgentStep("tool_call", f"Called {tool_name}", tool_name=tool_name, tool_result=result)
            steps.append(tool_step)
            tool_outputs.append(result.to_context())
            if on_step:
                await on_step(tool_step)

        iterations += 1

        # Phase 3: Reflect and answer
        tool_context = "\n\n".join(tool_outputs) if tool_outputs else "No tools were called."

        reflect_prompt = self.prompt_loader.load(
            "system/agent_reflect.txt",
            {
                "task": task,
                "context": context[:4000] if context else "No additional context.",
                "plan": str(plan_text),
                "tool_results": tool_context,
            },
        )

        answer_result = await self.gateway.generate(
            task_category=task_category,
            prompt=reflect_prompt,
            temperature=0.1,
            response_format="json",
        )

        answer_data = answer_result if isinstance(answer_result, dict) else {}
        confidence = float(answer_data.get("confidence", 0.7))
        answer = answer_data.get("answer", answer_data.get("response", answer_data))
        needs_review = confidence < CONFIDENCE_ESCALATION_THRESHOLD
        needs_more_tools = answer_data.get("needs_more_tools", False)

        # Phase 4: Additional iterations if the agent needs more information
        while needs_more_tools and iterations < MAX_ITERATIONS:
            additional_calls = answer_data.get("additional_tool_calls", [])
            if not additional_calls:
                break

            for tc in additional_calls[:3]:
                tool_name = tc.get("tool") or tc.get("name", "")
                tool_params = tc.get("parameters") or tc.get("params", {})
                if not tool_name or tool_name not in [t["name"] for t in tools]:
                    continue
                result = await execute_tool(tool_name, tool_params)
                tool_step = AgentStep("tool_call", f"Called {tool_name}", tool_name=tool_name, tool_result=result)
                steps.append(tool_step)
                tool_outputs.append(result.to_context())
                if on_step:
                    await on_step(tool_step)

            tool_context = "\n\n".join(tool_outputs)
            reflect_prompt = self.prompt_loader.load(
                "system/agent_reflect.txt",
                {
                    "task": task,
                    "context": context[:4000] if context else "No additional context.",
                    "plan": str(plan_text),
                    "tool_results": tool_context,
                },
            )
            answer_result = await self.gateway.generate(
                task_category=task_category,
                prompt=reflect_prompt,
                temperature=0.1,
                response_format="json",
            )
            answer_data = answer_result if isinstance(answer_result, dict) else {}
            confidence = float(answer_data.get("confidence", 0.7))
            answer = answer_data.get("answer", answer_data.get("response", answer_data))
            needs_review = confidence < CONFIDENCE_ESCALATION_THRESHOLD
            needs_more_tools = answer_data.get("needs_more_tools", False)
            iterations += 1

        reflect_step = AgentStep("reflection", f"Confidence: {confidence:.2f}")
        steps.append(reflect_step)
        if on_step:
            await on_step(reflect_step)

        answer_step = AgentStep("answer", str(answer)[:500])
        steps.append(answer_step)
        if on_step:
            await on_step(answer_step)

        if needs_review:
            logger.warning("Agent confidence below threshold — flagging for human review",
                           confidence=confidence, task=task[:100])

        return AgentResult(
            answer=answer,
            steps=steps,
            confidence=confidence,
            needs_human_review=needs_review,
            iterations=iterations,
        )

    async def should_rerun_extraction(self, corrections: List[Dict[str, Any]]) -> bool:
        """
        Determine if Pass 1 extraction should be re-run based on Pass 2 validation corrections.

        Returns True if there are more than CRITICAL_CORRECTIONS_RERUN_THRESHOLD critical corrections.
        """
        critical_count = sum(
            1 for c in corrections
            if c.get("severity", "").lower() in ("critical", "high", "breaking")
        )
        should_rerun = critical_count > CRITICAL_CORRECTIONS_RERUN_THRESHOLD
        if should_rerun:
            logger.warning(
                "Too many critical corrections — recommending extraction re-run",
                critical_count=critical_count,
                threshold=CRITICAL_CORRECTIONS_RERUN_THRESHOLD,
            )
        return should_rerun


# Global instance
_orchestrator: Optional[AgentOrchestrator] = None


def get_agent_orchestrator() -> AgentOrchestrator:
    """Get or create the global AgentOrchestrator."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator
