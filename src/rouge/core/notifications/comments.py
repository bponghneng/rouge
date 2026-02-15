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
from typing import TYPE_CHECKING, Optional

from rouge.core.database import create_comment
from rouge.core.models import Comment, CommentPayload

if TYPE_CHECKING:
    from rouge.core.workflow.artifacts import Artifact

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


def emit_artifact_comment(
    issue_id: Optional[int], adw_id: str, artifact: "Artifact"
) -> tuple[str, str]:
    """Create and insert a comment for an artifact save event.

    Best-effort helper that creates a comment when an artifact is saved during
    workflow execution. The comment includes the full artifact JSON in the raw
    field for detailed tracking and debugging.

    Args:
        issue_id: Optional Rouge issue ID. If None, the comment will be logged
            to console instead of persisted to the database.
        adw_id: Agent Development Workflow identifier for tracking.
        artifact: The Artifact instance that was saved.

    Returns:
        A tuple of (status, message) where status is "success", "skipped", or "error"
        and message contains details about the operation result.

    Example:
        from rouge.core.notifications.comments import emit_artifact_comment
        from rouge.core.workflow.artifacts import PlanArtifact, PlanData

        artifact = PlanArtifact(
            workflow_id="adw-123",
            plan_data=PlanData(plan="...", summary="Created plan")
        )
        status, msg = emit_artifact_comment(issue_id=1, adw_id="adw-123", artifact=artifact)
        logger.debug(msg) if status == "success" else logger.error(msg)

    Note:
        This function never raises exceptions. Error handling is delegated to
        emit_comment_from_payload, ensuring workflow execution continues even
        if comment insertion fails.
    """
    payload = CommentPayload(
        issue_id=issue_id,
        adw_id=adw_id,
        text=f"Artifact saved: {artifact.artifact_type}",
        source="artifact",
        kind=artifact.artifact_type,
        raw={
            "artifact_type": artifact.artifact_type,
            "artifact": artifact.model_dump(mode="json"),
        },
    )
    return emit_comment_from_payload(payload)
