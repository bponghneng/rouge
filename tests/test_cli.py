"""Tests for CLI commands."""

from unittest.mock import Mock, patch

from typer.testing import CliRunner

from cape.cli.cli import app
from cape.core.models import CapeIssue

runner = CliRunner()


def test_cli_help():
    """Test CLI help command."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Cape CLI" in result.output


def test_cli_version():
    """Test version flag."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "version" in result.output.lower()


@patch("cape.cli.cli.create_issue")
def test_create_command_success(mock_create_issue):
    """Test successful issue creation via CLI."""
    mock_issue = CapeIssue(id=123, description="Test issue", status="pending")
    mock_create_issue.return_value = mock_issue

    result = runner.invoke(app, ["create", "Test issue"])
    assert result.exit_code == 0
    assert "123" in result.output
    mock_create_issue.assert_called_once_with("Test issue")


@patch("cape.cli.cli.create_issue")
def test_create_command_empty_description(mock_create_issue):
    """Test create command with empty description."""
    mock_create_issue.side_effect = ValueError("Issue description cannot be empty")

    result = runner.invoke(app, ["create", ""])
    assert result.exit_code == 1
    assert "Error" in result.output


@patch("cape.cli.cli.create_issue")
def test_create_from_file_success(mock_create_issue, tmp_path):
    """Test successful issue creation from file."""
    mock_issue = CapeIssue(id=456, description="File issue", status="pending")
    mock_create_issue.return_value = mock_issue

    # Create temp file with issue description
    issue_file = tmp_path / "issue.txt"
    issue_file.write_text("File issue description")

    result = runner.invoke(app, ["create-from-file", str(issue_file)])
    assert result.exit_code == 0
    assert "456" in result.output


def test_create_from_file_not_found():
    """Test create-from-file with non-existent file."""
    result = runner.invoke(app, ["create-from-file", "/nonexistent/file.txt"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_create_from_file_empty(tmp_path):
    """Test create-from-file with empty file."""
    issue_file = tmp_path / "empty.txt"
    issue_file.write_text("")

    result = runner.invoke(app, ["create-from-file", str(issue_file)])
    assert result.exit_code == 1
    assert "empty" in result.output.lower()


def test_create_from_file_directory(tmp_path):
    """Test create-from-file with directory instead of file."""
    result = runner.invoke(app, ["create-from-file", str(tmp_path)])
    assert result.exit_code == 1
    assert "not a file" in result.output.lower()


@patch("cape.cli.cli.execute_workflow")
@patch("cape.cli.cli.setup_logger")
def test_run_command_success(mock_logger, mock_execute):
    """Test successful workflow execution."""
    mock_logger.return_value = Mock()
    mock_execute.return_value = True

    result = runner.invoke(app, ["run", "123"])
    assert result.exit_code == 0
    mock_execute.assert_called_once()


@patch("cape.cli.cli.execute_workflow")
@patch("cape.cli.cli.setup_logger")
def test_run_command_failure(mock_logger, mock_execute):
    """Test workflow execution failure."""
    mock_logger.return_value = Mock()
    mock_execute.return_value = False

    result = runner.invoke(app, ["run", "123"])
    assert result.exit_code == 1


@patch("cape.cli.cli.execute_workflow")
@patch("cape.cli.cli.setup_logger")
def test_run_command_with_adw_id(mock_logger, mock_execute):
    """Test run command with custom ADW ID."""
    mock_logger.return_value = Mock()
    mock_execute.return_value = True

    result = runner.invoke(app, ["run", "123", "--adw-id", "custom123"])
    assert result.exit_code == 0
    # Verify the custom ADW ID was passed
    call_args = mock_logger.call_args
    assert call_args[0][0] == "custom123"


def test_run_command_invalid_issue_id():
    """Test run command with invalid issue ID."""
    result = runner.invoke(app, ["run", "not-a-number"])
    assert result.exit_code != 0
