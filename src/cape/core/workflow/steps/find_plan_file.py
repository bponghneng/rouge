"""Find plan file step implementation."""

from cape.core.workflow.plan_file import get_plan_file
from cape.core.workflow.step_base import WorkflowContext, WorkflowStep
from cape.core.workflow.types import StepResult


class FindPlanFileStep(WorkflowStep):
    """Find the plan file path from plan output."""

    @property
    def name(self) -> str:
        return "Finding plan file"

    def run(self, context: WorkflowContext) -> StepResult:
        """Find plan file path and store in context.

        Args:
            context: Workflow context with plan_data

        Returns:
            StepResult with success status and optional error message
        """
        logger = context.logger
        plan_data = context.data.get("plan_data")

        if plan_data is None:
            logger.error("Cannot find plan file: plan_data not available")
            return StepResult.fail("Cannot find plan file: plan_data not available")

        plan_file_result = get_plan_file(plan_data.output, context.issue_id, context.adw_id, logger)

        if not plan_file_result.success:
            logger.error(f"Error finding plan file: {plan_file_result.error}")
            return StepResult.fail(f"Error finding plan file: {plan_file_result.error}")

        if plan_file_result.data is None:
            logger.error("Plan file data missing despite successful response")
            return StepResult.fail("Plan file data missing despite successful response")

        plan_file_path = plan_file_result.data.file_path
        logger.info(f"Plan file created: {plan_file_path}")

        # Store plan file path in context
        context.data["plan_file"] = plan_file_path

        return StepResult.ok(None)
