"""Plan acceptance validation functionality for workflow orchestration."""

import os
from logging import Logger
from typing import Callable, Optional

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.workflow.shared import AGENT_VALIDATOR
from rouge.core.workflow.types import StepResult

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
    plan_path: str,
    issue_id: int,
    adw_id: str,
    logger: Logger,
    stream_handler: Optional[Callable[[str], None]] = None,
) -> StepResult[None]:
    """Notify the /plan-acceptance template with the plan file to validate.

    Validates implementation against plan.

    Args:
        plan_path: Path to the plan file to validate
        issue_id: Rouge issue ID for tracking
        adw_id: Workflow ID for tracking
        logger: Logger instance
        stream_handler: Optional callback for streaming output

    Returns:
        StepResult with None data (success/failure only)
    """
    try:
        # Validate plan file exists
        if not os.path.exists(plan_path):
            logger.error(f"Plan file does not exist: {plan_path}")
            return StepResult.fail(f"Plan file does not exist: {plan_path}")

        logger.debug(f"Invoking /adw-acceptance template with plan file: {plan_path}")

        # Create template request
        request = ClaudeAgentTemplateRequest(
            agent_name=AGENT_VALIDATOR,
            slash_command="/adw-acceptance",
            args=[plan_path],
            adw_id=adw_id,
            issue_id=issue_id,
            model="sonnet",
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
            logger.error(f"Failed to execute /adw-acceptance template: {response.output}")
            return StepResult.fail(f"Failed to execute /adw-acceptance template: {response.output}")

        # Parse and validate JSON output
        parse_result = parse_and_validate_json(
            response.output, ACCEPTANCE_REQUIRED_FIELDS, logger, step_name="acceptance"
        )
        if not parse_result.success:
            return StepResult.fail(parse_result.error or "JSON parsing failed")

        return StepResult.ok(None, parsed_data=parse_result.data)

    except Exception as e:
        logger.error(f"Failed to notify plan acceptance template: {e}")
        return StepResult.fail(f"Failed to notify plan acceptance template: {e}")
