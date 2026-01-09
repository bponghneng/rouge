"""Stream handler factories for agent execution notifications.

This module provides factory functions that create stream handlers
for processing agent output and inserting progress comments.

Stream handlers follow a specific protocol:
- Receive raw output chunks (typically line-by-line)
- Parse and process content independently
- Handle errors gracefully without raising
- Never interrupt agent execution
"""

import json
import logging
from typing import Any, Callable, Dict, Iterable

from rouge.core.agents.claude import iter_assistant_items
from rouge.core.agents.opencode import iter_opencode_items
from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import emit_comment_from_payload

logger = logging.getLogger(__name__)


def make_progress_comment_handler(
    issue_id: int, adw_id: str, provider: str = "claude"
) -> Callable[[str], None]:
    """Create a stream handler that parses assistant messages and inserts progress comments.

    This handler parses JSONL output from agent providers (Claude or OpenCode),
    extracts assistant text and TodoWrite items, and inserts them as progress comments.

    The handler is best-effort and never raises exceptions, ensuring agent
    execution continues even if comment insertion fails.

    Args:
        issue_id: Issue ID for comment insertion
        adw_id: Workflow ID for logging context
        provider: Provider name ("claude" or "opencode")

    Returns:
        Stream handler function that processes output lines

    Example:
        handler = make_progress_comment_handler(123, "adw-456", "opencode")
        agent.execute_prompt(request, stream_handler=handler)
    """

    def handler(line: str) -> None:
        """Process a single line of agent output."""
        try:
            stripped = line.strip()
            if not stripped:
                return

            # Parse JSONL and extract items based on provider
            if provider == "opencode":
                items: Iterable[Dict[str, Any]] = iter_opencode_items(line)
            else:
                # Default to Claude
                items = iter_assistant_items(line)

            for item in items:
                try:
                    # Serialize item to JSON for comment
                    text = json.dumps(item, indent=2)

                    # Create CommentPayload with metadata
                    payload = CommentPayload(
                        issue_id=issue_id,
                        adw_id=adw_id,
                        text=text,
                        raw=item,  # Store the raw parsed dict
                        source="agent",
                        kind=provider,  # "claude" or "opencode"
                    )

                    # Insert progress comment (best-effort)
                    status, msg = emit_comment_from_payload(payload)
                    if status == "success":
                        logger.debug("Progress comment inserted: ADW=%s - %s", adw_id, msg)
                    else:
                        logger.error("Failed to insert progress comment: %s", msg)
                except Exception as exc:
                    logger.error("Error serializing assistant item: %s", exc)

        except json.JSONDecodeError as exc:
            # JSON parsing error - log but continue
            logger.debug("JSON decode error in stream handler: %s", exc)
        except Exception as exc:
            # Unexpected error - log but never raise
            logger.error("Stream handler error: %s", exc)

    return handler


def make_simple_logger_handler() -> Callable[[str], None]:
    """Create a stream handler that logs raw output lines for debugging.

    This is a simple handler useful for development and debugging,
    logging each output line at debug level.

    Returns:
        Stream handler function that logs each line

    Example:
        handler = make_simple_logger_handler()
        agent.execute_prompt(request, stream_handler=handler)
    """

    def handler(line: str) -> None:
        """Log a single line of agent output."""
        try:
            logger.debug("Agent output: %s", line.strip())
        except Exception as exc:
            # Even logging errors shouldn't interrupt execution
            logger.error("Logger handler error: %s", exc)

    return handler
