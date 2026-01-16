"""Main workflow orchestration runner.

This module provides the public API for executing workflows via the
pluggable step pipeline architecture.
"""

from typing import TYPE_CHECKING, Optional

from rouge.core.workflow.pipeline import WorkflowRunner, get_default_pipeline

if TYPE_CHECKING:
    from rouge.core.workflow.step_base import WorkflowStep


def execute_workflow(
    issue_id: int,
    adw_id: str,
    pipeline: Optional[list["WorkflowStep"]] = None,
) -> bool:
    """Execute complete workflow for an issue using pluggable step pipeline.

    This is the main orchestration function that runs all workflow steps:
    1. Fetch issue from database
    2. Classify the issue
    3. Build implementation plan
    4. Find plan file
    5. Implement the plan
    6. Find implemented plan file
    7. Generate CodeRabbit review
    8. Address review issues
    9. Run code quality checks (best-effort)
    10. Validate plan acceptance
    11. Prepare pull request (best-effort)

    Progress comments are inserted at key points (best-effort, non-blocking).

    Args:
        issue_id: The Rouge issue ID to process
        adw_id: Workflow ID for tracking
        pipeline: Optional custom pipeline of workflow steps. If not provided,
            uses the default pipeline.

    Returns:
        True if workflow completed successfully, False otherwise
    """
    steps = pipeline if pipeline is not None else get_default_pipeline()
    runner = WorkflowRunner(steps)
    return runner.run(issue_id, adw_id)
