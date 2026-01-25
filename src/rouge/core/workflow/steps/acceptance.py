"""Acceptance validation step implementation."""

import logging

from rouge.core.notifications.agent_stream_handlers import make_progress_comment_handler
from rouge.core.workflow.acceptance import notify_plan_acceptance
from rouge.core.workflow.artifacts import AcceptanceArtifact, PlanArtifact
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult
from rouge.core.workflow.workflow_io import emit_progress_comment

logger = logging.getLogger(__name__)


class ValidateAcceptanceStep(WorkflowStep):
    """Validate plan acceptance."""

    @property
    def name(self) -> str:
        return "Validating plan acceptance"

    @property
    def is_critical(self) -> bool:
        # Acceptance validation is not critical - workflow continues on failure
        return False

    def run(self, context: WorkflowContext) -> StepResult:
        """Validate implementation against plan.

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
            logger.warning("No plan available for acceptance validation")
            return StepResult.fail("No plan available for acceptance validation")

        acceptance_handler = make_progress_comment_handler(context.issue_id, context.adw_id)
        acceptance_result = notify_plan_acceptance(
            plan_data.plan,
            context.issue_id,
            context.adw_id,
            stream_handler=acceptance_handler,
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
        emit_progress_comment(
            context.issue_id,
            "Plan acceptance validation completed",
            raw={"text": "Plan acceptance validation completed."},
            adw_id=context.adw_id,
        )

        return StepResult.ok(None)
