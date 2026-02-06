"""Tests for CLI commands."""

from unittest.mock import patch

from typer.testing import CliRunner

from rouge.cli.cli import app, generate_title
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


# Tests for generate_title helper function


def test_generate_title_short_description():
    """Test generate_title with description of 10 words or fewer."""
    description = "Fix the login bug"
    result = generate_title(description)
    assert result == "Fix the login bug"


def test_generate_title_exact_10_words():
    """Test generate_title with exactly 10 words."""
    description = "One two three four five six seven eight nine ten"
    result = generate_title(description)
    assert result == "One two three four five six seven eight nine ten"


def test_generate_title_long_description():
    """Test generate_title with description longer than 10 words."""
    description = "One two three four five six seven eight nine ten eleven twelve"
    result = generate_title(description)
    assert result == "One two three four five six seven eight nine ten..."


def test_generate_title_empty_description():
    """Test generate_title with empty description."""
    assert generate_title("") == ""


def test_generate_title_whitespace_only():
    """Test generate_title with whitespace-only description."""
    assert generate_title("   ") == ""
    assert generate_title("\n\t") == ""


def test_generate_title_none():
    """Test generate_title with None."""
    assert generate_title(None) == ""


def test_generate_title_preserves_words():
    """Test that generate_title preserves word content correctly."""
    description = "Implement dark mode toggle in the application settings page component now"
    result = generate_title(description)
    assert result == "Implement dark mode toggle in the application settings page component..."


# Tests for new command


@patch("rouge.cli.cli.create_issue")
def test_new_command_description_only(mock_create_issue):
    """Test new command with description only (auto-generated title)."""
    mock_issue = Issue(id=123, description="Fix the login bug", status="pending")
    mock_create_issue.return_value = mock_issue

    result = runner.invoke(app, ["new", "Fix the login bug"])
    assert result.exit_code == 0
    assert "123" in result.output
    mock_create_issue.assert_called_once_with(
        description="Fix the login bug",
        title="Fix the login bug",
    )


@patch("rouge.cli.cli.create_issue")
def test_new_command_description_with_explicit_title(mock_create_issue):
    """Test new command with description and explicit title."""
    mock_issue = Issue(id=456, description="Fix the login bug", status="pending")
    mock_create_issue.return_value = mock_issue

    result = runner.invoke(
        app, ["new", "Fix the login bug in the auth module", "--title", "Login fix"]
    )
    assert result.exit_code == 0
    assert "456" in result.output
    mock_create_issue.assert_called_once_with(
        description="Fix the login bug in the auth module",
        title="Login fix",
    )


@patch("rouge.cli.cli.create_issue")
def test_new_command_spec_file_with_title(mock_create_issue, tmp_path):
    """Test new command with spec file and title."""
    mock_issue = Issue(id=789, description="Detailed spec content", status="pending")
    mock_create_issue.return_value = mock_issue

    spec_file = tmp_path / "spec.txt"
    spec_file.write_text("Detailed spec content from file")

    result = runner.invoke(app, ["new", "--spec-file", str(spec_file), "--title", "Feature X"])
    assert result.exit_code == 0
    assert "789" in result.output
    mock_create_issue.assert_called_once_with(
        description="Detailed spec content from file",
        title="Feature X",
    )


def test_new_command_spec_file_without_title(tmp_path):
    """Test new command with spec file but no title (should error)."""
    spec_file = tmp_path / "spec.txt"
    spec_file.write_text("Detailed spec content")

    result = runner.invoke(app, ["new", "--spec-file", str(spec_file)])
    assert result.exit_code == 1
    assert "--spec-file requires explicit --title" in result.output


def test_new_command_description_and_spec_file_error(tmp_path):
    """Test new command with both description and spec-file (should error: mutually exclusive)."""
    spec_file = tmp_path / "spec.txt"
    spec_file.write_text("Spec content")

    result = runner.invoke(
        app,
        ["new", "Some description", "--spec-file", str(spec_file), "--title", "Title"],
    )
    assert result.exit_code == 1
    assert "Cannot use both description argument and --spec-file" in result.output


def test_new_command_no_description_no_spec_file():
    """Test new command with neither description nor spec-file (should error)."""
    result = runner.invoke(app, ["new"])
    assert result.exit_code == 1
    assert "Must provide either a description argument or --spec-file" in result.output


