"""Pipeline orchestrator for workflow execution."""

import logging
from typing import List

from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.workflow_io import log_step_end, log_step_start

logger = logging.getLogger(__name__)


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

    def run(self, issue_id: int, adw_id: str) -> bool:
        """Execute all workflow steps in sequence.

        Args:
            issue_id: The Rouge issue ID to process
            adw_id: Workflow ID for tracking

        Returns:
            True if workflow completed successfully, False if a critical step failed
        """
        context = WorkflowContext(
            issue_id=issue_id,
            adw_id=adw_id,
        )

        logger.info(f"ADW ID: {adw_id}")
        logger.info(f"Processing issue ID: {issue_id}")

        for step in self._steps:
            log_step_start(step.name, issue_id=issue_id)

            result = step.run(context)

            if not result.success:
                if step.is_critical:
                    log_step_end(step.name, result.success, issue_id=issue_id)
                    error_msg = f"Critical step '{step.name}' failed"
                    if result.error:
                        error_msg += f": {result.error}"
                    logger.error(f"{error_msg}, aborting workflow")
                    return False
                else:
                    warning_msg = f"Best-effort step '{step.name}' failed"
                    if result.error:
                        warning_msg += f": {result.error}"
                    logger.warning(f"{warning_msg}, continuing")
            else:
                log_step_end(step.name, result.success, issue_id=issue_id)

        logger.info("\n=== Workflow completed successfully ===")
        return True


def get_default_pipeline() -> List[WorkflowStep]:
    """Create the default workflow pipeline.

    The pipeline conditionally includes a PR/MR creation step based on the
    DEV_SEC_OPS_PLATFORM environment variable:
    - "github": includes CreateGitHubPullRequestStep
    - "gitlab": includes CreateGitLabPullRequestStep
    - unset or other value: no PR/MR step included

    Returns:
        List of WorkflowStep instances in execution order
    """
    # Import here to avoid circular imports
    from rouge.core.workflow.steps.acceptance import ValidateAcceptanceStep
    from rouge.core.workflow.steps.classify import ClassifyStep
    from rouge.core.workflow.steps.create_github_pr import CreateGitHubPullRequestStep
    from rouge.core.workflow.steps.create_gitlab_pr import CreateGitLabPullRequestStep
    from rouge.core.workflow.steps.fetch import FetchIssueStep
    from rouge.core.workflow.steps.find_plan_file import FindPlanFileStep
    from rouge.core.workflow.steps.implement import (
        FindImplementedPlanStep,
        ImplementStep,
    )
    from rouge.core.workflow.steps.plan import BuildPlanStep
    from rouge.core.workflow.steps.pr import PreparePullRequestStep
    from rouge.core.workflow.steps.quality import CodeQualityStep
    from rouge.core.workflow.steps.review import AddressReviewStep, GenerateReviewStep

    steps: List[WorkflowStep] = [
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

    # Conditionally add PR/MR creation step based on platform
    platform = os.environ.get("DEV_SEC_OPS_PLATFORM", "").lower()
    if platform == "github":
        steps.append(CreateGitHubPullRequestStep())
    elif platform == "gitlab":
        steps.append(CreateGitLabPullRequestStep())

    return steps
