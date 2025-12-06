"""Database operations for the Rouge Worker."""

import logging
from typing import Optional, Tuple

from rouge.core.database import get_client as _get_client


def get_client():
    """Get a Supabase client instance.

    Returns:
        Supabase client configured with environment credentials
    """
    return _get_client()


def get_next_issue(
    worker_id: str,
    logger: Optional[logging.Logger] = None,
) -> Optional[Tuple[int, str]]:
    """
    Retrieve and lock the next pending issue from the database.

    Uses the PostgreSQL function get_and_lock_next_issue to atomically
    retrieve and lock an issue, preventing race conditions.

    Args:
        worker_id: Unique identifier for the worker requesting the issue
        logger: Optional logger for logging operations

    Returns:
        Tuple of (issue_id, description) if an issue is available, None otherwise
    """
    try:
        client = get_client()

        # Call the PostgreSQL function to get and lock the next issue
        response = client.rpc(
            "get_and_lock_next_issue", {"p_worker_id": worker_id}
        ).execute()

        if response.data and len(response.data) > 0:
            issue = response.data[0]
            issue_id = issue["issue_id"]
            description = issue["issue_description"]
            if logger:
                logger.info(f"Locked issue {issue_id} for processing")
            return (issue_id, description)

        return None

    except Exception as e:
        if logger:
            logger.error(f"Error retrieving next issue: {e}")
        return None


def update_issue_status(
    issue_id: int,
    status: str,
    logger: Optional[logging.Logger] = None,
) -> None:
    """
    Update the status of an issue in the database.

    Args:
        issue_id: The ID of the issue to update
        status: The new status ('pending', 'started', or 'completed')
        logger: Optional logger for logging operations
    """
    valid_statuses = {"pending", "started", "completed"}
    if status not in valid_statuses:
        error_message = (
            f"Invalid status '{status}' for issue {issue_id}. "
            f"Valid statuses are: {', '.join(sorted(valid_statuses))}"
        )
        if logger:
            logger.error(error_message)
        else:
            logging.getLogger(__name__).error(error_message)
        return

    try:
        client = get_client()

        client.table("cape_issues").update({"status": status}).eq(
            "id", issue_id
        ).execute()

        if logger:
            logger.debug(f"Updated issue {issue_id} status to {status}")

    except Exception as e:
        if logger:
            logger.error(f"Error updating issue {issue_id} status: {e}")
