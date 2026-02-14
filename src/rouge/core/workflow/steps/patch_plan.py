"""Patch plan building step implementation.

Builds a standalone implementation plan for a patch issue. The patch issue
contains its own description and does not depend on any parent workflow
artifacts (original issue or original plan).
"""

import logging

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.models import CommentPayload, Issue
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.workflow.artifacts import PlanArtifact
from rouge.core.workflow.shared import AGENT_PLANNER
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import PlanData, PlanSlashCommand, StepResult

logger = logging.getLogger(__name__)

# Required fields for plan output JSON
# Plan output must have type, output, plan (inline content), summary
PLAN_REQUIRED_FIELDS = {
    "type": str,
    "output": str,
    "plan": str,
    "summary": str,
}

PLAN_JSON_SCHEMA = """{
  "type": "object",
  "properties": {
    "type": { "type": "string", "minLength": 1 },
    "output": { "type": "string", "const": "plan" },
    "plan": { "type": "string", "minLength": 1 },
    "summary": { "type": "string", "minLength": 1 }
  },
  "required": ["type", "output", "plan", "summary"]
}"""


class BuildPatchPlanStep(WorkflowStep):
    """Standalone plan building step for patch issues.

    This step builds an implementation plan directly from the patch issue
    description, without referencing any parent workflow artifacts. It:
    1. Uses the patch issue from context (set by FetchPatchStep on context.issue)
    2. Generates a standalone implementation plan via the shared plan builder
    3. Stores the result in context and as a PlanArtifact
    """

    @property
    def name(self) -> str:
        return "Building patch plan"

    @property
    def is_critical(self) -> bool:
        """Patch planning is critical - workflow cannot proceed without it."""
        return True

    def _build_plan(
        self,
        issue: Issue,
        command: PlanSlashCommand,
        adw_id: str,
    ) -> StepResult[PlanData]:
        """Build implementation plan for the issue using the specified command.

        Args:
            issue: The Rouge issue to plan for
            command: The planning command to use (e.g., /adw-feature-plan)
            adw_id: Workflow ID for tracking

        Returns:
            StepResult with PlanData containing output and optional session_id
        """
        request = ClaudeAgentTemplateRequest(
            agent_name=AGENT_PLANNER,
            slash_command=command,
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
        """Build standalone plan for patch issue and store in context.

        Uses the patch issue already set on context.issue by FetchPatchStep.

        Args:
            context: Workflow context with patch issue from FetchPatchStep

        Returns:
            StepResult with success status and optional error message
        """
        # The patch issue is set on context.issue by FetchPatchStep
        issue = context.issue

        if issue is None:
            logger.error("Cannot build patch plan: patch issue not available")
            return StepResult.fail("Cannot build patch plan: patch issue not available")

        # Build standalone plan from patch issue description
        plan_response = self._build_plan(issue, "/adw-patch-plan", context.adw_id)

        if not plan_response.success:
            logger.error("Error building patch plan: %s", plan_response.error)
            return StepResult.fail(f"Error building patch plan: {plan_response.error}")

        # Store plan data in context
        context.data["plan_data"] = plan_response.data

        # Save artifact if artifact store is available
        if (
            context.artifacts_enabled
            and context.artifact_store is not None
            and plan_response.data is not None
        ):
            artifact = PlanArtifact(
                workflow_id=context.adw_id,
                plan_data=plan_response.data,
            )
            context.artifact_store.write_artifact(artifact)
            logger.debug("Saved plan artifact for workflow %s", context.adw_id)

        # Build progress comment from parsed plan data
        parsed_data = plan_response.metadata.get("parsed_data", {})
        # Extract title from one of: chore, bug, feature keys
        title = (
            parsed_data.get("chore")
            or parsed_data.get("bug")
            or parsed_data.get("feature")
            or "Implementation plan created"
        )
        summary = parsed_data.get("summary", "")
        comment_text = f"{title}\n\n{summary}" if summary else title

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
