"""Plan building and file discovery step implementations."""

from cape.core.notifications import make_progress_comment_handler
from cape.core.workflow.plan import build_plan
from cape.core.workflow.plan_file import get_plan_file
from cape.core.workflow.step_base import WorkflowContext, WorkflowStep
from cape.core.workflow.types import ClassifyData
from cape.core.workflow.workflow_io import emit_progress_comment


class BuildPlanStep(WorkflowStep):
    """Build implementation plan for the issue."""

    @property
    def name(self) -> str:
        return "Building implementation plan"

    def run(self, context: WorkflowContext) -> bool:
        """Build implementation plan and store in context.

        Args:
            context: Workflow context with classify_data

        Returns:
            True if plan built successfully, False otherwise
        """
        logger = context.logger
        issue = context.issue

        if issue is None:
            logger.error("Cannot build plan: issue not fetched")
            return False

        classify_data: ClassifyData | None = context.data.get("classify_data")
        if classify_data is None:
            logger.error("Cannot build plan: classify_data not available")
            return False

        plan_handler = make_progress_comment_handler(issue.id, context.adw_id, logger)
        plan_response = build_plan(
            issue, classify_data.command, context.adw_id, logger, stream_handler=plan_handler
        )

        if not plan_response.success:
            logger.error(f"Error building plan: {plan_response.error}")
            return False

        logger.info(f"Implementation plan created:\n\n{plan_response}")

        # Store plan data in context
        context.data["plan_data"] = plan_response.data

        # Insert progress comment - best-effort, non-blocking
        emit_progress_comment(
            issue.id,
            "Implementation plan created successfully",
            logger,
            raw={"text": "Implementation plan created successfully."},
        )

        return True


class FindPlanFileStep(WorkflowStep):
    """Find the plan file path from plan output."""

    @property
    def name(self) -> str:
        return "Finding plan file"

    def run(self, context: WorkflowContext) -> bool:
        """Find plan file path and store in context.

        Args:
            context: Workflow context with plan_data

        Returns:
            True if plan file found, False otherwise
        """
        logger = context.logger
        plan_data = context.data.get("plan_data")

        if plan_data is None:
            logger.error("Cannot find plan file: plan_data not available")
            return False

        plan_file_result = get_plan_file(plan_data.output, context.issue_id, context.adw_id, logger)

        if not plan_file_result.success:
            logger.error(f"Error finding plan file: {plan_file_result.error}")
            return False

        if plan_file_result.data is None:
            logger.error("Plan file data missing despite successful response")
            return False

        plan_file_path = plan_file_result.data.file_path
        logger.info(f"Plan file created: {plan_file_path}")

        # Store plan file path in context
        context.data["plan_file"] = plan_file_path

        return True
