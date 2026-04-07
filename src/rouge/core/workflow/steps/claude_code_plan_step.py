"""Claude Code plan building step implementation.

Builds a task-oriented implementation plan without requiring classification,
using a streamlined task-keyed schema (task, output, plan, summary).
"""

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.models import CommentPayload, Issue
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.prompts import PromptId
from rouge.core.utils import get_logger
from rouge.core.workflow.shared import AGENT_PLANNER
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import PlanData, StepResult

# Required fields for plan output JSON
# Plan output must have task, output, plan (inline content), summary
PLAN_REQUIRED_FIELDS = {
    "task": str,
    "output": str,
    "plan": str,
    "summary": str,
}

PLAN_JSON_SCHEMA = """{
  "type": "object",
  "properties": {
    "task": { "type": "string", "minLength": 1 },
    "output": { "type": "string", "const": "plan" },
    "plan": { "type": "string", "minLength": 1 },
    "summary": { "type": "string", "minLength": 1 }
  },
  "required": ["task", "output", "plan", "summary"]
}"""


class ClaudeCodePlanStep(WorkflowStep):
    """Task-oriented plan building step for full workflow.

    This step builds an implementation plan directly from the issue
    description, without requiring classification. It:
    1. Uses the issue from context (set by FetchIssueStep)
    2. Generates a task-oriented plan via the claude-code-plan prompt template
    3. Stores the result in context.data
    """

    @property
    def name(self) -> str:
        return "Building task-oriented implementation plan"

    def _build_plan(
        self,
        issue: Issue,
        adw_id: str,
    ) -> StepResult[PlanData]:
        """Build implementation plan for the issue using the claude-code-plan prompt template.

        Args:
            issue: The Rouge issue to plan for
            adw_id: Workflow ID for tracking

        Returns:
            StepResult with PlanData containing output and optional session_id
        """
        logger = get_logger(adw_id)
        request = ClaudeAgentTemplateRequest(
            agent_name=AGENT_PLANNER,
            prompt_id=PromptId.CLAUDE_CODE_PLAN,
            args=[issue.description],
            adw_id=adw_id,
            issue_id=issue.id,
            model="sonnet",
            json_schema=PLAN_JSON_SCHEMA,
        )
        logger.debug(
            "build_plan request: %s",
            request.model_dump_json(indent=2, by_alias=True),
        )
        response = execute_template(request)
        logger.debug(
            "build_plan response: %s",
            response.model_dump_json(indent=2, by_alias=True),
        )

        if not response.success:
            return StepResult.fail(response.output or "Agent failure: no output")

        # Guard: Check that response.output is present before parsing
        if not response.output:
            return StepResult.fail("No output from template execution")

        # Parse and validate JSON output
        parse_result = parse_and_validate_json(
            response.output, PLAN_REQUIRED_FIELDS, step_name="build_plan"
        )
        if not parse_result.success:
            return StepResult.fail(parse_result.error or "JSON parsing failed")

        parsed_data = parse_result.data or {}
        return StepResult.ok(
            PlanData(
                plan=parsed_data.get("plan", ""),
                summary=parsed_data.get("summary", ""),
                session_id=response.session_id,
            ),
            parsed_data=parsed_data,
        )

    def run(self, context: WorkflowContext) -> StepResult:
        """Build implementation plan and store in context.

        Args:
            context: Workflow context with issue from FetchIssueStep

        Returns:
            StepResult with success status and optional error message
        """
        logger = get_logger(context.adw_id)

        # Load issue from context (set by FetchIssueStep)
        issue = context.issue
        if issue is None:
            error_msg = "Cannot build plan: no issue in context"
            logger.error(error_msg)
            return StepResult.fail(error_msg)

        plan_response = self._build_plan(issue, context.adw_id)

        if not plan_response.success:
            logger.error("Error building plan: %s", plan_response.error)
            return StepResult.fail(f"Error building plan: {plan_response.error}")

        # Store plan data in context
        if plan_response.data is not None:
            context.data["plan_data"] = plan_response.data
            context.data["plan"] = plan_response.data
            logger.debug("Stored plan data for workflow %s", context.adw_id)

        # Build progress comment from parsed plan data
        parsed_data = plan_response.metadata.get("parsed_data", {})
        # Extract title from task key
        title = parsed_data.get("task", "Implementation plan created")
        summary = parsed_data.get("summary", "")
        comment_text = f"{title}\n\n{summary}" if summary else title

        # Insert progress comment - best-effort, non-blocking
        payload = CommentPayload(
            issue_id=issue.id,
            adw_id=context.adw_id,
            text=comment_text,
            raw={"text": comment_text, "parsed": parsed_data},
            source="system",
            kind="workflow",
        )
        status, msg = emit_comment_from_payload(payload)
        if status == "success":
            logger.debug(msg)
        else:
            logger.error(msg)

        return StepResult.ok(None)
