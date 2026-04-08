"""Pull request preparation step implementation."""

from typing import Any, Dict

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.prompts import PromptId
from rouge.core.utils import get_logger
from rouge.core.workflow.shared import AGENT_PULL_REQUEST_BUILDER, get_affected_repo_paths
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.step_utils import _sanitize_for_logging
from rouge.core.workflow.types import StepResult

# Required fields for pull request output JSON
PR_REQUIRED_FIELDS = {
    "output": str,
    "title": str,
    "summary": str,
    "commits": list,
}

PULL_REQUEST_JSON_SCHEMA = """{
  "type": "object",
  "properties": {
    "output": { "type": "string", "enum": ["pull-request"] },
    "title": { "type": "string" },
    "summary": { "type": "string" },
    "commits": {
      "type": "array",
      "items": {
        "required": ["message", "sha"],
        "properties": {
          "message": { "type": "string" },
          "sha": { "type": "string" },
          "files": { "type": "array", "items": { "type": "string" } }
        }
      }
    }
  },
  "required": ["output", "title", "summary", "commits"]
}"""


class ComposeRequestStep(WorkflowStep):
    """Compose pull request via the pull-request prompt template."""

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
        logger = get_logger(context.adw_id)

        try:
            affected_repos = get_affected_repo_paths(context)
            if not affected_repos:
                logger.info("No affected repos — skipping compose request")
                return StepResult.ok(None)

            request = ClaudeAgentTemplateRequest(
                agent_name=AGENT_PULL_REQUEST_BUILDER,
                prompt_id=PromptId.PULL_REQUEST,
                args=affected_repos,
                adw_id=context.adw_id,
                issue_id=context.require_issue_id,
                model="sonnet",
                json_schema=PULL_REQUEST_JSON_SCHEMA,
            )

            logger.debug(
                "pull_request request: %s",
                request.model_dump_json(indent=2, by_alias=True),
            )

            response = execute_template(request)

            logger.debug("pull_request response: success=%s", response.success)
            logger.debug("PR preparation LLM response: %s", _sanitize_for_logging(response.output))

            # Emit raw LLM response for debugging visibility
            payload = CommentPayload(
                issue_id=context.require_issue_id,
                adw_id=context.adw_id,
                text="PR preparation LLM response received",
                raw={
                    "output": "pr-preparation-response",
                    "llm_response": response.output[:500] if response.output else "",
                },
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.error(msg)

            if not response.success:
                logger.warning("Pull request preparation failed: %s", response.output)
                # Still mark workflow as completed even if PR prep fails
                self._emit_completion_comment(context)
                return StepResult.fail(f"Pull request preparation failed: {response.output}")

            # Parse and validate JSON output
            parse_result = parse_and_validate_json(
                response.output, PR_REQUIRED_FIELDS, step_name="pull_request"
            )
            if not parse_result.success:
                error_msg = parse_result.error or "JSON parsing failed"
                logger.warning("Pull request JSON parsing failed: %s", error_msg)
                # Still mark workflow as completed even if parse fails
                self._emit_completion_comment(context)
                return StepResult.fail(error_msg)

            logger.info("Pull request prepared successfully")

            # Store PR details for CreatePullRequestStep using validated data
            if parse_result.data is not None:
                self._store_pr_details(parse_result.data, context)

            # Insert progress comment - best-effort, non-blocking
            payload = CommentPayload(
                issue_id=context.require_issue_id,
                adw_id=context.adw_id,
                text="Pull request prepared.",
                raw={"text": "Pull request prepared.", "result": parse_result.data},
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.error(msg)

            # Finalize workflow
            self._emit_completion_comment(context)

            return StepResult.ok(None, parsed_data=parse_result.data)

        except Exception as e:
            logger.exception("Pull request preparation failed: %s", e)
            # Still mark workflow as completed
            self._emit_completion_comment(context)
            return StepResult.fail(f"Pull request preparation failed: {e}")

    def _emit_completion_comment(self, context: WorkflowContext) -> None:
        """Emit a completion comment for the workflow.

        Args:
            context: Workflow context
        """
        logger = get_logger(context.adw_id)
        # Insert progress comment - best-effort, non-blocking
        payload = CommentPayload(
            issue_id=context.require_issue_id,
            adw_id=context.adw_id,
            text="Solution implemented successfully",
            raw={"text": "Solution implemented successfully."},
            source="system",
            kind="workflow",
        )
        status, msg = emit_comment_from_payload(payload)
        if status == "success":
            logger.debug(msg)
        else:
            logger.error(msg)

    def _store_pr_details(self, pr_data: Dict[str, Any], context: WorkflowContext) -> None:
        """Store validated PR details in context for CreatePullRequestStep.

        Args:
            pr_data: The validated parsed PR data dict
            context: Workflow context
        """
        logger = get_logger(context.adw_id)
        # Store PR details for CreatePullRequestStep
        pr_details = {
            "title": pr_data.get("title", ""),
            "summary": pr_data.get("summary", ""),
            "commits": pr_data.get("commits", []),
        }
        context.data["pr_details"] = pr_details
        logger.debug(
            "Stored PR details in context: title=%s, commits=%d",
            pr_details["title"],
            len(pr_details["commits"]),
        )



