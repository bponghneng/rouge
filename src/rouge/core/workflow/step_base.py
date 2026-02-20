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


class StepInputError(RuntimeError):
    """Raised when a required artifact or input is missing for a workflow step."""


@dataclass
class WorkflowContext:
    """Shared state passed between workflow steps.

    Attributes:
        adw_id: Workflow ID for tracking
        artifact_store: ArtifactStore for artifact persistence (required)
        issue_id: The Rouge issue ID being processed (None for standalone workflows)
        issue: The fetched Issue object (set by FetchIssueStep)
        data: Dictionary to store intermediate step data
    """

    adw_id: str
    artifact_store: "ArtifactStore"
    issue_id: Optional[int] = None
    issue: Optional[Issue] = None
    data: Dict[str, Any] = field(default_factory=dict)

    @property
    def require_issue_id(self) -> int:
        """Return issue_id, raising if it is None.

        Use this property in workflow steps that require a valid issue ID
        (e.g. issue-based pipelines).  Standalone workflows such as
        ``codereview`` set ``issue_id=None`` and should not call this.

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

    def load_required_artifact(
        self,
        context_key: str,
        artifact_type: "ArtifactType",
        artifact_class: Type[T],
        extract_fn: Callable[[T], Any],
    ) -> Any:
        """Load a required artifact, raising if it is not found.

        Checks context cache first, then loads from the artifact store.  If the
        artifact file does not exist a ``StepInputError`` is raised so callers
        get a clear, actionable error message.

        Args:
            context_key: The key to store/check in context.data (cache)
            artifact_type: The artifact type identifier used by the store
            artifact_class: The artifact class to deserialize into
            extract_fn: Function to extract the desired value from the artifact

        Returns:
            The loaded and extracted value (from cache or artifact store)

        Raises:
            StepInputError: If the artifact file does not exist
        """
        # Check cache first
        existing = self.data.get(context_key)
        if existing is not None:
            return existing

        # Load from artifact store; propagate StepInputError on missing file
        try:
            artifact = self.artifact_store.read_artifact(artifact_type, artifact_class)
        except FileNotFoundError:
            raise StepInputError(
                f"Required artifact '{artifact_type}' not found for step. "
                "Ensure the preceding step completed successfully and wrote its artifact."
            )

        value = extract_fn(artifact)
        self.data[context_key] = value
        logger.debug("Loaded required artifact %s", artifact_type)
        return value

    def load_optional_artifact(
        self,
        context_key: str,
        artifact_type: "ArtifactType",
        artifact_class: Type[T],
        extract_fn: Callable[[T], Any],
    ) -> Optional[Any]:
        """Load an optional artifact, returning None if it is not found.

        Checks context cache first, then loads from the artifact store.  A
        missing artifact is treated as a normal condition and logged at DEBUG
        level rather than raising an error.

        Args:
            context_key: The key to store/check in context.data (cache)
            artifact_type: The artifact type identifier used by the store
            artifact_class: The artifact class to deserialize into
            extract_fn: Function to extract the desired value from the artifact

        Returns:
            The loaded and extracted value, or None if the artifact does not exist
        """
        # Check cache first
        existing = self.data.get(context_key)
        if existing is not None:
            return existing

        # Try to load from artifact store
        try:
            artifact = self.artifact_store.read_artifact(artifact_type, artifact_class)
        except FileNotFoundError:
            logger.debug(
                "Optional artifact '%s' not found; proceeding without it",
                artifact_type,
            )
            return None

        value = extract_fn(artifact)
        self.data[context_key] = value
        logger.debug("Loaded optional artifact %s", artifact_type)
        return value

    # ------------------------------------------------------------------
    # Deprecated helpers — kept for backward compatibility; do not use in
    # new code.  These will be removed in a future refactor phase.
    # ------------------------------------------------------------------

    def load_artifact_if_missing(
        self,
        context_key: str,
        artifact_type: "ArtifactType",
        artifact_class: Type[T],
        extract_fn: Callable[[T], Any],
    ) -> Optional[Any]:
        """Load artifact data into context if not already present.

        .. deprecated::
            Use :meth:`load_required_artifact` or :meth:`load_optional_artifact`
            instead.  This method will be removed in a future refactor phase.

        This helper encapsulates the common pattern of conditionally loading
        artifact data when it's missing from context. It handles:
        - Checking if data already exists in context
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

        .. deprecated::
            Use :meth:`load_required_artifact` or :meth:`load_optional_artifact`
            instead.  This method will be removed in a future refactor phase.

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

        # Try to load from artifact
        try:
            artifact = self.artifact_store.read_artifact("fetch-issue", artifact_class)
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
