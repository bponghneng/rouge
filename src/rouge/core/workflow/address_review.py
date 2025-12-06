"""Review issue addressing functionality for workflow orchestration."""

import os
from logging import Logger
from typing import Callable, Optional

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.models import Comment
from rouge.core.notifications import insert_progress_comment
from rouge.core.workflow.shared import AGENT_IMPLEMENTOR
from rouge.core.workflow.types import StepResult
from rouge.core.workflow.workflow_io import emit_progress_comment

# Required fields for address review output JSON
ADDRESS_REVIEW_REQUIRED_FIELDS = {
    "issues": list,
    "output": str,
    "summary": str,
}


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
        issue_id: Issue ID for tracking
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

        # Execute template - now requiring JSON with proper validation
        response = execute_template(request, stream_handler=stream_handler, require_json=True)

        logger.debug(
            "address_review_issues response: success=%s",
            response.success,
        )

        # Emit raw LLM response for debugging visibility
        emit_progress_comment(
            issue_id,
            "Address review LLM response received",
            logger,
            raw={"output": "address-review-response", "llm_response": response.output},
        )

        if not response.success:
            logger.error(f"Failed to execute /adw-implement-review template: {response.output}")
            return StepResult.fail(
                f"Failed to execute /adw-implement-review template: {response.output}"
            )

        # Parse and validate JSON output
        parse_result = parse_and_validate_json(
            response.output,
            ADDRESS_REVIEW_REQUIRED_FIELDS,
            logger,
            step_name="address_review",
        )
        if not parse_result.success:
            return StepResult.fail(parse_result.error or "JSON parsing failed")

        # Insert progress comment with parsed template output
        comment = Comment(
            issue_id=issue_id,
            comment="Review issues template executed successfully",
            raw={"template_output": parse_result.data},
            source="system",
            type="artifact",
        )
        status, msg = insert_progress_comment(comment)
        if status != "success":
            logger.error(f"Failed to insert template notification comment: {msg}")
        else:
            logger.debug(f"Template notification comment inserted: {msg}")

        return StepResult.ok(None, parsed_data=parse_result.data)

    except Exception as e:
        logger.error(f"Failed to address review issues: {e}")
        return StepResult.fail(f"Failed to address review issues: {e}")
