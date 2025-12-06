"""Acceptance validation step implementation."""

from rouge.core.notifications import make_progress_comment_handler
from rouge.core.workflow.acceptance import notify_plan_acceptance
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult
from rouge.core.workflow.workflow_io import emit_progress_comment


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
            context: Workflow context with implemented_plan_file

        Returns:
            StepResult with success status and optional error message
        """
        logger = context.logger
        plan_path = context.data.get("implemented_plan_file", "")

        if not plan_path:
            logger.warning("No plan file available for acceptance validation")
            return StepResult.fail("No plan file available for acceptance validation")

        acceptance_handler = make_progress_comment_handler(context.issue_id, context.adw_id, logger)
        acceptance_result = notify_plan_acceptance(
            plan_path,
            context.issue_id,
            context.adw_id,
            logger,
            stream_handler=acceptance_handler,
        )

        if not acceptance_result.success:
            logger.error(f"Failed to validate plan acceptance: {acceptance_result.error}")
            return StepResult.fail(f"Failed to validate plan acceptance: {acceptance_result.error}")

        logger.info("Plan acceptance validated successfully")

        # Insert progress comment - best-effort, non-blocking
        emit_progress_comment(
            context.issue_id,
            "Plan acceptance validation completed",
            logger,
            raw={"text": "Plan acceptance validation completed."},
        )

        return StepResult.ok(None)
