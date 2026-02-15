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
        issue_type="main",
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
        issue_type="main",
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
        issue_type="main",
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


def test_new_command_non_utf8_spec_file(tmp_path):
    """Test new command with non-UTF-8 spec file."""
    spec_file = tmp_path / "bad.txt"
    spec_file.write_bytes(b"\xff\xfe")

    result = runner.invoke(app, ["new", "--spec-file", str(spec_file), "--title", "Title"])
    assert result.exit_code == 1
    assert "not valid UTF-8" in result.output


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
        issue_type="main",
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
        issue_type="main",
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
        issue_type="main",
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


# Tests for read command


@patch("rouge.cli.cli.fetch_issue")
def test_read_command_success(mock_fetch_issue):
    """Test read command with valid issue ID."""
    mock_issue = Issue(
        id=123,
        title="Test Issue",
        description="This is a test issue description",
        status="pending",
        type="main",
        assigned_to="local-1",
        branch="feature/test",
        adw_id="test-adw-123",
    )
    mock_fetch_issue.return_value = mock_issue

    result = runner.invoke(app, ["read", "123"])
    assert result.exit_code == 0
    assert "Issue #123" in result.output
    assert "Title: Test Issue" in result.output
    assert "Type: main" in result.output
    assert "Status: pending" in result.output
    assert "Assigned to: local-1" in result.output
    assert "Branch: feature/test" in result.output
    assert "ADW ID: test-adw-123" in result.output
    assert "Description:" in result.output
    assert "This is a test issue description" in result.output
    mock_fetch_issue.assert_called_once_with(123)


@patch("rouge.cli.cli.fetch_issue")
def test_read_command_minimal_issue(mock_fetch_issue):
    """Test read command with minimal issue (only required fields)."""
    mock_issue = Issue(
        id=456,
        description="Minimal issue description",
        status="pending",
    )
    mock_fetch_issue.return_value = mock_issue

    result = runner.invoke(app, ["read", "456"])
    assert result.exit_code == 0
    assert "Issue #456" in result.output
    assert "Title: (none)" in result.output
    assert "Type: main" in result.output
    assert "Status: pending" in result.output
    assert "Assigned to: (none)" in result.output
    assert "Minimal issue description" in result.output
    # Branch and ADW ID should not appear when not set
    assert "Branch:" not in result.output
    assert "ADW ID:" not in result.output
    mock_fetch_issue.assert_called_once_with(456)


@patch("rouge.cli.cli.fetch_issue")
def test_read_command_non_existent_issue(mock_fetch_issue):
    """Test read command with non-existent issue ID."""
    mock_fetch_issue.side_effect = ValueError("Issue not found")

    result = runner.invoke(app, ["read", "999"])
    assert result.exit_code == 1
    assert "Error: Issue not found" in result.output
    mock_fetch_issue.assert_called_once_with(999)


@patch("rouge.cli.cli.fetch_issue")
def test_read_command_database_error(mock_fetch_issue):
    """Test read command handles unexpected errors."""
    mock_fetch_issue.side_effect = Exception("Database connection failed")

    result = runner.invoke(app, ["read", "123"])
    assert result.exit_code == 1
    assert "Unexpected error: Database connection failed" in result.output
    mock_fetch_issue.assert_called_once_with(123)


@patch("rouge.cli.cli.fetch_issue")
def test_read_command_completed_issue(mock_fetch_issue):
    """Test read command with completed issue."""
    mock_issue = Issue(
        id=789,
        title="Completed Task",
        description="This task is done",
        status="completed",
        type="patch",
    )
    mock_fetch_issue.return_value = mock_issue

    result = runner.invoke(app, ["read", "789"])
    assert result.exit_code == 0
    assert "Issue #789" in result.output
    assert "Status: completed" in result.output
    assert "Type: patch" in result.output


# Tests for list command


@patch("rouge.cli.cli.fetch_all_issues")
def test_list_command_no_issues(mock_fetch_all_issues):
    """Test list command with no issues."""
    mock_fetch_all_issues.return_value = []

    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "No issues found." in result.output
    mock_fetch_all_issues.assert_called_once()


