"""Tests for Claude Code agent module (legacy facade)."""

import json
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from cape.core.agent import execute_template, prompt_claude_code
from cape.core.agents.claude import (
    check_claude_installed,
    convert_jsonl_to_json,
    get_claude_env,
    parse_jsonl_output,
    save_prompt,
)
from cape.core.agents.claude_models import (
    ClaudeAgentPromptRequest as AgentPromptRequest,
    ClaudeAgentTemplateRequest as AgentTemplateRequest,
)


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


def test_parse_jsonl_output(tmp_path):
    """Test parsing JSONL output file."""
    jsonl_file = tmp_path / "test.jsonl"
    messages = [
        {"type": "message", "data": "test1"},
        {"type": "result", "is_error": False, "result": "success"},
    ]
    with open(jsonl_file, "w") as f:
        for msg in messages:
            f.write(json.dumps(msg) + "\n")

    all_messages, result_message = parse_jsonl_output(str(jsonl_file))
    assert len(all_messages) == 2
    assert result_message["type"] == "result"
    assert result_message["result"] == "success"


def test_convert_jsonl_to_json(tmp_path):
    """Test converting JSONL to JSON array."""
    jsonl_file = tmp_path / "test.jsonl"
    messages = [
        {"type": "message", "data": "test1"},
        {"type": "result", "result": "success"},
    ]
    with open(jsonl_file, "w") as f:
        for msg in messages:
            f.write(json.dumps(msg) + "\n")

    json_file = convert_jsonl_to_json(str(jsonl_file))
    assert Path(json_file).exists()
    with open(json_file) as f:
        data = json.load(f)
        assert len(data) == 2


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


def test_save_prompt(tmp_path, monkeypatch):
    """Test saving prompt to file."""
    monkeypatch.setenv("CAPE_AGENTS_DIR", str(tmp_path))

    save_prompt("/implement plan.md", "test123", "ops")

    expected_file = tmp_path / "test123" / "ops" / "prompts" / "implement.txt"
    assert expected_file.exists()
    assert expected_file.read_text() == "/implement plan.md"


@patch("cape.core.notifications.create_comment")
@patch("cape.core.agents.claude.check_claude_installed")
@patch("subprocess.Popen")
def test_prompt_claude_code_success(mock_popen, mock_check, mock_create_comment, tmp_path, monkeypatch):
    """Test successful Claude Code execution."""
    monkeypatch.setenv("CAPE_AGENTS_DIR", str(tmp_path))
    mock_check.return_value = None

    output_file = tmp_path / "output.jsonl"
    request = AgentPromptRequest(
        prompt="/implement plan.md",
        adw_id="test123",
        issue_id=1,
        output_file=str(output_file),
    )

    # Mock successful execution that writes JSONL output
    result_msg = {
        "type": "result",
        "is_error": False,
        "result": "Implementation complete",
        "session_id": "session123",
    }

    stdout_stream = StringIO(json.dumps(result_msg) + "\n")
    stderr_stream = StringIO("")

    process_mock = Mock()
    process_mock.stdout = stdout_stream
    process_mock.stderr = stderr_stream
    process_mock.wait.return_value = None
    process_mock.returncode = 0

    mock_popen.return_value = process_mock

    response = prompt_claude_code(request)
    assert response.success is True
    assert response.session_id == "session123"
    assert mock_create_comment.called


@patch("cape.core.notifications.create_comment")
@patch("cape.core.agents.claude.check_claude_installed")
def test_prompt_claude_code_cli_not_installed(mock_check, mock_create_comment):
    """Test handling of Claude Code CLI not installed."""
    mock_check.return_value = "Error: Claude Code CLI is not installed"

    request = AgentPromptRequest(
        prompt="/implement plan.md",
        adw_id="test123",
        issue_id=1,
        output_file="/tmp/output.jsonl",
    )

    response = prompt_claude_code(request)
    assert response.success is False
    assert "not installed" in response.output
    mock_create_comment.assert_not_called()


@patch("cape.core.agents.claude.check_claude_installed")
@patch("subprocess.Popen")
def test_execute_template(mock_popen, mock_check, tmp_path, monkeypatch):
    """Test executing template with slash command."""
    monkeypatch.setenv("CAPE_AGENTS_DIR", str(tmp_path))
    mock_check.return_value = None

    # Mock successful execution
    result_msg = {
        "type": "result",
        "is_error": False,
        "result": "Success",
        "session_id": "test",
    }

    stdout_stream = StringIO(json.dumps(result_msg) + "\n")
    stderr_stream = StringIO("")

    process_mock = Mock()
    process_mock.stdout = stdout_stream
    process_mock.stderr = stderr_stream
    process_mock.wait.return_value = None
    process_mock.returncode = 0

    mock_popen.return_value = process_mock

    request = AgentTemplateRequest(
        agent_name="ops",
        slash_command="/implement",
        args=["plan.md"],
        adw_id="test123",
        issue_id=1,
    )

    response = execute_template(request)
    assert response.success is True
