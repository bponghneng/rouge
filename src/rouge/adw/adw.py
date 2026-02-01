"""ADW workflow implementation."""

import logging
from typing import Any, Dict, Optional

from rouge.core.utils import make_adw_id
from rouge.core.workflow import execute_workflow
from rouge.core.workflow.artifacts import ArtifactStore
from rouge.core.workflow.pipeline import get_patch_pipeline
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.workflow_io import log_step_end, log_step_start
from rouge.core.workflow.workflow_registry import get_pipeline_for_type

logger = logging.getLogger(__name__)


def execute_code_review_loop(
    workflow_id: str,
    config: Optional[Dict[str, Any]] = None,
    max_iterations: int = 10,
) -> tuple[bool, str]:
    """Execute the code-review workflow loop.

    Runs the code-review pipeline repeatedly until either the review is
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
    """
    steps = get_pipeline_for_type("code-review")
    artifact_store = ArtifactStore(workflow_id)

    context = WorkflowContext(
        adw_id=workflow_id,
        issue_id=None,
        artifact_store=artifact_store,
    )

    # Seed context.data with caller-provided config
    if config is not None:
        context.data.update(config)

    logger.info("Starting code-review loop (max %d iterations)", max_iterations)
    logger.info("Workflow ID: %s", workflow_id)

    for iteration in range(1, max_iterations + 1):
        logger.info("=== Code-review iteration %d/%d ===", iteration, max_iterations)

        for step in steps:
            log_step_start(step.name)

            result = step.run(context)

            if not result.success:
                if step.is_critical:
                    log_step_end(step.name, result.success)
                    error_msg = f"Critical step '{step.name}' failed"
                    if result.error:
                        error_msg += f": {result.error}"
                    logger.error("%s, aborting code-review loop", error_msg)
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
        "Code-review loop exhausted %d iterations without clean review",
        max_iterations,
    )
    return False, workflow_id


def execute_adw_workflow(
    issue_id: Optional[int] = None,
    adw_id: Optional[str] = None,
    *,
    patch_mode: bool = False,
    workflow_type: str = "main",
    config: Optional[Dict[str, Any]] = None,
) -> tuple[bool, str]:
    """Execute the Agent Development Workflow for a given issue.

    Supports multiple workflow types:
    - ``"main"`` (default): Full issue-based workflow pipeline.
    - ``"patch"``: Patch pipeline for existing issues (also triggered
      by ``patch_mode=True`` for backward compatibility).
    - ``"code-review"``: Standalone review loop that does not require
      an issue.

    Args:
        issue_id: The ID of the issue to process.  Required for
            ``"main"`` and ``"patch"`` workflows; ignored for
            ``"code-review"``.
        adw_id: Optional workflow identifier (auto-generated if missing).
        patch_mode: If True, use the patch pipeline.  Kept for backward
            compatibility -- equivalent to ``workflow_type="patch"``.
        workflow_type: The type of workflow to execute.  One of
            ``"main"``, ``"patch"``, or ``"code-review"``.
        config: Optional configuration dict passed to the workflow
            (used by ``"code-review"`` to seed context data).

    Returns:
        Tuple of (success flag, workflow identifier).
    """
    workflow_id = adw_id or make_adw_id()

    # Route code-review workflows to the dedicated loop
    if workflow_type == "code-review":
        return execute_code_review_loop(
            workflow_id=workflow_id,
            config=config,
        )

    # Issue-based workflows require a valid issue_id
    if issue_id is None:
        raise ValueError(f"issue_id is required for workflow_type={workflow_type!r}")

    # Backward compatibility: patch_mode flag overrides workflow_type
    if patch_mode:
        success = execute_workflow(
            issue_id,
            workflow_id,
            pipeline=get_patch_pipeline(),
        )
    else:
        success = execute_workflow(issue_id, workflow_id)
    return success, workflow_id
