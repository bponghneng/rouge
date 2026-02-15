"""ADW workflow implementation."""

import logging
from typing import Optional

from rouge.core.utils import make_adw_id
from rouge.core.workflow import execute_workflow
from rouge.core.workflow.workflow_registry import get_pipeline_for_type

logger = logging.getLogger(__name__)


def execute_adw_workflow(
    issue_id: Optional[int] = None,
    adw_id: Optional[str] = None,
    *,
    workflow_type: str = "main",
) -> tuple[bool, str]:
    """Execute the Agent Development Workflow for a given issue.

    Supports multiple workflow types:
    - ``"main"`` (default): Full issue-based workflow pipeline.
    - ``"patch"``: Patch pipeline for existing issues.
    - ``"codereview"``: Issue-based codereview workflow pipeline.

    Args:
        issue_id: The ID of the issue to process.  Required for all
            workflow types.
        adw_id: Optional workflow identifier (auto-generated if missing).
        workflow_type: The type of workflow to execute.  One of
            ``"main"``, ``"patch"``, or ``"codereview"``.

    Returns:
        Tuple of (success flag, workflow identifier).
    """
    workflow_id = adw_id or make_adw_id()

    # Issue-based workflows require a valid issue_id
    if issue_id is None:
        raise ValueError(f"issue_id is required for workflow_type={workflow_type!r}")

    # Get the pipeline for the specified workflow type
    pipeline = get_pipeline_for_type(workflow_type)

    success = execute_workflow(issue_id, workflow_id, pipeline=pipeline)
    return success, workflow_id
