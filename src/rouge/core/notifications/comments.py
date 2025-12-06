"""Comment utilities for Rouge workflow notifications.

This module provides utilities for inserting progress comments during
workflow execution.

Example:
    from rouge.core.notifications import insert_progress_comment
    from rouge.core.models import CapeComment

    comment = CapeComment(issue_id=1, comment="Starting implementation")
    status, msg = insert_progress_comment(comment)
    logger.debug(msg) if status == "success" else logger.error(msg)
"""

from rouge.core.database import create_comment
from rouge.core.models import CapeComment


def insert_progress_comment(comment: CapeComment) -> tuple[str, str]:
    """Insert a progress comment for the given issue.

    Best-effort helper that returns a status tuple, allowing callers to
    decide how to handle logging. Never raises, ensuring workflow execution
    continues even if Supabase is unavailable.

    Args:
        comment: A CapeComment object containing the comment details.

    Returns:
        A tuple of (status, message) where status is "success" or "error"
        and message contains details about the operation result.
    """
    try:
        created_comment = create_comment(comment)
        return (
            "success",
            f"Comment inserted: ID={created_comment.id}, Text='{comment.comment}'",
        )
    except Exception as exc:  # pragma: no cover - logging path only
        return ("error", f"Failed to insert comment on issue {comment.issue_id}: {exc}")
