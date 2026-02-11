"""Tests for agent registry."""

import pytest

from rouge.core.agents.base import (
    AgentExecuteRequest,
    AgentExecuteResponse,
    CodingAgent,
)
from rouge.core.agents.claude import ClaudeAgent
from rouge.core.agents.opencode import OpenCodeAgent
from rouge.core.agents.registry import get_agent, get_implement_provider, register_agent


def test_get_agent_default():
    """Test getting default agent (claude)."""
    agent = get_agent()
    assert isinstance(agent, ClaudeAgent)


def test_get_agent_explicit_claude():
    """Test getting claude agent explicitly."""
    agent = get_agent("claude")
    assert isinstance(agent, ClaudeAgent)


def test_get_agent_environment_variable(monkeypatch):
    """Test getting agent via ROUGE_AGENT_PROVIDER environment variable."""
    monkeypatch.setenv("ROUGE_AGENT_PROVIDER", "claude")
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
        def execute_prompt(self, _request: AgentExecuteRequest) -> AgentExecuteResponse:
            return AgentExecuteResponse(output="test", success=True)

    test_agent = TestAgent()
    register_agent("test_agent", test_agent)

    agent = get_agent("test_agent")
    assert isinstance(agent, TestAgent)


def test_register_agent_duplicate_overwrites():
    """Test registering duplicate agent name overwrites existing."""

    class TestAgent1(CodingAgent):
        def execute_prompt(self, _request: AgentExecuteRequest) -> AgentExecuteResponse:
            return AgentExecuteResponse(output="v1", success=True)

    class TestAgent2(CodingAgent):
        def execute_prompt(self, _request: AgentExecuteRequest) -> AgentExecuteResponse:
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
        def execute_prompt(self, _request: AgentExecuteRequest) -> AgentExecuteResponse:
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
    monkeypatch.delenv("ROUGE_IMPLEMENT_PROVIDER", raising=False)
    monkeypatch.delenv("ROUGE_AGENT_PROVIDER", raising=False)

    provider = get_implement_provider()
    assert provider == "claude"


def test_get_implement_provider_explicit(monkeypatch):
    """Test get_implement_provider respects ROUGE_IMPLEMENT_PROVIDER."""
    monkeypatch.setenv("ROUGE_IMPLEMENT_PROVIDER", "opencode")

    provider = get_implement_provider()
    assert provider == "opencode"


def test_get_implement_provider_fallback_to_agent_provider(monkeypatch):
    """Test get_implement_provider falls back to ROUGE_AGENT_PROVIDER."""
    monkeypatch.delenv("ROUGE_IMPLEMENT_PROVIDER", raising=False)
    monkeypatch.setenv("ROUGE_AGENT_PROVIDER", "opencode")

    provider = get_implement_provider()
    assert provider == "opencode"


def test_get_implement_provider_precedence(monkeypatch):
    """Test ROUGE_IMPLEMENT_PROVIDER takes precedence over ROUGE_AGENT_PROVIDER."""
    monkeypatch.setenv("ROUGE_IMPLEMENT_PROVIDER", "opencode")
    monkeypatch.setenv("ROUGE_AGENT_PROVIDER", "claude")

    provider = get_implement_provider()
    assert provider == "opencode"
