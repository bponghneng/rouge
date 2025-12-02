"""Review issue addressing functionality for workflow orchestration."""

import os
from logging import Logger
from typing import Callable, Optional

from cape.core.agent import execute_template
from cape.core.agents.claude import ClaudeAgentTemplateRequest
from cape.core.models import CapeComment
from cape.core.notifications import insert_progress_comment
from cape.core.workflow.shared import AGENT_IMPLEMENTOR
from cape.core.workflow.types import StepResult


def address_review_issues(
    review_file: str,
    issue_id: int,
    adw_id: str,
    logger: Logger,
    stream_handler: Optional[Callable[[str], None]] = None,
) -> StepResult[None]:
    """Execute the /address-review-issues template with the review file.

    Args:
        review_file: Path to the review file
        issue_id: Cape issue ID for tracking
        adw_id: Workflow ID for tracking
        logger: Logger instance
        stream_handler: Optional callback for streaming output

    Returns:
        StepResult with None data (success/failure only)
    """
    try:
        # Validate review file exists
        if not os.path.exists(review_file):
            logger.error(f"Review file does not exist: {review_file}")
            return StepResult.fail(f"Review file does not exist: {review_file}")

        logger.debug(f"Invoking /adw-implement-review template with review file: {review_file}")

        # Call execute_template with the review file
        request = ClaudeAgentTemplateRequest(
            agent_name=AGENT_IMPLEMENTOR,
            slash_command="/adw-implement-review",
            args=[review_file],
            adw_id=adw_id,
            issue_id=issue_id,
            model="sonnet",
        )

        logger.debug(
            "address_review_issues request: %s",
            request.model_dump_json(indent=2, by_alias=True),
        )

        # GenerateReviewStep may return plain text output, not JSON
        response = execute_template(request, stream_handler=stream_handler, require_json=False)

        logger.debug(
            "address_review_issues response: success=%s",
            response.success,
        )

        if not response.success:
            logger.error(f"Failed to execute /adw-implement-review template: {response.output}")
            return StepResult.fail(
                f"Failed to execute /adw-implement-review template: {response.output}"
            )

        # Insert progress comment with template output
        comment = CapeComment(
            issue_id=issue_id,
            comment="Review issues template executed successfully",
            raw={"template_output": response.output[:1000]},  # First 1000 chars of output
            source="system",
            type="artifact",
        )
        status, msg = insert_progress_comment(comment)
        if status != "success":
            logger.error(f"Failed to insert template notification comment: {msg}")
        else:
            logger.debug(f"Template notification comment inserted: {msg}")

        return StepResult.ok(None)

    except Exception as e:
        logger.error(f"Failed to address review issues: {e}")
        return StepResult.fail(f"Failed to address review issues: {e}")
