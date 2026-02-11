"""Tests for base agent abstraction."""

import pytest

from rouge.core.agents.base import (
    AgentExecuteRequest,
    AgentExecuteResponse,
    CodingAgent,
)


def test_agent_execute_request_validation():
    """Test AgentExecuteRequest model validation."""
    request = AgentExecuteRequest(
        prompt="/implement plan.md",
        issue_id=123,
        adw_id="adw-456",
        agent_name="implementor",
    )
    assert request.prompt == "/implement plan.md"
    assert request.issue_id == 123
    assert request.adw_id == "adw-456"
    assert request.agent_name == "implementor"
    assert request.model is None
    assert request.output_path is None
    assert request.provider_options == {}


def test_agent_execute_request_with_optional_fields():
    """Test AgentExecuteRequest with all optional fields."""
    request = AgentExecuteRequest(
        prompt="/implement plan.md",
        issue_id=123,
        adw_id="adw-456",
        agent_name="implementor",
        model="sonnet",
        output_path="/tmp/output.jsonl",
        provider_options={"custom_flag": True},
    )
    assert request.model == "sonnet"
    assert request.output_path == "/tmp/output.jsonl"
    assert request.provider_options == {"custom_flag": True}


def test_agent_execute_response_validation():
    """Test AgentExecuteResponse model validation."""
    response = AgentExecuteResponse(
        output="Implementation complete",
        success=True,
    )
    assert response.output == "Implementation complete"
    assert response.success is True
    assert response.session_id is None
    assert response.raw_output_path is None
    assert response.error_detail is None


def test_agent_execute_response_with_optional_fields():
    """Test AgentExecuteResponse with all optional fields."""
    response = AgentExecuteResponse(
        output="Implementation complete",
        success=True,
        session_id="session-123",
        raw_output_path="/tmp/output.jsonl",
        error_detail=None,
    )
    assert response.session_id == "session-123"
    assert response.raw_output_path == "/tmp/output.jsonl"


def test_coding_agent_cannot_instantiate():
    """Test that CodingAgent abstract class cannot be instantiated."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        CodingAgent()


def test_coding_agent_must_implement_execute_prompt():
    """Test that CodingAgent subclass must implement execute_prompt."""

    class InvalidAgent(CodingAgent):
        pass

    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        InvalidAgent()


def test_coding_agent_valid_implementation():
    """Test that valid CodingAgent implementation works."""

    class ValidAgent(CodingAgent):
        def execute_prompt(self, request):
            return AgentExecuteResponse(
                output="Test output",
                success=True,
            )

    agent = ValidAgent()
    request = AgentExecuteRequest(
        prompt="test",
        issue_id=1,
        adw_id="test",
        agent_name="test",
    )
    response = agent.execute_prompt(request)
    assert response.success is True
    assert response.output == "Test output"
