"""Artifact type definitions and persistence layer for workflow steps.

This module provides typed artifact schemas and a filesystem-backed ArtifactStore
for persisting workflow step inputs and outputs to disk.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Type, TypeVar

from pydantic import BaseModel, Field

from rouge.core.models import Issue, Patch
from rouge.core.workflow.types import (
    ClassifyData,
    ImplementData,
    PatchPlanData,
    PlanData,
    ReviewData,
)

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Return current UTC time in a timezone-aware manner."""
    return datetime.now(timezone.utc)


# Type variable for generic artifact operations
T = TypeVar("T", bound="Artifact")

# Valid artifact type names
ArtifactType = Literal[
    "issue",
    "classification",
    "plan",
    "implementation",
    "review",
    "review_addressed",
    "quality_check",
    "acceptance",
    "pr_metadata",
    "pull_request",
    "patch",
    "patch_plan",
    "patch_acceptance",
]


class Artifact(BaseModel):
    """Base class for all workflow artifacts.

    Attributes:
        workflow_id: The workflow ID this artifact belongs to
        artifact_type: The type identifier for this artifact
        created_at: Timestamp when the artifact was created
    """

    workflow_id: str
    artifact_type: ArtifactType
    created_at: datetime = Field(default_factory=_utc_now)


class IssueArtifact(Artifact):
    """Artifact containing the fetched Issue data.

    Attributes:
        issue: The Issue model from the database
    """

    artifact_type: Literal["issue"] = "issue"
    issue: Issue


class ClassificationArtifact(Artifact):
    """Artifact containing issue classification results.

    Attributes:
        classify_data: The classification result data
    """

    artifact_type: Literal["classification"] = "classification"
    classify_data: ClassifyData


class PlanArtifact(Artifact):
    """Artifact containing plan building results.

    Attributes:
        plan_data: The plan data from the planning step
    """

    artifact_type: Literal["plan"] = "plan"
    plan_data: PlanData


class ImplementationArtifact(Artifact):
    """Artifact containing implementation results.

    Attributes:
        implement_data: The implementation output data
    """

    artifact_type: Literal["implementation"] = "implementation"
    implement_data: ImplementData


class ReviewArtifact(Artifact):
    """Artifact containing code review results.

    Attributes:
        review_data: The review content
    """

    artifact_type: Literal["review"] = "review"
    review_data: ReviewData


class ReviewAddressedArtifact(Artifact):
    """Artifact indicating review issues have been addressed.

    Attributes:
        success: Whether review issues were successfully addressed
        message: Optional message about the resolution
    """

    artifact_type: Literal["review_addressed"] = "review_addressed"
    success: bool
    message: Optional[str] = None


class QualityCheckArtifact(Artifact):
    """Artifact containing code quality check results.

    Attributes:
        output: The quality check output text
        tools: List of tools that were run
        parsed_data: Optional parsed JSON data from the check
    """

    artifact_type: Literal["quality_check"] = "quality_check"
    output: str
    tools: List[str]
    parsed_data: Optional[Dict[str, Any]] = None


class AcceptanceArtifact(Artifact):
    """Artifact containing acceptance validation results.

    Attributes:
        success: Whether the implementation passed acceptance criteria
        message: Optional message about the validation result
    """

    artifact_type: Literal["acceptance"] = "acceptance"
    success: bool
    message: Optional[str] = None


class PRMetadataArtifact(Artifact):
    """Artifact containing prepared pull request metadata.

    Attributes:
        title: The PR title
        summary: The PR body/summary
        commits: List of commit information
    """

    artifact_type: Literal["pr_metadata"] = "pr_metadata"
    title: str
    summary: str
    commits: List[Dict[str, Any]] = Field(default_factory=list)


class PullRequestArtifact(Artifact):
    """Artifact containing the created pull request details.

    Attributes:
        url: The URL of the created pull request
        platform: The platform where the PR was created (github/gitlab)
    """

    artifact_type: Literal["pull_request"] = "pull_request"
    url: str
    platform: Literal["github", "gitlab"]


class PatchArtifact(Artifact):
    """Artifact containing the fetched Patch data.

    Attributes:
        patch: The Patch model from the database
    """

    artifact_type: Literal["patch"] = "patch"
    patch: Patch


class PatchPlanArtifact(Artifact):
    """Artifact containing patch plan results.

    Attributes:
        patch_plan_data: The patch plan data from the planning step
    """

    artifact_type: Literal["patch_plan"] = "patch_plan"
    patch_plan_data: PatchPlanData


class PatchAcceptanceArtifact(Artifact):
    """Artifact containing patch acceptance validation results.

    Attributes:
        success: Whether the patch implementation passed acceptance criteria
        message: Optional message about the validation result
    """

    artifact_type: Literal["patch_acceptance"] = "patch_acceptance"
    success: bool
    message: Optional[str] = None


