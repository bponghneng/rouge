"""Implementation functionality for workflow orchestration."""

import logging

from rouge.core.agent import execute_implement_plan
from rouge.core.agents import AgentExecuteResponse
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.workflow.shared import AGENT_PLAN_IMPLEMENTOR
from rouge.core.workflow.types import ImplementData, StepResult

logger = logging.getLogger(__name__)

# Required fields for implement output JSON
IMPLEMENT_REQUIRED_FIELDS = {
    "files_modified": list,
    "git_diff_stat": str,
    "output": str,
    "planPath": str,
    "status": str,
    "summary": str,
}


def implement_plan(plan_content: str, issue_id: int, adw_id: str) -> StepResult[ImplementData]:
    """Implement the plan using configured provider.

    Uses the provider configured via ROUGE_IMPLEMENT_PROVIDER environment variable.
    Defaults to Claude if not set.

    Args:
        plan_content: The plan content (markdown) to implement
        issue_id: Issue ID for tracking
        adw_id: Workflow ID for tracking

    Returns:
        StepResult with ImplementData containing output and optional session_id
    """
    # Use new execute_implement_plan helper which handles provider selection
    response: AgentExecuteResponse = execute_implement_plan(
        plan_content=plan_content,
        issue_id=issue_id,
        adw_id=adw_id,
        agent_name=AGENT_PLAN_IMPLEMENTOR,
    )

    logger.debug(
        "implement response: success=%s, session_id=%s",
        response.success,
        response.session_id,
    )

    if not response.success:
        return StepResult.fail(response.output)

    # Parse and validate JSON output
    parse_result = parse_and_validate_json(
        response.output, IMPLEMENT_REQUIRED_FIELDS, step_name="implement"
    )
    if not parse_result.success:
        return StepResult.fail(parse_result.error or "JSON parsing failed")

    return StepResult.ok(
        ImplementData(output=response.output, session_id=response.session_id),
        parsed_data=parse_result.data,
    )
