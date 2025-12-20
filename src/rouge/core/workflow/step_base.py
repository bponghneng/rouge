"""Abstract base class for workflow steps and context management."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional

from rouge.core.models import Issue

if TYPE_CHECKING:
    from rouge.core.workflow.artifacts import ArtifactStore
    from rouge.core.workflow.types import StepResult


@dataclass
class WorkflowContext:
    """Shared state passed between workflow steps.

    Attributes:
        issue_id: The Rouge issue ID being processed
        adw_id: Workflow ID for tracking
        issue: The fetched Issue object (set by FetchIssueStep)
        data: Dictionary to store intermediate step data
        artifact_store: Optional ArtifactStore for artifact persistence
    """

    issue_id: int
    adw_id: str
    issue: Optional[Issue] = None
    data: Dict[str, Any] = field(default_factory=dict)
    artifact_store: Optional["ArtifactStore"] = None

    @property
    def artifacts_enabled(self) -> bool:
        """Check if artifact persistence is enabled.

        Returns:
            True if an artifact store is available
        """
        return self.artifact_store is not None


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
