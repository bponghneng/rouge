"""Shared utility helpers for workflow step implementations."""

import logging
import re
import subprocess
from typing import Any, Optional

from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.utils import get_logger

# Max characters to log from LLM response
MAX_LOG_LENGTH = 500


def sanitize_for_logging(text: Optional[str], max_length: int = MAX_LOG_LENGTH) -> str:
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


def resolve_base_ref(repo_path: str, logger: logging.Logger) -> Optional[str]:
    """Resolve the remote default branch ref (origin/HEAD) for a repository.

    Used by both ``has_commits_ahead_of_base`` and ``repo_filter.detect_affected_repos``
    to share origin/HEAD resolution logic and keep fallback behaviour consistent.

    Args:
        repo_path: Absolute path to the git repository.
        logger: Logger instance for debug output.

    Returns:
        The resolved ref string (e.g. a SHA or symbolic ref) when origin/HEAD is
        available, or None when it is not configured (shallow clone, no remote, etc.).
    """
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "origin/HEAD"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=repo_path,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    logger.debug("origin/HEAD unavailable for %s", repo_path)
    return None


def has_commits_ahead_of_base(repo_path: str, logger: logging.Logger) -> bool:
    """Check whether the current branch has commits ahead of origin/HEAD.

    Resolves the remote default branch ref via ``resolve_base_ref`` and counts
    commits with ``git rev-list --count``.  When origin/HEAD is unavailable
    (e.g., shallow clones or repos without a remote), falls back to counting total
    commits on HEAD — if there is at least one commit the branch is considered ahead.

    See also: ``repo_filter.detect_affected_repos`` which performs a similar check
    for fallback repo detection during the implement step.

    Args:
        repo_path: Absolute path to the git repository.
        logger: Logger instance for debug output.

    Returns:
        True if at least one commit ahead of the base ref, or if the check fails
        (fail-open to avoid skipping PR creation). False if even with base.
    """
    try:
        base_ref = resolve_base_ref(repo_path, logger)
        if base_ref is not None:
            ahead_result = subprocess.run(
                ["git", "rev-list", "--count", f"{base_ref}..HEAD"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=repo_path,
            )
            ahead_count = int(ahead_result.stdout.strip()) if ahead_result.returncode == 0 else 0
            return ahead_count > 0
        else:
            # origin/HEAD not configured — fall back to total commit count on this branch.
            # A single-commit branch (e.g., during tests or shallow clone) should still
            # trigger PR/MR creation rather than silently skipping.
            logger.debug(
                "origin/HEAD unavailable for %s; falling back to total commit count", repo_path
            )
            total_result = subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=repo_path,
            )
            total_count = int(total_result.stdout.strip()) if total_result.returncode == 0 else 0
            return total_count >= 1
    except (subprocess.TimeoutExpired, OSError, ValueError) as e:
        logger.debug("Delta check failed for %s: %s", repo_path, e)
        return True  # Proceed with PR/MR creation if check fails


def emit_and_log(issue_id: int, adw_id: str, text: str, raw: dict[str, Any]) -> None:
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
