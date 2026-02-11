"""Stream handler factories for agent execution notifications.

This module previously provided factory functions for creating stream handlers
to process agent output. With the architectural change to use JSON envelope
parsing (subprocess.run) instead of JSONL streaming, stream handlers are no
longer used by agent providers.

Progress tracking is now handled via Supabase comments inserted at workflow
step boundaries. See rouge.core.notifications.comments for comment insertion.

The make_progress_comment_handler function is retained for backward compatibility
but is no longer passed to agent.execute_prompt().
"""

import json
import logging
from typing import Any, Callable, Dict, Iterable

from rouge.core.agents.opencode import iter_opencode_items
from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import emit_comment_from_payload

logger = logging.getLogger(__name__)


def make_progress_comment_handler(
    issue_id: int, adw_id: str, provider: str = "opencode"
) -> Callable[[str], None]:
    """Create a handler that parses assistant messages and inserts progress comments.

    This handler parses JSONL output and extracts assistant text and TodoWrite
    items, inserting them as progress comments.

    The handler is best-effort and never raises exceptions.

    Note: This handler is no longer passed to agent.execute_prompt() as stream
    handlers have been removed from the CodingAgent interface. Progress tracking
    is now handled via Supabase comments at workflow step boundaries.

    This function is retained for backward compatibility and may be used for
    manual JSONL parsing if needed.

    Args:
        issue_id: Issue ID for comment insertion
        adw_id: Workflow ID for logging context
        provider: Provider name ("opencode" only - Claude uses JSON envelope)

    Returns:
        Handler function that processes output lines
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
                # Claude no longer uses streaming - log warning and return
                logger.warning(
                    "Stream handler called for provider '%s' but only 'opencode' is supported. "
                    "Claude now uses JSON envelope parsing from subprocess.run.",
                    provider,
                )
                return

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
                except Exception:
                    logger.exception("Error serializing assistant item")

        except json.JSONDecodeError as exc:
            # JSON parsing error - log but continue
            logger.debug("JSON decode error in stream handler: %s", exc)
        except Exception:
            # Unexpected error - log but never raise
            logger.exception("Stream handler error")

    return handler


def make_simple_logger_handler() -> Callable[[str], None]:
    """Create a handler that logs raw output lines for debugging.

    This is a simple handler useful for development and debugging,
    logging each output line at debug level.

    Note: This handler is no longer passed to agent.execute_prompt() as stream
    handlers have been removed from the CodingAgent interface.

    Returns:
        Handler function that logs each line
    """

    def handler(line: str) -> None:
        """Log a single line of agent output."""
        try:
            logger.debug("Agent output: %s", line.strip())
        except Exception:
            # Even logging errors shouldn't interrupt execution
            logger.exception("Logger handler error")

    return handler
