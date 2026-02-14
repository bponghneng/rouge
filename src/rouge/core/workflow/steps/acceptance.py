"""Acceptance validation step implementation."""

import logging
from typing import Optional

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.workflow.artifacts import AcceptanceArtifact, PlanArtifact
from rouge.core.workflow.shared import AGENT_VALIDATOR
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult

logger = logging.getLogger(__name__)

# Required fields for acceptance validation output JSON
ACCEPTANCE_REQUIRED_FIELDS = {
    "output": str,
    "notes": list,
    "plan_title": str,
    "requirements": list,
    "status": str,
    "summary": str,
    "unmet_blocking_requirements": list,
}

ACCEPTANCE_JSON_SCHEMA = """{
  "type": "object",
  "properties": {
    "output": { "type": "string" },
    "notes": { "type": "array", "items": { "type": "string" } },
    "plan_title": { "type": "string" },
    "requirements": {
      "type": "array",
      "items": {
        "required": ["id", "section", "description", "status", "blocking", "evidence"],
        "properties": {
          "id": { "type": "string" },
          "section": { "type": "string" },
          "description": { "type": "string" },
          "status": { "type": "string", "enum": ["met", "not_met", "unknown"] },
          "blocking": { "type": "boolean" },
          "evidence": { "type": "string" }
        }
      }
    },
    "status": { "type": "string", "enum": ["pass", "fail", "partial"] },
    "summary": { "type": "string" },
    "unmet_blocking_requirements": {
      "type": "array",
      "items": { "type": "string" }
    }
  },
  "required": [
    "output",
    "notes",
    "plan_title",
    "requirements",
    "status",
    "summary",
    "unmet_blocking_requirements"
  ]
}"""


class AcceptanceStep(WorkflowStep):
    """Validate plan acceptance."""

    @property
    def name(self) -> str:
        return "Validating plan acceptance"

    @property
    def is_critical(self) -> bool:
        # Acceptance validation is not critical - workflow continues on failure
        return False

    def _notify_plan_acceptance(
        self,
        plan_content: str,
        issue_id: int,
        adw_id: str,
    ) -> StepResult[None]:
        """Validate implementation against plan content.

        Args:
            plan_content: The plan content (markdown) to validate against
            issue_id: Rouge issue ID for tracking
            adw_id: Workflow ID for tracking

        Returns:
            StepResult with None data (success/failure only)
        """
        try:
            if not plan_content:
                logger.error("Plan content is empty")
                return StepResult.fail("Plan content is empty")

            logger.debug("Invoking /adw-acceptance template with plan content")

            # Create template request with plan content as argument
            request = ClaudeAgentTemplateRequest(
                agent_name=AGENT_VALIDATOR,
                slash_command="/adw-acceptance",
                args=[plan_content],
                adw_id=adw_id,
                issue_id=issue_id,
                model="sonnet",
                json_schema=ACCEPTANCE_JSON_SCHEMA,
            )

            logger.debug(
                "notify_plan_acceptance request: %s",
                request.model_dump_json(indent=2, by_alias=True),
            )

            # Execute template
            response = execute_template(request)

            logger.debug(
                "notify_plan_acceptance response: success=%s",
                response.success,
            )

            if not response.success:
                logger.error("Failed to execute /adw-acceptance template: %s", response.output)
                return StepResult.fail(
                    f"Failed to execute /adw-acceptance template: {response.output}"
                )

            # Parse and validate JSON output
            parse_result = parse_and_validate_json(
                response.output, ACCEPTANCE_REQUIRED_FIELDS, step_name="acceptance"
            )
            if not parse_result.success:
                return StepResult.fail(parse_result.error or "JSON parsing failed")

            return StepResult.ok(None, parsed_data=parse_result.data)

        except Exception as e:
            logger.error("Failed to notify plan acceptance template: %s", e)
            return StepResult.fail(f"Failed to notify plan acceptance template: {e}")

    def _load_plan_text(self, context: WorkflowContext) -> Optional[str]:
        """Load plan text from the plan artifact.

        Both main and patch workflows now store their plans as PlanArtifact,
        so a single lookup is sufficient.

        Args:
            context: Workflow context with artifact store

        Returns:
            Plan text string, or None if no plan artifact is available
        """
        plan_data = context.load_artifact_if_missing(
            "plan_data",
            "plan",
            PlanArtifact,
            lambda a: a.plan_data,
        )

        if plan_data is not None:
            logger.info("Using plan for acceptance validation")
            return plan_data.plan

        return None

    def run(self, context: WorkflowContext) -> StepResult:
        """Validate implementation against plan.

        Args:
            context: Workflow context with plan or patch_plan artifact

        Returns:
            StepResult with success status and optional error message
        """
        # Try to load plan content - prefer patch_plan over plan
        plan_text = self._load_plan_text(context)

        if plan_text is None:
            logger.warning("No plan or patch_plan available for acceptance validation")
            return StepResult.fail("No plan or patch_plan available for acceptance validation")

        try:
            issue_id = context.require_issue_id
        except RuntimeError as e:
            logger.error("Missing issue_id: %s", e)
            return StepResult.fail(str(e))

        acceptance_result = self._notify_plan_acceptance(
            plan_text,
            issue_id,
            context.adw_id,
        )

        if not acceptance_result.success:
            logger.error("Failed to validate plan acceptance: %s", acceptance_result.error)
            # Save artifact even on failure
            if context.artifacts_enabled and context.artifact_store is not None:
                artifact = AcceptanceArtifact(
                    workflow_id=context.adw_id,
                    success=False,
                    message=acceptance_result.error,
                )
                context.artifact_store.write_artifact(artifact)
            return StepResult.fail(f"Failed to validate plan acceptance: {acceptance_result.error}")

        logger.info("Plan acceptance validated successfully")

        # Save artifact if artifact store is available
        if context.artifacts_enabled and context.artifact_store is not None:
            artifact = AcceptanceArtifact(
                workflow_id=context.adw_id,
                success=True,
                message="Plan acceptance validated successfully",
            )
            context.artifact_store.write_artifact(artifact)
            logger.debug("Saved acceptance artifact for workflow %s", context.adw_id)

        # Insert progress comment - best-effort, non-blocking
        payload = CommentPayload(
            issue_id=context.require_issue_id,
            adw_id=context.adw_id,
            text="Plan acceptance validation completed",
            raw={"text": "Plan acceptance validation completed."},
            source="system",
            kind="workflow",
        )
        status, msg = emit_comment_from_payload(payload)
        if status == "success":
            logger.debug(msg)
        else:
            logger.error(msg)

        return StepResult.ok(None)


# Backwards compatibility alias
ValidateAcceptanceStep = AcceptanceStep
