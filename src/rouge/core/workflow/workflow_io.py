"""Shared I/O utilities for workflow steps.

Centralizes repetitive patterns for logging and progress comments.
"""

import logging

from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.utils import get_logger

logger = logging.getLogger(__name__)


def log_step_start(step_name: str, issue_id: int | None = None, adw_id: str | None = None) -> None:
    """Log the start of a workflow step and emit progress comment.

    Args:
        step_name: Name of the step starting
        issue_id: Optional issue ID for progress comment
        adw_id: Optional workflow ID for logger retrieval
    """
    step_logger = get_logger(adw_id) if adw_id else logger
    step_logger.info("\n=== %s ===", step_name)
    if issue_id is not None:
        message = f"Step {step_name} started"
        payload = CommentPayload(
            issue_id=issue_id,
            adw_id=None,
            text=message,
            raw={"step": step_name, "status": "started"},
            source="system",
            kind="workflow",
        )
        status, msg = emit_comment_from_payload(payload)
        if status == "success":
            step_logger.debug(msg)
        else:
            step_logger.error(msg)


def log_step_end(
    step_name: str, success: bool, issue_id: int | None = None, adw_id: str | None = None
) -> None:
    """Log the end of a workflow step and emit progress comment.

    Args:
        step_name: Name of the step ending
        success: Whether the step succeeded
        issue_id: Optional issue ID for progress comment
        adw_id: Optional workflow ID for logger retrieval
    """
    step_logger = get_logger(adw_id) if adw_id else logger
    status_text = "Success" if success else "Failed"
    if success:
        step_logger.info("%s completed successfully", step_name)
    else:
        step_logger.error("%s failed", step_name)

    if issue_id is not None:
        message = f"Step {step_name} completed: {status_text}"
        payload = CommentPayload(
            issue_id=issue_id,
            adw_id=None,
            text=message,
            raw={"step": step_name, "status": "completed", "success": success},
            source="system",
            kind="workflow",
        )
        status, msg = emit_comment_from_payload(payload)
        if status == "success":
            step_logger.debug(msg)
        else:
            step_logger.error(msg)
