"""Plan file path extraction functionality for workflow orchestration."""

from logging import Logger

from cape.core.agent import execute_template
from cape.core.agents.claude import ClaudeAgentTemplateRequest
from cape.core.workflow.shared import AGENT_PLAN_FINDER
from cape.core.workflow.types import PlanFileData, StepResult


def get_plan_file(
    plan_output: str, issue_id: int, adw_id: str, logger: Logger
) -> StepResult[PlanFileData]:
    """Get the path to the plan file that was just created.

    Args:
        plan_output: The output from the build_plan step
        issue_id: Cape issue ID for tracking
        adw_id: Workflow ID for tracking
        logger: Logger instance

    Returns:
        StepResult with PlanFileData containing file path
    """
    request = ClaudeAgentTemplateRequest(
        agent_name=AGENT_PLAN_FINDER,
        slash_command="/adw-find-plan-file",
        args=[plan_output],
        adw_id=adw_id,
        issue_id=issue_id,
        model="sonnet",
    )
    logger.debug(
        "get_plan_file request: %s",
        request.model_dump_json(indent=2, by_alias=True),
    )
    # FindPlanFileStep returns a plain text file path, not JSON
    response = execute_template(request, require_json=False)
    logger.debug(
        "get_plan_file response: %s",
        response.model_dump_json(indent=2, by_alias=True),
    )

    if not response.success:
        return StepResult.fail(response.output)

    # Clean up the response - get just the file path
    file_path = response.output.strip()

    # Validate it looks like a file path
    if file_path and file_path != "0" and "/" in file_path:
        return StepResult.ok(PlanFileData(file_path=file_path))
    elif file_path == "0":
        return StepResult.fail("No plan file found in output")
    else:
        # If response doesn't look like a path, return error
        return StepResult.fail(f"Invalid file path response: {file_path}")
