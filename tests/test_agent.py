"""Tests for Claude Code agent module (legacy facade)."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

from rouge.core.agent import execute_template
from rouge.core.agents.claude import (
    check_claude_installed,
    get_claude_env,
    save_prompt,
)
from rouge.core.agents.claude.claude_models import (
    ClaudeAgentTemplateRequest as AgentTemplateRequest,
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
def test_execute_template(mock_run: Mock, mock_check: Mock, mock_wd: Mock, tmp_path: Path) -> None:
    """Test executing template with slash command."""
    mock_wd.return_value = str(tmp_path)
    mock_check.return_value = None

    # Mock successful execution with JSON envelope
    result_envelope = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "session_id": "test",
        "duration_ms": 1234,
        "structured_output": {"status": "Success"},
    }

    mock_run.return_value = Mock(
        stdout=json.dumps(result_envelope),
        stderr="",
        returncode=0,
    )

    request = AgentTemplateRequest(
        agent_name="ops",
        slash_command="/adw-implement-plan",
        args=["plan.md"],
        adw_id="test123",
        issue_id=1,
    )

    response = execute_template(request)
    assert response.success is True


@patch(_WORKING_DIR_PATCH)
@patch("rouge.core.notifications.comments.create_comment")
@patch("rouge.core.agents.claude.claude.check_claude_installed")
@patch("subprocess.run")
def test_execute_template_require_json_false(
    mock_run: Mock, mock_check: Mock, _mock_create_comment: Mock, mock_wd: Mock, tmp_path: Path
) -> None:
    """Test execute_template with require_json=False allows plain text output."""
    mock_wd.return_value = str(tmp_path)
    mock_check.return_value = None

    # Mock execution that returns plain text in structured_output
    result_envelope = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "session_id": "test",
        "duration_ms": 1234,
        "structured_output": "specs/feature-plan.md",
    }

    mock_run.return_value = Mock(
        stdout=json.dumps(result_envelope),
        stderr="",
        returncode=0,
    )

    request = AgentTemplateRequest(
        agent_name="ops",
        slash_command="/adw-find-plan-file",
        args=["output"],
        adw_id="test123",
        issue_id=1,
    )

    # Should not error even though structured_output is plain text
    response = execute_template(request, require_json=False)
    assert response.success is True
    assert response.output == "specs/feature-plan.md"


@patch(_WORKING_DIR_PATCH)
@patch("rouge.core.notifications.comments.create_comment")
@patch("rouge.core.agents.claude.claude.check_claude_installed")
@patch("subprocess.run")
def test_execute_template_sanitizes_markdown_fence(
    mock_run: Mock, mock_check: Mock, _mock_create_comment: Mock, mock_wd: Mock, tmp_path: Path
) -> None:
    """Test execute_template strips Markdown fences before parsing JSON."""
    mock_wd.return_value = str(tmp_path)
    mock_check.return_value = None

    # Mock execution that returns JSON wrapped in Markdown fences in structured_output
    result_envelope = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "session_id": "test",
        "duration_ms": 1234,
        "structured_output": '```json\n{"status": "success"}\n```',
    }

    mock_run.return_value = Mock(
        stdout=json.dumps(result_envelope),
        stderr="",
        returncode=0,
    )

    request = AgentTemplateRequest(
        agent_name="ops",
        slash_command="/adw-classify",
        args=["issue"],
        adw_id="test123",
        issue_id=1,
    )

    # Should successfully parse JSON after stripping fences
    response = execute_template(request)
    assert response.success is True
