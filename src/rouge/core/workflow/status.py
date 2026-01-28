"""Status update functionality for workflow orchestration."""

import logging
from typing import Optional

from postgrest.exceptions import APIError

from rouge.core.database import get_client, update_issue_status

logger = logging.getLogger(__name__)


def update_status(issue_id: int, status: str) -> None:
    """Update the status of an issue.

    This is a best-effort operation - database failures are logged but never halt
    workflow execution. Successful updates are logged at DEBUG level, failures
    at ERROR level.

    Args:
        issue_id: The Rouge issue ID
        status: The new status value ("pending", "started", or "completed")
    """
    try:
        update_issue_status(issue_id, status)
        logger.debug("Issue %s status updated to '%s'", issue_id, status)
    except APIError:
        logger.exception("Failed to update issue %s status to %s", issue_id, status)


def transition_to_patch_pending(issue_id: int) -> None:
    """Transition an issue to 'patch pending' status.

    This is a best-effort operation - database failures are logged but never halt
    workflow execution. Successful updates are logged at DEBUG level, failures
    at ERROR level.

    Args:
        issue_id: The Rouge issue ID
    """
    try:
        client = get_client()
        client.table("issues").update({"status": "patch pending"}).eq("id", issue_id).execute()
        logger.debug("Issue %s status updated to 'patch pending'", issue_id)
    except APIError:
        logger.exception("Failed to update issue %s status to 'patch pending'", issue_id)


def transition_to_patched(issue_id: int, _patch_id: Optional[int]) -> None:
    """Transition an issue to 'patched' status.

    Updates the issue status to 'patched'. The _patch_id parameter is accepted
    for backward compatibility but is no longer used (legacy patches table
    has been removed).

    This is a best-effort operation - database failures are logged but never halt
    workflow execution. Successful updates are logged at DEBUG level, failures
    at ERROR level.

    Args:
        issue_id: The Rouge issue ID
        _patch_id: Legacy patch ID (no longer used, accepted for compatibility)
    """
    try:
        client = get_client()
        client.table("issues").update({"status": "patched"}).eq("id", issue_id).execute()
        logger.debug("Issue %s status updated to 'patched'", issue_id)
    except APIError:
        logger.exception("Failed to update issue %s status to 'patched'", issue_id)
