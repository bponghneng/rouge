"""ADW workflow implementation."""

import logging
from typing import Any, Dict, Optional

from rouge.core.utils import make_adw_id
from rouge.core.workflow import execute_workflow
from rouge.core.workflow.artifacts import ArtifactStore
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.workflow_io import log_step_end, log_step_start
from rouge.core.workflow.workflow_registry import get_pipeline_for_type

logger = logging.getLogger(__name__)


def execute_code_review_loop(
    workflow_id: str,
    config: Optional[Dict[str, Any]] = None,
    max_iterations: int = 10,
) -> tuple[bool, str]:
    """Execute the codereview workflow loop.

    Runs the codereview pipeline repeatedly until either the review is
    clean (no actionable issues) or the maximum number of iterations is
    reached.  Each iteration executes all pipeline steps in order.
    Critical step failures abort the loop immediately.

    This function operates without database/issue tracking -- the
    WorkflowContext is created with ``issue_id=None``.

    Args:
        workflow_id: Unique identifier for this workflow run.
        config: Optional configuration dict seeded into context.data
            (e.g. ``{"base_commit": "abc123"}``).
        max_iterations: Maximum number of loop iterations before giving
            up.  Defaults to 10.

    Returns:
        Tuple of (success, workflow_id) where success is True if the
        review became clean within the allowed iterations.

    Raises:
        ValueError: If max_iterations is not a positive integer or if
            config contains reserved keys.
    """
    # Validate max_iterations
    if not isinstance(max_iterations, int) or max_iterations < 1:
        raise ValueError(f"max_iterations must be a positive integer, got: {max_iterations}")

    # Validate config type
    if config is not None and not isinstance(config, dict):
        raise ValueError(f"config must be a dict or None, got: {type(config).__name__}")

    # Define reserved keys that should not be in caller-provided config
    RESERVED_KEYS = {"review_is_clean"}

    # Validate config doesn't contain reserved keys
    if config is not None:
        conflicting_keys = RESERVED_KEYS & config.keys()
        if conflicting_keys:
            raise ValueError(
                f"config contains reserved keys: {conflicting_keys}. "
                f"Reserved keys are: {RESERVED_KEYS}"
            )

    steps = get_pipeline_for_type("codereview")
    artifact_store = ArtifactStore(workflow_id)

    context = WorkflowContext(
        adw_id=workflow_id,
        issue_id=None,
        artifact_store=artifact_store,
    )

    # Seed context.data with caller-provided config
    if config is not None:
        context.data.update(config)

    logger.info("Starting codereview loop (max %d iterations)", max_iterations)
    logger.info("Workflow ID: %s", workflow_id)

    for iteration in range(1, max_iterations + 1):
        logger.info("=== Codereview iteration %d/%d ===", iteration, max_iterations)

        # Reset review_is_clean flag at the start of each iteration
        # to prevent stale values from causing premature success
        context.data["review_is_clean"] = False

        for step in steps:
            log_step_start(step.name)

            try:
                result = step.run(context)
            except Exception as e:
                # Convert exception to failed result for consistent handling
                logger.exception("Step '%s' raised exception", step.name)
                from rouge.core.workflow.types import StepResult

                result = StepResult(success=False, error=str(e))

            if not result.success:
                if step.is_critical:
                    log_step_end(step.name, result.success)
                    error_msg = f"Critical step '{step.name}' failed"
                    if result.error:
                        error_msg += f": {result.error}"
                    logger.error("%s, aborting codereview loop", error_msg)
                    return False, workflow_id
                else:
                    log_step_end(step.name, result.success)
                    warning_msg = f"Best-effort step '{step.name}' failed"
                    if result.error:
                        warning_msg += f": {result.error}"
                    logger.warning("%s, continuing", warning_msg)
            else:
                log_step_end(step.name, result.success)

        # Check if the review is clean after running all steps
        if context.data.get("review_is_clean", False):
            logger.info("Review is clean after iteration %d", iteration)
            return True, workflow_id

    logger.warning(
        "Codereview loop exhausted %d iterations without clean review",
        max_iterations,
    )
    return False, workflow_id


def execute_adw_workflow(
    issue_id: Optional[int] = None,
    adw_id: Optional[str] = None,
    *,
    workflow_type: str = "main",
    config: Optional[Dict[str, Any]] = None,
) -> tuple[bool, str]:
    """Execute the Agent Development Workflow for a given issue.

    Supports multiple workflow types:
    - ``"main"`` (default): Full issue-based workflow pipeline.
    - ``"patch"``: Patch pipeline for existing issues.
    - ``"codereview"``: Standalone review loop that does not require
      an issue.

    Args:
        issue_id: The ID of the issue to process.  Required for
            ``"main"`` and ``"patch"`` workflows; ignored for
            ``"codereview"``.
        adw_id: Optional workflow identifier (auto-generated if missing).
        workflow_type: The type of workflow to execute.  One of
            ``"main"``, ``"patch"``, or ``"codereview"``.
        config: Optional configuration dict passed to the workflow
            (used by ``"codereview"`` to seed context data).

    Returns:
        Tuple of (success flag, workflow identifier).
    """
    workflow_id = adw_id or make_adw_id()

    # Route codereview workflows to the dedicated loop
    if workflow_type == "codereview":
        return execute_code_review_loop(
            workflow_id=workflow_id,
            config=config,
        )

    # Issue-based workflows require a valid issue_id
    if issue_id is None:
        raise ValueError(f"issue_id is required for workflow_type={workflow_type!r}")

    # Get the pipeline for the specified workflow type
    pipeline = get_pipeline_for_type(workflow_type)

    success = execute_workflow(issue_id, workflow_id, pipeline=pipeline)
    return success, workflow_id
