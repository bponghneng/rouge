"""Tests for OpenCode agent provider."""

import json
import subprocess
from io import StringIO
from unittest.mock import Mock, patch

from rouge.core.agents.base import AgentExecuteRequest
from rouge.core.agents.opencode import (
    OpenCodeAgent,
    check_opencode_installed,
    convert_jsonl_to_json,
    get_opencode_env,
    parse_opencode_jsonl,
)

_WORKING_DIR_PATCH = "rouge.core.workflow.shared.get_working_dir"


def test_check_opencode_installed_success():
    """Test checking for OpenCode CLI success."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0)
        result = check_opencode_installed()
        assert result is None


def test_check_opencode_installed_not_found():
    """Test checking for OpenCode CLI when not found."""
    with patch("subprocess.run", side_effect=FileNotFoundError):
        result = check_opencode_installed()
        assert result is not None
        assert "not installed" in result


def test_check_opencode_installed_timeout():
    """Test checking for OpenCode CLI timeout."""
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("opencode", 5)):
        result = check_opencode_installed()
        assert result is not None
        assert "timeout" in result.lower()


def test_get_opencode_env(monkeypatch):
    """Test getting OpenCode environment variables."""
    monkeypatch.setenv("OPENCODE_API_KEY", "test_key")
    monkeypatch.setenv("HOME", "/home/test")
    monkeypatch.setenv("PATH", "/usr/bin")

    env = get_opencode_env()
    assert "OPENCODE_API_KEY" in env
    assert env["OPENCODE_API_KEY"] == "test_key"
    assert "HOME" in env
    assert "PATH" in env


def test_get_opencode_env_with_github_pat(monkeypatch):
    """Test environment includes GitHub tokens when GITHUB_PAT is set."""
    monkeypatch.setenv("GITHUB_PAT", "test_pat")
    monkeypatch.setenv("HOME", "/home/test")

    env = get_opencode_env()
    assert env.get("GITHUB_PAT") == "test_pat"
    assert env.get("GH_TOKEN") == "test_pat"


def test_get_opencode_env_filters_none(monkeypatch):
    """Test that None values are filtered from environment."""
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    monkeypatch.setenv("HOME", "/home/test")

    env = get_opencode_env()
    assert "OPENCODE_API_KEY" not in env
    assert "HOME" in env


def test_parse_opencode_jsonl(tmp_path):
    """Test parsing OpenCode JSONL output file."""
    jsonl_file = tmp_path / "test.jsonl"
    messages = [
        {"type": "message", "data": "test1"},
        {"type": "result", "is_error": False, "result": "success", "session_id": "123"},
    ]
    with open(jsonl_file, "w") as f:
        for msg in messages:
            f.write(json.dumps(msg) + "\n")

    all_messages, result_message = parse_opencode_jsonl(str(jsonl_file))
    assert len(all_messages) == 2
    assert result_message["type"] == "result"
    assert result_message["result"] == "success"
    assert result_message["session_id"] == "123"


def test_parse_opencode_jsonl_result_message_extraction(tmp_path):
    """Test that result message is correctly extracted from reversed search."""
    jsonl_file = tmp_path / "test.jsonl"
    messages = [
        {"type": "message", "data": "test1"},
        {"type": "message", "data": "test2"},
        {"type": "result", "is_error": False, "result": "success"},
        {"type": "message", "data": "test3"},  # After result
    ]
    with open(jsonl_file, "w") as f:
        for msg in messages:
            f.write(json.dumps(msg) + "\n")

    all_messages, result_message = parse_opencode_jsonl(str(jsonl_file))
    assert len(all_messages) == 4
    assert result_message["type"] == "result"


def test_parse_opencode_jsonl_malformed(tmp_path, caplog):
    """Test parsing JSONL with malformed JSON lines."""
    jsonl_file = tmp_path / "test.jsonl"
    with open(jsonl_file, "w") as f:
        f.write('{"type": "message", "data": "test1"}\n')
        f.write("invalid json line\n")
        f.write('{"type": "result", "result": "success"}\n')

    all_messages, result_message = parse_opencode_jsonl(str(jsonl_file))
    assert len(all_messages) == 2  # Invalid line skipped
    assert result_message["type"] == "result"
    assert "malformed" in caplog.text.lower()


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
    assert json_file == str(tmp_path / "test.json")
    with open(json_file) as f:
        data = json.load(f)
        assert len(data) == 2


@patch(_WORKING_DIR_PATCH)
@patch("rouge.core.agents.opencode.opencode.check_opencode_installed")
@patch("subprocess.Popen")
def test_opencode_agent_execute_prompt_success(mock_popen, mock_check, mock_wd, tmp_path, monkeypatch):
    """Test successful OpenCodeAgent execution."""
    mock_wd.return_value = str(tmp_path)
    mock_check.return_value = None

    # Mock successful execution
    result_msg = {
        "type": "result",
        "is_error": False,
        "result": "Implementation complete",
        "session_id": "session123",
    }

    # Create mock process
    mock_process = Mock()
    mock_process.returncode = 0
    mock_process.stdout = StringIO(json.dumps(result_msg) + "\n")
    mock_process.stderr = StringIO("")
    mock_popen.return_value = mock_process

    # Execute
    agent = OpenCodeAgent()
    request = AgentExecuteRequest(
        prompt="# Test Plan\nImplement feature X",
        issue_id=123,
        adw_id="test456",
        agent_name="test_agent",
    )
    response = agent.execute_prompt(request)

    # Verify
    assert response.success is True
    assert response.session_id == "session123"
    assert "Implementation complete" in response.output


@patch(_WORKING_DIR_PATCH)
@patch("rouge.core.agents.opencode.opencode.check_opencode_installed")
@patch("subprocess.Popen")
def test_opencode_agent_execute_prompt_error(mock_popen, mock_check, mock_wd, tmp_path, monkeypatch):
    """Test OpenCodeAgent execution with error."""
    mock_wd.return_value = str(tmp_path)
    mock_check.return_value = None

    # Mock failed execution
    mock_process = Mock()
    mock_process.returncode = 1
    mock_process.stdout = StringIO('{"type": "message", "data": "processing..."}\n')
    mock_process.stderr = StringIO("Error: Something went wrong\n")
    mock_popen.return_value = mock_process

    # Execute
    agent = OpenCodeAgent()
    request = AgentExecuteRequest(
        prompt="# Test Plan",
        issue_id=123,
        adw_id="test456",
        agent_name="test_agent",
    )
    response = agent.execute_prompt(request)

    # Verify
    assert response.success is False
    assert "Something went wrong" in response.error_detail or "OpenCode error" in response.output


@patch(_WORKING_DIR_PATCH)
@patch("rouge.core.agents.opencode.opencode.check_opencode_installed")
def test_opencode_agent_cli_not_installed(mock_check, mock_wd, tmp_path, monkeypatch):
    """Test OpenCodeAgent when CLI is not installed."""
    mock_wd.return_value = str(tmp_path)
    mock_check.return_value = "Error: OpenCode CLI is not installed"

    agent = OpenCodeAgent()
    request = AgentExecuteRequest(
        prompt="# Test Plan",
        issue_id=123,
        adw_id="test456",
        agent_name="test_agent",
    )
    response = agent.execute_prompt(request)

    assert response.success is False
    assert "not installed" in response.error_detail


@patch(_WORKING_DIR_PATCH)
@patch("rouge.core.agents.opencode.opencode.check_opencode_installed")
@patch("subprocess.Popen")
def test_opencode_agent_with_stream_handler(mock_popen, mock_check, mock_wd, tmp_path, monkeypatch):
    """Test OpenCodeAgent with stream handler invocation."""
    mock_wd.return_value = str(tmp_path)
    mock_check.return_value = None

    # Mock process output
    result_msg = {
        "type": "result",
        "is_error": False,
        "result": "Done",
        "session_id": "123",
    }
    mock_process = Mock()
    mock_process.returncode = 0
    mock_process.stdout = StringIO(json.dumps(result_msg) + "\n")
    mock_process.stderr = StringIO("")
    mock_popen.return_value = mock_process

    # Create stream handler
    stream_calls = []

    def handler(line: str):
        stream_calls.append(line)

    # Execute
    agent = OpenCodeAgent()
    request = AgentExecuteRequest(
        prompt="# Test Plan",
        issue_id=123,
        adw_id="test456",
        agent_name="test_agent",
    )
    response = agent.execute_prompt(request, stream_handler=handler)

    # Verify stream handler was called
    assert len(stream_calls) > 0
    assert response.success is True


@patch(_WORKING_DIR_PATCH)
@patch("rouge.core.agents.opencode.opencode.check_opencode_installed")
@patch("subprocess.Popen")
def test_opencode_command_construction(mock_popen, mock_check, mock_wd, tmp_path, monkeypatch):
    """Test OpenCode CLI command construction."""
    mock_wd.return_value = str(tmp_path)
    monkeypatch.setenv("OPENCODE_PATH", "/usr/bin/opencode")
    mock_check.return_value = None

    # Mock process
    mock_process = Mock()
    mock_process.returncode = 0
    mock_process.stdout = StringIO("")
    mock_process.stderr = StringIO("")
    mock_popen.return_value = mock_process

    # Execute
    agent = OpenCodeAgent()
    request = AgentExecuteRequest(
        prompt="# Test Plan Content",
        issue_id=123,
        adw_id="test456",
        agent_name="test_agent",
    )
    agent.execute_prompt(request)

    # Verify command construction
    call_args = mock_popen.call_args
    cmd = call_args[0][0]
    assert cmd[0] == "/usr/bin/opencode" or cmd[0] == "opencode"
    assert "--model" in cmd
    assert "--command" in cmd
    assert "implement" in cmd
    assert "--format" in cmd
    assert "json" in cmd
    assert "# Test Plan Content" in cmd


@patch(_WORKING_DIR_PATCH)
@patch("rouge.core.agents.opencode.opencode.check_opencode_installed")
@patch("subprocess.Popen")
def test_opencode_model_selection(mock_popen, mock_check, mock_wd, tmp_path, monkeypatch):
    """Test OpenCode model parameter handling."""
    mock_wd.return_value = str(tmp_path)
    mock_check.return_value = None

    mock_process = Mock()
    mock_process.returncode = 0
    mock_process.stdout = StringIO("")
    mock_process.stderr = StringIO("")
    mock_popen.return_value = mock_process

    # Execute with custom model
    agent = OpenCodeAgent()
    request = AgentExecuteRequest(
        prompt="# Test Plan",
        issue_id=123,
        adw_id="test456",
        agent_name="test_agent",
        provider_options={"model": "custom-model"},
    )
    agent.execute_prompt(request)

    # Verify custom model in command
    call_args = mock_popen.call_args
    cmd = call_args[0][0]
    model_idx = cmd.index("--model")
    assert cmd[model_idx + 1] == "custom-model"


@patch(_WORKING_DIR_PATCH)
@patch("rouge.core.agents.opencode.opencode.check_opencode_installed")
@patch("subprocess.Popen")
def test_opencode_agent_exception_handling(mock_popen, mock_check, mock_wd, tmp_path, monkeypatch):
    """Test OpenCodeAgent exception handling."""
    mock_wd.return_value = str(tmp_path)
    mock_check.return_value = None

    # Mock process that raises exception
    mock_popen.side_effect = Exception("Unexpected error")

    agent = OpenCodeAgent()
    request = AgentExecuteRequest(
        prompt="# Test Plan",
        issue_id=123,
        adw_id="test456",
        agent_name="test_agent",
    )
    response = agent.execute_prompt(request)

    assert response.success is False
    assert "Unexpected error" in response.error_detail


@patch(_WORKING_DIR_PATCH)
@patch("rouge.core.agents.opencode.opencode.check_opencode_installed")
@patch("subprocess.Popen")
def test_opencode_agent_stream_handler_exception(
    mock_popen, mock_check, mock_wd, tmp_path, monkeypatch, caplog
):
    """Test that stream handler exceptions don't interrupt execution."""
    mock_wd.return_value = str(tmp_path)
    mock_check.return_value = None

    result_msg = {"type": "result", "is_error": False, "result": "Done"}
    mock_process = Mock()
    mock_process.returncode = 0
    mock_process.stdout = StringIO(json.dumps(result_msg) + "\n")
    mock_process.stderr = StringIO("")
    mock_popen.return_value = mock_process

    # Stream handler that raises exception
    def bad_handler(line: str):
        raise ValueError("Handler error")

    agent = OpenCodeAgent()
    request = AgentExecuteRequest(
        prompt="# Test Plan",
        issue_id=123,
        adw_id="test456",
        agent_name="test_agent",
    )
    response = agent.execute_prompt(request)

    # Execution should still succeed despite handler error
    assert response.success is True
    # Error should be logged
    assert "handler error" in caplog.text.lower() or response.success