def test_new_command_file_not_found():
    """Test new command with non-existent spec file."""
    result = runner.invoke(app, ["new", "--spec-file", "/nonexistent/file.txt", "--title", "Title"])
    assert result.exit_code == 1
    assert "File not found" in result.output


def test_new_command_empty_file(tmp_path):
    """Test new command with empty spec file."""
    spec_file = tmp_path / "empty.txt"
    spec_file.write_text("")

    result = runner.invoke(app, ["new", "--spec-file", str(spec_file), "--title", "Title"])
    assert result.exit_code == 1
    assert "File is empty" in result.output


def test_new_command_directory_instead_of_file(tmp_path):
    """Test new command with directory instead of file."""
    result = runner.invoke(app, ["new", "--spec-file", str(tmp_path), "--title", "Title"])
    assert result.exit_code == 1
    assert "not a file" in result.output.lower()


def test_new_command_empty_description():
    """Test new command with empty string description.

    Note: Typer treats an empty string argument as no argument provided,
    so this triggers the 'must provide description or spec-file' error.
    """
    result = runner.invoke(app, ["new", ""])
    assert result.exit_code == 1
    assert "Must provide either a description argument or --spec-file" in result.output


def test_new_command_whitespace_description():
    """Test new command with whitespace-only description."""
    result = runner.invoke(app, ["new", "   "])
    assert result.exit_code == 1
    assert "Description cannot be empty" in result.output


@patch("rouge.cli.cli.create_issue")
def test_new_command_whitespace_only_file(mock_create_issue, tmp_path):
    """Test new command with file containing only whitespace."""
    spec_file = tmp_path / "whitespace.txt"
    spec_file.write_text("   \n\t\n   ")

    result = runner.invoke(app, ["new", "--spec-file", str(spec_file), "--title", "Title"])
    assert result.exit_code == 1
    assert "File is empty" in result.output
    mock_create_issue.assert_not_called()


@patch("rouge.cli.cli.create_issue")
def test_new_command_long_description_auto_title(mock_create_issue):
    """Test new command with long description gets truncated auto-generated title."""
    mock_issue = Issue(id=111, description="Long description", status="pending")
    mock_create_issue.return_value = mock_issue

    long_desc = "One two three four five six seven eight nine ten eleven twelve thirteen"
    result = runner.invoke(app, ["new", long_desc])
    assert result.exit_code == 0
    assert "111" in result.output
    mock_create_issue.assert_called_once_with(
        description=long_desc,
        title="One two three four five six seven eight nine ten...",
    )


@patch("rouge.cli.cli.create_issue")
def test_new_command_create_issue_value_error(mock_create_issue):
    """Test new command handles ValueError from create_issue."""
    mock_create_issue.side_effect = ValueError("Database error")

    result = runner.invoke(app, ["new", "Some description"])
    assert result.exit_code == 1
    assert "Error: Database error" in result.output


@patch("rouge.cli.cli.create_issue")
def test_new_command_short_title_flag(mock_create_issue):
    """Test new command with -t short flag for title."""
    mock_issue = Issue(id=222, description="Description", status="pending")
    mock_create_issue.return_value = mock_issue

    result = runner.invoke(app, ["new", "Some description", "-t", "Short Title"])
    assert result.exit_code == 0
    assert "222" in result.output
    mock_create_issue.assert_called_once_with(
        description="Some description",
        title="Short Title",
    )


@patch("rouge.cli.cli.create_issue")
def test_new_command_short_spec_file_flag(mock_create_issue, tmp_path):
    """Test new command with -f short flag for spec-file."""
    mock_issue = Issue(id=333, description="File content", status="pending")
    mock_create_issue.return_value = mock_issue

    spec_file = tmp_path / "spec.txt"
    spec_file.write_text("File content from short flag")

    result = runner.invoke(app, ["new", "-f", str(spec_file), "-t", "Title from Short Flags"])
    assert result.exit_code == 0
    assert "333" in result.output
    mock_create_issue.assert_called_once_with(
        description="File content from short flag",
        title="Title from Short Flags",
    )


# Tests for run command


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
    assert call_args.kwargs.get("workflow_type") == "patch"


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
