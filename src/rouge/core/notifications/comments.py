"""Comment utilities for Rouge workflow notifications.

This module provides utilities for inserting progress comments during
workflow execution.

Example:
    from rouge.core.notifications.comments import emit_comment_from_payload
    from rouge.core.models import CommentPayload

    payload = CommentPayload(
        issue_id=1,
        text="Starting implementation",
        source="system",
        adw_id="example-adw-id",
        kind="status",
    )
    status, msg = emit_comment_from_payload(payload)
    logger.debug(msg) if status == "success" else logger.error(msg)
"""

import logging

from rouge.core.database import create_comment
from rouge.core.models import Comment, CommentPayload

logger = logging.getLogger(__name__)


def emit_comment_from_payload(payload: CommentPayload) -> tuple[str, str]:
    """Create and insert a comment from a CommentPayload.

    Best-effort helper that returns a status tuple, allowing callers to
    decide how to handle logging. Never raises, ensuring workflow execution
    continues even if Supabase is unavailable.

    Args:
        payload: A CommentPayload object containing the comment details.

    Returns:
        A tuple of (status, message) where status is "success", "skipped", or "error"
        and message contains details about the operation result.
    """
    # Skip comment creation if issue_id is None
    if payload.issue_id is None:
        logger.debug("Skipping comment emission - issue_id is None")
        logger.info("📝 %s", payload.text)
        if payload.raw:
            # Log sanitized version of raw data to avoid exposing PII
            raw_str = str(payload.raw)
            sanitized = raw_str[:100] + "..." if len(raw_str) > 100 else raw_str
            logger.debug("Raw data (truncated): %s", sanitized)
        return ("skipped", "No issue_id - logged to console")

    comment = Comment(
        comment=payload.text,
        raw=payload.raw or {"text": payload.text},
        source=payload.source,
        type=payload.kind,
        adw_id=payload.adw_id,
        issue_id=payload.issue_id,
    )
    try:
        created_comment = create_comment(comment)
        return (
            "success",
            f"Comment inserted: ID={created_comment.id}, Text='{comment.comment}'",
        )
    except Exception as exc:  # pragma: no cover - logging path only
        return ("error", f"Failed to insert comment on issue {comment.issue_id}: {exc}")
