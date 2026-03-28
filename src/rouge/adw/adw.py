"""ADW workflow implementation."""

from typing import Optional

from rouge.core.workflow import execute_workflow
from rouge.core.workflow.workflow_registry import get_pipeline_for_type


def execute_adw_workflow(
    adw_id: str,
    issue_id: Optional[int] = None,
    *,
    workflow_type: str = "full",
    resume_from: Optional[str] = None,
) -> tuple[bool, str]:
    """Execute the Agent Development Workflow for a given issue.

    Supports multiple workflow types:
    - ``"full"`` (default): Full issue-based workflow pipeline with Claude Code planning.
    - ``"patch"``: Patch pipeline for existing issues.

    Resume behavior:
    - When ``resume_from`` is provided, the workflow will skip all steps before
      the specified step name and resume execution from that step forward.
    - This is an operator-driven manual CLI operation, typically used to recover
      from failures or retry specific workflow stages.

    Args:
        adw_id: Workflow identifier (required string parameter).
        issue_id: The ID of the issue to process.  Required for all
            workflow types.
        workflow_type: The type of workflow to execute.  One of
            ``"full"`` or ``"patch"``.
        resume_from: Optional step name to resume workflow execution from.
            When provided, all steps before this step will be skipped.

    Returns:
        Tuple of (success flag, workflow identifier).
    """
    workflow_id = adw_id

    # Issue-based workflows require a valid issue_id
    if issue_id is None:
        raise ValueError(f"issue_id is required for workflow_type={workflow_type!r}")

    # Get the pipeline for the specified workflow type
    pipeline = get_pipeline_for_type(workflow_type)

    success = execute_workflow(
        issue_id,
        workflow_id,
        pipeline=pipeline,
        resume_from=resume_from,
        pipeline_type=workflow_type,
    )
    return success, workflow_id
