"""Status update functionality for workflow orchestration."""

import logging

from postgrest.exceptions import APIError

from rouge.core.database import update_issue
from rouge.core.utils import get_logger

logger = logging.getLogger(__name__)


def update_status(issue_id: int, status: str, adw_id: str | None = None) -> None:
    """Update the status of an issue.

    This is a best-effort operation - database failures are logged but never halt
    workflow execution. Successful updates are logged at DEBUG level, failures
    at ERROR level.

    Args:
        issue_id: The Rouge issue ID
        status: The new status value ("pending", "started", or "completed")
        adw_id: Optional workflow ID for logger retrieval
    """
    status_logger = get_logger(adw_id) if adw_id else logger
    try:
        update_issue(issue_id, status=status)
        status_logger.debug("Issue %s status updated to '%s'", issue_id, status)
    except (APIError, ValueError):
        status_logger.exception("Failed to update issue %s status to %s", issue_id, status)
