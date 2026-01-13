"""Notification helpers for workflows including progress comments and stream handlers.

This package provides utilities for inserting progress comments during
workflow execution and creating stream handlers for agent output processing.

Example:
    from rouge.core.models import CommentPayload
    from rouge.core.notifications.agent_stream_handlers import make_progress_comment_handler
    from rouge.core.notifications.comments import emit_comment_from_payload

    # Insert a manual progress comment
    payload = CommentPayload(issue_id=123, text="Starting implementation", source="system")
    status, msg = emit_comment_from_payload(payload)
    logger.debug(msg) if status == "success" else logger.error(msg)

    # Create a stream handler for agent execution
    handler = make_progress_comment_handler(issue_id, adw_id, logger)
    agent.execute_prompt(request, stream_handler=handler)
"""
