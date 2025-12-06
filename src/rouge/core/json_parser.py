"""Shared JSON parsing helper for agent outputs.

This module provides consistent JSON extraction, parsing, and validation
for agent outputs across all core components and workflow steps.
"""

import json
import re
from logging import Logger
from typing import Any, Dict, Generic, Mapping, Optional, TypeVar

from pydantic import BaseModel

# Generic type parameter for StepResult data payload
T = TypeVar("T")


class StepResult(BaseModel, Generic[T]):
    """Generic result type for parsing operations.

    Provides consistent success/error handling with optional typed data.
    This is defined here to avoid circular imports - it's API-compatible
    with rouge.core.workflow.types.StepResult.

    Attributes:
        success: Whether the operation completed successfully
        data: Optional typed payload
        error: Optional error message if operation failed
        metadata: Additional context (kept for compatibility)
    """

    success: bool
    data: Optional[T] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = {}

    @classmethod
    def ok(cls, data: T, **metadata: Any) -> "StepResult[T]":
        """Create a successful result with data."""
        return cls(success=True, data=data, error=None, metadata=metadata)

    @classmethod
    def fail(cls, error: str, **metadata: Any) -> "StepResult[T]":
        """Create a failed result with error message."""
        return cls(success=False, data=None, error=error, metadata=metadata)


# Regex pattern to match Markdown code fences wrapping JSON
# Matches: ```json\n...\n``` or ```\n...\n``` anywhere in the string
_MARKDOWN_FENCE_PATTERN = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)


def _sanitize_json_output(output: str) -> str:
    """Strip Markdown code fences and surrounding prose from JSON output.

    LLM outputs may wrap JSON in Markdown code fences (e.g., ```json ... ```)
    or include leading/trailing prose before/after the JSON object.
    This helper extracts the raw JSON content.

    Args:
        output: Raw output string that may contain Markdown fences or prose

    Returns:
        The extracted JSON content
    """
    stripped = output.strip()

    # First try to match markdown fences anywhere in the string
    match = _MARKDOWN_FENCE_PATTERN.search(stripped)
    if match:
        return match.group(1).strip()

    # If no fences, try to extract JSON object by finding { and }
    # This handles cases where prose surrounds the JSON
    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")

    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return stripped[first_brace : last_brace + 1]

    return stripped


def parse_and_validate_json(
    output: Optional[str],
    required_fields: Mapping[str, type[Any]],
    logger: Logger,
    step_name: Optional[str] = None,
) -> StepResult[Dict[str, Any]]:
    """Parse and validate JSON output from agent responses.

    Sanitizes the output (strips markdown fences, trims prose), parses JSON,
    and validates that required fields are present with correct types.

    Args:
        output: Raw output string from agent
        required_fields: Dictionary mapping field names to expected types
            (e.g., {"type": str, "level": str})
        logger: Logger instance for debugging
        step_name: Optional step name for error messages

    Returns:
        StepResult with parsed dict on success, or error message on failure
    """
    step_prefix = f"[{step_name}] " if step_name else ""
    raw_output = output.strip() if output else ""

    if not raw_output:
        logger.error(f"{step_prefix}Empty output received")
        return StepResult.fail(f"{step_prefix}Empty output received")

    # Sanitize output to strip Markdown code fences and prose
    sanitized_output = _sanitize_json_output(raw_output)
    logger.debug(f"{step_prefix}Sanitized output: {sanitized_output[:200]}...")

    # Parse JSON
    try:
        parsed_data = json.loads(sanitized_output)
    except json.JSONDecodeError as exc:
        logger.error(
            f"{step_prefix}JSON decode failed: {exc} | raw={raw_output[:200]}..."
        )
        return StepResult.fail(
            f"{step_prefix}Invalid JSON: {exc}. Output starts with: {raw_output[:100]}..."
        )

    # Validate it's a dict
    if not isinstance(parsed_data, dict):
        logger.error(f"{step_prefix}Expected dict, got {type(parsed_data).__name__}")
        return StepResult.fail(
            f"{step_prefix}Expected JSON object, got {type(parsed_data).__name__}"
        )

    # Validate required fields and types
    for field_name, expected_type in required_fields.items():
        if field_name not in parsed_data:
            logger.error(f"{step_prefix}Missing required field: '{field_name}'")
            return StepResult.fail(
                f"{step_prefix}Missing required field: '{field_name}'"
            )

        field_value = parsed_data[field_name]
        # Special case: reject bool when expecting int (bool is subclass of int)
        if expected_type is int and isinstance(field_value, bool):
            actual_type = type(field_value).__name__
            expected_type_name = expected_type.__name__
            logger.error(
                f"{step_prefix}Field '{field_name}' has wrong type: "
                f"expected {expected_type_name}, got {actual_type}"
            )
            return StepResult.fail(
                f"{step_prefix}Field '{field_name}' has wrong type: "
                f"expected {expected_type_name}, got {actual_type}"
            )
        if not isinstance(field_value, expected_type):
            actual_type = type(field_value).__name__
            expected_type_name = expected_type.__name__
            logger.error(
                f"{step_prefix}Field '{field_name}' has wrong type: "
                f"expected {expected_type_name}, got {actual_type}"
            )
            return StepResult.fail(
                f"{step_prefix}Field '{field_name}' has wrong type: "
                f"expected {expected_type_name}, got {actual_type}"
            )

    logger.debug(f"{step_prefix}JSON parsed and validated successfully")
    return StepResult.ok(parsed_data)
