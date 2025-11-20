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
from typing import Callable

from cape.core.agents.claude import iter_assistant_items
from cape.core.agents.opencode import iter_opencode_items
from cape.core.database import create_comment


def make_progress_comment_handler(
    issue_id: int, adw_id: str, logger: logging.Logger, provider: str = "claude"
) -> Callable[[str], None]:
    """Create a stream handler that parses assistant messages and inserts progress comments.

    This handler parses JSONL output from agent providers (Claude or OpenCode),
    extracts assistant text and TodoWrite items, and inserts them as progress comments.

    The handler is best-effort and never raises exceptions, ensuring agent
    execution continues even if comment insertion fails.

    Args:
        issue_id: Cape issue ID for comment insertion
        adw_id: Workflow ID for logging context
        logger: Logger instance for error reporting
        provider: Provider name ("claude" or "opencode")

    Returns:
        Stream handler function that processes output lines

    Example:
        handler = make_progress_comment_handler(123, "adw-456", logger, "opencode")
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
                items = iter_opencode_items(line)
            else:
                # Default to Claude
                items = iter_assistant_items(line)

            for item in items:
                try:
                    # Serialize item to JSON for comment
                    text = json.dumps(item, indent=2)

                    # Insert progress comment (best-effort)
                    try:
                        comment = create_comment(issue_id, text)
                        logger.debug(
                            "Progress comment inserted: ID=%s, ADW=%s",
                            comment.id,
                            adw_id,
                        )
                    except Exception as exc:
                        logger.error(
                            "Failed to insert progress comment for issue %s: %s",
                            issue_id,
                            exc,
                        )
                except Exception as exc:
                    logger.error("Error serializing assistant item: %s", exc)

        except json.JSONDecodeError as exc:
            # JSON parsing error - log but continue
            logger.debug("JSON decode error in stream handler: %s", exc)
        except Exception as exc:
            # Unexpected error - log but never raise
            logger.error("Stream handler error: %s", exc)

    return handler


def make_simple_logger_handler(logger: logging.Logger) -> Callable[[str], None]:
    """Create a stream handler that logs raw output lines for debugging.

    This is a simple handler useful for development and debugging,
    logging each output line at debug level.

    Args:
        logger: Logger instance

    Returns:
        Stream handler function that logs each line

    Example:
        handler = make_simple_logger_handler(logger)
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
