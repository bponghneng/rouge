"""Pipeline orchestrator for workflow execution."""

import logging
import os
from typing import Dict, List, Optional

from rouge.core.workflow.artifacts import ArtifactStore
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.workflow_io import log_step_end, log_step_start

logger = logging.getLogger(__name__)


class WorkflowRunner:
    """Orchestrates execution of workflow steps in sequence.

    Runs steps linearly, stopping on critical step failures and
    continuing past best-effort step failures.  Steps may request a
    rerun by setting ``result.rerun_from`` to the name of an earlier
    step; the runner will rewind to that step up to ``max_step_reruns``
    times before forcing forward progress.
    """

    max_step_reruns: int = 5

    def __init__(self, steps: List[WorkflowStep]) -> None:
        """Initialize the runner with a list of steps.

        Args:
            steps: Ordered list of workflow steps to execute
        """
        self._steps = steps

    def run(
        self,
        issue_id: int,
        adw_id: str,
    ) -> bool:
        """Execute all workflow steps in sequence.

        Args:
            issue_id: The Rouge issue ID to process
            adw_id: Workflow ID for tracking

        Returns:
            True if workflow completed successfully, False if a critical step failed
        """
        # Create artifact store unconditionally
        artifact_store = ArtifactStore(adw_id)
        logger.debug("Artifact persistence enabled at %s", artifact_store.workflow_dir)

        context = WorkflowContext(
            issue_id=issue_id,
            adw_id=adw_id,
            artifact_store=artifact_store,
        )

        logger.info("ADW ID: %s", adw_id)
        logger.info("Processing issue ID: %s", issue_id)

        # Build index for fast step-name -> position lookup
        step_name_to_index: Dict[str, int] = {s.name: i for i, s in enumerate(self._steps)}
        rerun_counts: Dict[str, int] = {}
        step_index = 0

        while step_index < len(self._steps):
            step = self._steps[step_index]
            log_step_start(step.name, issue_id=issue_id)

            result = step.run(context)

            if not result.success:
                if step.is_critical:
                    log_step_end(step.name, result.success, issue_id=issue_id)
                    error_msg = f"Critical step '{step.name}' failed"
                    if result.error:
                        error_msg += f": {result.error}"
                    logger.error("%s, aborting workflow", error_msg)
                    return False
                else:
                    warning_msg = f"Best-effort step '{step.name}' failed"
                    if result.error:
                        warning_msg += f": {result.error}"
                    logger.warning("%s, continuing", warning_msg)
            else:
                log_step_end(step.name, result.success, issue_id=issue_id)

            # Handle rerun requests
            if result.rerun_from is not None:
                target = result.rerun_from
                count = rerun_counts.get(target, 0)
                if count < self.max_step_reruns:
                    if target not in step_name_to_index:
                        logger.warning(
                            "Rerun requested for unknown step '%s', ignoring",
                            target,
                        )
                    else:
                        rerun_counts[target] = count + 1
                        logger.info(
                            "Rerun requested: rewinding to step '%s' (attempt %d/%d)",
                            target,
                            rerun_counts[target],
                            self.max_step_reruns,
                        )
                        step_index = step_name_to_index[target]
                        continue
                else:
                    logger.warning(
                        "Max reruns (%d) reached for step '%s', continuing to next step",
                        self.max_step_reruns,
                        target,
                    )

            step_index += 1

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

        logger.info("ADW ID: %s", adw_id)
        logger.info("Running single step '%s' for issue ID: %s", step_name, issue_id)

        log_step_start(target_step.name, issue_id=issue_id)
        result = target_step.run(context)
        log_step_end(target_step.name, result.success, issue_id=issue_id)

        if not result.success:
            error_msg = f"Step '{step_name}' failed"
            if result.error:
                error_msg += f": {result.error}"
            logger.error(error_msg)
            return False

        logger.info("Step '%s' completed successfully", step_name)
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
    from rouge.core.workflow.steps.implement import ImplementStep
    from rouge.core.workflow.steps.plan import BuildPlanStep
    from rouge.core.workflow.steps.pr import PreparePullRequestStep
    from rouge.core.workflow.steps.quality import CodeQualityStep
    from rouge.core.workflow.steps.review import AddressReviewStep, GenerateReviewStep
    from rouge.core.workflow.steps.setup import SetupStep

    steps: List[WorkflowStep] = [
        SetupStep(),
        FetchIssueStep(),
        ClassifyStep(),
        BuildPlanStep(),
        ImplementStep(),
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


def get_code_review_pipeline() -> List[WorkflowStep]:
    """Create the codereview workflow pipeline.

    The codereview workflow runs an automated review loop on commits.
    Note: This workflow can run with or without an issue_id. When issue_id
    is provided, GenerateReviewStep and AddressReviewStep will emit progress
    comments via emit_comment_from_payload. When issue_id is None, these
    steps will skip comment emission but still execute review generation and
    addressing logic.

    Pipeline sequence:
    1. GenerateReviewStep  - Generate review of the current changes
    2. AddressReviewStep   - Address any review feedback
    3. CodeQualityStep     - Run code quality checks

    Returns:
        List of WorkflowStep instances in execution order
    """
    # Import here to avoid circular imports
    from rouge.core.workflow.steps.quality import CodeQualityStep
    from rouge.core.workflow.steps.review import AddressReviewStep, GenerateReviewStep

    return [
        GenerateReviewStep(),
        AddressReviewStep(),
        CodeQualityStep(),
    ]


def get_patch_pipeline() -> List[WorkflowStep]:
    """Create the patch workflow pipeline.

    The patch workflow is a subset of the default workflow, designed to process
    patches against an existing issue that has already been through the main
    workflow.

    Routing:
    --------
    Worker routing uses the `issues.type` column to determine which pipeline to run:
    - `type='main'`: Routes to the default pipeline (get_default_pipeline)
    - `type='patch'`: Routes to this patch pipeline

    Patch workflows are represented as issue rows with `type='patch'` rather than
    as separate patch table entries. This type-based routing replaced the previous
    status-based routing (which used 'pending' vs 'patch pending' statuses).

    Assumptions:
    - SetupStep is NOT needed: The repository is already set up from the main workflow
    - ClassifyStep is NOT needed: The classification exists in parent workflow artifacts
    - PR/MR creation steps are NOT needed: Patch commits will be added to the
      existing PR/MR created by the main workflow

    The patch workflow sequence is:
    1. FetchPatchStep - Fetch patch data; writes PatchArtifact only
    2. BuildPatchPlanStep - Build a plan specific to the patch changes
    3. ImplementStep - Implement using patch_plan (or fall back to plan from parent)
    4. GenerateReviewStep - Generate review of the implementation
    5. AddressReviewStep - Address any review feedback
    6. CodeQualityStep - Run code quality checks
    7. ValidateAcceptanceStep - Validate patch meets acceptance criteria
    8. UpdatePRCommitsStep - Update existing PR with new commits (fails if no PR)

    Returns:
        List of WorkflowStep instances in execution order for patch processing
    """
    # Import here to avoid circular imports
    from rouge.core.workflow.steps.acceptance import ValidateAcceptanceStep
    from rouge.core.workflow.steps.fetch_patch import FetchPatchStep
    from rouge.core.workflow.steps.implement import ImplementStep
    from rouge.core.workflow.steps.patch_plan import BuildPatchPlanStep
    from rouge.core.workflow.steps.quality import CodeQualityStep
    from rouge.core.workflow.steps.review import AddressReviewStep, GenerateReviewStep
    from rouge.core.workflow.steps.update_pr_commits import UpdatePRCommitsStep

    steps: List[WorkflowStep] = [
        FetchPatchStep(),
        BuildPatchPlanStep(),
        ImplementStep(),
        GenerateReviewStep(),
        AddressReviewStep(),
        CodeQualityStep(),
        ValidateAcceptanceStep(),
        UpdatePRCommitsStep(),
    ]

    return steps
