"""Status update functionality for workflow orchestration."""

import logging

from rouge.core.database import update_issue_status

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
        logger.debug(f"Issue {issue_id} status updated to '{status}'")
    except Exception as e:
        logger.error(f"Failed to update issue {issue_id} status to '{status}': {e}")
