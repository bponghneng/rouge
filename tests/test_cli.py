"""Tests for CLI commands."""

from unittest.mock import patch

from typer.testing import CliRunner

from rouge.cli.cli import app
from rouge.core.models import Issue

runner = CliRunner()


def test_cli_help():
    """Test CLI help command."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Rouge CLI" in result.output


def test_cli_version():
    """Test version flag."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "version" in result.output.lower()


@patch("rouge.cli.cli.create_issue")
def test_create_command_success(mock_create_issue):
    """Test successful issue creation via CLI."""
    mock_issue = Issue(id=123, description="Test issue", status="pending")
    mock_create_issue.return_value = mock_issue

    result = runner.invoke(app, ["create", "Test issue"])
    assert result.exit_code == 0
    assert "123" in result.output
    mock_create_issue.assert_called_once_with("Test issue")


@patch("rouge.cli.cli.create_issue")
def test_create_command_empty_description(mock_create_issue):
    """Test create command with empty description."""
    mock_create_issue.side_effect = ValueError("Issue description cannot be empty")

    result = runner.invoke(app, ["create", ""])
    assert result.exit_code == 1
    assert "Error" in result.output


@patch("rouge.cli.cli.create_issue")
def test_create_from_file_success(mock_create_issue, tmp_path):
    """Test successful issue creation from file."""
    mock_issue = Issue(id=456, description="File issue", status="pending")
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


@patch("rouge.cli.cli.execute_adw_workflow")
def test_run_command_success(mock_execute):
    """Test successful workflow execution."""
    mock_execute.return_value = (True, "some-workflow-id")

    result = runner.invoke(app, ["run", "123"])
    assert result.exit_code == 0
    mock_execute.assert_called_once()


@patch("rouge.cli.cli.execute_adw_workflow")
def test_run_command_failure(mock_execute):
    """Test workflow execution failure."""
    mock_execute.return_value = (False, "some-workflow-id")

    result = runner.invoke(app, ["run", "123"])
    assert result.exit_code == 1


@patch("rouge.cli.cli.execute_adw_workflow")
@patch("rouge.cli.cli.make_adw_id")
def test_run_command_with_adw_id(mock_make_adw_id, mock_execute):
    """Test run command with custom ADW ID."""
    mock_execute.return_value = (True, "some-workflow-id")

    result = runner.invoke(app, ["run", "123", "--adw-id", "custom123"])
    assert result.exit_code == 0
    # When custom ADW ID is provided, make_adw_id should not be called
    mock_make_adw_id.assert_not_called()
    # Verify the custom ADW ID was passed to execute_adw_workflow
    call_args = mock_execute.call_args
    assert call_args[0][1] == "custom123"


def test_run_command_invalid_issue_id():
    """Test run command with invalid issue ID."""
    result = runner.invoke(app, ["run", "not-a-number"])
    assert result.exit_code != 0


# Tests for patch command


@patch("rouge.cli.cli.execute_adw_workflow")
def test_patch_command_success(mock_execute):
    """Test successful patch workflow execution."""
    mock_execute.return_value = (True, "some-workflow-id")

    result = runner.invoke(app, ["patch", "123"])
    assert result.exit_code == 0
    mock_execute.assert_called_once()
    # Verify workflow_type="patch" was passed
    call_args = mock_execute.call_args
    assert call_args[1].get("workflow_type") == "patch" or (
        len(call_args[0]) >= 3 and call_args[0][2] == "patch"
    )


@patch("rouge.cli.cli.execute_adw_workflow")
def test_patch_command_failure(mock_execute):
    """Test patch workflow execution failure."""
    mock_execute.return_value = (False, "some-workflow-id")

    result = runner.invoke(app, ["patch", "123"])
    assert result.exit_code == 1


@patch("rouge.cli.cli.execute_adw_workflow")
@patch("rouge.cli.cli.make_adw_id")
def test_patch_command_with_adw_id(mock_make_adw_id, mock_execute):
    """Test patch command with custom ADW ID."""
    mock_execute.return_value = (True, "some-workflow-id")

    result = runner.invoke(app, ["patch", "123", "--adw-id", "custom123"])
    assert result.exit_code == 0
    # When custom ADW ID is provided, make_adw_id should not be called
    mock_make_adw_id.assert_not_called()
    # Verify the custom ADW ID was passed to execute_adw_workflow
    call_args = mock_execute.call_args
    assert call_args[0][1] == "custom123"


def test_patch_command_invalid_issue_id():
    """Test patch command with invalid issue ID."""
    result = runner.invoke(app, ["patch", "not-a-number"])
    assert result.exit_code != 0


# Tests for new-patch command


@patch("rouge.cli.cli.create_issue")
def test_new_patch_success(mock_create_issue, tmp_path):
    """Test successful patch issue creation from file."""
    mock_issue = Issue(id=789, description="Patch issue", status="pending")
    mock_create_issue.return_value = mock_issue

    # Create temp file with patch description
    patch_file = tmp_path / "patch.txt"
    patch_file.write_text("Patch issue description")

    result = runner.invoke(
        app,
        ["new-patch", str(patch_file)],
    )
    assert result.exit_code == 0
    assert "789" in result.output
    mock_create_issue.assert_called_once_with(
        description="Patch issue description",
        issue_type="patch",
    )


def test_new_patch_file_not_found():
    """Test new-patch with non-existent file."""
    result = runner.invoke(
        app,
        ["new-patch", "/nonexistent/file.txt"],
    )
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


def test_new_patch_empty_file(tmp_path):
    """Test new-patch with empty file."""
    patch_file = tmp_path / "empty.txt"
    patch_file.write_text("")

    result = runner.invoke(
        app,
        ["new-patch", str(patch_file)],
    )
    assert result.exit_code == 1
    assert "empty" in result.output.lower()


def test_new_patch_directory_instead_of_file(tmp_path):
    """Test new-patch with directory instead of file."""
    result = runner.invoke(
        app,
        ["new-patch", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "not a file" in result.output.lower()


@patch("rouge.cli.cli.create_issue")
def test_new_patch_whitespace_only_file(mock_create_issue, tmp_path):
    """Test new-patch with file containing only whitespace."""
    patch_file = tmp_path / "whitespace.txt"
    patch_file.write_text("   \n\t\n   ")

    result = runner.invoke(
        app,
        ["new-patch", str(patch_file)],
    )
    assert result.exit_code == 1
    assert "empty" in result.output.lower()
    mock_create_issue.assert_not_called()
