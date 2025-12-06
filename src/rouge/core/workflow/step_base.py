"""Abstract base class for workflow steps and context management."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from logging import Logger
from typing import TYPE_CHECKING, Any, Dict, Optional

from rouge.core.models import CapeIssue

if TYPE_CHECKING:
    from rouge.core.workflow.types import StepResult


@dataclass
class WorkflowContext:
    """Shared state passed between workflow steps.

    Attributes:
        issue_id: The Rouge issue ID being processed
        adw_id: Workflow ID for tracking
        logger: Logger instance for step logging
        issue: The fetched CapeIssue object (set by FetchIssueStep)
        data: Dictionary to store intermediate step data
    """

    issue_id: int
    adw_id: str
    logger: Logger
    issue: Optional[CapeIssue] = None
    data: Dict[str, Any] = field(default_factory=dict)


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
