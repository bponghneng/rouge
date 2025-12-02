"""Provider-agnostic agent execution facade.

This module provides a backward-compatible facade over the agent registry,
maintaining the original API while delegating to the new abstraction layer.

For new code, prefer importing from cape.core.agents directly:
    from cape.core.agents import get_agent, AgentExecuteRequest
"""

import json
import logging
import re
from typing import Callable, Optional

from cape.core.agents import (
    AgentExecuteRequest,
    AgentExecuteResponse,
    get_agent,
    get_implement_provider,
)
from cape.core.agents.claude import (
    ClaudeAgentPromptRequest,
    ClaudeAgentPromptResponse,
    ClaudeAgentTemplateRequest,
    execute_claude_template,
)
from cape.core.models import CapeComment
from cape.core.notifications import insert_progress_comment, make_progress_comment_handler

_DEFAULT_LOGGER = logging.getLogger(__name__)

# Regex pattern to match Markdown code fences wrapping JSON
# Matches: ```json\n...\n``` or ```\n...\n```
_MARKDOWN_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*\n(.*?)\n```\s*$", re.DOTALL)


def _sanitize_json_output(output: str) -> str:
    """Strip Markdown code fences from JSON output if present.

    LLM outputs may wrap JSON in Markdown code fences (e.g., ```json ... ```).
    This helper detects and removes such fencing to extract the raw JSON content.

    Args:
        output: Raw output string that may contain Markdown code fences

    Returns:
        The inner content if Markdown fences are found, otherwise the original output
    """
    stripped = output.strip()
    match = _MARKDOWN_FENCE_PATTERN.match(stripped)
    if match:
        return match.group(1).strip()
    return output


def _get_issue_logger(adw_id: str) -> logging.Logger:
    """Return logger bound to a specific workflow or fall back to module logger."""
    issue_logger = logging.getLogger(f"cape_{adw_id}")
    return issue_logger if issue_logger.handlers else _DEFAULT_LOGGER


def prompt_claude_code(request: ClaudeAgentPromptRequest) -> ClaudeAgentPromptResponse:
    """Execute Claude Code with the given prompt configuration.

    Legacy function for backward compatibility. Prefer using get_agent()
    and AgentExecuteRequest directly for new code.

    Args:
        request: Claude-specific prompt request

    Returns:
        Claude-specific prompt response
    """
    # Map ClaudeAgentPromptRequest to AgentExecuteRequest
    agent_request = AgentExecuteRequest(
        prompt=request.prompt,
        issue_id=request.issue_id,
        adw_id=request.adw_id,
        agent_name=request.agent_name,
        model=request.model,
        output_path=request.output_file,
        provider_options={"dangerously_skip_permissions": request.dangerously_skip_permissions},
    )

    # Create progress comment handler
    logger = _get_issue_logger(request.adw_id)
    handler = make_progress_comment_handler(request.issue_id, request.adw_id, logger)

    # Get agent and execute
    agent = get_agent("claude")
    response = agent.execute_prompt(agent_request, stream_handler=handler)

    # Insert final progress comment if successful
    if response.success and response.raw_output_path:
        comment = CapeComment(
            issue_id=request.issue_id,
            comment=f"Output saved to: {response.raw_output_path}",
            raw={},
            source="agent",
            type="claude",
        )
        status, msg = insert_progress_comment(comment)
        logger.debug(msg) if status == "success" else logger.error(msg)

    # Map AgentExecuteResponse to ClaudeAgentPromptResponse
    return ClaudeAgentPromptResponse(
        output=response.output, success=response.success, session_id=response.session_id
    )


def execute_template(
    request: ClaudeAgentTemplateRequest,
    stream_handler: Optional[Callable[[str], None]] = None,
    *,
    require_json: bool = True,
) -> ClaudeAgentPromptResponse:
    """Execute a Claude Code template with slash command and arguments.

    Legacy function for backward compatibility. Delegates to Claude provider
    template helper. Enforces JSON parsing and emits progress comments with
    parsed data in the raw field.

    Args:
        request: Claude-specific template request
        stream_handler: Optional callback for streaming output
        require_json: If True (default), validates output as JSON and emits
            error comments for non-JSON output. If False, skips JSON validation
            and allows plain text output (used by FindPlanFileStep and
            GenerateReviewStep).

    Returns:
        Claude-specific prompt response
    """
    response = execute_claude_template(request, stream_handler=stream_handler)
    logger = _get_issue_logger(request.adw_id)

    # Import here to avoid circular import
    from cape.core.workflow.workflow_io import emit_progress_comment

    # Handle JSON validation based on require_json parameter
    if response.success and response.output:
        raw_output = response.output.strip()

        if require_json:
            # Sanitize output to strip Markdown code fences before parsing
            sanitized_output = _sanitize_json_output(raw_output)
            try:
                parsed_json = json.loads(sanitized_output)
                # Emit progress comment with parsed JSON in raw field
                emit_progress_comment(
                    issue_id=request.issue_id,
                    message=f"Template {request.slash_command} completed",
                    logger=logger,
                    raw={"template": request.slash_command, "result": parsed_json},
                    comment_type="workflow",
                )
                logger.debug("Template output parsed as JSON successfully")
            except json.JSONDecodeError as exc:
                # Emit error progress comment for non-JSON output
                logger.error("Template output is not valid JSON: %s", exc)
                emit_progress_comment(
                    issue_id=request.issue_id,
                    message=f"Template {request.slash_command} returned non-JSON output",
                    logger=logger,
                    raw={
                        "template": request.slash_command,
                        "error": str(exc),
                        "output": raw_output[:500],
                    },
                    comment_type="workflow",
                )
        else:
            # Skip JSON validation for plain text output (FindPlanFileStep, GenerateReviewStep)
            emit_progress_comment(
                issue_id=request.issue_id,
                message=f"Template {request.slash_command} completed",
                logger=logger,
                raw={"template": request.slash_command, "output": raw_output[:500]},
                comment_type="workflow",
            )
            logger.debug("Template output accepted as plain text (require_json=False)")

    return response


def execute_agent_prompt(
    request: AgentExecuteRequest,
    provider: Optional[str] = None,
    *,
    stream_handler: Optional[Callable[[str], None]] = None,
) -> AgentExecuteResponse:
    """Execute agent prompt with specified or default provider.

    This is the new provider-agnostic API for agent execution.
    Use stream_handler for notifications and progress tracking.

    Args:
        request: Provider-agnostic execution request
        provider: Optional provider name (defaults to "claude")
        stream_handler: Optional callback for streaming output

    Returns:
        Provider-agnostic execution response

    Example:
        from cape.core.agent import execute_agent_prompt
        from cape.core.agents import AgentExecuteRequest
        from cape.core.notifications import make_progress_comment_handler

        request = AgentExecuteRequest(
            prompt="/implement plan.md",
            issue_id=123,
            adw_id="adw-456",
            agent_name="implementor"
        )
        handler = make_progress_comment_handler(123, "adw-456", logger)
        response = execute_agent_prompt(request, stream_handler=handler)
    """
    agent = get_agent(provider)
    return agent.execute_prompt(request, stream_handler=stream_handler)


def execute_implement_plan(
    plan_file: str, issue_id: int, adw_id: str, agent_name: str, logger: logging.Logger
) -> AgentExecuteResponse:
    """Execute implementation plan using configured provider.

    This helper function executes the plan using the provider configured
    via CAPE_IMPLEMENT_PROVIDER environment variable. It automatically
    handles progress comment integration and provider-specific formatting.

    Provider selection priority:
    1. CAPE_IMPLEMENT_PROVIDER environment variable
    2. CAPE_AGENT_PROVIDER environment variable (fallback)
    3. Default to "claude"

    Provider-specific behavior:
    - Claude: Uses /implement slash command with file path
    - OpenCode: Reads file content and passes directly with --command implement

    Args:
        plan_file: Path to the plan file to implement
        issue_id: Cape issue ID for tracking
        adw_id: Workflow ID for tracking
        agent_name: Agent name for directory structure
        logger: Logger instance for logging

    Returns:
        AgentExecuteResponse with execution results

    Example:
        from cape.core.agent import execute_implement_plan

        response = execute_implement_plan(
            plan_file="specs/feature-plan.md",
            issue_id=123,
            adw_id="adw-456",
            agent_name="sdlc_implementor",
            logger=logger
        )
    """
    # Get the configured provider for implementation
    provider_name = get_implement_provider()
    logger.info(f"Using provider '{provider_name}' for implementation")

    # Provider-specific prompt construction
    if provider_name == "claude":
        # Claude uses /adw-implement-plan with file path (template reads file)
        prompt = f"/adw-implement-plan {plan_file}"
    else:
        # Other providers (e.g., OpenCode) need file content directly
        try:
            with open(plan_file, "r") as f:
                prompt = f.read()
        except Exception as e:
            error_msg = f"Failed to read plan file {plan_file}: {e}"
            logger.error(error_msg)
            return AgentExecuteResponse(
                output=error_msg,
                success=False,
                session_id=None,
                raw_output_path=None,
                error_detail=str(e),
            )

    # Create AgentExecuteRequest
    request = AgentExecuteRequest(
        prompt=prompt,
        issue_id=issue_id,
        adw_id=adw_id,
        agent_name=agent_name,
    )

    # Create progress comment handler
    handler = make_progress_comment_handler(issue_id, adw_id, logger, provider=provider_name)

    # Get agent and execute
    agent = get_agent(provider_name)
    response = agent.execute_prompt(request, stream_handler=handler)

    return response