@patch("rouge.cli.cli.fetch_all_issues")
def test_list_command_single_issue(mock_fetch_all_issues):
    """Test list command with single issue."""
    mock_issue = Issue(
        id=1,
        title="Single Issue",
        description="Test description",
        status="pending",
        type="main",
    )
    mock_fetch_all_issues.return_value = [mock_issue]

    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "ID" in result.output
    assert "Title" in result.output
    assert "Type" in result.output
    assert "Status" in result.output
    assert "Assigned To" in result.output
    assert "1" in result.output
    assert "Single Issue" in result.output
    assert "pending" in result.output
    assert "main" in result.output
    assert "(none)" in result.output  # No assignment
    mock_fetch_all_issues.assert_called_once()


@patch("rouge.cli.cli.fetch_all_issues")
def test_list_command_multiple_issues(mock_fetch_all_issues):
    """Test list command with multiple issues."""
    mock_issues = [
        Issue(
            id=1,
            title="First Issue",
            description="First description",
            status="pending",
            type="main",
            assigned_to="local-1",
        ),
        Issue(
            id=2,
            title="Second Issue",
            description="Second description",
            status="started",
            type="patch",
            assigned_to="local-2",
        ),
        Issue(
            id=3,
            title="Third Issue",
            description="Third description",
            status="completed",
            type="main",
        ),
    ]
    mock_fetch_all_issues.return_value = mock_issues

    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    # Check header is present
    assert "ID" in result.output
    assert "Title" in result.output
    # Check all issues are present
    assert "1" in result.output
    assert "First Issue" in result.output
    assert "local-1" in result.output
    assert "2" in result.output
    assert "Second Issue" in result.output
    assert "local-2" in result.output
    assert "3" in result.output
    assert "Third Issue" in result.output
    assert "(none)" in result.output  # Third issue has no assignment
    mock_fetch_all_issues.assert_called_once()


@patch("rouge.cli.cli.fetch_all_issues")
def test_list_command_json_format(mock_fetch_all_issues):
    """Test list command with JSON output format."""
    mock_issues = [
        Issue(
            id=1,
            title="JSON Test Issue",
            description="Test description",
            status="pending",
            type="main",
        ),
    ]
    mock_fetch_all_issues.return_value = mock_issues

    result = runner.invoke(app, ["list", "--format", "json"])
    assert result.exit_code == 0
    # Verify JSON output
    import json

    issues_data = json.loads(result.output)
    assert isinstance(issues_data, list)
    assert len(issues_data) == 1
    assert issues_data[0]["id"] == 1
    assert issues_data[0]["title"] == "JSON Test Issue"
    assert issues_data[0]["description"] == "Test description"
    assert issues_data[0]["status"] == "pending"
    assert issues_data[0]["type"] == "main"
    mock_fetch_all_issues.assert_called_once()


@patch("rouge.cli.cli.fetch_all_issues")
def test_list_command_json_format_empty(mock_fetch_all_issues):
    """Test list command with JSON format and no issues."""
    mock_fetch_all_issues.return_value = []

    result = runner.invoke(app, ["list", "--format", "json"])
    assert result.exit_code == 0
    # Should output empty JSON array
    import json

    issues_data = json.loads(result.output)
    assert isinstance(issues_data, list)
    assert len(issues_data) == 0
    mock_fetch_all_issues.assert_called_once()


@patch("rouge.cli.cli.fetch_all_issues")
def test_list_command_table_format_explicit(mock_fetch_all_issues):
    """Test list command with explicit table format."""
    mock_issue = Issue(
        id=1,
        title="Table Test",
        description="Test",
        status="pending",
        type="main",
    )
    mock_fetch_all_issues.return_value = [mock_issue]

    result = runner.invoke(app, ["list", "--format", "table"])
    assert result.exit_code == 0
    assert "ID" in result.output
    assert "Table Test" in result.output
    mock_fetch_all_issues.assert_called_once()


@patch("rouge.cli.cli.fetch_all_issues")
def test_list_command_short_format_flag(mock_fetch_all_issues):
    """Test list command with -f short flag."""
    mock_issue = Issue(
        id=1,
        title="Short Flag Test",
        description="Test",
        status="pending",
        type="main",
    )
    mock_fetch_all_issues.return_value = [mock_issue]

    result = runner.invoke(app, ["list", "-f", "json"])
    assert result.exit_code == 0
    import json

    issues_data = json.loads(result.output)
    assert len(issues_data) == 1
    assert issues_data[0]["title"] == "Short Flag Test"
    mock_fetch_all_issues.assert_called_once()


