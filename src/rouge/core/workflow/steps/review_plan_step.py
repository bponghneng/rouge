"""Review plan step implementation.

This step derives the base commit reference for code review workflows by parsing
the issue description. It invokes an AI agent to extract the base commit ref/SHA
and rationale, storing the result as a PlanArtifact.
"""

import logging

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.models import CommentPayload, Issue
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.workflow.artifacts import FetchIssueArtifact, PlanArtifact
from rouge.core.workflow.shared import AGENT_PLANNER
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import PlanData, StepResult

logger = logging.getLogger(__name__)

# Required fields for review plan output JSON
# Review plan output must have output="plan", base_commit, and summary
REVIEW_PLAN_REQUIRED_FIELDS = {
    "output": str,
    "base_commit": str,
    "summary": str,
}

REVIEW_PLAN_JSON_SCHEMA = """{
  "type": "object",
  "properties": {
    "output": { "type": "string", "const": "plan" },
    "base_commit": { "type": "string", "minLength": 1 },
    "summary": { "type": "string", "minLength": 1 }
  },
  "required": ["output", "base_commit", "summary"]
}"""


class ReviewPlanStep(WorkflowStep):
    """Derive review base commit from issue description.

    This step parses the issue description to extract the base commit reference
    for code review workflows. It uses an AI agent to identify the commit SHA
    and provide a rationale for the selection.
    """

    @property
    def name(self) -> str:
        return "Deriving review base commit"

    @property
    def is_critical(self) -> bool:
        """This step is critical - workflow cannot proceed without base commit."""
        return True

    def _derive_base_commit(
        self,
        issue: Issue,
        adw_id: str,
    ) -> StepResult[PlanData]:
        """Parse issue description to extract base commit reference.

        Args:
            issue: The Rouge issue containing the description
            adw_id: Workflow ID for tracking

        Returns:
            StepResult with PlanData containing base_commit as plan field
            and rationale as summary field
        """
        # Validate issue description is present
        desc = (issue.description or "").strip()
        if not desc:
            raise ValueError("Issue description is required for review plan generation")

        request = ClaudeAgentTemplateRequest(
            agent_name=AGENT_PLANNER,
            slash_command="/adw-review-plan",
            args=[desc],
            adw_id=adw_id,
            issue_id=issue.id,
            model="sonnet",
            json_schema=REVIEW_PLAN_JSON_SCHEMA,
        )
        logger.debug(
            "derive_base_commit request: %s",
            request.model_dump_json(indent=2, by_alias=True),
        )
        response = execute_template(request)
        logger.debug(
            "derive_base_commit response: %s",
            response.model_dump_json(indent=2, by_alias=True),
        )

        if not response.success:
            return StepResult.fail(response.output or "Agent failed without message")

        # Parse and validate JSON output
        parse_result = parse_and_validate_json(
            response.output, REVIEW_PLAN_REQUIRED_FIELDS, step_name="derive_base_commit"
        )
        if not parse_result.success:
            return StepResult.fail(parse_result.error or "JSON parsing failed")

        parsed_data = parse_result.data or {}

        # Validate output field value
        if parsed_data.get("output") != "plan":
            return StepResult.fail("Invalid output field in review plan response")

        # Extract base_commit and summary
        # Validate base_commit is present and non-empty
        if "base_commit" not in parsed_data or not parsed_data["base_commit"].strip():
            return StepResult.fail("base_commit is required in review plan response")
        base_commit = parsed_data["base_commit"].strip()
        summary = parsed_data.get("summary", "")

        # Store base_commit as the plan field and summary as rationale
        return StepResult.ok(
            PlanData(
                plan=base_commit,
                summary=summary,
                session_id=response.session_id,
            ),
            parsed_data=parsed_data,
        )

    def run(self, context: WorkflowContext) -> StepResult:
        """Derive base commit and store in context.

        Args:
            context: Workflow context with issue data

        Returns:
            StepResult with success status and optional error message
        """
        # Try to load issue from artifact if not in context
        issue = context.load_issue_artifact_if_missing(FetchIssueArtifact, lambda a: a.issue)

        if issue is None:
            logger.error("Cannot derive base commit: issue not fetched")
            return StepResult.fail("Cannot derive base commit: issue not fetched")

        derive_response = self._derive_base_commit(
            issue,
            context.adw_id,
        )

        if not derive_response.success:
            logger.error("Error deriving base commit: %s", derive_response.error)
            return StepResult.fail(f"Error deriving base commit: {derive_response.error}")

        if derive_response.data is None:
            logger.error("Agent did not return base commit data")
            return StepResult.fail("Agent did not return base commit data")

        # Store plan data in context (plan field contains base_commit)
        context.data["plan_data"] = derive_response.data

        # Also store base_commit directly in context for convenience
        context.data["base_commit"] = derive_response.data.plan

        # Save artifact if artifact store is available
        if context.artifacts_enabled and context.artifact_store is not None:
            artifact = PlanArtifact(
                workflow_id=context.adw_id,
                plan_data=derive_response.data,
            )
            context.artifact_store.write_artifact(artifact)
            logger.debug("Saved review plan artifact for workflow %s", context.adw_id)

        # Build progress comment from parsed data
        parsed_data = derive_response.metadata.get("parsed_data", {})
        base_commit = parsed_data.get("base_commit", "")
        summary = parsed_data.get("summary", "")
        comment_text = (
            f"Review base commit derived: {base_commit}\n\n{summary}" if summary else base_commit
        )

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
