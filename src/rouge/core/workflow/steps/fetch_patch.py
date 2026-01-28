"""Fetch patch step implementation."""

import logging

from rouge.core.database import fetch_issue
from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.workflow.artifacts import PatchArtifact
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult

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
        """Fetch pending patch issue from database.

        Fetches the issue (which should have type='patch') directly from the database.
        The patch workflow uses a different workflow_id than the main workflow,
        so artifacts from the main workflow are not accessible here.

        Args:
            context: Workflow context to update

        Returns:
            StepResult with success status and optional error message
        """
        issue_id = context.issue_id

        try:
            # Fetch issue from database (should be type='patch')
            issue = fetch_issue(issue_id)
            context.issue = issue

            # Verify this is actually a patch issue
            if issue.type != "patch":
                return StepResult.fail(f"Issue {issue_id} is not a patch issue (type={issue.type})")

            logger.info(
                "Patch issue fetched: ID=%s, Type=%s, Status=%s, ADW_ID=%s",
                issue.id,
                issue.type,
                issue.status,
                issue.adw_id,
            )

            # Save artifact if artifact store is available
            if context.artifacts_enabled and context.artifact_store is not None:
                # Save patch artifact with the issue
                artifact = PatchArtifact(
                    workflow_id=context.adw_id,
                    patch=issue,
                )
                context.artifact_store.write_artifact(artifact)
                logger.debug("Saved patch artifact for workflow %s", context.adw_id)

            # Emit progress comment with patch description
            payload = CommentPayload(
                issue_id=issue_id,
                adw_id=context.adw_id,
                text=f"Patch fetched: {issue.description}",
                raw={
                    "issue_id": issue_id,
                    "description": issue.description,
                    "type": issue.type,
                },
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.error(msg)

            return StepResult.ok(None)

        except ValueError as e:
            logger.exception("Error fetching patch issue")
            return StepResult.fail(f"Error fetching patch issue: {e}")
        except Exception as e:
            logger.exception("Unexpected error fetching patch issue")
            return StepResult.fail(f"Unexpected error fetching patch issue: {e}")
