"""Agent provider registry and factory.

This module provides a central registry for coding agent providers,
allowing selection via explicit parameters or environment variables.
Supports multiple provider instances (e.g., different Claude configurations).
"""

import logging
import os
from typing import Dict, Optional

from cape.core.agents.base import CodingAgent
from cape.core.agents.claude import ClaudeAgent
from cape.core.agents.opencode import OpenCodeAgent

_DEFAULT_LOGGER = logging.getLogger(__name__)

# Internal registry mapping provider names to agent instances
_AGENTS: Dict[str, CodingAgent] = {}


def register_agent(name: str, agent: CodingAgent) -> None:
    """Register a coding agent provider.

    Args:
        name: Provider name (e.g., "claude", "claude_alt", "aider")
        agent: CodingAgent implementation instance

    Raises:
        ValueError: If name is empty or agent is not a CodingAgent instance
    """
    if not name or not isinstance(name, str):
        raise ValueError("Provider name must be a non-empty string")

    if not isinstance(agent, CodingAgent):
        raise ValueError(f"Agent must be a CodingAgent instance, got {type(agent)}")

    _AGENTS[name] = agent
    _DEFAULT_LOGGER.debug("Registered agent provider: %s", name)


def get_agent(provider: Optional[str] = None) -> CodingAgent:
    """Get a coding agent provider by name.

    Provider selection priority:
    1. Explicit provider parameter
    2. CAPE_AGENT_PROVIDER environment variable
    3. Default to "claude"

    Args:
        provider: Optional explicit provider name

    Returns:
        CodingAgent instance for the selected provider

    Raises:
        ValueError: If provider not found in registry

    Example:
        # Use default provider (claude)
        agent = get_agent()

        # Use explicit provider
        agent = get_agent("claude_alt")

        # Use environment variable
        os.environ["CAPE_AGENT_PROVIDER"] = "aider"
        agent = get_agent()
    """
    # Determine provider name
    if provider is None:
        provider = os.getenv("CAPE_AGENT_PROVIDER")

    if provider is None:
        provider = "claude"

    # Look up in registry
    if provider not in _AGENTS:
        available = list(_AGENTS.keys())
        raise ValueError(
            f"Agent provider '{provider}' not registered. " f"Available providers: {available}"
        )

    return _AGENTS[provider]


def get_implement_provider() -> str:
    """Get the provider name for the implementation step.

    Provider selection priority:
    1. CAPE_IMPLEMENT_PROVIDER environment variable
    2. CAPE_AGENT_PROVIDER environment variable (fallback)
    3. Default to "claude"

    This function allows selective provider usage for the implementation
    step while keeping classification and planning with Claude.

    Returns:
        Provider name string (e.g., "claude", "opencode")

    Example:
        # Use OpenCode for implementation
        os.environ["CAPE_IMPLEMENT_PROVIDER"] = "opencode"
        provider_name = get_implement_provider()  # Returns "opencode"

        # Fallback to general provider setting
        os.environ["CAPE_AGENT_PROVIDER"] = "opencode"
        provider_name = get_implement_provider()  # Returns "opencode"

        # Default behavior
        provider_name = get_implement_provider()  # Returns "claude"
    """
    # Check CAPE_IMPLEMENT_PROVIDER first (most specific)
    provider = os.getenv("CAPE_IMPLEMENT_PROVIDER")

    # Fallback to CAPE_AGENT_PROVIDER
    if provider is None:
        provider = os.getenv("CAPE_AGENT_PROVIDER")

    # Default to claude
    if provider is None:
        provider = "claude"

    _DEFAULT_LOGGER.debug("Selected implementation provider: %s", provider)
    return provider


# Register default Claude provider
register_agent("claude", ClaudeAgent())
_DEFAULT_LOGGER.debug("Default Claude agent provider registered")

# Register OpenCode provider
register_agent("opencode", OpenCodeAgent())
_DEFAULT_LOGGER.debug("OpenCode agent provider registered")
