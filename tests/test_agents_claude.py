"""Tests for Claude Code agent provider."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

from rouge.core.agents.base import AgentExecuteRequest
from rouge.core.agents.claude import (
    ClaudeAgent,
    check_claude_installed,
    get_claude_env,
    save_prompt,
)

_WORKING_DIR_PATCH = "rouge.core.workflow.shared.get_working_dir"


def test_check_claude_installed_success():
    """Test checking for Claude Code CLI success."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0)
        result = check_claude_installed()
        assert result is None


def test_check_claude_installed_not_found():
    """Test checking for Claude Code CLI failure."""
    with patch("subprocess.run", side_effect=FileNotFoundError):
        result = check_claude_installed()
        assert result is not None
        assert "not installed" in result


def test_get_claude_env(monkeypatch):
    """Test getting Claude Code environment variables."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test_key")
    monkeypatch.setenv("HOME", "/home/test")
    monkeypatch.setenv("PATH", "/usr/bin")

    env = get_claude_env()
    assert "ANTHROPIC_API_KEY" in env
    assert "HOME" in env
    assert "PATH" in env


def test_get_claude_env_with_github_pat(monkeypatch):
    """Test environment includes GitHub tokens when GITHUB_PAT is set."""
    monkeypatch.setenv("GITHUB_PAT", "test_pat")
    monkeypatch.setenv("HOME", "/home/test")

    env = get_claude_env()
    assert env.get("GITHUB_PAT") == "test_pat"
    assert env.get("GH_TOKEN") == "test_pat"


def test_save_prompt(tmp_path: Path) -> None:
    """Test saving prompt to file."""
    with patch(_WORKING_DIR_PATCH, return_value=str(tmp_path)):
        save_prompt("/implement plan.md", "test123", "ops")

        expected_file = (
            tmp_path
            / ".rouge"
            / "agents"
            / "logs"
            / "test123"
            / "ops"
            / "prompts"
            / "implement.txt"
        )
        assert expected_file.exists()
        assert expected_file.read_text() == "/implement plan.md"


@patch(_WORKING_DIR_PATCH)
@patch("rouge.core.agents.claude.claude.check_claude_installed")
@patch("subprocess.run")
def test_claude_agent_execute_prompt_success(
    mock_run: Mock, mock_check: Mock, mock_wd: Mock, tmp_path: Path
) -> None:
    """Test successful ClaudeAgent execution."""
    mock_wd.return_value = str(tmp_path)
    mock_check.return_value = None

    # Mock successful execution with JSON envelope containing structured_output
    result_envelope = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "session_id": "session123",
        "duration_ms": 1234,
        "structured_output": {"status": "Implementation complete"},
    }

    mock_run.return_value = Mock(
        stdout=json.dumps(result_envelope),
        stderr="",
        returncode=0,
    )

    agent = ClaudeAgent()
    request = AgentExecuteRequest(
        prompt="/implement plan.md",
        issue_id=1,
        adw_id="test123",
        agent_name="implementor",
    )

    response = agent.execute_prompt(request)
    assert response.success is True
    assert response.session_id == "session123"
    assert response.output == json.dumps({"status": "Implementation complete"})
    assert response.raw_output_path is None  # No file output with subprocess.run


@patch("rouge.core.agents.claude.claude.check_claude_installed")
def test_claude_agent_execute_prompt_cli_not_installed(mock_check: Mock) -> None:
    """Test ClaudeAgent handles CLI not installed."""
    mock_check.return_value = "Error: Claude Code CLI is not installed"

    agent = ClaudeAgent()
    request = AgentExecuteRequest(
        prompt="/implement plan.md",
        issue_id=1,
        adw_id="test123",
        agent_name="implementor",
    )

    response = agent.execute_prompt(request)
    assert response.success is False
    assert "not installed" in response.output
    assert response.error_detail is not None


@patch(_WORKING_DIR_PATCH)
@patch("rouge.core.agents.claude.claude.check_claude_installed")
@patch("subprocess.run")
def test_claude_agent_execute_prompt_error_handling(
    mock_run: Mock, mock_check: Mock, mock_wd: Mock, tmp_path: Path
) -> None:
    """Test ClaudeAgent error handling."""
    mock_wd.return_value = str(tmp_path)
    mock_check.return_value = None

    result_envelope = {
        "type": "result",
        "subtype": "error",
        "is_error": True,
        "result": "Error occurred",
        "session_id": "session123",
        "duration_ms": 500,
    }

    mock_run.return_value = Mock(
        stdout=json.dumps(result_envelope),
        stderr="",
        returncode=0,
    )

    agent = ClaudeAgent()
    request = AgentExecuteRequest(
        prompt="/implement plan.md",
        issue_id=1,
        adw_id="test123",
        agent_name="implementor",
    )

    response = agent.execute_prompt(request)
    assert response.success is False
    assert response.error_detail is not None
