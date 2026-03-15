"""Shared plan-building constants and helpers for PlanStep and PatchPlanStep.

Both steps produce a PlanArtifact from the same JSON schema; centralising the
schema and the template-execution logic avoids divergence across copies.
"""

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.models import Issue
from rouge.core.prompts import PromptId
from rouge.core.utils import get_logger
from rouge.core.workflow.shared import AGENT_PLANNER
from rouge.core.workflow.types import PlanData, StepResult

# Required fields for plan output JSON.
# Plan output must have type, output, plan (inline content), summary.
PLAN_REQUIRED_FIELDS = {
    "type": str,
    "output": str,
    "plan": str,
    "summary": str,
}

PLAN_JSON_SCHEMA = """{
  "type": "object",
  "properties": {
    "type": { "type": "string", "minLength": 1 },
    "output": { "type": "string", "const": "plan" },
    "plan": { "type": "string", "minLength": 1 },
    "summary": { "type": "string", "minLength": 1 }
  },
  "required": ["type", "output", "plan", "summary"]
}"""


def build_plan_from_template(
    issue: Issue,
    prompt_id: PromptId,
    adw_id: str,
) -> StepResult[PlanData]:
    """Build an implementation plan by executing *prompt_id* against *issue*.

    Shared by PlanStep and PatchPlanStep so that schema changes and empty-output
    guards are applied consistently in both paths.

    Args:
        issue: The Rouge issue to plan for.
        prompt_id: The planning prompt to use (e.g. PromptId.FEATURE_PLAN).
        adw_id: Workflow ID used for scoped logging.

    Returns:
        StepResult with PlanData containing the plan text and optional session_id.
    """
    logger = get_logger(adw_id)
    request = ClaudeAgentTemplateRequest(
        agent_name=AGENT_PLANNER,
        prompt_id=prompt_id,
        args=[issue.description],
        adw_id=adw_id,
        issue_id=issue.id,
        model="sonnet",
        json_schema=PLAN_JSON_SCHEMA,
    )
    logger.debug(
        "build_plan request: %s",
        request.model_dump_json(indent=2, by_alias=True),
    )
    response = execute_template(request)
    logger.debug(
        "build_plan response: %s",
        response.model_dump_json(indent=2, by_alias=True),
    )

    if not response.success:
        return StepResult.fail(response.output or "Agent failed without message")

    # Guard: ensure output is present before attempting JSON parse.
    if not response.output:
        return StepResult.fail("No output from template execution")

    # Parse and validate JSON output.
    parse_result = parse_and_validate_json(
        response.output, PLAN_REQUIRED_FIELDS, step_name="build_plan"
    )
    if not parse_result.success:
        return StepResult.fail(parse_result.error or "JSON parsing failed")

    parsed_data = parse_result.data or {}
    return StepResult.ok(
        PlanData(
            plan=parsed_data.get("plan", ""),
            summary=parsed_data.get("summary", ""),
            session_id=response.session_id,
        ),
        parsed_data=parsed_data,
    )
