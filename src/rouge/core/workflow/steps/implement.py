"""Implementation step implementations."""

import logging

from rouge.core.workflow.artifacts import (
    ImplementationArtifact,
    PlanArtifact,
)
from rouge.core.workflow.implement import implement_plan
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult
from rouge.core.workflow.workflow_io import emit_progress_comment

logger = logging.getLogger(__name__)


class ImplementStep(WorkflowStep):
    """Execute implementation of the plan."""

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
        # Load plan content from artifact
        plan_data = context.load_artifact_if_missing(
            "plan_data",
            "plan",
            PlanArtifact,
            lambda a: a.plan_data,
        )

        if plan_data is None:
            logger.error("Cannot implement: plan not available")
            return StepResult.fail("Cannot implement: plan not available")

        implement_response = implement_plan(plan_data.plan, context.issue_id, context.adw_id)

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
        emit_progress_comment(
            context.issue_id,
            "Implementation complete.",
            raw={"text": "Implementation complete."},
            adw_id=context.adw_id,
        )

        return StepResult.ok(None)
