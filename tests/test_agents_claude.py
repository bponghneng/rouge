"""Tests for Claude Code agent provider."""

import json
from io import StringIO
from unittest.mock import Mock, patch

from rouge.core.agents.base import AgentExecuteRequest
from rouge.core.agents.claude import (
    ClaudeAgent,
    check_claude_installed,
    convert_jsonl_to_json,
    get_claude_env,
    iter_assistant_items,
    parse_jsonl_output,
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
    assert tmp_path / "test.json"
    with open(json_file) as f:
        data = json.load(f)
        assert len(data) == 2


def test_iter_assistant_items():
    """Test extracting assistant items from JSONL line."""
    line = json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Hello"},
                    {"type": "tool_use", "name": "TodoWrite", "input": {}},
                    {"type": "other", "data": "ignored"},
                ]
            },
        }
    )
    items = list(iter_assistant_items(line))
    assert len(items) == 2
    assert items[0]["type"] == "text"
    assert items[1]["type"] == "tool_use"


def test_iter_assistant_items_empty_line():
    """Test iter_assistant_items with empty line."""
    items = list(iter_assistant_items(""))
    assert len(items) == 0


def test_iter_assistant_items_non_assistant():
    """Test iter_assistant_items with non-assistant message."""
    line = json.dumps({"type": "user", "message": {"content": []}})
    items = list(iter_assistant_items(line))
    assert len(items) == 0


def test_iter_assistant_items_includes_task_tool_use():
    """Test extracting Task tool_use items from JSONL line."""
    line = json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Starting implementation"},
                    {
                        "type": "tool_use",
                        "name": "Task",
                        "input": {"action": "create", "task_id": "task-123"},
                    },
                    {"type": "tool_use", "name": "OtherTool", "input": {}},
                ]
            },
        }
    )
    items = list(iter_assistant_items(line))
    assert len(items) == 2
    assert items[0]["type"] == "text"
    assert items[1]["type"] == "tool_use"
    assert items[1]["name"] == "Task"
    assert items[1]["input"] == {"action": "create", "task_id": "task-123"}


def test_save_prompt(tmp_path, monkeypatch):
    """Test saving prompt to file."""
    with patch(_WORKING_DIR_PATCH, return_value=str(tmp_path)):
        save_prompt("/implement plan.md", "test123", "ops")

        expected_file = tmp_path / ".rouge" / "agents" / "logs" / "test123" / "ops" / "prompts" / "implement.txt"
        assert expected_file.exists()
        assert expected_file.read_text() == "/implement plan.md"


@patch(_WORKING_DIR_PATCH)
@patch("rouge.core.agents.claude.claude.check_claude_installed")
@patch("subprocess.Popen")
def test_claude_agent_execute_prompt_success(mock_popen, mock_check, mock_wd, tmp_path, monkeypatch):
    """Test successful ClaudeAgent execution."""
    mock_wd.return_value = str(tmp_path)
    mock_check.return_value = None

    # Mock successful execution
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
    assert response.output == "Implementation complete"
    assert response.raw_output_path is not None


@patch("rouge.core.agents.claude.claude.check_claude_installed")
def test_claude_agent_execute_prompt_cli_not_installed(mock_check):
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
@patch("subprocess.Popen")
def test_claude_agent_execute_prompt_with_stream_handler(
    mock_popen, mock_check, mock_wd, tmp_path, monkeypatch
):
    """Test ClaudeAgent calls stream handler."""
    mock_wd.return_value = str(tmp_path)
    mock_check.return_value = None

    result_msg = {
        "type": "result",
        "is_error": False,
        "result": "Complete",
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

    # Track stream handler calls
    handler_calls = []

    def test_handler(line):
        handler_calls.append(line)

    agent = ClaudeAgent()
    request = AgentExecuteRequest(
        prompt="/implement plan.md",
        issue_id=1,
        adw_id="test123",
        agent_name="implementor",
    )

    response = agent.execute_prompt(request, stream_handler=test_handler)
    assert response.success is True
    assert len(handler_calls) > 0


@patch(_WORKING_DIR_PATCH)
@patch("rouge.core.agents.claude.claude.check_claude_installed")
@patch("subprocess.Popen")
def test_claude_agent_execute_prompt_error_handling(mock_popen, mock_check, mock_wd, tmp_path, monkeypatch):
    """Test ClaudeAgent error handling."""
    mock_wd.return_value = str(tmp_path)
    mock_check.return_value = None

    result_msg = {
        "type": "result",
        "is_error": True,
        "result": "Error occurred",
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
