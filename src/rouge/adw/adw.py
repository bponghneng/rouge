"""ADW workflow implementation."""

from typing import Optional

from rouge.core.utils import make_adw_id
from rouge.core.workflow import execute_workflow
from rouge.core.workflow.pipeline import get_patch_pipeline

# Suffix used by make_patch_workflow_id to create patch workflow IDs
_PATCH_SUFFIX = "-patch"


def _extract_parent_workflow_id(patch_workflow_id: str) -> str | None:
    """Extract parent workflow ID from a patch workflow ID.

    Reverses the operation of make_patch_workflow_id by removing the '-patch' suffix.

    Args:
        patch_workflow_id: The patch workflow ID (e.g., "abc12345-patch")

    Returns:
        The parent workflow ID if the suffix is present, None otherwise
    """
    if patch_workflow_id.endswith(_PATCH_SUFFIX):
        return patch_workflow_id[: -len(_PATCH_SUFFIX)]
    return None


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
        # Extract parent workflow ID from patch workflow ID to access main workflow artifacts
        parent_workflow_id = _extract_parent_workflow_id(workflow_id)
        if parent_workflow_id is None:
            raise ValueError(
                f"Invalid patch workflow ID: '{workflow_id}'. "
                f"Patch workflows must have a workflow ID ending with '{_PATCH_SUFFIX}' "
                "to enable parent workflow artifact sharing."
            )
        success = execute_workflow(
            issue_id,
            workflow_id,
            pipeline=get_patch_pipeline(),
            parent_workflow_id=parent_workflow_id,
        )
    else:
        success = execute_workflow(issue_id, workflow_id)
    return success, workflow_id
