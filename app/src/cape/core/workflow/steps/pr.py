"""Pull request preparation step implementation."""

import json

from cape.core.agent import execute_template
from cape.core.agents.claude import ClaudeAgentTemplateRequest
from cape.core.notifications import make_progress_comment_handler
from cape.core.workflow.shared import AGENT_IMPLEMENTOR
from cape.core.workflow.status import update_status
from cape.core.workflow.step_base import WorkflowContext, WorkflowStep
from cape.core.workflow.types import StepResult
from cape.core.workflow.workflow_io import emit_progress_comment


class PreparePullRequestStep(WorkflowStep):
    """Prepare pull request via /adw-pull-request slash command."""

    @property
    def name(self) -> str:
        return "Preparing pull request"

    @property
    def is_critical(self) -> bool:
        # PR preparation is best-effort - workflow continues on failure
        return False

    def run(self, context: WorkflowContext) -> StepResult:
        """Prepare pull request and finalize workflow.

        Args:
            context: Workflow context

        Returns:
            StepResult with success status and optional error message
        """
        logger = context.logger

        try:
            pr_handler = make_progress_comment_handler(context.issue_id, context.adw_id, logger)

            request = ClaudeAgentTemplateRequest(
                agent_name=AGENT_IMPLEMENTOR,
                slash_command="/adw-pull-request",
                args=[],
                adw_id=context.adw_id,
                issue_id=context.issue_id,
                model="sonnet",
            )

            logger.debug(
                "pull_request request: %s",
                request.model_dump_json(indent=2, by_alias=True),
            )

            response = execute_template(request, stream_handler=pr_handler)

            logger.debug("pull_request response: success=%s", response.success)

            if not response.success:
                logger.warning(f"Pull request preparation failed: {response.output}")
                # Still mark workflow as completed even if PR prep fails
                self._finalize_workflow(context)
                return StepResult.fail(f"Pull request preparation failed: {response.output}")

            logger.info("Pull request prepared successfully")

            # Parse and store PR details for CreatePullRequestStep
            self._store_pr_details(response.output, context, logger)

            # Insert progress comment - best-effort, non-blocking
            emit_progress_comment(
                context.issue_id,
                "Pull request prepared.",
                logger,
                raw={"text": "Pull request prepared."},
            )

            # Finalize workflow
            self._finalize_workflow(context)

            return StepResult.ok(None)

        except Exception as e:
            logger.warning(f"Pull request preparation failed: {e}")
            # Still mark workflow as completed
            self._finalize_workflow(context)
            return StepResult.fail(f"Pull request preparation failed: {e}")

    def _finalize_workflow(self, context: WorkflowContext) -> None:
        """Finalize workflow by updating status and inserting completion comment.

        Args:
            context: Workflow context
        """
        logger = context.logger

        # Update status to "completed" - best-effort, non-blocking
        update_status(context.issue_id, "completed", logger)

        # Insert progress comment - best-effort, non-blocking
        emit_progress_comment(
            context.issue_id,
            "Solution implemented successfully",
            logger,
            raw={"text": "Solution implemented successfully."},
        )

    def _store_pr_details(self, output: str, context: WorkflowContext, logger) -> None:
        """Parse and store PR details in context for CreatePullRequestStep.

        Args:
            output: The output from /adw-pull-request command
            context: Workflow context
            logger: Logger instance
        """
        try:
            pr_data = json.loads(output)
            # Store PR details for CreatePullRequestStep
            context.data["pr_details"] = {
                "title": pr_data.get("title", ""),
                "summary": pr_data.get("summary", ""),
                "commits": pr_data.get("commits", []),
            }
            logger.debug(
                "Stored PR details in context: title=%s, commits=%d",
                context.data["pr_details"]["title"],
                len(context.data["pr_details"]["commits"]),
            )
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse PR details JSON: {e}")
            # Don't fail the step, just log the warning
        except Exception as e:
            logger.warning(f"Error storing PR details: {e}")
