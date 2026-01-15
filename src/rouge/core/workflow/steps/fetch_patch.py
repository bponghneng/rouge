"""Fetch patch step implementation."""

import logging

from rouge.core.database import fetch_issue, fetch_pending_patch
from rouge.core.workflow.artifacts import IssueArtifact, PatchArtifact
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult
from rouge.core.workflow.workflow_io import emit_progress_comment

logger = logging.getLogger(__name__)


class FetchPatchStep(WorkflowStep):
    """Fetch pending patch for an issue from Supabase."""

    @property
    def name(self) -> str:
        return "Fetching pending patch"

    @property
    def is_critical(self) -> bool:
        """Patch fetch is critical - workflow cannot proceed without it."""
        return True

    def run(self, context: WorkflowContext) -> StepResult:
        """Fetch pending patch and issue from database.

        Fetches both the issue and its pending patch directly from the database.
        The patch workflow uses a different workflow_id than the main workflow,
        so artifacts from the main workflow are not accessible here.

        Args:
            context: Workflow context to update

        Returns:
            StepResult with success status and optional error message
        """
        issue_id = context.issue_id

        try:
            # Fetch issue from database
            issue = fetch_issue(issue_id)
            context.issue = issue

            # Fetch the pending patch for this issue
            patch = fetch_pending_patch(issue_id)
            logger.info(
                f"Patch fetched: ID={patch.id}, Issue={patch.issue_id}, Status={patch.status}"
            )

            # Store patch in context data
            context.data["patch"] = patch

            # Save artifact if artifact store is available
            if context.artifacts_enabled and context.artifact_store is not None:
                artifact = PatchArtifact(
                    workflow_id=context.adw_id,
                    patch=patch,
                )
                context.artifact_store.write_artifact(artifact)
                logger.debug("Saved patch artifact for workflow %s", context.adw_id)

            # Emit progress comment with patch description
            emit_progress_comment(
                issue_id,
                f"Patch fetched: {patch.description}",
                raw={
                    "patch_id": patch.id,
                    "issue_id": issue_id,
                    "description": patch.description,
                },
                adw_id=context.adw_id,
            )

            return StepResult.ok(None)

        except ValueError as e:
            logger.error(f"Error fetching patch: {e}")
            return StepResult.fail(f"Error fetching patch: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching patch: {e}")
            return StepResult.fail(f"Unexpected error fetching patch: {e}")
