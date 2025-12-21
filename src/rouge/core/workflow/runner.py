"""Main workflow orchestration runner.

This module provides the public API for executing workflows via the
pluggable step pipeline architecture.
"""

from rouge.core.workflow.pipeline import WorkflowRunner, get_default_pipeline


def execute_workflow(
    issue_id: int,
    adw_id: str,
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

    Returns:
        True if workflow completed successfully, False otherwise
    """
    pipeline = get_default_pipeline()
    runner = WorkflowRunner(pipeline, enable_artifacts=True)
    return runner.run(issue_id, adw_id)
