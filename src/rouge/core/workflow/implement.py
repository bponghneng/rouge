"""Implementation functionality for workflow orchestration."""

import logging

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.workflow.shared import AGENT_PLAN_IMPLEMENTOR
from rouge.core.workflow.types import ImplementData, StepResult

logger = logging.getLogger(__name__)

# Required fields for implement output JSON
IMPLEMENT_REQUIRED_FIELDS = {
    "files_modified": list,
    "git_diff_stat": str,
    "output": str,
    "status": str,
    "summary": str,
}

IMPLEMENT_JSON_SCHEMA = """{
  "type": "object",
  "properties": {
    "files_modified": { "type": "array", "items": { "type": "string" } },
    "git_diff_stat": { "type": "string" },
    "output": { "type": "string", "enum": ["implement-plan"] },
    "status": { "type": "string" },
    "summary": { "type": "string" }
  },
  "required": ["files_modified", "git_diff_stat", "output", "status", "summary"]
}"""


def implement_plan(plan_content: str, issue_id: int, adw_id: str) -> StepResult[ImplementData]:
    """Implement the plan using Claude Code template.

    Uses the /adw-implement-plan slash command via execute_template pattern.

    Args:
        plan_content: The plan content (markdown) to implement
        issue_id: Issue ID for tracking
        adw_id: Workflow ID for tracking

    Returns:
        StepResult with ImplementData containing output and optional session_id
    """
    # Create template request with /adw-implement-plan slash command
    request = ClaudeAgentTemplateRequest(
        slash_command="/adw-implement-plan",
        args=[plan_content.lstrip()],
        issue_id=issue_id,
        adw_id=adw_id,
        agent_name=AGENT_PLAN_IMPLEMENTOR,
        json_schema=IMPLEMENT_JSON_SCHEMA,
    )

    # Execute template
    response = execute_template(request)

    logger.debug(
        "implement response: success=%s, session_id=%s",
        response.success,
        response.session_id,
    )

    if not response.success:
        error_message = response.output or "Implement step failed"
        return StepResult.fail(error_message)

    # Guard: Check that response.output is present before parsing
    if not response.output:
        return StepResult.fail("Implement step returned empty output")

    # Parse and validate JSON output with IMPLEMENT_REQUIRED_FIELDS
    parse_result = parse_and_validate_json(
        response.output, IMPLEMENT_REQUIRED_FIELDS, step_name="implement"
    )
    if not parse_result.success:
        return StepResult.fail(parse_result.error or "JSON parsing failed")

    return StepResult.ok(
        ImplementData(output=response.output, session_id=response.session_id),
        parsed_data=parse_result.data,
    )
