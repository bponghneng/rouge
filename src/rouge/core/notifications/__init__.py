"""Notification helpers for workflows including progress comments.

This package provides utilities for inserting progress comments during
workflow execution.

Example:
    from rouge.core.models import CommentPayload
    from rouge.core.notifications.comments import emit_comment_from_payload

    # Insert a progress comment
    payload = CommentPayload(
        issue_id=123,
        adw_id="example-adw-id",
        kind="progress",
        text="Starting implementation",
        source="system",
    )
    status, msg = emit_comment_from_payload(payload)
    logger.debug(msg) if status == "success" else logger.error(msg)
"""
