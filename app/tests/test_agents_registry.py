"""Tests for agent registry."""

import pytest

from cape.core.agents.base import AgentExecuteRequest, AgentExecuteResponse, CodingAgent
from cape.core.agents.claude import ClaudeAgent
from cape.core.agents.registry import get_agent, register_agent


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
    request = AgentExecuteRequest(
        prompt="test", issue_id=1, adw_id="test", agent_name="test"
    )
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