@patch("rouge.cli.cli.fetch_all_issues")
def test_list_command_truncates_long_title(mock_fetch_all_issues):
    """Test list command truncates very long titles in table format."""
    long_title = "This is a very long title that should be truncated in the table view"
    mock_issue = Issue(
        id=1,
        title=long_title,
        description="Test",
        status="pending",
        type="main",
    )
    mock_fetch_all_issues.return_value = [mock_issue]

    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    # Title should be truncated with "..."
    assert "..." in result.output
    # Full title should not appear in table output
    assert long_title not in result.output
    mock_fetch_all_issues.assert_called_once()


@patch("rouge.cli.cli.fetch_all_issues")
def test_list_command_database_error(mock_fetch_all_issues):
    """Test list command handles database errors."""
    mock_fetch_all_issues.side_effect = ValueError("Database error")

    result = runner.invoke(app, ["list"])
    assert result.exit_code == 1
    assert "Error: Database error" in result.output
    mock_fetch_all_issues.assert_called_once()


@patch("rouge.cli.cli.fetch_all_issues")
def test_list_command_unexpected_error(mock_fetch_all_issues):
    """Test list command handles unexpected errors."""
    mock_fetch_all_issues.side_effect = Exception("Unexpected failure")

    result = runner.invoke(app, ["list"])
    assert result.exit_code == 1
    assert "Unexpected error: Unexpected failure" in result.output
    mock_fetch_all_issues.assert_called_once()


# Tests for update command


@patch("rouge.cli.cli.update_issue")
def test_update_command_single_field_assigned_to(mock_update_issue):
    """Test update command with single field (assigned_to)."""
    mock_issue = Issue(
        id=123,
        description="Test description",
        status="pending",
        assigned_to="alleycat-1",
    )
    mock_update_issue.return_value = mock_issue

    result = runner.invoke(app, ["update", "123", "--assigned-to", "alleycat-1"])
    assert result.exit_code == 0
    assert "123" in result.output
    mock_update_issue.assert_called_once_with(123, assigned_to="alleycat-1")


@patch("rouge.cli.cli.update_issue")
def test_update_command_single_field_type(mock_update_issue):
    """Test update command with single field (type)."""
    mock_issue = Issue(
        id=456,
        description="Test description",
        status="pending",
        type="patch",
    )
    mock_update_issue.return_value = mock_issue

    result = runner.invoke(app, ["update", "456", "--type", "patch"])
    assert result.exit_code == 0
    assert "456" in result.output
    mock_update_issue.assert_called_once_with(456, issue_type="patch")


@patch("rouge.cli.cli.update_issue")
def test_update_command_single_field_title(mock_update_issue):
    """Test update command with single field (title)."""
    mock_issue = Issue(
        id=789,
        title="New Title",
        description="Test description",
        status="pending",
    )
    mock_update_issue.return_value = mock_issue

    result = runner.invoke(app, ["update", "789", "--title", "New Title"])
    assert result.exit_code == 0
    assert "789" in result.output
    mock_update_issue.assert_called_once_with(789, title="New Title")


@patch("rouge.cli.cli.update_issue")
def test_update_command_single_field_description(mock_update_issue):
    """Test update command with single field (description)."""
    mock_issue = Issue(
        id=111,
        description="New description with more than 10 characters",
        status="pending",
    )
    mock_update_issue.return_value = mock_issue

    result = runner.invoke(
        app, ["update", "111", "--description", "New description with more than 10 characters"]
    )
    assert result.exit_code == 0
    assert "111" in result.output
    mock_update_issue.assert_called_once_with(
        111, description="New description with more than 10 characters"
    )


