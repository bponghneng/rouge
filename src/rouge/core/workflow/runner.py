"""Main workflow orchestration runner.

This module provides the public API for executing workflows via the
pluggable step pipeline architecture.
"""

from typing import TYPE_CHECKING, Optional

from rouge.core.workflow.pipeline import WorkflowRunner, get_full_pipeline

if TYPE_CHECKING:
    from rouge.core.workflow.step_base import WorkflowStep


def execute_workflow(
    issue_id: int,
    adw_id: str,
    pipeline: Optional[list["WorkflowStep"]] = None,
    resume_from: Optional[str] = None,
    pipeline_type: str = "full",
) -> bool:
    """Execute complete workflow for an issue using pluggable step pipeline.

    This is the main orchestration function that runs all workflow steps:
    1. Fetch issue from database
    2. Git branch setup
    3. Build plan (ClaudeCodePlan)
    4. Implement plan
    5. Code quality checks (best-effort)
    6. Compose request (best-effort)
    7. PR/MR creation (conditional, best-effort)

    Progress comments are inserted at key points (best-effort, non-blocking).

    Resume behavior:
    - When ``resume_from`` is provided, the workflow will skip all steps before
      the specified step name and resume execution from that step forward.

    Args:
        issue_id: The Rouge issue ID to process
        adw_id: Workflow ID for tracking
        pipeline: Optional custom pipeline of workflow steps. If not provided,
            uses the default pipeline.
        resume_from: Optional step name to resume workflow execution from.
            When provided, all steps before this step will be skipped.
        pipeline_type: The type of pipeline being executed (default: "full").

    Returns:
        True if workflow completed successfully, False otherwise
    """
    # Normalise legacy pipeline_type value from before the main→full rename.
    if pipeline_type == "main":
        pipeline_type = "full"

    steps = pipeline if pipeline is not None else get_full_pipeline()
    runner = WorkflowRunner(steps)
    return runner.run(issue_id, adw_id, resume_from=resume_from, pipeline_type=pipeline_type)
