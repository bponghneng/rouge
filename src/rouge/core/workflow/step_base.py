"""Abstract base class for workflow steps and context management."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from rouge.core.models import Issue
from rouge.core.utils import get_logger
from rouge.core.workflow.shared import get_repo_paths

if TYPE_CHECKING:
    from rouge.core.workflow.types import StepResult


class StepInputError(RuntimeError):
    """Raised when a required artifact or input is missing for a workflow step."""


@dataclass
class WorkflowContext:
    """Shared state passed between workflow steps.

    Attributes:
        adw_id: Workflow ID for tracking
        issue_id: The Rouge issue ID being processed (None for standalone workflows)
        issue: The fetched Issue object (set by FetchIssueStep)
        resume_from: Optional step name to resume workflow execution from
        pipeline_type: The type of pipeline being executed (default: "full")
        repo_paths: List of repository root paths (populated from REPO_PATH env var)
        data: Dictionary to store intermediate step data
    """

    adw_id: str
    issue_id: Optional[int] = None
    issue: Optional[Issue] = None
    resume_from: Optional[str] = None
    pipeline_type: str = "full"
    repo_paths: List[str] = field(default_factory=get_repo_paths)
    data: Dict[str, Any] = field(default_factory=dict)
    _logger: logging.Logger = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize cached logger after dataclass initialization."""
        self._logger = get_logger(self.adw_id)

    @property
    def require_issue_id(self) -> int:
        """Return issue_id, raising if it is None.

        Use this property in workflow steps that require a valid issue ID
        (e.g. issue-based pipelines). Some workflows set ``issue_id=None``
        and should not call this.

        Returns:
            The issue ID as an ``int``.

        Raises:
            RuntimeError: If ``issue_id`` is ``None``.
        """
        if self.issue_id is None:
            raise RuntimeError(
                "issue_id is required for this workflow step but is None. "
                "This step cannot be used in standalone (issue-free) workflows."
            )
        return self.issue_id

    def load_required_artifact(self, key: str, artifact_cls: Any = None) -> Any:  # noqa: ARG002
        """Load a required value from the context data dict.

        Args:
            key: The key to look up in context.data
            artifact_cls: Ignored (kept for backward compatibility)

        Returns:
            The value from context.data

        Raises:
            StepInputError: If the key is not found in context.data
        """
        value = self.data.get(key)
        if value is None:
            raise StepInputError(f"Required data '{key}' not found in context")
        return value

    def load_optional_artifact(self, key: str, artifact_cls: Any = None) -> Any:  # noqa: ARG002
        """Load an optional value from the context data dict.

        Args:
            key: The key to look up in context.data
            artifact_cls: Ignored (kept for backward compatibility)

        Returns:
            The value from context.data, or None if not found
        """
        return self.data.get(key)


class WorkflowStep(ABC):
    """Abstract base class for workflow steps.

    Each step implements the run() method to perform its work.
    Steps can be marked as critical (default) or best-effort.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for logging/identification."""
        ...

    @property
    def is_critical(self) -> bool:
        """Whether failure of this step should abort the workflow.

        Returns:
            True if step failure should abort workflow (default).
            False for best-effort steps that continue on failure.
        """
        return True

    @abstractmethod
    def run(self, context: WorkflowContext) -> "StepResult":
        """Execute the step logic.

        Args:
            context: Shared workflow context with state and data

        Returns:
            StepResult with success status, optional data, and optional error message
        """
        ...
