"""Provider-agnostic coding agent interfaces and registry.

This package provides a clean abstraction for integrating multiple
coding agent providers (Claude Code, Aider, Cursor, etc.) with Cape.

Use get_agent() to obtain the configured provider instance.

Example:
    from cape.core.agents import get_agent, AgentExecuteRequest

    # Get default agent (usually Claude)
    agent = get_agent()

    # Execute a prompt
    request = AgentExecuteRequest(
        prompt="/implement feature.md",
        issue_id=123,
        adw_id="adw-456",
        agent_name="implementor"
    )
    response = agent.execute_prompt(request)
"""

from cape.core.agents.base import AgentExecuteRequest, AgentExecuteResponse, CodingAgent
from cape.core.agents.claude import ClaudeAgent
from cape.core.agents.opencode import OpenCodeAgent
from cape.core.agents.registry import get_agent, get_implement_provider, register_agent

__all__ = [
    "CodingAgent",
    "AgentExecuteRequest",
    "AgentExecuteResponse",
    "ClaudeAgent",
    "OpenCodeAgent",
    "get_agent",
    "get_implement_provider",
    "register_agent",
]
