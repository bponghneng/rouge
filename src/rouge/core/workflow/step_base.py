"""Abstract base class for workflow steps and context management."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Type, TypeVar

from rouge.core.models import Issue

if TYPE_CHECKING:
    from rouge.core.workflow.artifacts import Artifact, ArtifactStore, ArtifactType
    from rouge.core.workflow.types import StepResult

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="Artifact")


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

    @property
    def parent_workflow_id(self) -> Optional[str]:
        """Get the parent workflow ID from the artifact store.

        Returns:
            Parent workflow ID if artifact store exists and has parent, None otherwise
        """
        if self.artifact_store is None:
            return None
        return self.artifact_store.parent_workflow_id

    def load_artifact_if_missing(
        self,
        context_key: str,
        artifact_type: "ArtifactType",
        artifact_class: Type[T],
        extract_fn: Callable[[T], Any],
    ) -> Optional[Any]:
        """Load artifact data into context if not already present.

        This helper encapsulates the common pattern of conditionally loading
        artifact data when it's missing from context. It handles:
        - Checking if data already exists in context
        - Checking if artifacts are enabled
        - Reading the artifact and extracting the data
        - Silent FileNotFoundError handling (missing artifacts are acceptable)
        - Updating context.data with the loaded value
        - Consistent debug logging

        Args:
            context_key: The key to store/check in context.data
            artifact_type: The artifact type identifier for read_artifact
            artifact_class: The artifact class to deserialize into
            extract_fn: Function to extract the desired value from the artifact

        Returns:
            The loaded value (from context or artifact), or None if not available
        """
        # Check if already in context
        existing = self.data.get(context_key)
        if existing is not None:
            return existing

        # Check if artifacts are enabled
        if not self.artifacts_enabled or self.artifact_store is None:
            return None

        # Try to load from artifact
        try:
            artifact = self.artifact_store.read_artifact(artifact_type, artifact_class)
            value = extract_fn(artifact)
            self.data[context_key] = value
            logger.debug("Loaded %s from artifact", artifact_type)
            return value
        except FileNotFoundError:
            logger.debug(
                "No existing %s artifact found; proceeding without artifact",
                artifact_type,
            )
            return None

    def load_issue_artifact_if_missing(
        self,
        artifact_class: Type[T],
        extract_fn: Callable[[T], Issue],
    ) -> Optional[Issue]:
        """Load issue from artifact if not already set on context.

        Similar to load_artifact_if_missing, but specifically for the issue
        attribute which lives on context directly rather than in context.data.

        Args:
            artifact_class: The artifact class to deserialize into (e.g., IssueArtifact)
            extract_fn: Function to extract Issue from the artifact

        Returns:
            The loaded Issue (from context or artifact), or None if not available
        """
        # Check if already set
        if self.issue is not None:
            return self.issue

        # Check if artifacts are enabled
        if not self.artifacts_enabled or self.artifact_store is None:
            return None

        # Try to load from artifact
        try:
            artifact = self.artifact_store.read_artifact("issue", artifact_class)
            issue = extract_fn(artifact)
            self.issue = issue
            logger.debug("Loaded issue from artifact")
            return issue
        except FileNotFoundError:
            logger.debug("No existing issue artifact found; proceeding without artifact")
            return None


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
