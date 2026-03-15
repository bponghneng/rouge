"""Shared utility helpers for workflow step implementations."""

from typing import Any

from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.utils import get_logger


def _emit_and_log(issue_id: int, adw_id: str, text: str, raw: dict[str, Any]) -> None:
    """Helper to emit comment and log based on status.

    Args:
        issue_id: Issue ID
        adw_id: ADW ID
        text: Comment text
        raw: Raw payload data
    """
    logger = get_logger(adw_id)
    payload = CommentPayload(
        issue_id=issue_id,
        adw_id=adw_id,
        text=text,
        raw=raw,
        source="system",
        kind="workflow",
    )
    status, msg = emit_comment_from_payload(payload)
    if status == "success":
        logger.debug(msg)
    elif status == "skipped":
        logger.info(msg)
    else:
        logger.error(msg)
