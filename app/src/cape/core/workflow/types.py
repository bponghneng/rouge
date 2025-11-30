"""Unified result types for workflow orchestration.

This module provides consistent return types for all workflow steps,
replacing various patterns (tuples, booleans, response objects) with
a unified StepResult[T] generic type.
"""

from typing import Any, Dict, Generic, Literal, Optional, TypeVar

from pydantic import BaseModel

# Slash commands that can be output from classify step
ClassifySlashCommand = Literal[
    "/adw-chore-plan",
    "/adw-bug-plan",
    "/adw-feature-plan",
]

# Generic type parameter for StepResult data payload
T = TypeVar("T")


class StepResult(BaseModel, Generic[T]):
    """Generic result type for workflow steps.

    Provides consistent success/error handling with optional typed data
    and metadata for all workflow operations.

    Attributes:
        success: Whether the step completed successfully
        data: Optional typed payload specific to the step
        error: Optional error message if step failed
        metadata: Additional context (e.g., session IDs, timing)
    """

    success: bool
    data: Optional[T] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = {}

    @classmethod
    def ok(cls, data: T, **metadata: Any) -> "StepResult[T]":
        """Create a successful result with data.

        Args:
            data: The success payload
            **metadata: Additional metadata key-value pairs

        Returns:
            StepResult instance marked as successful
        """
        return cls(success=True, data=data, error=None, metadata=metadata)

    @classmethod
    def fail(cls, error: str, **metadata: Any) -> "StepResult[T]":
        """Create a failed result with error message.

        Args:
            error: Description of the failure
            **metadata: Additional metadata key-value pairs

        Returns:
            StepResult instance marked as failed
        """
        return cls(success=False, data=None, error=error, metadata=metadata)


class ClassifyData(BaseModel):
    """Data payload for issue classification results.

    Attributes:
        command: The slash command to execute (e.g., "/triage:feature")
        classification: Normalized classification dict with "type" and "level"
    """

    command: ClassifySlashCommand
    classification: Dict[str, str]


class PlanData(BaseModel):
    """Data payload for plan building results.

    Attributes:
        output: The plan output text
        session_id: Optional session ID for continuation
    """

    output: str
    session_id: Optional[str] = None


class PlanFileData(BaseModel):
    """Data payload for plan file discovery results.

    Attributes:
        file_path: Path to the discovered plan file
    """

    file_path: str


class ImplementData(BaseModel):
    """Data payload for implementation results.

    Attributes:
        output: The implementation output text
        session_id: Optional session ID for continuation
    """

    output: str
    session_id: Optional[str] = None


class ReviewData(BaseModel):
    """Data payload for review generation results.

    Attributes:
        review_text: The generated review content
        review_file: Path where review was saved
    """

    review_text: str
    review_file: str
