"""Fetch issue step implementation."""

from cape.core.database import fetch_issue
from cape.core.workflow.status import update_status
from cape.core.workflow.step_base import WorkflowContext, WorkflowStep
from cape.core.workflow.types import StepResult
from cape.core.workflow.workflow_io import emit_progress_comment


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
        logger = context.logger
        issue_id = context.issue_id

        try:
            issue = fetch_issue(issue_id)
            logger.info(f"Issue fetched: ID={issue.id}, Status={issue.status}")
            context.issue = issue

            # Update status to "started" - best-effort, non-blocking
            update_status(issue_id, "started", logger)

            # Insert progress comment - best-effort, non-blocking
            emit_progress_comment(
                issue_id,
                "Workflow started. Issue fetched and validated",
                logger,
                raw={
                    "issue_id": issue_id,
                    "text": "Workflow started. Issue fetched and validated.",
                },
            )

            return StepResult.ok(None)

        except ValueError as e:
            logger.error(f"Error fetching issue: {e}")
            return StepResult.fail(f"Error fetching issue: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching issue: {e}")
            return StepResult.fail(f"Unexpected error fetching issue: {e}")
