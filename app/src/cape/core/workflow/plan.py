"""Plan building functionality for workflow orchestration."""

from logging import Logger

from cape.core.agent import execute_template
from cape.core.agents.claude import ClaudeAgentPromptResponse, ClaudeAgentTemplateRequest
from cape.core.models import CapeIssue, SlashCommand
from cape.core.workflow.shared import AGENT_PLANNER


def build_plan(
    issue: CapeIssue, command: SlashCommand, adw_id: str, logger: Logger
) -> ClaudeAgentPromptResponse:
    """Build implementation plan for the issue using the specified command.

    Args:
        issue: The Cape issue to plan for
        command: The triage command to use (e.g., /triage:feature)
        adw_id: Workflow ID for tracking
        logger: Logger instance

    Returns:
        Agent response with plan output
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
    response = execute_template(request)
    logger.debug(
        "build_plan response: %s",
        response.model_dump_json(indent=2, by_alias=True),
    )
    return response