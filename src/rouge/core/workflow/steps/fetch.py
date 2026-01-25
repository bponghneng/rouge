"""Fetch issue step implementation."""

import logging

from rouge.core.database import fetch_issue
from rouge.core.workflow.artifacts import IssueArtifact
from rouge.core.workflow.status import update_status
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult
from rouge.core.workflow.workflow_io import emit_progress_comment

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
        issue_id = context.issue_id

        try:
            issue = fetch_issue(issue_id)
            logger.info("Issue fetched: ID=%s, Status=%s", issue.id, issue.status)
            context.issue = issue

            # Save artifact if artifact store is available
            if context.artifacts_enabled and context.artifact_store is not None:
                artifact = IssueArtifact(
                    workflow_id=context.adw_id,
                    issue=issue,
                )
                context.artifact_store.write_artifact(artifact)
                logger.debug("Saved issue artifact for workflow %s", context.adw_id)

            # Update status to "started" - best-effort, non-blocking
            update_status(issue_id, "started")

            # Insert progress comment - best-effort, non-blocking
            emit_progress_comment(
                issue_id,
                "Workflow started. Issue fetched and validated",
                raw={
                    "issue_id": issue_id,
                    "text": "Workflow started. Issue fetched and validated.",
                },
                adw_id=context.adw_id,
            )

            return StepResult.ok(None)

        except ValueError as e:
            logger.exception("Error fetching issue")
            return StepResult.fail(f"Error fetching issue: {e}")
        except Exception as e:
            logger.exception("Unexpected error fetching issue")
            return StepResult.fail(f"Unexpected error fetching issue: {e}")
