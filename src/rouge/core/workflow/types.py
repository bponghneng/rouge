"""Unified result types for workflow orchestration.

This module provides consistent return types for all workflow steps,
replacing various patterns (tuples, booleans, response objects) with
a unified StepResult[T] generic type.
"""

from typing import Any, Dict, Generic, Optional, TypeVar

from pydantic import BaseModel, Field, field_validator

# Generic type parameter for StepResult data payload
T = TypeVar("T")


class StepResult(BaseModel, Generic[T]):
    """Generic result type for workflow steps.

    Provides consistent success/error handling with optional typed data
    and metadata for all workflow operations.

    Rerun Signal:
        A step may set ``rerun_from`` to the *name* of an earlier pipeline
        step.  When the pipeline orchestrator sees a non-None ``rerun_from``
        it should rewind execution to that step instead of advancing.
        The orchestrator is responsible for enforcing a maximum rerun count
        (default: 5) to prevent runaway loops.  The rerun mechanism is
        generic -- any step can request it without embedding domain-specific
        logic in the pipeline.

    Attributes:
        success: Whether the step completed successfully
        data: Optional typed payload specific to the step
        error: Optional error message if step failed
        metadata: Additional context (e.g., session IDs, timing)
        rerun_from: Optional step name to rewind pipeline execution to.
            When set, the pipeline should re-execute starting from the
            named step rather than continuing forward.
    """

    success: bool
    data: Optional[T] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = {}
    rerun_from: Optional[str] = Field(
        default=None,
        min_length=1,
        description="Step name to rewind pipeline execution to. Must be non-empty if provided.",
    )

    @field_validator("rerun_from", mode="before")
    @classmethod
    def validate_rerun_from(cls, v: Optional[str]) -> Optional[str]:
        """Validate and normalize rerun_from field.

        Trims whitespace and rejects empty/whitespace-only strings.

        Args:
            v: The input value for rerun_from

        Returns:
            Trimmed string or None

        Raises:
            ValueError: If the value is empty or whitespace-only
        """
        if v is None:
            return None
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("rerun_from cannot be empty or whitespace-only")
        return trimmed

    @classmethod
    def ok(
        cls,
        data: T,
        rerun_from: Optional[str] = None,
        **metadata: Any,
    ) -> "StepResult[T]":
        """Create a successful result with data.

        Args:
            data: The success payload
            rerun_from: Optional step name to rewind pipeline execution to.
                When provided, the pipeline orchestrator will re-execute
                from the named step instead of advancing. Max 5 reruns
                by default to prevent runaway loops.
            **metadata: Additional metadata key-value pairs

        Returns:
            StepResult instance marked as successful
        """
        return cls(
            success=True,
            data=data,
            error=None,
            metadata=metadata,
            rerun_from=rerun_from,
        )

    @classmethod
    def fail(
        cls,
        error: str,
        rerun_from: Optional[str] = None,
        **metadata: Any,
    ) -> "StepResult[T]":
        """Create a failed result with error message.

        Args:
            error: Description of the failure
            rerun_from: Optional step name to rewind pipeline execution to.
                When provided, the pipeline orchestrator will re-execute
                from the named step instead of aborting. Max 5 reruns
                by default to prevent runaway loops.
            **metadata: Additional metadata key-value pairs

        Returns:
            StepResult instance marked as failed
        """
        return cls(
            success=False,
            data=None,
            error=error,
            metadata=metadata,
            rerun_from=rerun_from,
        )


class PlanData(BaseModel):
    """Data payload for plan building results.

    Attributes:
        plan: The parsed plan content (markdown)
        summary: Summary of the plan
        session_id: Optional session ID for continuation
        pr_number: Optional PR number if plan was created from PR context
    """

    plan: str
    summary: str
    session_id: Optional[str] = None
    pr_number: Optional[int] = Field(default=None, gt=0)


class RepoChangeDetail(BaseModel):
    """Per-repository change details from implementation."""

    repo_path: str
    files_modified: list[str] = Field(default_factory=list)
    git_diff_stat: str = ""


class ImplementData(BaseModel):
    """Data payload for implementation results.

    Attributes:
        output: The implementation output text
        session_id: Optional session ID for continuation
        affected_repos: Per-repository change details from implementation.
            Per-repo files and diff stats are accessed by iterating this list.
            A top-level ``files_by_repo`` mapping and flattened ``files_modified``
            aggregate are intentionally omitted; no current consumer needs them,
            and they can be derived from ``affected_repos`` if needed later.
    """

    output: str
    session_id: Optional[str] = None
    affected_repos: list[RepoChangeDetail] = Field(default_factory=list)
