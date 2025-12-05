"""Tests for agent registry."""

import pytest

from cape.core.agents.base import AgentExecuteRequest, AgentExecuteResponse, CodingAgent
from cape.core.agents.claude import ClaudeAgent
from cape.core.agents.opencode import OpenCodeAgent
from cape.core.agents.registry import get_agent, get_implement_provider, register_agent


def test_get_agent_default():
    """Test getting default agent (claude)."""
    agent = get_agent()
    assert isinstance(agent, ClaudeAgent)


def test_get_agent_explicit_claude():
    """Test getting claude agent explicitly."""
    agent = get_agent("claude")
    assert isinstance(agent, ClaudeAgent)


def test_get_agent_environment_variable(monkeypatch):
    """Test getting agent via CAPE_AGENT_PROVIDER environment variable."""
    monkeypatch.setenv("CAPE_AGENT_PROVIDER", "claude")
    agent = get_agent()
    assert isinstance(agent, ClaudeAgent)


def test_get_agent_not_found():
    """Test getting non-existent agent raises ValueError."""
    with pytest.raises(ValueError, match="not registered"):
        get_agent("nonexistent")


def test_get_agent_not_found_shows_available():
    """Test error message shows available providers."""
    with pytest.raises(ValueError, match="Available providers"):
        get_agent("nonexistent")


def test_register_agent():
    """Test registering a custom agent."""

    class TestAgent(CodingAgent):
        def execute_prompt(self, request, *, stream_handler=None):
            return AgentExecuteResponse(output="test", success=True)

    test_agent = TestAgent()
    register_agent("test_agent", test_agent)

    agent = get_agent("test_agent")
    assert isinstance(agent, TestAgent)


def test_register_agent_duplicate_overwrites():
    """Test registering duplicate agent name overwrites existing."""

    class TestAgent1(CodingAgent):
        def execute_prompt(self, request, *, stream_handler=None):
            return AgentExecuteResponse(output="v1", success=True)

    class TestAgent2(CodingAgent):
        def execute_prompt(self, request, *, stream_handler=None):
            return AgentExecuteResponse(output="v2", success=True)

    register_agent("test_dup", TestAgent1())
    register_agent("test_dup", TestAgent2())

    agent = get_agent("test_dup")
    request = AgentExecuteRequest(prompt="test", issue_id=1, adw_id="test", agent_name="test")
    response = agent.execute_prompt(request)
    assert response.output == "v2"


def test_register_agent_invalid_name():
    """Test registering agent with invalid name raises ValueError."""

    class TestAgent(CodingAgent):
        def execute_prompt(self, request, *, stream_handler=None):
            return AgentExecuteResponse(output="test", success=True)

    with pytest.raises(ValueError, match="non-empty string"):
        register_agent("", TestAgent())


def test_register_agent_invalid_agent():
    """Test registering invalid agent raises ValueError."""
    with pytest.raises(ValueError, match="CodingAgent instance"):
        register_agent("invalid", "not an agent")


def test_get_agent_opencode():
    """Test getting opencode agent by name."""
    agent = get_agent("opencode")
    assert isinstance(agent, OpenCodeAgent)


def test_get_implement_provider_default(monkeypatch):
    """Test get_implement_provider defaults to 'claude'."""
    monkeypatch.delenv("CAPE_IMPLEMENT_PROVIDER", raising=False)
    monkeypatch.delenv("CAPE_AGENT_PROVIDER", raising=False)

    provider = get_implement_provider()
    assert provider == "claude"


def test_get_implement_provider_explicit(monkeypatch):
    """Test get_implement_provider respects CAPE_IMPLEMENT_PROVIDER."""
    monkeypatch.setenv("CAPE_IMPLEMENT_PROVIDER", "opencode")

    provider = get_implement_provider()
    assert provider == "opencode"


def test_get_implement_provider_fallback_to_agent_provider(monkeypatch):
    """Test get_implement_provider falls back to CAPE_AGENT_PROVIDER."""
    monkeypatch.delenv("CAPE_IMPLEMENT_PROVIDER", raising=False)
    monkeypatch.setenv("CAPE_AGENT_PROVIDER", "opencode")

    provider = get_implement_provider()
    assert provider == "opencode"


def test_get_implement_provider_precedence(monkeypatch):
    """Test CAPE_IMPLEMENT_PROVIDER takes precedence over CAPE_AGENT_PROVIDER."""
    monkeypatch.setenv("CAPE_IMPLEMENT_PROVIDER", "opencode")
    monkeypatch.setenv("CAPE_AGENT_PROVIDER", "claude")

    provider = get_implement_provider()
    assert provider == "opencode"
