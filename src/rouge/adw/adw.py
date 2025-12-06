"""ADW workflow implementation."""

from logging import Logger
from typing import Optional

from rouge.core.utils import make_adw_id, setup_logger
from rouge.core.workflow import execute_workflow


def execute_adw_workflow(
    issue_id: int,
    adw_id: Optional[str] = None,
    logger: Optional[Logger] = None,
) -> tuple[bool, str]:
    """
    Execute the Agent Development Workflow for a given issue.

    Args:
        issue_id: The ID of the issue to process
        adw_id: Optional workflow identifier (auto-generated if missing)
        logger: Optional logger instance (defaults to workflow logger)

    Returns:
        Tuple of (success flag, workflow identifier).
    """
    workflow_id = adw_id or make_adw_id()
    workflow_logger = logger or setup_logger(workflow_id, "adw_plan_build")
    success = execute_workflow(issue_id, workflow_id, workflow_logger)
    return success, workflow_id
