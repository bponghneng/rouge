"""Pipeline orchestrator for workflow execution."""

import os
from typing import Dict, List, Optional

from rouge.core.utils import get_logger
from rouge.core.workflow.artifacts import ArtifactStore
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.workflow_io import log_step_end, log_step_start


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
        resume_from: Optional[str] = None,
        pipeline_type: str = "main",
    ) -> bool:
        """Execute all workflow steps in sequence.

        Args:
            issue_id: The Rouge issue ID to process
            adw_id: Workflow ID for tracking
            resume_from: Optional step name to resume workflow execution from
            pipeline_type: The type of pipeline being executed (default: "main")

        Returns:
            True if workflow completed successfully, False if a critical step failed
        """
        logger = get_logger(adw_id)

        # Create artifact store unconditionally
        artifact_store = ArtifactStore(adw_id)
        logger.debug("Artifact persistence enabled at %s", artifact_store.workflow_dir)

        context = WorkflowContext(
            issue_id=issue_id,
            adw_id=adw_id,
            artifact_store=artifact_store,
            resume_from=resume_from,
            pipeline_type=pipeline_type,
        )

        logger.info("ADW ID: %s", adw_id)
        logger.info("Processing issue ID: %s", issue_id)

        # Build index for fast step-name -> position lookup
        step_name_to_index: Dict[str, int] = {s.name: i for i, s in enumerate(self._steps)}
        rerun_counts: Dict[str, int] = {}
        step_index = 0

        # Handle resume: skip all steps before the resume target
        if resume_from is not None:
            if resume_from in step_name_to_index:
                step_index = step_name_to_index[resume_from]
                logger.info("Resuming workflow from step '%s' (index %d)", resume_from, step_index)
            else:
                logger.warning(
                    "Resume target step '%s' not found in pipeline, starting from beginning",
                    resume_from,
                )

        # Track the name of the last successfully completed step
        last_completed_step: Optional[str] = None

        while step_index < len(self._steps):
            step = self._steps[step_index]
            log_step_start(step.name, adw_id, issue_id=issue_id)

            result = step.run(context)

            if not result.success:
                if step.is_critical:
                    log_step_end(step.name, result.success, adw_id, issue_id=issue_id)
                    error_msg = f"Critical step '{step.name}' failed"
                    if result.error:
                        error_msg += f": {result.error}"
                    logger.error("%s, aborting workflow", error_msg)

                    # Best-effort write of WorkflowStateArtifact on critical failure
                    self._write_workflow_state(
                        artifact_store,
                        adw_id,
                        last_completed_step=last_completed_step,
                        failed_step=step.name,
                        pipeline_type=pipeline_type,
                    )

                    return False
                else:
                    warning_msg = f"Best-effort step '{step.name}' failed"
                    if result.error:
                        warning_msg += f": {result.error}"
                    logger.warning("%s, continuing", warning_msg)
            else:
                log_step_end(step.name, result.success, adw_id, issue_id=issue_id)

                # Update last completed step and write WorkflowStateArtifact (best-effort)
                last_completed_step = step.name
                self._write_workflow_state(
                    artifact_store,
                    adw_id,
                    last_completed_step=last_completed_step,
                    failed_step=None,
                    pipeline_type=pipeline_type,
                )

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

    def _write_workflow_state(
        self,
        artifact_store: ArtifactStore,
        workflow_id: str,
        last_completed_step: Optional[str],
        failed_step: Optional[str],
        pipeline_type: str,
    ) -> None:
        """Write WorkflowStateArtifact in a best-effort manner.

        This method ensures artifact writes never halt the pipeline. Write
        failures are logged at WARNING level but do not raise exceptions.

        Args:
            artifact_store: The artifact store to write to
            workflow_id: The workflow ID
            last_completed_step: Name of the last successfully completed step (or None)
            failed_step: Name of the step that failed (or None)
            pipeline_type: The type of pipeline being executed
        """
        logger = get_logger(workflow_id)
        try:
            from rouge.core.workflow.artifacts import WorkflowStateArtifact

            state_artifact = WorkflowStateArtifact(
                workflow_id=workflow_id,
                last_completed_step=last_completed_step,
                failed_step=failed_step,
                pipeline_type=pipeline_type,
            )
            artifact_store.write_artifact(state_artifact)
            logger.debug(
                "Wrote workflow state: last_completed=%s, failed=%s, type=%s",
                last_completed_step,
                failed_step,
                pipeline_type,
            )
        except Exception as e:
            logger.warning(
                "Failed to write WorkflowStateArtifact (best-effort): %s",
                e,
                exc_info=True,
            )

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
        logger = get_logger(adw_id)

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

        log_step_start(target_step.name, adw_id, issue_id=issue_id)
        result = target_step.run(context)
        log_step_end(target_step.name, result.success, adw_id, issue_id=issue_id)

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
    - "github": includes GhPullRequestStep
    - "gitlab": includes GlabPullRequestStep
    - unset or other value: no PR/MR step included

    Returns:
        List of WorkflowStep instances in execution order
    """
    # Import here to avoid circular imports
    from rouge.core.workflow.steps.acceptance_step import AcceptanceStep
    from rouge.core.workflow.steps.classify_step import ClassifyStep
    from rouge.core.workflow.steps.code_quality_step import CodeQualityStep
    from rouge.core.workflow.steps.code_review_step import CodeReviewStep
    from rouge.core.workflow.steps.compose_request_step import ComposeRequestStep
    from rouge.core.workflow.steps.fetch_issue_step import FetchIssueStep
    from rouge.core.workflow.steps.gh_pull_request_step import (
        GhPullRequestStep,
    )
    from rouge.core.workflow.steps.git_branch_step import GitBranchStep
    from rouge.core.workflow.steps.glab_pull_request_step import (
        GlabPullRequestStep,
    )
    from rouge.core.workflow.steps.implement_step import ImplementStep
    from rouge.core.workflow.steps.plan_step import PlanStep
    from rouge.core.workflow.steps.review_fix_step import ReviewFixStep

    steps: List[WorkflowStep] = [
        FetchIssueStep(),
        GitBranchStep(),
        ClassifyStep(),
        PlanStep(),
        ImplementStep(plan_step_name="Building implementation plan"),
        CodeReviewStep(),
        ReviewFixStep(),
        CodeQualityStep(),
        AcceptanceStep(),
        ComposeRequestStep(),
    ]

    # Conditionally add PR/MR creation step based on platform
    platform = os.environ.get("DEV_SEC_OPS_PLATFORM", "").lower()
    if platform == "github":
        steps.append(GhPullRequestStep())
    elif platform == "gitlab":
        steps.append(GlabPullRequestStep())

    return steps


def get_code_review_pipeline() -> List[WorkflowStep]:
    """Create the codereview workflow pipeline.

    The codereview workflow runs an automated review loop on repository changes
    based on an existing issue. This is now an issue-based workflow that requires
    an issue_id to be provided.

    Pipeline sequence:
    1. FetchIssueStep    - Fetch the issue from the database
    2. GitCheckoutStep   — Check out the branch stored on the issue
    3. ReviewPlanStep    - Generate a review plan from the issue
    4. CodeReviewStep    - Generate review of the current changes
    5. ReviewFixStep     - Address any review feedback
    6. CodeQualityStep   - Run code quality checks
    7. ComposeCommitsStep - Compose conventional commits from the changes

    Returns:
        List of WorkflowStep instances in execution order
    """
    # Import here to avoid circular imports
    from rouge.core.workflow.steps.code_quality_step import CodeQualityStep
    from rouge.core.workflow.steps.code_review_step import CodeReviewStep
    from rouge.core.workflow.steps.compose_commits_step import ComposeCommitsStep
    from rouge.core.workflow.steps.fetch_issue_step import FetchIssueStep
    from rouge.core.workflow.steps.git_checkout_step import GitCheckoutStep
    from rouge.core.workflow.steps.review_fix_step import ReviewFixStep
    from rouge.core.workflow.steps.review_plan_step import ReviewPlanStep

    return [
        FetchIssueStep(),
        GitCheckoutStep(),
        ReviewPlanStep(),
        CodeReviewStep(),
        ReviewFixStep(),
        CodeQualityStep(),
        ComposeCommitsStep(),
    ]


def get_patch_pipeline() -> List[WorkflowStep]:
    """Create the patch workflow pipeline.

    The patch workflow is a fully decoupled pipeline designed to process patch
    issues independently. Each patch workflow receives its own unique ADW ID and
    operates in a separate artifact directory, without accessing or depending on
    any parent workflow's artifacts.

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
    - ClassifyStep is NOT needed: The patch issue description is self-contained
    - PR/MR creation steps are NOT needed: Patch commits are pushed to the
      existing branch and the associated PR/MR updates automatically

    Each patch workflow has a unique ADW ID and its own artifact directory. All
    steps read and write artifacts within this directory; no artifacts are loaded
    from any parent or prior workflow.

    The patch workflow sequence is:
    1. FetchPatchStep - Fetch the patch issue from the database; writes PatchArtifact
    2. BuildPatchPlanStep - Build a standalone plan from the patch issue description;
       writes a standard PlanArtifact (no parent issue or plan is referenced)
    3. ImplementStep - Implement the plan by loading PlanArtifact from the current
       patch workflow's artifact directory
    4. CodeReviewStep - Generate review of the implementation
    5. ReviewFixStep - Address any review feedback
    6. CodeQualityStep - Run code quality checks
    7. AcceptanceStep - Validate patch meets acceptance criteria
    8. UpdatePRCommitsStep - Push commits to the existing PR/MR branch; detects the
       PR/MR via git CLI tools (gh/glab) rather than loading parent artifacts

    Returns:
        List of WorkflowStep instances in execution order for patch processing
    """
    # Import here to avoid circular imports
    from rouge.core.workflow.steps.acceptance_step import AcceptanceStep
    from rouge.core.workflow.steps.code_quality_step import CodeQualityStep
    from rouge.core.workflow.steps.code_review_step import CodeReviewStep
    from rouge.core.workflow.steps.compose_commits_step import ComposeCommitsStep
    from rouge.core.workflow.steps.fetch_patch_step import FetchPatchStep
    from rouge.core.workflow.steps.git_checkout_step import GitCheckoutStep
    from rouge.core.workflow.steps.implement_step import ImplementStep
    from rouge.core.workflow.steps.patch_plan_step import PatchPlanStep
    from rouge.core.workflow.steps.review_fix_step import ReviewFixStep

    steps: List[WorkflowStep] = [
        FetchPatchStep(),
        GitCheckoutStep(),
        PatchPlanStep(),
        ImplementStep(plan_step_name="Building patch plan"),
        CodeReviewStep(),
        ReviewFixStep(),
        CodeQualityStep(),
        AcceptanceStep(),
        ComposeCommitsStep(),
    ]

    return steps
