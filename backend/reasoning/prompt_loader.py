"""Load prompts from .txt files with variable substitution."""
import re
from pathlib import Path
from typing import Dict, Any, Optional
from functools import lru_cache

from backend.config.logging_config import get_logger

logger = get_logger(__name__)


class PromptLoader:
    """
    Load prompts from .txt files in the prompts directory.
    Supports {variable_name} substitution.
    """

    def __init__(self, prompts_dir: Optional[Path] = None):
        """
        Initialize the prompt loader.

        Args:
            prompts_dir: Path to prompts directory. Defaults to ./prompts/
        """
        self.prompts_dir = prompts_dir or Path("prompts")
        if not self.prompts_dir.exists():
            raise FileNotFoundError(f"Prompts directory not found: {self.prompts_dir}")

    @lru_cache(maxsize=100)
    def _load_raw_prompt(self, prompt_path: str) -> str:
        """
        Load raw prompt content from file (cached).

        Args:
            prompt_path: Relative path within prompts directory (e.g., "policy_analysis/coverage_assessment.txt")

        Returns:
            Raw prompt content
        """
        full_path = (self.prompts_dir / prompt_path).resolve()
        try:
            full_path.relative_to(self.prompts_dir.resolve())
        except ValueError:
            raise ValueError(f"Path traversal attempt blocked: {prompt_path}")
        if not full_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {full_path}")

        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        logger.debug("Loaded prompt", prompt_path=prompt_path, length=len(content))
        return content

    def load(self, prompt_path: str, variables: Optional[Dict[str, Any]] = None) -> str:
        """
        Load a prompt and substitute variables.

        Args:
            prompt_path: Relative path within prompts directory
            variables: Dictionary of variables to substitute

        Returns:
            Prompt with variables substituted
        """
        raw_prompt = self._load_raw_prompt(prompt_path)

        if not variables:
            return raw_prompt

        # Substitute variables using {variable_name} syntax
        result = raw_prompt
        for key, value in variables.items():
            placeholder = "{" + key + "}"
            if isinstance(value, dict):
                # Convert dict to formatted string
                import json
                value_str = json.dumps(value, indent=2, default=str)
            elif isinstance(value, list):
                import json
                value_str = json.dumps(value, indent=2, default=str)
            else:
                value_str = str(value)
            result = result.replace(placeholder, value_str)

        # Check for unsubstituted variables
        remaining_vars = re.findall(r"\{(\w+)\}", result)
        if remaining_vars:
            logger.warning(
                "Unsubstituted variables in prompt",
                prompt_path=prompt_path,
                variables=remaining_vars
            )

        return result

    def list_prompts(self) -> Dict[str, list]:
        """
        List all available prompts organized by directory.

        Returns:
            Dictionary mapping directories to list of prompt files
        """
        prompts = {}
        for path in self.prompts_dir.rglob("*.txt"):
            rel_path = path.relative_to(self.prompts_dir)
            directory = str(rel_path.parent)
            if directory not in prompts:
                prompts[directory] = []
            prompts[directory].append(rel_path.name)
        return prompts

    def get_prompt_variables(self, prompt_path: str) -> list:
        """
        Extract variable names from a prompt template.

        Args:
            prompt_path: Relative path to prompt file

        Returns:
            List of variable names found in the prompt
        """
        raw_prompt = self._load_raw_prompt(prompt_path)
        return re.findall(r"\{(\w+)\}", raw_prompt)

    def clear_cache(self) -> None:
        """Clear the prompt cache."""
        self._load_raw_prompt.cache_clear()
        logger.info("Prompt cache cleared")


# Global instance
_prompt_loader: Optional[PromptLoader] = None


def get_prompt_loader() -> PromptLoader:
    """Get or create the global prompt loader instance."""
    global _prompt_loader
    if _prompt_loader is None:
        _prompt_loader = PromptLoader()
    return _prompt_loader
