"""Shared JSON extraction utility for LLM response parsing."""
import json
import re
from typing import Dict, Any

from backend.config.logging_config import get_logger

logger = get_logger(__name__)


def extract_json_from_text(text: str) -> Dict[str, Any]:
    """
    Extract a JSON object from LLM response text.

    Uses a three-step approach:
    1. Direct parse (response is pure JSON)
    2. Markdown code block extraction
    3. Brace-counting parser (robust against trailing text)

    Args:
        text: Response text potentially containing JSON

    Returns:
        Parsed JSON object

    Raises:
        json.JSONDecodeError: If no valid JSON found
    """
    # Step 1: Direct parse
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        # LLM returned a JSON array — fall through to brace-counting parser
    except json.JSONDecodeError:
        pass

    # Step 2: Extract from markdown code blocks
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if json_match:
        try:
            parsed = json.loads(json_match.group(1))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # Step 3: Brace-counting parser (handles nested JSON + trailing text)
    first_brace = text.find("{")
    if first_brace == -1:
        raise json.JSONDecodeError("No valid JSON found", text, 0)

    depth = 0
    last_brace = -1
    in_string = False
    escape_next = False

    for i, char in enumerate(text[first_brace:], first_brace):
        if escape_next:
            escape_next = False
            continue
        if char == '\\':
            escape_next = True
            continue
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                last_brace = i
                break

    if last_brace == -1:
        raise json.JSONDecodeError("Unclosed braces in JSON", text, first_brace)

    json_text = text[first_brace:last_brace + 1]
    return json.loads(json_text)
