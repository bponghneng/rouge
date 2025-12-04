"""Plan building functionality for workflow orchestration."""

from logging import Logger
from typing import Callable, Optional

from cape.core.agent import execute_template
from cape.core.agents.claude import ClaudeAgentTemplateRequest
from cape.core.models import CapeIssue
from cape.core.workflow.json_parser import parse_and_validate_json
from cape.core.workflow.shared import AGENT_PLANNER
from cape.core.workflow.types import ClassifySlashCommand, PlanData, StepResult

# Required fields for plan output JSON
# Plan output must have output, planPath, summary
PLAN_REQUIRED_FIELDS = {
    "output": str,
    "planPath": str,
    "summary": str,
}


def build_plan(
    issue: CapeIssue,
    command: ClassifySlashCommand,
    adw_id: str,
    logger: Logger,
    stream_handler: Optional[Callable[[str], None]] = None,
) -> StepResult[PlanData]:
    """Build implementation plan for the issue using the specified command.

    Args:
        issue: The Cape issue to plan for
        command: The triage command to use (e.g., /triage:feature)
        adw_id: Workflow ID for tracking
        logger: Logger instance
        stream_handler: Optional callback for streaming output

    Returns:
        StepResult with PlanData containing output and optional session_id
    """
    request = ClaudeAgentTemplateRequest(
        agent_name=AGENT_PLANNER,
        slash_command=command,
        args=[issue.description],
        adw_id=adw_id,
        issue_id=issue.id,
        model="sonnet",
    )
    logger.debug(
        "build_plan request: %s",
        request.model_dump_json(indent=2, by_alias=True),
    )
    response = execute_template(request, stream_handler=stream_handler)
    logger.debug(
        "build_plan response: %s",
        response.model_dump_json(indent=2, by_alias=True),
    )

    if not response.success:
        return StepResult.fail(response.output)

    # Parse and validate JSON output
    parse_result = parse_and_validate_json(
        response.output, PLAN_REQUIRED_FIELDS, logger, step_name="build_plan"
    )
    if not parse_result.success:
        return StepResult.fail(parse_result.error or "JSON parsing failed")

    return StepResult.ok(
        PlanData(output=response.output, session_id=response.session_id),
        parsed_data=parse_result.data,
    )
