"""Implementation step."""

from pydantic import ValidationError

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.prompts import PromptId
from rouge.core.utils import get_logger
from rouge.core.workflow.shared import AGENT_PLAN_IMPLEMENTOR, IMPLEMENT_PLAN_STEP_NAME
from rouge.core.workflow.step_base import StepInputError, WorkflowContext, WorkflowStep
from rouge.core.workflow.types import ImplementData, RepoChangeDetail, StepResult

# Required fields for implement output JSON
IMPLEMENT_REQUIRED_FIELDS = {
    "files_modified": list,
    "git_diff_stat": str,
    "output": str,
    "status": str,
    "summary": str,
}

IMPLEMENT_JSON_SCHEMA = """{
  "type": "object",
  "properties": {
    "files_modified": { "type": "array", "items": { "type": "string" } },
    "git_diff_stat": { "type": "string" },
    "output": { "type": "string", "enum": ["implement-plan"] },
    "status": { "type": "string" },
    "summary": { "type": "string" },
    "affected_repos": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "repo_path": { "type": "string" },
          "files_modified": { "type": "array", "items": { "type": "string" } },
          "git_diff_stat": { "type": "string" }
        },
        "required": ["repo_path"]
      }
    }
  },
  "required": ["files_modified", "git_diff_stat", "output", "status", "summary"]
}"""
# Note: "affected_repos" is intentionally omitted from "required" to maintain
# backward compatibility with older agent outputs. When absent, downstream steps
# fall back to context.repo_paths via get_affected_repo_paths().


IMPLEMENT_DIRECT_REQUIRED_FIELDS = IMPLEMENT_REQUIRED_FIELDS

IMPLEMENT_DIRECT_JSON_SCHEMA = """{
  "type": "object",
  "properties": {
    "files_modified": { "type": "array", "items": { "type": "string" } },
    "git_diff_stat": { "type": "string" },
    "output": { "type": "string", "enum": ["implement-direct"] },
    "status": { "type": "string" },
    "summary": { "type": "string" },
    "affected_repos": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "repo_path": { "type": "string" },
          "files_modified": { "type": "array", "items": { "type": "string" } },
          "git_diff_stat": { "type": "string" }
        },
        "required": ["repo_path"]
      }
    }
  },
  "required": ["files_modified", "git_diff_stat", "output", "status", "summary"]
}"""


class ImplementPlanStep(WorkflowStep):
    """Execute plan-based implementation."""

    def __init__(self, plan_step_name: str | None = None) -> None:
        """Initialize ImplementPlanStep.

        Args:
            plan_step_name: Name of the preceding plan step for rerun messages.
                Defaults to "Building implementation plan" when not provided.
        """
        self.plan_step_name = plan_step_name or "Building implementation plan"

    @property
    def name(self) -> str:
        return IMPLEMENT_PLAN_STEP_NAME

    def _implement_plan(
        self, plan_content: str, issue_id: int, adw_id: str
    ) -> StepResult[ImplementData]:
        """Implement the plan using Claude Code template.

        Uses the implement-plan prompt template via execute_template pattern.

        Args:
            plan_content: The plan content (markdown) to implement
            issue_id: Issue ID for tracking
            adw_id: Workflow ID for tracking

        Returns:
            StepResult with ImplementData containing output and optional session_id
        """
        logger = get_logger(adw_id)
        # Create template request using packaged prompt
        request = ClaudeAgentTemplateRequest(
            prompt_id=PromptId.IMPLEMENT_PLAN,
            args=[plan_content.lstrip()],
            issue_id=issue_id,
            adw_id=adw_id,
            agent_name=AGENT_PLAN_IMPLEMENTOR,
            json_schema=IMPLEMENT_JSON_SCHEMA,
        )

        # Execute template
        response = execute_template(request)

        logger.debug(
            "implement response: success=%s, session_id=%s",
            response.success,
            response.session_id,
        )

        if not response.success:
            error_message = response.output or "Implement step failed"
            return StepResult.fail(error_message)

        # Guard: Check that response.output is present before parsing
        if not response.output:
            return StepResult.fail("Implement step returned empty output")

        # Parse and validate JSON output with IMPLEMENT_REQUIRED_FIELDS
        parse_result = parse_and_validate_json(
            response.output, IMPLEMENT_REQUIRED_FIELDS, step_name="implement"
        )
        if not parse_result.success:
            return StepResult.fail(parse_result.error or "JSON parsing failed")

        raw_repos = (parse_result.data or {}).get("affected_repos", [])
        try:
            repo_details = [RepoChangeDetail(**r) for r in raw_repos] if raw_repos else []
        except (ValidationError, TypeError):
            logger.warning(
                "Could not parse affected_repos from LLM output, continuing without repo details"
            )
            repo_details = []

        return StepResult.ok(
            ImplementData(
                output=response.output,
                session_id=response.session_id,
                affected_repos=repo_details,
            ),
            parsed_data=parse_result.data,
        )

    def run(self, context: WorkflowContext) -> StepResult:
        """Implement the plan and store result in context.

        Args:
            context: Workflow context with plan data

        Returns:
            StepResult with success status and optional error message
        """
        logger = get_logger(context.adw_id)

        # Load plan from context data (required)
        try:
            plan_data = context.load_required_artifact("plan_data")
        except StepInputError as e:
            logger.error("Cannot implement: no plan available: %s", e)
            return StepResult.fail(
                f"Cannot implement: no plan available: {e}",
                rerun_from=self.plan_step_name,
            )
        plan_text = plan_data.plan if plan_data is not None else None

        if plan_text is None:
            logger.error("Cannot implement: no plan available")
            return StepResult.fail(
                "Cannot implement: no plan available",
                rerun_from=self.plan_step_name,
            )

        implement_response = self._implement_plan(
            plan_text, context.require_issue_id, context.adw_id
        )

        if not implement_response.success:
            logger.error("Error implementing solution: %s", implement_response.error)
            return StepResult.fail(f"Error implementing solution: {implement_response.error}")

        logger.info("Solution implemented")

        if implement_response.data is None:
            logger.error("Implementation data missing despite successful response")
            return StepResult.fail("Implementation data missing despite successful response")

        logger.debug("Output preview: %s...", implement_response.data.output[:200])

        # Store implementation data in context
        context.data["implement_data"] = implement_response.data
        context.data["implement"] = implement_response.data
        logger.debug("Stored implementation data for workflow %s", context.adw_id)

        # Insert progress comment - best-effort, non-blocking
        payload = CommentPayload(
            issue_id=context.require_issue_id,
            adw_id=context.adw_id,
            text="Implementation complete.",
            raw={"text": "Implementation complete."},
            source="system",
            kind="workflow",
        )
        status, msg = emit_comment_from_payload(payload)
        if status == "success":
            logger.debug(msg)
        else:
            logger.error(msg)

        return StepResult.ok(None)
