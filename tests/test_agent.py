"""Tests for Claude Code agent module (legacy facade)."""

import json
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from rouge.core.agent import execute_template, prompt_claude_code
from rouge.core.agents.claude import (
    check_claude_installed,
    convert_jsonl_to_json,
    get_claude_env,
    parse_jsonl_output,
    save_prompt,
)
from rouge.core.agents.claude.claude_models import (
    ClaudeAgentPromptRequest as AgentPromptRequest,
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
@patch("rouge.core.notifications.comments.create_comment")
@patch("rouge.core.agents.claude.claude.check_claude_installed")
@patch("subprocess.Popen")
def test_prompt_claude_code_success(
    mock_popen: Mock,
    mock_check: Mock,
    mock_create_comment: Mock,
    mock_wd: Mock,
    tmp_path: Path,
) -> None:
    """Test successful Claude Code execution."""
    mock_wd.return_value = str(tmp_path)
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


@patch("rouge.core.notifications.comments.create_comment")
@patch("rouge.core.agents.claude.claude.check_claude_installed")
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


@patch(_WORKING_DIR_PATCH)
@patch("rouge.core.agents.claude.claude.check_claude_installed")
@patch("subprocess.run")
def test_execute_template(
    mock_run: Mock, mock_check: Mock, mock_wd: Mock, tmp_path: Path
) -> None:
    """Test executing template with slash command and JSON envelope output."""
    mock_wd.return_value = str(tmp_path)
    mock_check.return_value = None

    # Mock successful execution with JSON envelope format
    envelope = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "structured_output": {"output": "Implementation complete", "status": "success"},
        "session_id": "test-session-123",
    }

    mock_run.return_value = Mock(
        stdout=json.dumps(envelope),
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
    assert response.session_id == "test-session-123"
    # Output should be the structured_output as JSON string
    parsed = json.loads(response.output)
    assert parsed["output"] == "Implementation complete"
    assert parsed["status"] == "success"


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

    # Mock execution that returns JSON envelope with structured_output
    # The structured_output contains the plain text file path
    envelope = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "structured_output": {"output": "specs/feature-plan.md"},
        "session_id": "test",
    }

    mock_run.return_value = Mock(
        stdout=json.dumps(envelope),
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

    # Should not error even though output is plain text
    response = execute_template(request, require_json=False)
    assert response.success is True
    # With JSON envelope, output is JSON string of structured_output
    parsed = json.loads(response.output)
    assert parsed["output"] == "specs/feature-plan.md"


@patch(_WORKING_DIR_PATCH)
@patch("rouge.core.notifications.comments.create_comment")
@patch("rouge.core.agents.claude.claude.check_claude_installed")
@patch("subprocess.run")
def test_execute_template_with_json_schema(
    mock_run: Mock, mock_check: Mock, _mock_create_comment: Mock, mock_wd: Mock, tmp_path: Path
) -> None:
    """Test execute_template passes json_schema to CLI when provided."""
    mock_wd.return_value = str(tmp_path)
    mock_check.return_value = None

    # Mock successful execution with structured output
    envelope = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "structured_output": {
            "output": "classified",
            "type": "feature",
            "level": "simple",
        },
        "session_id": "test-schema-session",
    }

    mock_run.return_value = Mock(
        stdout=json.dumps(envelope),
        stderr="",
        returncode=0,
    )

    # Define a test JSON schema
    test_schema = '{"type": "object", "properties": {"type": {"type": "string"}}}'

    request = AgentTemplateRequest(
        agent_name="ops",
        slash_command="/adw-classify",
        args=["issue"],
        adw_id="test123",
        issue_id=1,
        json_schema=test_schema,
    )

    response = execute_template(request)
    assert response.success is True

    # Verify json_schema was passed to CLI
    call_args = mock_run.call_args
    cmd = call_args[0][0]  # First positional arg is the command list
    assert "--json-schema" in cmd
    schema_idx = cmd.index("--json-schema")
    assert cmd[schema_idx + 1] == test_schema


@patch(_WORKING_DIR_PATCH)
@patch("rouge.core.agents.claude.claude.check_claude_installed")
@patch("subprocess.run")
def test_execute_template_json_envelope_is_error(
    mock_run: Mock, mock_check: Mock, mock_wd: Mock, tmp_path: Path
) -> None:
    """Test execute_template handles is_error=True in JSON envelope."""
    mock_wd.return_value = str(tmp_path)
    mock_check.return_value = None

    # Mock execution that returns error envelope
    envelope = {
        "type": "result",
        "subtype": "error",
        "is_error": True,
        "result": "Failed to implement plan: missing dependencies",
        "session_id": "error-session",
    }

    mock_run.return_value = Mock(
        stdout=json.dumps(envelope),
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
    assert response.success is False
    assert "Failed to implement plan" in response.output
    assert response.session_id == "error-session"


@patch(_WORKING_DIR_PATCH)
@patch("rouge.core.agents.claude.claude.check_claude_installed")
@patch("subprocess.run")
def test_execute_template_invalid_envelope_type(
    mock_run: Mock, mock_check: Mock, mock_wd: Mock, tmp_path: Path
) -> None:
    """Test execute_template rejects envelope with type != 'result'."""
    mock_wd.return_value = str(tmp_path)
    mock_check.return_value = None

    # Mock execution that returns invalid envelope type
    envelope = {
        "type": "assistant",  # Wrong type
        "is_error": False,
        "structured_output": {"output": "test"},
        "session_id": "invalid-type-session",
    }

    mock_run.return_value = Mock(
        stdout=json.dumps(envelope),
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

    response = execute_template(request)
    assert response.success is False
    assert "Invalid envelope type" in response.output


@patch(_WORKING_DIR_PATCH)
@patch("rouge.core.agents.claude.claude.check_claude_installed")
@patch("subprocess.run")
def test_execute_template_missing_structured_output(
    mock_run: Mock, mock_check: Mock, mock_wd: Mock, tmp_path: Path
) -> None:
    """Test execute_template rejects envelope without structured_output dict."""
    mock_wd.return_value = str(tmp_path)
    mock_check.return_value = None

    # Mock execution that returns envelope without structured_output
    envelope = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "Some text result",
        "session_id": "missing-structured",
    }

    mock_run.return_value = Mock(
        stdout=json.dumps(envelope),
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

    response = execute_template(request)
    assert response.success is False
    assert "Invalid structured_output" in response.output