@patch("rouge.cli.cli.update_issue")
def test_update_command_multiple_fields(mock_update_issue):
    """Test update command with multiple fields simultaneously."""
    mock_issue = Issue(
        id=222,
        title="Updated Title",
        description="Updated description here",
        status="pending",
        type="patch",
        assigned_to="alleycat-2",
    )
    mock_update_issue.return_value = mock_issue

    result = runner.invoke(
        app,
        [
            "update",
            "222",
            "--title",
            "Updated Title",
            "--description",
            "Updated description here",
            "--type",
            "patch",
            "--assigned-to",
            "alleycat-2",
        ],
    )
    assert result.exit_code == 0
    assert "222" in result.output
    mock_update_issue.assert_called_once_with(
        222,
        title="Updated Title",
        description="Updated description here",
        issue_type="patch",
        assigned_to="alleycat-2",
    )


@patch("rouge.cli.cli.update_issue")
def test_update_command_no_fields_provided(mock_update_issue):
    """Test update command with no fields provided (should show error)."""
    mock_update_issue.side_effect = ValueError("No fields provided for update")

    result = runner.invoke(app, ["update", "123"])
    assert result.exit_code == 1
    assert "Error: No fields provided for update" in result.output
    mock_update_issue.assert_called_once_with(123)


@patch("rouge.cli.cli.update_issue")
def test_update_command_invalid_worker_id(mock_update_issue):
    """Test update command with invalid worker ID."""
    mock_update_issue.side_effect = ValueError(
        "Invalid worker ID 'invalid-worker'. Must be one of: alleycat-1, alleycat-2, "
        "local-1, local-2, local-3"
    )

    result = runner.invoke(app, ["update", "123", "--assigned-to", "invalid-worker"])
    assert result.exit_code == 1
    assert "Error: Invalid worker ID 'invalid-worker'" in result.output
    mock_update_issue.assert_called_once_with(123, assigned_to="invalid-worker")


@patch("rouge.cli.cli.update_issue")
def test_update_command_invalid_type(mock_update_issue):
    """Test update command with invalid type."""
    mock_update_issue.side_effect = ValueError(
        "Invalid issue_type 'invalid'. Must be one of: main, patch"
    )

    result = runner.invoke(app, ["update", "123", "--type", "invalid"])
    assert result.exit_code == 1
    assert "Error: Invalid issue_type 'invalid'" in result.output
    mock_update_issue.assert_called_once_with(123, issue_type="invalid")


@patch("rouge.cli.cli.update_issue")
def test_update_command_empty_title(mock_update_issue):
    """Test update command with empty title."""
    mock_update_issue.side_effect = ValueError("Title cannot be empty/whitespace if provided")

    result = runner.invoke(app, ["update", "123", "--title", "   "])
    assert result.exit_code == 1
    assert "Error: Title cannot be empty/whitespace if provided" in result.output
    mock_update_issue.assert_called_once_with(123, title="   ")


@patch("rouge.cli.cli.update_issue")
def test_update_command_empty_description(mock_update_issue):
    """Test update command with empty description."""
    mock_update_issue.side_effect = ValueError("Description cannot be empty")

    result = runner.invoke(app, ["update", "123", "--description", ""])
    assert result.exit_code == 1
    assert "Error: Description cannot be empty" in result.output
    mock_update_issue.assert_called_once_with(123, description="")


@patch("rouge.cli.cli.update_issue")
def test_update_command_non_existent_issue(mock_update_issue):
    """Test update command with non-existent issue ID."""
    mock_update_issue.side_effect = ValueError("Issue with id 999 not found")

    result = runner.invoke(app, ["update", "999", "--title", "New Title"])
    assert result.exit_code == 1
    assert "Error: Issue with id 999 not found" in result.output
    mock_update_issue.assert_called_once_with(999, title="New Title")


@patch("rouge.cli.cli.update_issue")
def test_update_command_type_error(mock_update_issue):
    """Test update command handles TypeError."""
    mock_update_issue.side_effect = TypeError("Worker ID must be a string")

    result = runner.invoke(app, ["update", "123", "--assigned-to", "worker1"])
    assert result.exit_code == 1
    assert "Error: Worker ID must be a string" in result.output
    mock_update_issue.assert_called_once_with(123, assigned_to="worker1")


@patch("rouge.cli.cli.update_issue")
def test_update_command_unexpected_error(mock_update_issue):
    """Test update command handles unexpected errors."""
    mock_update_issue.side_effect = Exception("Database connection failed")

    result = runner.invoke(app, ["update", "123", "--title", "New Title"])
    assert result.exit_code == 1
    assert "Unexpected error: Database connection failed" in result.output
    mock_update_issue.assert_called_once_with(123, title="New Title")


