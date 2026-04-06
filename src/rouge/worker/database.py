"""Database operations for the Rouge Worker."""

import logging
from typing import Optional, Tuple

import httpx

from rouge.core.database import get_client as _get_client
from rouge.core.database import reset_client
from rouge.core.database import update_issue as _update_issue
from rouge.worker.exceptions import TransientDatabaseError


def get_client():
    """Get a Supabase client instance.

    Returns:
        Supabase client configured with environment credentials
    """
    return _get_client()


def get_next_issue(
    worker_id: str,
    logger: Optional[logging.Logger] = None,
) -> Optional[Tuple[int, str, str, str, Optional[str]]]:
    """
    Atomically retrieve and lock the next pending issue via RPC.

    Calls the ``get_and_lock_next_issue`` Postgres RPC function which uses
    ``FOR UPDATE SKIP LOCKED`` to atomically select and lock an issue,
    preventing race conditions when multiple workers poll simultaneously.

    Args:
        worker_id: Unique identifier for the worker requesting the issue.
            Passed as ``p_worker_id`` to the RPC so only issues assigned
            to this worker are returned.
        logger: Optional logger for logging operations

    Returns:
        Tuple of (issue_id, description, status, type, adw_id) if an issue is
        available, None otherwise. Status and type allow the worker to route
        correctly between new issue processing and patch application. adw_id
        is the optional ADW workflow identifier (nullable column).

    Raises:
        TransientDatabaseError: If a transient network/timeout error occurs during
            the RPC call. The database client is automatically reset on these errors.
    """
    try:
        client = get_client()

        if logger:
            logger.debug("Fetching next issue for worker %s", worker_id)

        response = client.rpc("get_and_lock_next_issue", {"p_worker_id": worker_id}).execute()

        if response.data and len(response.data) > 0:
            issue = response.data[0]
            issue_id = issue["issue_id"]
            description = issue["issue_description"]
            status = issue["issue_status"]
            issue_type = issue["issue_type"]
            adw_id: Optional[str] = issue.get("issue_adw_id")
            if logger:
                logger.info(
                    "Locked issue %s (status: %s, type: %s, adw_id: %s) for processing",
                    issue_id,
                    status,
                    issue_type,
                    adw_id,
                )
            return (issue_id, description, status, issue_type, adw_id)

        return None

    except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError) as e:
        if logger:
            logger.warning(
                "Transient database error during get_next_issue: %s. Resetting client.",
                type(e).__name__,
            )
        reset_client()
        raise TransientDatabaseError(
            f"Database connection error while fetching next issue for worker {worker_id}",
            original_error=e,
        ) from e

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
        status: The new status reflecting the issue lifecycle:
            pending → claimed → started → completed|failed
        logger: Optional logger for logging operations
    """
    valid_statuses = {"pending", "claimed", "started", "completed", "failed"}
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
        _update_issue(issue_id, status=status)

        if logger:
            logger.debug("Updated issue %s status to %s", issue_id, status)

    except Exception:
        if logger:
            logger.exception("Error updating issue %s status", issue_id)
