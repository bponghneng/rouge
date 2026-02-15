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

from rouge.core.models import Issue
from rouge.core.workflow.types import (
    ClassifyData,
    ImplementData,
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
    "fetch-issue",
    "classify",
    "plan",
    "implement",
    "code-review",
    "review-fix",
    "code-quality",
    "acceptance",
    "compose-request",
    "gh-pull-request",
    "fetch-patch",
    "git-setup",
    "compose-commits",
    "glab-pull-request",
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


class FetchIssueArtifact(Artifact):
    """Artifact containing the fetched Issue data.

    Attributes:
        issue: The Issue model from the database
    """

    artifact_type: Literal["fetch-issue"] = "fetch-issue"
    issue: Issue = Field(
        description=(
            "The Issue model fetched from the database containing "
            "workflow metadata, status, and assignment information"
        )
    )


class ClassifyArtifact(Artifact):
    """Artifact containing issue classification results.

    Attributes:
        classify_data: The classification result data
    """

    artifact_type: Literal["classify"] = "classify"
    classify_data: ClassifyData = Field(
        description=(
            "Classification results including the slash command to execute "
            "and normalized classification metadata with type and level"
        )
    )


class PlanArtifact(Artifact):
    """Artifact containing plan building results.

    Attributes:
        plan_data: The plan data from the planning step
    """

    artifact_type: Literal["plan"] = "plan"
    plan_data: PlanData = Field(
        description=(
            "Plan building results containing the parsed plan markdown, "
            "summary, and optional session ID for continuation"
        )
    )


class ImplementArtifact(Artifact):
    """Artifact containing implementation results.

    Attributes:
        implement_data: The implementation output data
    """

    artifact_type: Literal["implement"] = "implement"
    implement_data: ImplementData = Field(
        description=(
            "Implementation output data containing the execution results "
            "and optional session ID for continuation"
        )
    )


class CodeReviewArtifact(Artifact):
    """Artifact containing code review results.

    Attributes:
        review_data: The review content
    """

    artifact_type: Literal["code-review"] = "code-review"
    review_data: ReviewData


class ReviewFixArtifact(Artifact):
    """Artifact indicating review issues have been addressed.

    Attributes:
        success: Whether review issues were successfully addressed
        message: Optional message about the resolution
    """

    artifact_type: Literal["review-fix"] = "review-fix"
    success: bool = Field(description="Whether all review issues were successfully addressed")
    message: Optional[str] = Field(
        default=None, description="Optional details about the resolution process"
    )


class CodeQualityArtifact(Artifact):
    """Artifact containing code quality check results.

    Attributes:
        output: The quality check output text
        tools: List of tools that were run
        parsed_data: Optional parsed JSON data from the check
    """

    artifact_type: Literal["code-quality"] = "code-quality"
    output: str = Field(description="Raw output text from code quality tools", min_length=1)
    tools: List[str] = Field(
        description="List of quality tool names that were executed", min_length=1
    )
    parsed_data: Optional[Dict[str, Any]] = Field(
        default=None, description="Structured JSON data parsed from tool output"
    )


class AcceptanceArtifact(Artifact):
    """Artifact containing acceptance validation results.

    Attributes:
        success: Whether the implementation passed acceptance criteria
        message: Optional message about the validation result
    """

    artifact_type: Literal["acceptance"] = "acceptance"
    success: bool = Field(description="Whether the implementation satisfies acceptance criteria")
    message: Optional[str] = Field(default=None, description="Optional validation result details")


class ComposeRequestArtifact(Artifact):
    """Artifact containing prepared pull request metadata.

    Attributes:
        title: The PR title
        summary: The PR body/summary
        commits: List of commit information
    """

    artifact_type: Literal["compose-request"] = "compose-request"
    title: str
    summary: str
    commits: List[Dict[str, Any]] = Field(default_factory=list)


class GhPullRequestArtifact(Artifact):
    """Artifact containing the created GitHub pull request details.

    Attributes:
        url: The URL of the created pull request
        platform: The platform where the PR was created (github)
    """

    artifact_type: Literal["gh-pull-request"] = "gh-pull-request"
    url: str = Field(description="The URL of the created GitHub pull request", min_length=1)
    platform: Literal["github"] = "github"


class FetchPatchArtifact(Artifact):
    """Artifact containing the fetched Patch issue data.

    Attributes:
        patch: The Issue model from the database (with type='patch')
    """

    artifact_type: Literal["fetch-patch"] = "fetch-patch"
    patch: Issue = Field(
        description=(
            "The Issue model fetched from the database with type='patch', "
            "containing patch-specific workflow metadata and configuration"
        )
    )


class GitSetupArtifact(Artifact):
    """Artifact containing git setup results.

    Attributes:
        branch: The name of the branch created or checked out
    """

    artifact_type: Literal["git-setup"] = "git-setup"
    branch: str = Field(
        description=("The name of the git branch created or checked out for the workflow"),
        min_length=1,
    )


class ComposeCommitsArtifact(Artifact):
    """Artifact containing composed commit metadata.

    Attributes:
        summary: A summary of the commits being composed
        commits: List of commit information dictionaries
    """

    artifact_type: Literal["compose-commits"] = "compose-commits"
    summary: str
    commits: List[Dict[str, Any]] = Field(default_factory=list)


class GlabPullRequestArtifact(Artifact):
    """Artifact containing the created GitLab pull request (merge request) details.

    Attributes:
        url: The URL of the created merge request
        platform: The platform where the MR was created (gitlab)
    """

    artifact_type: Literal["glab-pull-request"] = "glab-pull-request"
    url: str = Field(description="The URL of the created GitLab merge request", min_length=1)
    platform: Literal["gitlab"] = "gitlab"


# Mapping from artifact type to model class
ARTIFACT_MODELS: Dict[ArtifactType, Type[Artifact]] = {
    "fetch-issue": FetchIssueArtifact,
    "classify": ClassifyArtifact,
    "plan": PlanArtifact,
    "implement": ImplementArtifact,
    "code-review": CodeReviewArtifact,
    "review-fix": ReviewFixArtifact,
    "code-quality": CodeQualityArtifact,
    "acceptance": AcceptanceArtifact,
    "compose-request": ComposeRequestArtifact,
    "gh-pull-request": GhPullRequestArtifact,
    "fetch-patch": FetchPatchArtifact,
    "git-setup": GitSetupArtifact,
    "compose-commits": ComposeCommitsArtifact,
    "glab-pull-request": GlabPullRequestArtifact,
}


class ArtifactStore:
    """Filesystem-backed store for workflow artifacts.

    Manages reading, writing, and listing of artifacts for a specific workflow.
    Artifacts are stored as JSON files in `.rouge/workflows/{workflow_id}/`.
    """

    def __init__(
        self,
        workflow_id: str,
        base_path: Optional[Path] = None,
    ) -> None:
        """Initialize the artifact store for a workflow.

        Args:
            workflow_id: The workflow ID to manage artifacts for
            base_path: Optional base path override (defaults to RougePaths.get_workflows_dir())
        """
        self._workflow_id = workflow_id

        if base_path is None:
            from rouge.core.paths import RougePaths

            base_path = RougePaths.get_workflows_dir()

        self._base_path = base_path
        self._workflow_dir = base_path / workflow_id

        self._ensure_workflow_dir()

    def _ensure_workflow_dir(self) -> None:
        """Ensure the workflow directory exists."""
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

    def write_artifact(self, artifact: Artifact) -> None:
        """Write an artifact to disk.

        Args:
            artifact: The artifact to persist

        Raises:
            IOError: If the file cannot be written
        """
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

        if not artifact_path.exists():
            raise FileNotFoundError(f"Artifact not found: {artifact_type}")

        if model_class is None:
            model_class = ARTIFACT_MODELS.get(artifact_type)  # type: ignore
            if model_class is None:
                raise ValueError(f"Unknown artifact type: {artifact_type}")

        try:
            json_data = artifact_path.read_text(encoding="utf-8")
            artifact = model_class.model_validate_json(json_data)
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
