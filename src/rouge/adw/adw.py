"""ADW workflow implementation."""

from typing import Optional

from rouge.core.utils import make_adw_id
from rouge.core.workflow import execute_workflow


def execute_adw_workflow(
    issue_id: int,
    adw_id: Optional[str] = None,
) -> tuple[bool, str]:
    """
    Execute the Agent Development Workflow for a given issue.

    Args:
        issue_id: The ID of the issue to process
        adw_id: Optional workflow identifier (auto-generated if missing)

    Returns:
        Tuple of (success flag, workflow identifier).
    """
    workflow_id = adw_id or make_adw_id()
    success = execute_workflow(issue_id, workflow_id)
    return success, workflow_id
