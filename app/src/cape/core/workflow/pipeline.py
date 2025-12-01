"""Pipeline orchestrator for workflow execution."""

from logging import Logger
from typing import List

from cape.core.workflow.step_base import WorkflowContext, WorkflowStep
from cape.core.workflow.workflow_io import log_step_end, log_step_start


class WorkflowRunner:
    """Orchestrates execution of workflow steps in sequence.

    Runs steps linearly, stopping on critical step failures and
    continuing past best-effort step failures.
    """

    def __init__(self, steps: List[WorkflowStep]) -> None:
        """Initialize the runner with a list of steps.

        Args:
            steps: Ordered list of workflow steps to execute
        """
        self._steps = steps

    def run(self, issue_id: int, adw_id: str, logger: Logger) -> bool:
        """Execute all workflow steps in sequence.

        Args:
            issue_id: The Cape issue ID to process
            adw_id: Workflow ID for tracking
            logger: Logger instance

        Returns:
            True if workflow completed successfully, False if a critical step failed
        """
        context = WorkflowContext(
            issue_id=issue_id,
            adw_id=adw_id,
            logger=logger,
        )

        logger.info(f"ADW ID: {adw_id}")
        logger.info(f"Processing issue ID: {issue_id}")

        for step in self._steps:
            log_step_start(step.name, logger)

            success = step.run(context)

            if not success:
                if step.is_critical:
                    log_step_end(step.name, success, logger)
                    logger.error(f"Critical step '{step.name}' failed, aborting workflow")
                    return False
                else:
                    logger.warning(f"Best-effort step '{step.name}' failed, continuing")
            else:
                log_step_end(step.name, success, logger)

        logger.info("\n=== Workflow completed successfully ===")
        return True


def get_default_pipeline() -> List[WorkflowStep]:
    """Create the default workflow pipeline with all 11 steps.

    Returns:
        List of WorkflowStep instances in execution order
    """
    # Import here to avoid circular imports
    from cape.core.workflow.steps.acceptance import ValidateAcceptanceStep
    from cape.core.workflow.steps.classify import ClassifyStep
    from cape.core.workflow.steps.fetch import FetchIssueStep
    from cape.core.workflow.steps.implement import FindImplementedPlanStep, ImplementStep
    from cape.core.workflow.steps.plan import BuildPlanStep, FindPlanFileStep
    from cape.core.workflow.steps.pr import PreparePullRequestStep
    from cape.core.workflow.steps.quality import CodeQualityStep
    from cape.core.workflow.steps.review import AddressReviewStep, GenerateReviewStep

    return [
        FetchIssueStep(),
        ClassifyStep(),
        BuildPlanStep(),
        FindPlanFileStep(),
        ImplementStep(),
        FindImplementedPlanStep(),
        GenerateReviewStep(),
        AddressReviewStep(),
        CodeQualityStep(),
        ValidateAcceptanceStep(),
        PreparePullRequestStep(),
    ]
