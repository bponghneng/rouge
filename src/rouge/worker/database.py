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
) -> Optional[Tuple[int, str, str, str]]:
    """
    Retrieve the next pending or patch pending issue from the database.

    Queries the issues table directly (no RPC). Selects issues where type is
    'main' or 'patch' and status is 'pending' or 'patch pending'.

    Args:
        worker_id: Unique identifier for the worker requesting the issue
        logger: Optional logger for logging operations

    Returns:
        Tuple of (issue_id, description, status, type) if an issue is available,
        None otherwise. Status and type allow the worker to route correctly
        between new issue processing and patch application.
    """
    try:
        client = get_client()

        if logger:
            logger.debug("Fetching next issue for worker %s", worker_id)

        response = (
            client.table("issues")
            .select("id,description,status,type")
            .in_("status", ["pending"])
            .in_("type", ["main", "patch"])
            .order("id")
            .limit(1)
            .execute()
        )

        if response.data and len(response.data) > 0:
            issue = response.data[0]
            issue_id = issue["id"]
            description = issue["description"]
            status = issue["status"]
            issue_type = issue["type"]
            if logger:
                logger.info(
                    "Locked issue %s (status: %s, type: %s) for processing",
                    issue_id,
                    status,
                    issue_type,
                )
            return (issue_id, description, status, issue_type)

        return None

    except Exception:
        if logger:
            logger.exception("Error retrieving next issue")
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
        status: The new status ('pending', 'started', 'completed', 'patch pending', or 'patched')
        logger: Optional logger for logging operations
    """
    valid_statuses = {"pending", "started", "completed", "patch pending", "patched"}
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

        client.table("issues").update({"status": status}).eq("id", issue_id).execute()

        if logger:
            logger.debug("Updated issue %s status to %s", issue_id, status)

    except Exception:
        if logger:
            logger.exception("Error updating issue %s status", issue_id)
