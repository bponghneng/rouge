"""Pipeline orchestrator for workflow execution."""

import logging
import os
from typing import List, Optional

from rouge.core.workflow.artifacts import ArtifactStore
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.workflow_io import log_step_end, log_step_start

logger = logging.getLogger(__name__)


class WorkflowRunner:
    """Orchestrates execution of workflow steps in sequence.

    Runs steps linearly, stopping on critical step failures and
    continuing past best-effort step failures.
    """

    def __init__(self, steps: List[WorkflowStep], enable_artifacts: bool = False) -> None:
        """Initialize the runner with a list of steps.

        Args:
            steps: Ordered list of workflow steps to execute
            enable_artifacts: Whether to enable artifact persistence
        """
        self._steps = steps
        self._enable_artifacts = enable_artifacts

    def run(self, issue_id: int, adw_id: str) -> bool:
        """Execute all workflow steps in sequence.

        Args:
            issue_id: The Rouge issue ID to process
            adw_id: Workflow ID for tracking

        Returns:
            True if workflow completed successfully, False if a critical step failed
        """
        # Create artifact store if enabled
        artifact_store: Optional[ArtifactStore] = None
        if self._enable_artifacts:
            artifact_store = ArtifactStore(adw_id)
            logger.debug("Artifact persistence enabled at %s", artifact_store.workflow_dir)

        context = WorkflowContext(
            issue_id=issue_id,
            adw_id=adw_id,
            artifact_store=artifact_store,
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

    def run_single_step(
        self,
        step_name: str,
        issue_id: int,
        adw_id: str,
        has_dependencies: bool = True,
    ) -> bool:
        """Execute a single step by name, using artifacts for dependencies.

        This method enables running individual steps independently by loading
        their dependencies from previously stored artifacts.

        Args:
            step_name: The name of the step to execute
            issue_id: The Rouge issue ID to process
            adw_id: Workflow ID for artifact persistence
            has_dependencies: Whether the step has dependencies (if False, skip artifact dir check)

        Returns:
            True if step completed successfully, False otherwise

        Raises:
            ValueError: If step_name is not found in the pipeline
        """
        # Find the step by name
        target_step: Optional[WorkflowStep] = None
        for step in self._steps:
            if step.name == step_name:
                target_step = step
                break

        if target_step is None:
            raise ValueError(f"Step not found: {step_name}")

        # Always enable artifacts for single-step execution
        artifact_store = ArtifactStore(adw_id)
        workflow_dir = artifact_store.workflow_dir

        # For steps with dependencies, ensure the workflow directory exists with artifacts
        # For dependency-free steps, skip this check (artifacts will be created by this step)
        if has_dependencies:
            if not os.path.isdir(workflow_dir) or not os.listdir(workflow_dir):
                logger.error(
                    "Workflow directory '%s' does not exist or contains no artifacts. "
                    "Run the full workflow or prior steps before executing this step.",
                    workflow_dir,
                )
                return False
            logger.debug("Single-step execution with artifacts at %s", workflow_dir)
        else:
            logger.debug("Dependency-free step execution, workflow dir: %s", workflow_dir)

        context = WorkflowContext(
            issue_id=issue_id,
            adw_id=adw_id,
            artifact_store=artifact_store,
        )

        logger.info(f"ADW ID: {adw_id}")
        logger.info(f"Running single step '{step_name}' for issue ID: {issue_id}")

        log_step_start(target_step.name, issue_id=issue_id)
        result = target_step.run(context)
        log_step_end(target_step.name, result.success, issue_id=issue_id)

        if not result.success:
            error_msg = f"Step '{step_name}' failed"
            if result.error:
                error_msg += f": {result.error}"
            logger.error(error_msg)
            return False

        logger.info(f"Step '{step_name}' completed successfully")
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
