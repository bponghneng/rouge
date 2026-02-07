import logging
from typing import Callable, Optional

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.workflow.schemas import IMPLEMENT_REVIEW_JSON_SCHEMA
from rouge.core.workflow.types import StepResult

logger = logging.getLogger(__name__)

# Required fields for address review output JSON
ADDRESS_REVIEW_REQUIRED_FIELDS = {
    "issues": list,
    "output": str,
    "summary": str,
}


def address_review_issues(
    issue_id: int | None,
    adw_id: str,
    review_text: str,
    stream_handler: Optional[Callable[[str], None]] = None,
) -> StepResult:
    """Address issues found in the review.

    This step runs the /adw-implement-review slash command to address
    the issues identified in the review step.

    Args:
        issue_id: Optional Issue ID (None for standalone review)
        adw_id: ADW workflow ID
        review_text: The review text containing issues to address
        stream_handler: Optional handler for streaming output

    Returns:
        StepResult indicating success or failure
    """
    logger.info("Addressing review issues for issue %s (adw_id=%s)", issue_id, adw_id)

    if not review_text or not review_text.strip():
        logger.error("Review text is empty")
        return StepResult.fail("Review text is empty")

    try:
        # Construct the template request
        # Pass the review text as an argument to the slash command
        request = ClaudeAgentTemplateRequest(
            agent_name="code_review",
            slash_command="/adw-implement-review",
            args=[review_text],
            adw_id=adw_id,
            issue_id=issue_id,
            model="sonnet",
            json_schema=IMPLEMENT_REVIEW_JSON_SCHEMA,
        )

        logger.debug(
            "address_review request: %s",
            request.model_dump_json(indent=2, by_alias=True),
        )

        # Execute the template
        response = execute_template(request, stream_handler=stream_handler, require_json=True)

        logger.debug("address_review response: success=%s", response.success)

        # Emit progress comment
        payload = CommentPayload(
            issue_id=issue_id,
            text="Addressing review issues...",
            raw={"output": "address-review-response", "llm_response": response.output},
            source="system",
            kind="workflow",
            adw_id=adw_id,
        )
        status, msg = emit_comment_from_payload(payload)
        if status == "success":
            logger.debug(msg)
        else:
            logger.error(msg)

        if not response.success:
            logger.error("Failed to execute /adw-implement-review template: %s", response.output)
            return StepResult.fail(
                f"Failed to execute /adw-implement-review template: {response.output}"
            )

        # Parse and validate JSON output
        parse_result = parse_and_validate_json(
            response.output,
            ADDRESS_REVIEW_REQUIRED_FIELDS,
            step_name="address_review",
        )
        if not parse_result.success:
            return StepResult.fail(parse_result.error or "JSON parsing failed")

        logger.info("Review issues addressed successfully")

        # Emit result comment
        parsed_data = parse_result.data or {}
        result_payload = CommentPayload(
            issue_id=issue_id,
            text="Review issues addressed",
            raw={
                "output": parsed_data.get("output", ""),
                "summary": parsed_data.get("summary", ""),
                "issues": parsed_data.get("issues", []),
                "parsed_data": parsed_data,
            },
            source="system",
            kind="address_review",
            adw_id=adw_id,
        )
        status, msg = emit_comment_from_payload(result_payload)
        if status == "success":
            logger.debug(msg)
        else:
            logger.error(msg)

        return StepResult.ok(None, parsed_data=parse_result.data)

    except Exception as e:
        logger.exception("Failed to address review issues")
        return StepResult.fail(f"Failed to address review issues: {e}")
