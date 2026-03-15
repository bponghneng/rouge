"""Shared utility helpers for workflow step implementations."""

import re
from typing import Any, Optional

from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.utils import get_logger

# Max characters to log from LLM response
MAX_LOG_LENGTH = 500


def _sanitize_for_logging(text: Optional[str], max_length: int = MAX_LOG_LENGTH) -> str:
    """Sanitize text by redacting secrets and truncating to safe length.

    Redacts common secret patterns (API keys, tokens, emails) and truncates
    to max_length characters to prevent logging of sensitive/verbose content.

    Pattern matching is intentionally conservative to err on the side of safety.
    The final catch-all pattern may redact some non-sensitive data (e.g., hashes),
    but this trade-off is acceptable given the security risk of logging secrets.

    Args:
        text: Text to sanitize (None is converted to "[None]")
        max_length: Maximum length of returned string

    Returns:
        Sanitized and truncated text safe for logging
    """
    if text is None:
        return "[None]"

    # Redact common secret patterns
    sanitized = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL]", text)
    # GitHub tokens: prefix + 36-40 chars (ghp_, gho_, ghu_, ghs_, ghr_)
    sanitized = re.sub(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}\b", "[GITHUB_TOKEN]", sanitized)
    # GitLab tokens: prefix + 20+ chars (glpat-, gldt-, gloas-, glcbt-)
    sanitized = re.sub(
        r"\b(?:glpat|gldt|gloas|glcbt)-[A-Za-z0-9_-]{20,}\b", "[GITLAB_TOKEN]", sanitized
    )
    # OpenAI-style API keys: sk- prefix
    sanitized = re.sub(r"\bsk-[A-Za-z0-9]{20,}\b", "[API_KEY]", sanitized)
    # Generic long alphanumeric tokens (catch-all for safety)
    sanitized = re.sub(r"\b[A-Za-z0-9]{32,}\b", "[TOKEN]", sanitized)

    # Truncate if longer than max_length
    if len(sanitized) > max_length:
        return sanitized[:max_length] + "..."
    return sanitized


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
