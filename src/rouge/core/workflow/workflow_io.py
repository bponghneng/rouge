"""Shared I/O utilities for workflow steps.

Centralizes repetitive patterns for logging and progress comments.
"""

import logging
from typing import Tuple

from rouge.core.models import Comment
from rouge.core.notifications import insert_progress_comment

logger = logging.getLogger(__name__)


def emit_progress_comment(
    issue_id: int,
    message: str,
    raw: dict | None = None,
    comment_type: str = "workflow",
) -> Tuple[str, str]:
    """Insert a progress comment for an issue.

    Wraps the comment creation and insertion with consistent handling.

    Args:
        issue_id: The issue ID
        message: The comment message text
        raw: Optional raw data dict for the comment
        comment_type: Type of comment (default: "workflow")

    Returns:
        Tuple of (status, message) from insert_progress_comment
    """
    comment = Comment(
        issue_id=issue_id,
        comment=message,
        raw=raw or {"text": message},
        source="system",
        type=comment_type,
    )
    status, msg = insert_progress_comment(comment)
    if status == "success":
        logger.debug(msg)
    else:
        logger.error(msg)
    return status, msg


def log_step_start(step_name: str, issue_id: int | None = None) -> None:
    """Log the start of a workflow step and emit progress comment.

    Args:
        step_name: Name of the step starting
        issue_id: Optional issue ID for progress comment
    """
    logger.info(f"\n=== {step_name} ===")
    if issue_id is not None:
        emit_progress_comment(
            issue_id=issue_id,
            message=f"Step {step_name} started",
            raw={"step": step_name, "status": "started"},
            comment_type="workflow",
        )


def log_step_end(step_name: str, success: bool, issue_id: int | None = None) -> None:
    """Log the end of a workflow step and emit progress comment.

    Args:
        step_name: Name of the step ending
        success: Whether the step succeeded
        issue_id: Optional issue ID for progress comment
    """
    status_text = "Success" if success else "Failed"
    if success:
        logger.info(f"{step_name} completed successfully")
    else:
        logger.error(f"{step_name} failed")

    if issue_id is not None:
        emit_progress_comment(
            issue_id=issue_id,
            message=f"Step {step_name} completed: {status_text}",
            raw={"step": step_name, "status": "completed", "success": success},
            comment_type="workflow",
        )