# Mapping from artifact type to model class
ARTIFACT_MODELS: Dict[ArtifactType, Type[Artifact]] = {
    "issue": IssueArtifact,
    "classification": ClassificationArtifact,
    "plan": PlanArtifact,
    "implementation": ImplementationArtifact,
    "review": ReviewArtifact,
    "review_addressed": ReviewAddressedArtifact,
    "quality_check": QualityCheckArtifact,
    "acceptance": AcceptanceArtifact,
    "pr_metadata": PRMetadataArtifact,
    "pull_request": PullRequestArtifact,
    "patch": PatchArtifact,
    "patch_plan": PatchPlanArtifact,
    "patch_acceptance": PatchAcceptanceArtifact,
}

# Artifact types that can be read from a parent workflow directory.
# These artifacts are shared across patch workflows and the original issue workflow.
SHARED_ARTIFACT_TYPES: frozenset[ArtifactType] = frozenset(
    [
        "issue",
        "classification",
        "plan",
        "pr_metadata",
        "pull_request",
    ]
)

# Artifact types that are specific to each patch/workflow and should never be
# read from a parent workflow directory.
PATCH_SPECIFIC_ARTIFACT_TYPES: frozenset[ArtifactType] = frozenset(
    [
        "patch",
        "patch_plan",
        "patch_acceptance",
        "implementation",
        "review",
        "review_addressed",
        "quality_check",
        "acceptance",
    ]
)


