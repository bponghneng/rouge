"""Pull request preparation step implementation."""

import logging

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.notifications import make_progress_comment_handler
from rouge.core.workflow.shared import AGENT_PULL_REQUEST_BUILDER
from rouge.core.workflow.status import update_status
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult
from rouge.core.workflow.workflow_io import emit_progress_comment

logger = logging.getLogger(__name__)

# Required fields for pull request output JSON
PR_REQUIRED_FIELDS = {
    "output": str,
    "title": str,
    "summary": str,
    "commits": list,
}


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
        try:
            pr_handler = make_progress_comment_handler(context.issue_id, context.adw_id)

            request = ClaudeAgentTemplateRequest(
                agent_name=AGENT_PULL_REQUEST_BUILDER,
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
            logger.debug("PR preparation LLM response: %s", response.output)

            # Emit raw LLM response for debugging visibility
            emit_progress_comment(
                context.issue_id,
                "PR preparation LLM response received",
                raw={
                    "output": "pr-preparation-response",
                    "llm_response": response.output,
                },
            )

            if not response.success:
                logger.warning(f"Pull request preparation failed: {response.output}")
                # Still mark workflow as completed even if PR prep fails
                self._finalize_workflow(context)
                return StepResult.fail(f"Pull request preparation failed: {response.output}")

            # Parse and validate JSON output
            parse_result = parse_and_validate_json(
                response.output, PR_REQUIRED_FIELDS, step_name="pull_request"
            )
            if not parse_result.success:
                error_msg = parse_result.error or "JSON parsing failed"
                logger.warning(f"Pull request JSON parsing failed: {error_msg}")
                # Still mark workflow as completed even if parse fails
                self._finalize_workflow(context)
                return StepResult.fail(error_msg)

            logger.info("Pull request prepared successfully")

            # Store PR details for CreatePullRequestStep using validated data
            if parse_result.data is not None:
                self._store_pr_details(parse_result.data, context)

            # Insert progress comment - best-effort, non-blocking
            emit_progress_comment(
                context.issue_id,
                "Pull request prepared.",
                raw={"text": "Pull request prepared.", "result": parse_result.data},
            )

            # Finalize workflow
            self._finalize_workflow(context)

            return StepResult.ok(None, parsed_data=parse_result.data)

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
        # Update status to "completed" - best-effort, non-blocking
        update_status(context.issue_id, "completed")

        # Insert progress comment - best-effort, non-blocking
        emit_progress_comment(
            context.issue_id,
            "Solution implemented successfully",
            raw={"text": "Solution implemented successfully."},
        )

    def _store_pr_details(self, pr_data: dict, context: WorkflowContext) -> None:
        """Store validated PR details in context for CreatePullRequestStep.

        Args:
            pr_data: The validated parsed PR data dict
            context: Workflow context
        """
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