# Tests for delete command


@patch("rouge.cli.cli.delete_issue")
def test_delete_command_with_force(mock_delete_issue):
    """Test delete command with --force flag (no confirmation)."""
    mock_delete_issue.return_value = True

    result = runner.invoke(app, ["delete", "123", "--force"])
    assert result.exit_code == 0
    assert "Issue 123 deleted successfully." in result.output
    mock_delete_issue.assert_called_once_with(123)


@patch("rouge.cli.cli.delete_issue")
def test_delete_command_with_confirmation_yes(mock_delete_issue):
    """Test delete command with confirmation (user answers yes)."""
    mock_delete_issue.return_value = True

    result = runner.invoke(app, ["delete", "456"], input="y\n")
    assert result.exit_code == 0
    assert "Delete issue 456?" in result.output
    assert "Issue 456 deleted successfully." in result.output
    mock_delete_issue.assert_called_once_with(456)


@patch("rouge.cli.cli.delete_issue")
def test_delete_command_with_confirmation_yes_full(mock_delete_issue):
    """Test delete command with confirmation (user answers 'yes' full word)."""
    mock_delete_issue.return_value = True

    result = runner.invoke(app, ["delete", "789"], input="yes\n")
    assert result.exit_code == 0
    assert "Delete issue 789?" in result.output
    assert "Issue 789 deleted successfully." in result.output
    mock_delete_issue.assert_called_once_with(789)


@patch("rouge.cli.cli.delete_issue")
def test_delete_command_with_confirmation_no(mock_delete_issue):
    """Test delete command with confirmation (user answers no)."""
    result = runner.invoke(app, ["delete", "111"], input="n\n")
    assert result.exit_code == 0
    assert "Delete issue 111?" in result.output
    assert "Deletion cancelled." in result.output
    mock_delete_issue.assert_not_called()


@patch("rouge.cli.cli.delete_issue")
def test_delete_command_with_confirmation_empty(mock_delete_issue):
    """Test delete command with confirmation (user enters just whitespace)."""
    result = runner.invoke(app, ["delete", "222"], input=" \n")
    assert result.exit_code == 0
    assert "Delete issue 222?" in result.output
    assert "Deletion cancelled." in result.output
    mock_delete_issue.assert_not_called()


@patch("rouge.cli.cli.delete_issue")
def test_delete_command_with_confirmation_invalid(mock_delete_issue):
    """Test delete command with confirmation (user answers something else)."""
    result = runner.invoke(app, ["delete", "333"], input="maybe\n")
    assert result.exit_code == 0
    assert "Delete issue 333?" in result.output
    assert "Deletion cancelled." in result.output
    mock_delete_issue.assert_not_called()


@patch("rouge.cli.cli.delete_issue")
def test_delete_command_non_existent_issue(mock_delete_issue):
    """Test delete command with non-existent issue ID."""
    mock_delete_issue.side_effect = ValueError("Issue with id 999 not found")

    result = runner.invoke(app, ["delete", "999", "--force"])
    assert result.exit_code == 1
    assert "Error: Issue with id 999 not found" in result.output
    mock_delete_issue.assert_called_once_with(999)


@patch("rouge.cli.cli.delete_issue")
def test_delete_command_database_error(mock_delete_issue):
    """Test delete command handles database errors."""
    mock_delete_issue.side_effect = ValueError("Database error")

    result = runner.invoke(app, ["delete", "123", "--force"])
    assert result.exit_code == 1
    assert "Error: Database error" in result.output
    mock_delete_issue.assert_called_once_with(123)


@patch("rouge.cli.cli.delete_issue")
def test_delete_command_unexpected_error(mock_delete_issue):
    """Test delete command handles unexpected errors."""
    mock_delete_issue.side_effect = Exception("Unexpected failure")

    result = runner.invoke(app, ["delete", "123", "--force"])
    assert result.exit_code == 1
    assert "Unexpected error: Unexpected failure" in result.output
    mock_delete_issue.assert_called_once_with(123)
