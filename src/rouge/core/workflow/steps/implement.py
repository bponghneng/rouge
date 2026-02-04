"""Implementation step."""

import logging

from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.workflow.artifacts import (
    ImplementationArtifact,
    PlanArtifact,
)
from rouge.core.workflow.implement import implement_plan
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult

logger = logging.getLogger(__name__)


class ImplementStep(WorkflowStep):
    """Execute implementation of the plan."""

    def __init__(self, plan_step_name: str | None = None):
        """Initialize ImplementStep.

        Args:
            plan_step_name: Name of the preceding plan step for rerun messages.
                Defaults to "Building implementation plan" when not provided.
        """
        self.plan_step_name = plan_step_name or "Building implementation plan"

    @property
    def name(self) -> str:
        return "Implementing solution"

    def run(self, context: WorkflowContext) -> StepResult:
        """Implement the plan and store result in context.

        Args:
            context: Workflow context with plan artifact

        Returns:
            StepResult with success status and optional error message
        """
        # Load plan from current workflow artifacts
        plan_data = context.load_artifact_if_missing(
            "plan_data",
            "plan",
            PlanArtifact,
            lambda a: a.plan_data,
        )
        plan_text = plan_data.plan if plan_data is not None else None

        if plan_text is None:
            logger.error("Cannot implement: no plan available")
            return StepResult.fail(
                "Cannot implement: no plan available",
                rerun_from=self.plan_step_name,
            )

        implement_response = implement_plan(plan_text, context.require_issue_id, context.adw_id)

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

        # Save artifact if artifact store is available
        if context.artifacts_enabled and context.artifact_store is not None:
            artifact = ImplementationArtifact(
                workflow_id=context.adw_id,
                implement_data=implement_response.data,
            )
            context.artifact_store.write_artifact(artifact)
            logger.debug("Saved implementation artifact for workflow %s", context.adw_id)

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