class ArtifactStore:
    """Filesystem-backed store for workflow artifacts.

    Manages reading, writing, and listing of artifacts for a specific workflow.
    Artifacts are stored as JSON files in `.rouge/workflows/{workflow_id}/`.
    """

    def __init__(
        self,
        workflow_id: str,
        base_path: Optional[Path] = None,
        parent_workflow_id: Optional[str] = None,
    ) -> None:
        """Initialize the artifact store for a workflow.

        Args:
            workflow_id: The workflow ID to manage artifacts for
            base_path: Optional base path override (defaults to RougePaths.get_workflows_dir())
            parent_workflow_id: Optional parent workflow ID for accessing shared artifacts
        """
        self._workflow_id = workflow_id
        self._parent_workflow_id = parent_workflow_id

        if base_path is None:
            from rouge.core.paths import RougePaths

            base_path = RougePaths.get_workflows_dir()

        self._base_path = base_path
        self._workflow_dir = base_path / workflow_id

        # Compute parent workflow directory if parent_workflow_id is provided
        if parent_workflow_id is not None:
            self._parent_workflow_dir: Optional[Path] = base_path / parent_workflow_id
        else:
            self._parent_workflow_dir = None

        self._ensure_workflow_dir()

    @property
    def parent_workflow_id(self) -> Optional[str]:
        """Get the parent workflow ID.

        Returns:
            Parent workflow ID if set, None otherwise
        """
        return self._parent_workflow_id

    def _ensure_workflow_dir(self) -> None:
        """Ensure the workflow directory exists.

        Also validates that the parent workflow directory exists if parent_workflow_id
        was provided.

        Raises:
            FileNotFoundError: If parent_workflow_id is set but the parent directory
                doesn't exist
        """
        # Validate parent workflow directory exists if parent_workflow_id is set
        if self._parent_workflow_dir is not None:
            if not self._parent_workflow_dir.exists():
                raise FileNotFoundError(
                    f"Parent workflow directory not found: {self._parent_workflow_dir}"
                )

        self._workflow_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    def _get_artifact_path(self, artifact_type: ArtifactType) -> Path:
        """Get the file path for an artifact type.

        Args:
            artifact_type: The type of artifact

        Returns:
            Path to the artifact JSON file
        """
        return self._workflow_dir / f"{artifact_type}.json"

    @property
    def workflow_id(self) -> str:
        """Get the workflow ID for this store."""
        return self._workflow_id

    @property
    def workflow_dir(self) -> Path:
        """Get the workflow directory path."""
        return self._workflow_dir

    def _is_patch_workflow(self) -> bool:
        """Check if this is a patch workflow.

        Patch workflows are identified by workflow IDs ending in '-patch'.

        Returns:
            True if this is a patch workflow, False otherwise
        """
        return self._workflow_id.endswith("-patch")

    def write_artifact(self, artifact: Artifact) -> None:
        """Write an artifact to disk.

        Args:
            artifact: The artifact to persist

        Raises:
            IOError: If the file cannot be written

        Note:
            Logs a warning if a patch workflow attempts to write a shared artifact
            type (issue, classification, plan, pr_metadata, pull_request). Shared
            artifacts should be read from the parent workflow directory instead.
        """
        # Warn if a patch workflow is writing a shared artifact type
        if self._is_patch_workflow() and artifact.artifact_type in SHARED_ARTIFACT_TYPES:
            logger.warning(
                "Patch workflow %s is writing shared artifact type '%s'. "
                "Shared artifacts should typically be read from the parent workflow. "
                "This write may cause inconsistency with the parent workflow's artifacts.",
                self._workflow_id,
                artifact.artifact_type,
            )

        artifact_path = self._get_artifact_path(artifact.artifact_type)

        try:
            json_data = artifact.model_dump_json(indent=2)
            artifact_path.write_text(json_data, encoding="utf-8")
            logger.debug(
                "Wrote artifact %s to %s",
                artifact.artifact_type,
                artifact_path,
            )
        except Exception as e:
            logger.exception(
                "Failed to write artifact %s: %s",
                artifact.artifact_type,
                e,
            )
            raise IOError(f"Failed to write artifact {artifact.artifact_type}: {e}")

    def read_artifact(
        self, artifact_type: ArtifactType, model_class: Optional[Type[T]] = None
    ) -> T:
        """Read an artifact from disk.

        For shared artifact types (issue, classification, plan, pr_metadata,
        pull_request), if the artifact is not found in the primary workflow
        directory and a parent_workflow_id is set, the method will fall back
        to reading from the parent workflow directory.

        Args:
            artifact_type: The type of artifact to read
            model_class: Optional model class (auto-detected if not provided)

        Returns:
            The deserialized and validated artifact

        Raises:
            FileNotFoundError: If the artifact file doesn't exist
            ValueError: If the artifact fails validation
        """
        artifact_path = self._get_artifact_path(artifact_type)

        # Determine if we should fall back to parent directory
        use_parent = False
        if not artifact_path.exists():
            # Check if we can fall back to parent for this artifact type
            if self._parent_workflow_dir is not None and artifact_type in SHARED_ARTIFACT_TYPES:
                parent_artifact_path = self._parent_workflow_dir / f"{artifact_type}.json"
                if parent_artifact_path.exists():
                    logger.info(
                        "Artifact %s not found in workflow %s, falling back to parent workflow %s",
                        artifact_type,
                        self._workflow_id,
                        self._parent_workflow_id,
                    )
                    artifact_path = parent_artifact_path
                    use_parent = True

        if not artifact_path.exists():
            raise FileNotFoundError(f"Artifact not found: {artifact_type}")

        if model_class is None:
            model_class = ARTIFACT_MODELS.get(artifact_type)  # type: ignore
            if model_class is None:
                raise ValueError(f"Unknown artifact type: {artifact_type}")

        try:
            json_data = artifact_path.read_text(encoding="utf-8")
            artifact = model_class.model_validate_json(json_data)
            if use_parent:
                logger.debug(
                    "Read artifact %s from parent workflow at %s",
                    artifact_type,
                    artifact_path,
                )
            else:
                logger.debug("Read artifact %s from %s", artifact_type, artifact_path)
            return artifact
        except json.JSONDecodeError as e:
            logger.exception("Failed to parse artifact %s: %s", artifact_type, e)
            raise ValueError(f"Corrupted artifact JSON for {artifact_type}: {e}") from e
        except Exception as e:
            logger.exception("Failed to read artifact %s: %s", artifact_type, e)
            raise ValueError(f"Failed to validate artifact {artifact_type}: {e}") from e

    def artifact_exists(self, artifact_type: ArtifactType) -> bool:
        """Check if an artifact exists.

        Args:
            artifact_type: The type of artifact to check

        Returns:
            True if the artifact file exists
        """
        return self._get_artifact_path(artifact_type).exists()

    def list_artifacts(self) -> List[ArtifactType]:
        """List all artifacts in the workflow directory.

        Returns:
            List of artifact type names that exist
        """
        artifacts: List[ArtifactType] = []

        for artifact_type in ARTIFACT_MODELS.keys():
            if self.artifact_exists(artifact_type):
                artifacts.append(artifact_type)

        return artifacts

    def get_artifact_info(self, artifact_type: ArtifactType) -> Optional[Dict[str, Any]]:
        """Get metadata about an artifact without fully loading it.

        Args:
            artifact_type: The type of artifact

        Returns:
            Dict with file size, modified time, or None if not found
        """
        artifact_path = self._get_artifact_path(artifact_type)

        if not artifact_path.exists():
            return None

        stat = artifact_path.stat()
        return {
            "artifact_type": artifact_type,
            "file_path": str(artifact_path),
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        }

    def delete_artifact(self, artifact_type: ArtifactType) -> bool:
        """Delete an artifact file.

        Args:
            artifact_type: The type of artifact to delete

        Returns:
            True if the artifact was deleted, False if it didn't exist
        """
        artifact_path = self._get_artifact_path(artifact_type)

        if not artifact_path.exists():
            return False

        try:
            artifact_path.unlink()
            logger.debug("Deleted artifact %s", artifact_type)
            return True
        except Exception as e:
            logger.exception("Failed to delete artifact %s: %s", artifact_type, e)
            return False
