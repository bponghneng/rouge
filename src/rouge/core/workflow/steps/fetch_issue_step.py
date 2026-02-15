"""Fetch issue step implementation."""

import logging

from rouge.core.database import fetch_issue
from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import emit_artifact_comment, emit_comment_from_payload
from rouge.core.workflow.artifacts import FetchIssueArtifact
from rouge.core.workflow.status import update_status
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult

logger = logging.getLogger(__name__)


class FetchIssueStep(WorkflowStep):
    """Fetch and validate issue from Supabase."""

    @property
    def name(self) -> str:
        return "Fetching issue from Supabase"

    def run(self, context: WorkflowContext) -> StepResult:
        """Fetch issue and store in context.

        Args:
            context: Workflow context to update

        Returns:
            StepResult with success status and optional error message
        """
        try:
            issue_id = context.require_issue_id
        except RuntimeError as e:
            # Handle missing issue_id from require_issue_id
            logger.error("Missing issue_id: %s", e)
            return StepResult.fail(str(e))

        try:
            issue = fetch_issue(issue_id)
            logger.info("Issue fetched: ID=%s, Status=%s", issue.id, issue.status)
            context.issue = issue

            # Save artifact if artifact store is available
            if context.artifacts_enabled and context.artifact_store is not None:
                artifact = FetchIssueArtifact(
                    workflow_id=context.adw_id,
                    issue=issue,
                )
                context.artifact_store.write_artifact(artifact)
                logger.debug("Saved issue artifact for workflow %s", context.adw_id)

                status, msg = emit_artifact_comment(context.issue_id, context.adw_id, artifact)
                if status == "success":
                    logger.debug(msg)
                elif status == "skipped":
                    logger.debug(msg)
                else:
                    logger.error(msg)

            # Update status to "started" - best-effort, non-blocking
            update_status(issue_id, "started")

            # Insert progress comment - best-effort, non-blocking
            payload = CommentPayload(
                issue_id=issue_id,
                adw_id=context.adw_id,
                text="Workflow started. Issue fetched and validated",
                raw={
                    "issue_id": issue_id,
                    "text": "Workflow started. Issue fetched and validated.",
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
            logger.exception("Error fetching issue")
            return StepResult.fail(f"Error fetching issue: {e}")
        except Exception as e:
            logger.exception("Unexpected error fetching issue (not related to require_issue_id)")
            return StepResult.fail(f"Failed to fetch issue: {e}")
