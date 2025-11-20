"""Provider-agnostic agent execution facade.

This module provides a backward-compatible facade over the agent registry,
maintaining the original API while delegating to the new abstraction layer.

For new code, prefer importing from cape.core.agents directly:
    from cape.core.agents import get_agent, AgentExecuteRequest
"""

import logging
import os
from typing import Callable, Optional

from cape.core.agents import AgentExecuteRequest, AgentExecuteResponse, get_agent, get_implement_provider
from cape.core.agents.claude import (
    ClaudeAgentPromptRequest,
    ClaudeAgentPromptResponse,
    ClaudeAgentTemplateRequest,
    execute_claude_template,
)
from cape.core.notifications import insert_progress_comment, make_progress_comment_handler

_DEFAULT_LOGGER = logging.getLogger(__name__)


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
        insert_progress_comment(
            request.issue_id, f"Output saved to: {response.raw_output_path}", logger
        )

    # Map AgentExecuteResponse to ClaudeAgentPromptResponse
    return ClaudeAgentPromptResponse(
        output=response.output, success=response.success, session_id=response.session_id
    )


def execute_template(request: ClaudeAgentTemplateRequest) -> ClaudeAgentPromptResponse:
    """Execute a Claude Code template with slash command and arguments.

    Legacy function for backward compatibility. Delegates to Claude provider
    template helper.

    Args:
        request: Claude-specific template request

    Returns:
        Claude-specific prompt response
    """
    return execute_claude_template(request)


def execute_agent_prompt(
    request: AgentExecuteRequest,
    provider: Optional[str] = None,
    *,
    stream_handler: Optional[Callable[[str], None]] = None
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
    plan_file: str,
    issue_id: int,
    adw_id: str,
    agent_name: str,
    logger: logging.Logger
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
        # Claude uses /implement with file path (template reads file)
        prompt = f"/implement {plan_file}"
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

    # Insert final progress comment if successful
    if response.success and response.raw_output_path:
        insert_progress_comment(
            issue_id, f"Implementation complete. Output saved to: {response.raw_output_path}", logger
        )

    return response
