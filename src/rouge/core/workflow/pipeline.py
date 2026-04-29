"""Pipeline orchestrator for workflow execution."""

import os
from typing import Dict, List, Optional

from rouge.core.utils import get_logger
from rouge.core.workflow.artifacts import ArtifactStore
from rouge.core.workflow.config import StepCondition, StepInvocation, WorkflowConfig
from rouge.core.workflow.config_resolver import resolve_workflow
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
        pipeline_type: str = "full",
    ) -> bool:
        """Execute all workflow steps in sequence.

        Args:
            issue_id: The Rouge issue ID to process
            adw_id: Workflow ID for tracking
            resume_from: Optional step name to resume workflow execution from
            pipeline_type: The type of pipeline being executed (default: "full")

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

        # Build indexes for fast lookup. ``step_id`` (if set) takes priority over
        # ``step.name`` for resume/rerun targets so declarative pipelines can use
        # stable identifiers; ``step.name`` remains as a fallback for steps that
        # do not declare a ``step_id``. Direct attribute access is safe because
        # ``WorkflowStep`` declares a class-level default ``step_id = None``, so
        # ``Mock(spec=WorkflowStep)`` exposes the attribute; we filter to ``str``
        # to exclude Mock proxy objects in tests that do not set step_id.
        step_id_to_index: Dict[str, int] = {
            sid: i for i, s in enumerate(self._steps) if isinstance(sid := s.step_id, str) and sid
        }
        step_name_to_index: Dict[str, int] = {s.name: i for i, s in enumerate(self._steps)}
        rerun_counts: Dict[str, int] = {}
        step_index = 0

        def _resolve_target(target: str) -> Optional[int]:
            """Resolve a resume/rerun target to a step index.

            Tries ``step_id`` first, then falls back to ``step.name``.
            """
            if target in step_id_to_index:
                return step_id_to_index[target]
            if target in step_name_to_index:
                return step_name_to_index[target]
            return None

        # Handle resume: skip all steps before the resume target
        if resume_from is not None:
            resolved = _resolve_target(resume_from)
            if resolved is not None:
                step_index = resolved
                logger.info("Resuming workflow from step '%s' (index %d)", resume_from, step_index)
            else:
                logger.warning(
                    "Resume target step '%s' not found in pipeline, starting from beginning",
                    resume_from,
                )

        # Track the name (and optional step_id) of the last successfully completed step
        last_completed_step: Optional[str] = None
        last_completed_step_id: Optional[str] = None

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
                        last_completed_step_id=last_completed_step_id,
                        failed_step=step.name,
                        pipeline_type=pipeline_type,
                    )

                    return False
                else:
                    log_step_end(step.name, result.success, adw_id, issue_id=issue_id)
                    warning_msg = f"Best-effort step '{step.name}' failed"
                    if result.error:
                        warning_msg += f": {result.error}"
                    logger.warning("%s, continuing", warning_msg)
            else:
                log_step_end(step.name, result.success, adw_id, issue_id=issue_id)

                # Update last completed step and write WorkflowStateArtifact (best-effort)
                last_completed_step = step.name
                _sid = step.step_id
                last_completed_step_id = _sid if isinstance(_sid, str) else None
                self._write_workflow_state(
                    artifact_store,
                    adw_id,
                    last_completed_step=last_completed_step,
                    last_completed_step_id=last_completed_step_id,
                    failed_step=None,
                    pipeline_type=pipeline_type,
                )

            # Handle rerun requests
            if result.rerun_from is not None:
                target = result.rerun_from
                count = rerun_counts.get(target, 0)
                if count < self.max_step_reruns:
                    resolved_index = _resolve_target(target)
                    if resolved_index is None:
                        valid_keys = sorted(
                            set(step_id_to_index.keys()) | set(step_name_to_index.keys())
                        )
                        logger.warning(
                            "Rerun requested for unknown step '%s'; ignoring. "
                            "Valid step IDs/names: %s",
                            target,
                            valid_keys,
                        )
                    else:
                        rerun_counts[target] = count + 1
                        logger.info(
                            "Rerun requested: rewinding to step '%s' (attempt %d/%d)",
                            target,
                            rerun_counts[target],
                            self.max_step_reruns,
                        )
                        step_index = resolved_index
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
        last_completed_step_id: Optional[str] = None,
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
            last_completed_step_id: Optional stable step_id of the last successfully
                completed step (or None when the step has no ``step_id`` set)
        """
        logger = get_logger(workflow_id)
        try:
            from rouge.core.workflow.artifacts import WorkflowStateArtifact

            state_artifact = WorkflowStateArtifact(
                workflow_id=workflow_id,
                last_completed_step=last_completed_step,
                last_completed_step_id=last_completed_step_id,
                failed_step=failed_step,
                pipeline_type=pipeline_type,
            )
            artifact_store.write_artifact(state_artifact)
            logger.debug(
                "Wrote workflow state: last_completed=%s, last_completed_id=%s, failed=%s, type=%s",
                last_completed_step,
                last_completed_step_id,
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

        # Find the step by step_id (stable slug, preferred) or by name (fallback).
        # Preferring step_id ensures single-step execution parity with the full
        # pipeline's resume/rerun resolution, which also tries step_id first.
        target_step: Optional[WorkflowStep] = None
        for step in self._steps:
            sid = step.step_id
            if (isinstance(sid, str) and sid == step_name) or step.name == step_name:
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


# ---------------------------------------------------------------------------
# Built-in workflow configurations
# ---------------------------------------------------------------------------
#
# Each ``WorkflowConfig`` below is the declarative analogue of one of the
# legacy ``get_*_pipeline`` functions. The resolver in
# ``config_resolver.resolve_workflow`` translates these configs into runnable
# step lists, including:
#
#   * Per-slug factory overrides (e.g. ``claude-code-plan`` -> ``PromptJsonStep``).
#   * Default settings injected for the three plan slugs, so invocation
#     ``settings`` can stay empty here.
#   * ``StepCondition`` evaluation for the GitHub / GitLab PR steps, replacing
#     the previous ``DEV_SEC_OPS_PLATFORM`` env-var branch in this module.
#     A ``when`` clause with no ``equals``/``in_`` test includes the step only
#     when the env var is **set and non-empty** (not just set to any value).

PATCH_WORKFLOW_CONFIG = WorkflowConfig(
    type_id="patch",
    description="Patch workflow pipeline",
    steps=[
        StepInvocation(id="fetch-patch"),
        StepInvocation(id="git-checkout"),
        StepInvocation(id="patch-plan", display_name="Building patch plan"),
        # ``plan_step_name`` is resolved from the preceding invocation's
        # ``display_name`` ("Building patch plan") — no settings block needed.
        StepInvocation(id="implement-plan"),
        StepInvocation(id="code-quality"),
        StepInvocation(id="compose-commits"),
    ],
)


THIN_WORKFLOW_CONFIG = WorkflowConfig(
    type_id="thin",
    description="Thin workflow pipeline for straightforward issues",
    steps=[
        StepInvocation(id="fetch-issue"),
        StepInvocation(id="git-branch"),
        StepInvocation(id="thin-plan", display_name="Building thin implementation plan"),
        # ``plan_step_name`` resolved from the preceding invocation's
        # ``display_name`` ("Building thin implementation plan").
        StepInvocation(id="implement-plan"),
        StepInvocation(id="compose-request"),
        StepInvocation(
            id="gh-pull-request",
            when=StepCondition(env="DEV_SEC_OPS_PLATFORM", equals="github"),
        ),
        StepInvocation(
            id="glab-pull-request",
            when=StepCondition(env="DEV_SEC_OPS_PLATFORM", equals="gitlab"),
        ),
    ],
)


DIRECT_WORKFLOW_CONFIG = WorkflowConfig(
    type_id="direct",
    description="Direct workflow — implements from issue description without planning",
    steps=[
        StepInvocation(id="fetch-issue"),
        StepInvocation(id="git-prepare"),
        StepInvocation(id="implement-direct"),
    ],
)


FULL_WORKFLOW_CONFIG = WorkflowConfig(
    type_id="full",
    description="Full workflow pipeline",
    steps=[
        StepInvocation(id="fetch-issue"),
        StepInvocation(id="git-branch"),
        # claude-code-plan uses the default display_name ("Building implementation plan")
        # from PromptJsonStep; implement-plan picks it up from previous_invocation.display_name.
        StepInvocation(id="claude-code-plan"),
        StepInvocation(id="implement-plan"),
        StepInvocation(id="code-quality"),
        StepInvocation(id="compose-request"),
        StepInvocation(
            id="gh-pull-request",
            when=StepCondition(env="DEV_SEC_OPS_PLATFORM", equals="github"),
        ),
        StepInvocation(
            id="glab-pull-request",
            when=StepCondition(env="DEV_SEC_OPS_PLATFORM", equals="gitlab"),
        ),
    ],
)


def get_patch_pipeline() -> List[WorkflowStep]:
    """Create the patch workflow pipeline.

    Resolves :data:`PATCH_WORKFLOW_CONFIG` into a list of step instances. See
    that constant for the declarative shape; the resolver handles step
    construction and any conditional ``StepCondition`` gating.

    Returns:
        List of WorkflowStep instances in execution order for patch processing
    """
    return resolve_workflow(PATCH_WORKFLOW_CONFIG)


def get_thin_pipeline() -> List[WorkflowStep]:
    """Create the thin workflow pipeline for straightforward issues.

    Resolves :data:`THIN_WORKFLOW_CONFIG`. The PR/MR creation step is gated by
    the ``DEV_SEC_OPS_PLATFORM`` environment variable via ``StepCondition``;
    no Python-level branching happens in this function.
    """
    return resolve_workflow(THIN_WORKFLOW_CONFIG)


def get_direct_pipeline() -> List[WorkflowStep]:
    """Create the direct workflow pipeline for straightforward issues.

    Resolves :data:`DIRECT_WORKFLOW_CONFIG`. Skips planning and implements
    directly from the issue description.
    """
    return resolve_workflow(DIRECT_WORKFLOW_CONFIG)


def get_full_pipeline() -> List[WorkflowStep]:
    """Create the full workflow pipeline with Claude Code planning.

    Resolves :data:`FULL_WORKFLOW_CONFIG`. The PR/MR creation step is gated by
    the ``DEV_SEC_OPS_PLATFORM`` environment variable via ``StepCondition``;
    no Python-level branching happens in this function.

    Returns:
        List of WorkflowStep instances in execution order
    """
    return resolve_workflow(FULL_WORKFLOW_CONFIG)
