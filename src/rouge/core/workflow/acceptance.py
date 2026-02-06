"""Plan acceptance validation functionality for workflow orchestration."""

import json
import logging
from typing import Callable, Optional

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.workflow.schemas import ACCEPTANCE_SCHEMA
from rouge.core.workflow.shared import AGENT_VALIDATOR
from rouge.core.workflow.types import StepResult

logger = logging.getLogger(__name__)

# Required fields for acceptance validation output JSON
ACCEPTANCE_REQUIRED_FIELDS = {
    "output": str,
    "notes": list,
    "plan_title": str,
    "requirements": list,
    "status": str,
    "summary": str,
    "unmet_blocking_requirements": list,
}


def notify_plan_acceptance(
    plan_content: str,
    issue_id: int,
    adw_id: str,
    stream_handler: Optional[Callable[[str], None]] = None,
) -> StepResult[None]:
    """Validate implementation against plan content.

    Args:
        plan_content: The plan content (markdown) to validate against
        issue_id: Rouge issue ID for tracking
        adw_id: Workflow ID for tracking
        stream_handler: Optional callback for streaming output

    Returns:
        StepResult with None data (success/failure only)
    """
    try:
        if not plan_content:
            logger.error("Plan content is empty")
            return StepResult.fail("Plan content is empty")

        logger.debug("Invoking /adw-acceptance template with plan content")

        # Create template request with plan content as argument
        request = ClaudeAgentTemplateRequest(
            agent_name=AGENT_VALIDATOR,
            slash_command="/adw-acceptance",
            args=[plan_content],
            adw_id=adw_id,
            issue_id=issue_id,
            model="sonnet",
            json_schema=json.dumps(ACCEPTANCE_SCHEMA),
        )

        logger.debug(
            "notify_plan_acceptance request: %s",
            request.model_dump_json(indent=2, by_alias=True),
        )

        # Execute template
        response = execute_template(request, stream_handler=stream_handler)

        logger.debug(
            "notify_plan_acceptance response: success=%s",
            response.success,
        )

        if not response.success:
            logger.error("Failed to execute /adw-acceptance template: %s", response.output)
            return StepResult.fail(f"Failed to execute /adw-acceptance template: {response.output}")

        # Parse and validate JSON output
        parse_result = parse_and_validate_json(
            response.output, ACCEPTANCE_REQUIRED_FIELDS, step_name="acceptance"
        )
        if not parse_result.success:
            return StepResult.fail(parse_result.error or "JSON parsing failed")

        return StepResult.ok(None, parsed_data=parse_result.data)

    except Exception as e:
        logger.error("Failed to notify plan acceptance template: %s", e)
        return StepResult.fail(f"Failed to notify plan acceptance template: {e}")
