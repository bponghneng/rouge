"""Fetch patch step implementation."""

import logging

from rouge.core.database import fetch_issue
from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import emit_artifact_comment, emit_comment_from_payload
from rouge.core.workflow.artifacts import FetchPatchArtifact
from rouge.core.workflow.status import update_status
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
        issue_id = context.require_issue_id

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
                artifact = FetchPatchArtifact(
                    workflow_id=context.adw_id,
                    patch=issue,
                )
                context.artifact_store.write_artifact(artifact)
                logger.debug("Saved patch artifact for workflow %s", context.adw_id)

                status, msg = emit_artifact_comment(context.issue_id, context.adw_id, artifact)
                if status == "success":
                    logger.debug(msg)
                elif status == "skipped":
                    logger.debug(msg)
                else:
                    logger.error(msg)

            # Update status to "started" - best-effort, non-blocking
            update_status(issue_id, "started")

            # Emit progress comment
            payload = CommentPayload(
                issue_id=issue_id,
                adw_id=context.adw_id,
                text="Workflow started. Patch fetched and validated.",
                raw={
                    "issue_id": issue_id,
                    "text": "Workflow started. Patch fetched and validated.",
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
