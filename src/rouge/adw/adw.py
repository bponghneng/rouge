"""ADW workflow implementation."""

from typing import Optional

from rouge.core.utils import make_adw_id
from rouge.core.workflow import execute_workflow
from rouge.core.workflow.pipeline import get_patch_pipeline


def execute_adw_workflow(
    issue_id: int,
    adw_id: Optional[str] = None,
    *,
    patch_mode: bool = False,
) -> tuple[bool, str]:
    """
    Execute the Agent Development Workflow for a given issue.

    Args:
        issue_id: The ID of the issue to process
        adw_id: Optional workflow identifier (auto-generated if missing)
        patch_mode: If True, use the patch pipeline instead of the default pipeline

    Returns:
        Tuple of (success flag, workflow identifier).
    """
    workflow_id = adw_id or make_adw_id()
    if patch_mode:
        success = execute_workflow(issue_id, workflow_id, pipeline=get_patch_pipeline())
    else:
        success = execute_workflow(issue_id, workflow_id)
    return success, workflow_id
