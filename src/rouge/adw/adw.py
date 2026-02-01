"""ADW workflow implementation."""

from typing import Optional

from rouge.core.utils import make_adw_id
from rouge.core.workflow import execute_workflow
from rouge.core.workflow.workflow_registry import get_pipeline_for_type


def execute_adw_workflow(
    issue_id: int,
    adw_id: Optional[str] = None,
    *,
    workflow_type: str = "main",
) -> tuple[bool, str]:
    """
    Execute the Agent Development Workflow for a given issue.

    Args:
        issue_id: The ID of the issue to process
        adw_id: Optional workflow identifier (auto-generated if missing)
        workflow_type: The workflow type to execute (resolved via the workflow registry)

    Returns:
        Tuple of (success flag, workflow identifier).
    """
    workflow_id = adw_id or make_adw_id()
    pipeline = get_pipeline_for_type(workflow_type)
    success = execute_workflow(issue_id, workflow_id, pipeline=pipeline)
    return success, workflow_id
