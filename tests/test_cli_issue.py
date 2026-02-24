"""Tests for issue CLI commands."""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from rouge.cli.issue import app, generate_title
from rouge.core.models import Issue

runner = CliRunner()


# Tests for generate_title helper function


def test_generate_title_short_description() -> None:
    """Test generate_title with description of 10 words or fewer."""
    description = "Fix the login bug"
    result = generate_title(description)
    assert result == "Fix the login bug"


def test_generate_title_exact_10_words() -> None:
    """Test generate_title with exactly 10 words."""
    description = "One two three four five six seven eight nine ten"
    result = generate_title(description)
    assert result == "One two three four five six seven eight nine ten"


def test_generate_title_long_description() -> None:
    """Test generate_title with description longer than 10 words."""
    description = "One two three four five six seven eight nine ten eleven twelve"
    result = generate_title(description)
    assert result == "One two three four five six seven eight nine ten..."


def test_generate_title_empty_description() -> None:
    """Test generate_title with empty description."""
    assert generate_title("") == ""


def test_generate_title_whitespace_only() -> None:
    """Test generate_title with whitespace-only description."""
    assert generate_title("   ") == ""
    assert generate_title("\n\t") == ""


def test_generate_title_none() -> None:
    """Test generate_title with None."""
    assert generate_title(None) == ""


def test_generate_title_preserves_words() -> None:
    """Test that generate_title preserves word content correctly."""
    description = "Implement dark mode toggle in the application settings page component now"
    result = generate_title(description)
    assert result == "Implement dark mode toggle in the application settings page component..."


# Tests for create command


@patch("rouge.cli.issue.create_issue")
def test_create_command_description_only(mock_create_issue) -> None:
    """Test create command with description only (auto-generated title)."""
    mock_issue = Issue(id=123, description="Fix the login bug", status="pending")
    mock_create_issue.return_value = mock_issue

    result = runner.invoke(app, ["create", "Fix the login bug"])
    assert result.exit_code == 0
    assert "123" in result.output
    mock_create_issue.assert_called_once_with(
        description="Fix the login bug",
        title="Fix the login bug",
        issue_type="main",
        branch=None,
    )


@patch("rouge.cli.issue.create_issue")
def test_create_command_description_with_explicit_title(mock_create_issue) -> None:
    """Test create command with description and explicit title."""
    mock_issue = Issue(id=456, description="Fix the login bug", status="pending")
    mock_create_issue.return_value = mock_issue

    result = runner.invoke(
        app, ["create", "Fix the login bug in the auth module", "--title", "Login fix"]
    )
    assert result.exit_code == 0
    assert "456" in result.output
    mock_create_issue.assert_called_once_with(
        description="Fix the login bug in the auth module",
        title="Login fix",
        issue_type="main",
        branch=None,
    )


@patch("rouge.cli.issue.create_issue")
def test_create_command_spec_file_with_title(mock_create_issue, tmp_path) -> None:
    """Test create command with spec file and title."""
    mock_issue = Issue(id=789, description="Detailed spec content", status="pending")
    mock_create_issue.return_value = mock_issue

    spec_file = tmp_path / "spec.txt"
    spec_file.write_text("Detailed spec content from file")

    result = runner.invoke(app, ["create", "--spec-file", str(spec_file), "--title", "Feature X"])
    assert result.exit_code == 0
    assert "789" in result.output
    mock_create_issue.assert_called_once_with(
        description="Detailed spec content from file",
        title="Feature X",
        issue_type="main",
        branch=None,
    )


def test_create_command_spec_file_without_title(tmp_path) -> None:
    """Test create command with spec file but no title (should error)."""
    spec_file = tmp_path / "spec.txt"
    spec_file.write_text("Detailed spec content")

    result = runner.invoke(app, ["create", "--spec-file", str(spec_file)])
    assert result.exit_code == 1
    assert "--spec-file requires explicit --title" in result.output


def test_create_command_description_and_spec_file_error(tmp_path) -> None:
    """Test create command with both description and spec-file (mutually exclusive)."""
    spec_file = tmp_path / "spec.txt"
    spec_file.write_text("Spec content")

    result = runner.invoke(
        app,
        ["create", "Some description", "--spec-file", str(spec_file), "--title", "Title"],
    )
    assert result.exit_code == 1
    assert "Cannot use both description argument and --spec-file" in result.output


def test_create_command_no_description_no_spec_file() -> None:
    """Test create command with neither description nor spec-file (should error)."""
    result = runner.invoke(app, ["create"])
    assert result.exit_code == 1
    assert "Must provide either a description argument or --spec-file" in result.output


def test_create_command_file_not_found() -> None:
    """Test create command with non-existent spec file."""
    result = runner.invoke(
        app, ["create", "--spec-file", "/nonexistent/file.txt", "--title", "Title"]
    )
    assert result.exit_code == 1
    assert "File not found" in result.output


def test_create_command_empty_file(tmp_path) -> None:
    """Test create command with empty spec file."""
    spec_file = tmp_path / "empty.txt"
    spec_file.write_text("")

    result = runner.invoke(app, ["create", "--spec-file", str(spec_file), "--title", "Title"])
    assert result.exit_code == 1
    assert "File is empty" in result.output


def test_create_command_directory_instead_of_file(tmp_path) -> None:
    """Test create command with directory instead of file."""
    result = runner.invoke(app, ["create", "--spec-file", str(tmp_path), "--title", "Title"])
    assert result.exit_code == 1
    assert "not a file" in result.output.lower()


def test_create_command_non_utf8_spec_file(tmp_path) -> None:
    """Test create command with non-UTF-8 spec file."""
    spec_file = tmp_path / "bad.txt"
    spec_file.write_bytes(b"\xff\xfe")

    result = runner.invoke(app, ["create", "--spec-file", str(spec_file), "--title", "Title"])
    assert result.exit_code == 1
    assert "not valid UTF-8" in result.output


def test_create_command_empty_description() -> None:
    """Test create command with empty string description.

    Empty string is treated as whitespace-only and rejected early in validation.
    """
    result = runner.invoke(app, ["create", ""])
    assert result.exit_code == 1
    assert "Description cannot be whitespace only" in result.output


def test_create_command_whitespace_description() -> None:
    """Test create command with whitespace-only description."""
    result = runner.invoke(app, ["create", "   "])
    assert result.exit_code == 1
    assert "Description cannot be whitespace only" in result.output


@patch("rouge.cli.issue.create_issue")
def test_create_command_whitespace_only_file(mock_create_issue, tmp_path) -> None:
    """Test create command with file containing only whitespace."""
    spec_file = tmp_path / "whitespace.txt"
    spec_file.write_text("   \n\t\n   ")

    result = runner.invoke(app, ["create", "--spec-file", str(spec_file), "--title", "Title"])
    assert result.exit_code == 1
    assert "File is empty" in result.output
    mock_create_issue.assert_not_called()


@patch("rouge.cli.issue.create_issue")
def test_create_command_long_description_auto_title(mock_create_issue) -> None:
    """Test create command with long description gets truncated auto-generated title."""
    mock_issue = Issue(id=111, description="Long description", status="pending")
    mock_create_issue.return_value = mock_issue

    long_desc = "One two three four five six seven eight nine ten eleven twelve thirteen"
    result = runner.invoke(app, ["create", long_desc])
    assert result.exit_code == 0
    assert "111" in result.output
    mock_create_issue.assert_called_once_with(
        description=long_desc,
        title="One two three four five six seven eight nine ten...",
        issue_type="main",
        branch=None,
    )


@patch("rouge.cli.issue.create_issue")
def test_create_command_create_issue_value_error(mock_create_issue) -> None:
    """Test create command handles ValueError from create_issue."""
    mock_create_issue.side_effect = ValueError("Database error")

    result = runner.invoke(app, ["create", "Some description"])
    assert result.exit_code == 1
    assert "Error: Database error" in result.output


@patch("rouge.cli.issue.create_issue")
def test_create_command_short_title_flag(mock_create_issue) -> None:
    """Test create command with -t short flag for title."""
    mock_issue = Issue(id=222, description="Description", status="pending")
    mock_create_issue.return_value = mock_issue

    result = runner.invoke(app, ["create", "Some description", "-t", "Short Title"])
    assert result.exit_code == 0
    assert "222" in result.output
    mock_create_issue.assert_called_once_with(
        description="Some description",
        title="Short Title",
        issue_type="main",
        branch=None,
    )


@patch("rouge.cli.issue.create_issue")
def test_create_command_short_spec_file_flag(mock_create_issue, tmp_path) -> None:
    """Test create command with -f short flag for spec-file."""
    mock_issue = Issue(id=333, description="File content", status="pending")
    mock_create_issue.return_value = mock_issue

    spec_file = tmp_path / "spec.txt"
    spec_file.write_text("File content from short flag")

    result = runner.invoke(app, ["create", "-f", str(spec_file), "-t", "Title from Short Flags"])
    assert result.exit_code == 0
    assert "333" in result.output
    mock_create_issue.assert_called_once_with(
        description="File content from short flag",
        title="Title from Short Flags",
        issue_type="main",
        branch=None,
    )


@patch("rouge.cli.issue.create_issue")
def test_create_command_branch_long_flag(mock_create_issue) -> None:
    """Test create command with --branch long flag."""
    mock_issue = Issue(id=321, description="Some description", status="pending")
    mock_create_issue.return_value = mock_issue

    result = runner.invoke(app, ["create", "Some description", "--branch", "feature/new-flag"])
    assert result.exit_code == 0
    assert "321" in result.output
    mock_create_issue.assert_called_once_with(
        description="Some description",
        title="Some description",
        issue_type="main",
        branch="feature/new-flag",
    )


@patch("rouge.cli.issue.create_issue")
def test_create_command_branch_short_flag(mock_create_issue) -> None:
    """Test create command with -b short flag for branch."""
    mock_issue = Issue(id=321, description="Some description", status="pending")
    mock_create_issue.return_value = mock_issue

    result = runner.invoke(app, ["create", "Some description", "-b", "feature/short-flag"])
    assert result.exit_code == 0
    assert "321" in result.output
    mock_create_issue.assert_called_once_with(
        description="Some description",
        title="Some description",
        issue_type="main",
        branch="feature/short-flag",
    )


# Tests for patch creation with branch and parent_issue_id


@patch("rouge.cli.issue.create_issue")
def test_create_patch_with_branch_succeeds(mock_create_issue: MagicMock) -> None:
    """Test patch creation with --branch succeeds."""
    mock_issue = Issue(
        id=400,
        description="Patch description",
        status="pending",
        type="patch",
        branch="feature/test",
    )
    mock_create_issue.return_value = mock_issue

    result = runner.invoke(
        app,
        ["create", "Patch description", "--type", "patch", "--branch", "feature/test"],
    )
    assert result.exit_code == 0
    assert "400" in result.output
    mock_create_issue.assert_called_once_with(
        description="Patch description",
        title="Patch description",
        issue_type="patch",
        branch="feature/test",
    )


@patch("rouge.cli.issue.fetch_issue")
@patch("rouge.cli.issue.create_issue")
def test_create_patch_with_parent_issue_id_succeeds(
    mock_create_issue: MagicMock, mock_fetch_issue: MagicMock
) -> None:
    """Test patch creation with --parent-issue-id (parent has branch) succeeds and inherits branch."""
    # Mock parent issue with branch
    parent_issue = Issue(
        id=100, description="Parent issue", status="pending", branch="feature/parent"
    )
    mock_fetch_issue.return_value = parent_issue

    mock_patch_issue = Issue(
        id=401,
        description="Patch description",
        status="pending",
        type="patch",
        branch="feature/parent",
    )
    mock_create_issue.return_value = mock_patch_issue

    result = runner.invoke(
        app,
        ["create", "Patch description", "--type", "patch", "--parent-issue-id", "100"],
    )
    assert result.exit_code == 0
    assert "401" in result.output
    mock_fetch_issue.assert_called_once_with(100)
    mock_create_issue.assert_called_once_with(
        description="Patch description",
        title="Patch description",
        issue_type="patch",
        branch="feature/parent",
    )


@patch("rouge.cli.issue.create_issue")
def test_create_patch_with_both_branch_and_parent_issue_id_fails(
    mock_create_issue: MagicMock,
) -> None:
    """Test patch creation with both --branch and --parent-issue-id fails."""
    result = runner.invoke(
        app,
        [
            "create",
            "Patch description",
            "--type",
            "patch",
            "--branch",
            "feature/test",
            "--parent-issue-id",
            "100",
        ],
    )
    assert result.exit_code == 1
    assert (
        "Error: For patch issues, cannot use both --branch and --parent-issue-id" in result.output
    )
    mock_create_issue.assert_not_called()


@patch("rouge.cli.issue.create_issue")
def test_create_patch_with_neither_branch_nor_parent_issue_id_fails(
    mock_create_issue: MagicMock,
) -> None:
    """Test patch creation with neither --branch nor --parent-issue-id fails."""
    result = runner.invoke(
        app,
        ["create", "Patch description", "--type", "patch"],
    )
    assert result.exit_code == 1
    assert (
        "Error: For patch issues, either --branch or --parent-issue-id must be provided"
        in result.output
    )
    mock_create_issue.assert_not_called()


@patch("rouge.cli.issue.fetch_issue")
@patch("rouge.cli.issue.create_issue")
def test_create_patch_with_parent_issue_id_without_branch_fails(
    mock_create_issue: MagicMock, mock_fetch_issue: MagicMock
) -> None:
    """Test patch creation with --parent-issue-id pointing to parent without branch fails."""
    # Mock parent issue without branch
    parent_issue = Issue(id=100, description="Parent issue", status="pending", branch=None)
    mock_fetch_issue.return_value = parent_issue

    result = runner.invoke(
        app,
        ["create", "Patch description", "--type", "patch", "--parent-issue-id", "100"],
    )
    assert result.exit_code == 1
    assert "Error: Parent issue 100 has no branch" in result.output
    mock_fetch_issue.assert_called_once_with(100)
    mock_create_issue.assert_not_called()


@patch("rouge.cli.issue.fetch_issue")
@patch("rouge.cli.issue.create_issue")
def test_create_patch_with_nonexistent_parent_issue_id_fails(
    mock_create_issue: MagicMock, mock_fetch_issue: MagicMock
) -> None:
    """Test patch creation with --parent-issue-id pointing to non-existent issue fails."""
    # Mock fetch_issue to raise ValueError for non-existent issue
    mock_fetch_issue.side_effect = ValueError("Issue with id 999 not found")

    result = runner.invoke(
        app,
        ["create", "Patch description", "--type", "patch", "--parent-issue-id", "999"],
    )
    assert result.exit_code == 1
    assert "Error: Issue with id 999 not found" in result.output
    mock_fetch_issue.assert_called_once_with(999)
    mock_create_issue.assert_not_called()


@pytest.mark.parametrize("type_arg", ["main", "codereview"])
@patch("rouge.cli.issue.create_issue")
def test_create_non_patch_with_parent_issue_id_fails(
    mock_create_issue: MagicMock, type_arg: str
) -> None:
    """Test non-patch creation with --parent-issue-id fails."""
    result = runner.invoke(
        app,
        ["create", "Main issue description", "--type", type_arg, "--parent-issue-id", "100"],
    )
    assert result.exit_code == 1
    assert (
        f"Error: --parent-issue-id is only allowed for patch issues, not {type_arg} issues"
        in result.output
    )
    mock_create_issue.assert_not_called()


# Tests for read command


@patch("rouge.cli.issue.fetch_issue")
def test_read_command_success(mock_fetch_issue) -> None:
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


@patch("rouge.cli.issue.fetch_issue")
def test_read_command_minimal_issue(mock_fetch_issue) -> None:
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


@patch("rouge.cli.issue.fetch_issue")
def test_read_command_non_existent_issue(mock_fetch_issue) -> None:
    """Test read command with non-existent issue ID."""
    mock_fetch_issue.side_effect = ValueError("Issue not found")

    result = runner.invoke(app, ["read", "999"])
    assert result.exit_code == 1
    assert "Error: Issue not found" in result.output
    mock_fetch_issue.assert_called_once_with(999)


@patch("rouge.cli.issue.fetch_issue")
def test_read_command_database_error(mock_fetch_issue) -> None:
    """Test read command handles unexpected errors."""
    mock_fetch_issue.side_effect = Exception("Database connection failed")

    result = runner.invoke(app, ["read", "123"])
    assert result.exit_code == 1
    assert "Unexpected error: Database connection failed" in result.output
    mock_fetch_issue.assert_called_once_with(123)


@patch("rouge.cli.issue.fetch_issue")
def test_read_command_completed_issue(mock_fetch_issue) -> None:
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


@patch("rouge.cli.issue.fetch_all_issues")
def test_list_command_no_issues(mock_fetch_all_issues) -> None:
    """Test list command with no issues."""
    mock_fetch_all_issues.return_value = []

    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "No issues found." in result.output
    mock_fetch_all_issues.assert_called_once_with(limit=5, issue_type=None, status=None)


@patch("rouge.cli.issue.fetch_all_issues")
def test_list_command_single_issue(mock_fetch_all_issues) -> None:
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
    assert "Branch" in result.output
    assert "Assigned To" in result.output
    assert "1" in result.output
    assert "Single Issue" in result.output
    assert "pending" in result.output
    assert "main" in result.output
    assert "(none)" in result.output  # No branch
    assert "(none)" in result.output  # No assignment
    mock_fetch_all_issues.assert_called_once_with(limit=5, issue_type=None, status=None)


@patch("rouge.cli.issue.fetch_all_issues")
def test_list_command_multiple_issues(mock_fetch_all_issues) -> None:
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
            branch="feature/patch-2",
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
    assert "feature/patch-2" in result.output
    assert "local-2" in result.output
    assert "3" in result.output
    assert "Third Issue" in result.output
    assert "(none)" in result.output  # Third issue has no assignment
    mock_fetch_all_issues.assert_called_once_with(limit=5, issue_type=None, status=None)


@patch("rouge.cli.issue.fetch_all_issues")
def test_list_command_json_format(mock_fetch_all_issues) -> None:
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
    mock_fetch_all_issues.assert_called_once_with(limit=5, issue_type=None, status=None)


@patch("rouge.cli.issue.fetch_all_issues")
def test_list_command_json_format_empty(mock_fetch_all_issues) -> None:
    """Test list command with JSON format and no issues."""
    mock_fetch_all_issues.return_value = []

    result = runner.invoke(app, ["list", "--format", "json"])
    assert result.exit_code == 0
    # Should output empty JSON array
    import json

    issues_data = json.loads(result.output)
    assert isinstance(issues_data, list)
    assert len(issues_data) == 0
    mock_fetch_all_issues.assert_called_once_with(limit=5, issue_type=None, status=None)


@patch("rouge.cli.issue.fetch_all_issues")
def test_list_command_table_format_explicit(mock_fetch_all_issues) -> None:
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
    mock_fetch_all_issues.assert_called_once_with(limit=5, issue_type=None, status=None)


@patch("rouge.cli.issue.fetch_all_issues")
def test_list_command_short_format_flag(mock_fetch_all_issues) -> None:
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
    mock_fetch_all_issues.assert_called_once_with(limit=5, issue_type=None, status=None)


@patch("rouge.cli.issue.fetch_all_issues")
def test_list_command_truncates_long_title(mock_fetch_all_issues) -> None:
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
    mock_fetch_all_issues.assert_called_once_with(limit=5, issue_type=None, status=None)


@patch("rouge.cli.issue.fetch_all_issues")
def test_list_command_database_error(mock_fetch_all_issues) -> None:
    """Test list command handles database errors."""
    mock_fetch_all_issues.side_effect = ValueError("Database error")

    result = runner.invoke(app, ["list"])
    assert result.exit_code == 1
    assert "Error: Database error" in result.output
    mock_fetch_all_issues.assert_called_once_with(limit=5, issue_type=None, status=None)


@patch("rouge.cli.issue.fetch_all_issues")
def test_list_command_unexpected_error(mock_fetch_all_issues) -> None:
    """Test list command handles unexpected errors."""
    mock_fetch_all_issues.side_effect = Exception("Unexpected failure")

    result = runner.invoke(app, ["list"])
    assert result.exit_code == 1
    assert "Unexpected error: Unexpected failure" in result.output
    mock_fetch_all_issues.assert_called_once_with(limit=5, issue_type=None, status=None)


@patch("rouge.cli.issue.fetch_all_issues")
def test_list_command_default_limit_five(mock_fetch_all_issues) -> None:
    """Test list command returns only 5 issues by default when more are available."""
    # Create 10 mock issues
    mock_issues = [
        Issue(
            id=i,
            title=f"Issue {i}",
            description=f"Description {i}",
            status="pending",
            type="main",
        )
        for i in range(1, 11)
    ]
    # Mock returns only 5 (simulating server-side limit)
    mock_fetch_all_issues.return_value = mock_issues[:5]

    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    # Verify default limit of 5 is used
    mock_fetch_all_issues.assert_called_once_with(limit=5, issue_type=None, status=None)
    # Verify only 5 issues are in output
    for i in range(1, 6):
        assert f"Issue {i}" in result.output
    # Verify issues 6-10 are not in output
    for i in range(6, 11):
        assert f"Issue {i}" not in result.output


@patch("rouge.cli.issue.fetch_all_issues")
def test_list_command_limit_override(mock_fetch_all_issues) -> None:
    """Test list command with --limit 20 returns up to 20 issues."""
    # Create 25 mock issues
    mock_issues = [
        Issue(
            id=i,
            title=f"Issue {i}",
            description=f"Description {i}",
            status="pending",
            type="main",
        )
        for i in range(1, 26)
    ]
    # Mock returns 20 (simulating server-side limit)
    mock_fetch_all_issues.return_value = mock_issues[:20]

    result = runner.invoke(app, ["list", "--limit", "20"])
    assert result.exit_code == 0
    # Verify limit of 20 is used
    mock_fetch_all_issues.assert_called_once_with(limit=20, issue_type=None, status=None)
    # Verify first 20 issues are in output
    for i in range(1, 21):
        assert f"Issue {i}" in result.output
    # Verify issues 21-25 are not in output
    for i in range(21, 26):
        assert f"Issue {i}" not in result.output


@patch("rouge.cli.issue.fetch_all_issues")
def test_list_command_filter_by_type_patch(mock_fetch_all_issues) -> None:
    """Test list command with --type patch returns only patch issues."""
    mock_issues = [
        Issue(
            id=1,
            title="Patch Issue 1",
            description="Patch description",
            status="pending",
            type="patch",
        ),
        Issue(
            id=2,
            title="Patch Issue 2",
            description="Patch description",
            status="completed",
            type="patch",
        ),
    ]
    mock_fetch_all_issues.return_value = mock_issues

    result = runner.invoke(app, ["list", "--type", "patch"])
    assert result.exit_code == 0
    # Verify type filter is passed correctly
    mock_fetch_all_issues.assert_called_once_with(limit=5, issue_type="patch", status=None)
    # Verify patch issues are in output
    assert "Patch Issue 1" in result.output
    assert "Patch Issue 2" in result.output
    assert "patch" in result.output


@patch("rouge.cli.issue.fetch_all_issues")
def test_list_command_filter_by_type_codereview(mock_fetch_all_issues) -> None:
    """Test list command with --type codereview returns only codereview issues."""
    mock_issues = [
        Issue(
            id=1,
            title="Code Review Issue",
            description="Review description",
            status="pending",
            type="codereview",
        ),
    ]
    mock_fetch_all_issues.return_value = mock_issues

    result = runner.invoke(app, ["list", "--type", "codereview"])
    assert result.exit_code == 0
    # Verify type filter is passed correctly
    mock_fetch_all_issues.assert_called_once_with(limit=5, issue_type="codereview", status=None)
    # Verify codereview issue is in output
    assert "Code Review Issue" in result.output
    assert "codereview" in result.output


@patch("rouge.cli.issue.fetch_all_issues")
def test_list_command_filter_by_status_failed(mock_fetch_all_issues) -> None:
    """Test list command with --status failed returns only failed issues."""
    mock_issues = [
        Issue(
            id=1,
            title="Failed Issue 1",
            description="Failed description",
            status="failed",
            type="main",
        ),
        Issue(
            id=2,
            title="Failed Issue 2",
            description="Failed description",
            status="failed",
            type="patch",
        ),
    ]
    mock_fetch_all_issues.return_value = mock_issues

    result = runner.invoke(app, ["list", "--status", "failed"])
    assert result.exit_code == 0
    # Verify status filter is passed correctly
    mock_fetch_all_issues.assert_called_once_with(limit=5, issue_type=None, status="failed")
    # Verify failed issues are in output
    assert "Failed Issue 1" in result.output
    assert "Failed Issue 2" in result.output
    assert "failed" in result.output


@patch("rouge.cli.issue.fetch_all_issues")
def test_list_command_combined_filters(mock_fetch_all_issues) -> None:
    """Test list command with --limit 10 --type patch --status started honors all filters."""
    mock_issues = [
        Issue(
            id=1,
            title="Started Patch 1",
            description="Patch description",
            status="started",
            type="patch",
        ),
        Issue(
            id=2,
            title="Started Patch 2",
            description="Patch description",
            status="started",
            type="patch",
        ),
    ]
    mock_fetch_all_issues.return_value = mock_issues

    result = runner.invoke(app, ["list", "--limit", "10", "--type", "patch", "--status", "started"])
    assert result.exit_code == 0
    # Verify all filters are passed correctly
    mock_fetch_all_issues.assert_called_once_with(limit=10, issue_type="patch", status="started")
    # Verify filtered issues are in output
    assert "Started Patch 1" in result.output
    assert "Started Patch 2" in result.output


@patch("rouge.cli.issue.fetch_all_issues")
def test_list_command_json_format_with_filters(mock_fetch_all_issues) -> None:
    """Test list command with --format json --limit 3 --type main honors filters and outputs JSON."""
    mock_issues = [
        Issue(
            id=1,
            title="Main Issue 1",
            description="Main description",
            status="pending",
            type="main",
        ),
        Issue(
            id=2,
            title="Main Issue 2",
            description="Main description",
            status="completed",
            type="main",
        ),
        Issue(
            id=3,
            title="Main Issue 3",
            description="Main description",
            status="started",
            type="main",
        ),
    ]
    mock_fetch_all_issues.return_value = mock_issues

    result = runner.invoke(app, ["list", "--format", "json", "--limit", "3", "--type", "main"])
    assert result.exit_code == 0
    # Verify filters are passed correctly
    mock_fetch_all_issues.assert_called_once_with(limit=3, issue_type="main", status=None)
    # Verify JSON output
    import json

    issues_data = json.loads(result.output)
    assert isinstance(issues_data, list)
    assert len(issues_data) == 3
    assert all(issue["type"] == "main" for issue in issues_data)
    assert issues_data[0]["title"] == "Main Issue 1"
    assert issues_data[1]["title"] == "Main Issue 2"
    assert issues_data[2]["title"] == "Main Issue 3"


# Tests for update command


@patch("rouge.cli.issue.update_issue")
def test_update_command_single_field_assigned_to(mock_update_issue) -> None:
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


@patch("rouge.cli.issue.update_issue")
def test_update_command_single_field_type(mock_update_issue) -> None:
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


@patch("rouge.cli.issue.update_issue")
def test_update_command_single_field_title(mock_update_issue) -> None:
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


@patch("rouge.cli.issue.update_issue")
def test_update_command_single_field_description(mock_update_issue) -> None:
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


@patch("rouge.cli.issue.update_issue")
def test_update_command_multiple_fields(mock_update_issue) -> None:
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


@patch("rouge.cli.issue.update_issue")
def test_update_command_no_fields_provided(mock_update_issue) -> None:
    """Test update command with no fields provided (should show error)."""
    # Error is now caught at CLI validation layer before calling update_issue
    result = runner.invoke(app, ["update", "123"])
    assert result.exit_code == 1
    assert (
        "Error: No fields provided for update. At least one field must be specified."
        in result.output
    )
    # update_issue should not be called since validation fails early
    mock_update_issue.assert_not_called()


@patch("rouge.cli.issue.update_issue")
def test_update_command_invalid_worker_id(mock_update_issue) -> None:
    """Test update command with invalid worker ID."""
    mock_update_issue.side_effect = ValueError(
        "Invalid worker ID 'invalid-worker'. Must be one of: alleycat-1, alleycat-2, "
        "local-1, local-2, local-3"
    )

    result = runner.invoke(app, ["update", "123", "--assigned-to", "invalid-worker"])
    assert result.exit_code == 1
    assert "Error: Invalid worker ID 'invalid-worker'" in result.output
    mock_update_issue.assert_called_once_with(123, assigned_to="invalid-worker")


@patch("rouge.cli.issue.update_issue")
def test_update_command_invalid_type(mock_update_issue) -> None:
    """Test update command with invalid type."""
    # Error is now caught at CLI validation layer with improved message
    result = runner.invoke(app, ["update", "123", "--type", "invalid"])
    assert result.exit_code == 1
    assert "Error: Invalid issue type 'invalid'. Must be one of: main, patch" in result.output
    # update_issue should not be called since validation fails early
    mock_update_issue.assert_not_called()


@patch("rouge.cli.issue.update_issue")
def test_update_command_empty_title(mock_update_issue) -> None:
    """Test update command with empty title."""
    # Whitespace-only title triggers validation error
    result = runner.invoke(app, ["update", "123", "--title", "   "])
    assert result.exit_code == 1
    assert "Error: Field 'title' cannot be whitespace only" in result.output
    # update_issue should not be called since validation fails early
    mock_update_issue.assert_not_called()


@patch("rouge.cli.issue.update_issue")
def test_update_command_empty_description(mock_update_issue) -> None:
    """Test update command with empty description."""
    # Empty description triggers validation error
    result = runner.invoke(app, ["update", "123", "--description", ""])
    assert result.exit_code == 1
    assert "Error: Field 'description' cannot be whitespace only" in result.output
    # update_issue should not be called since validation fails early
    mock_update_issue.assert_not_called()


@patch("rouge.cli.issue.update_issue")
def test_update_command_non_existent_issue(mock_update_issue) -> None:
    """Test update command with non-existent issue ID."""
    mock_update_issue.side_effect = ValueError("Issue with id 999 not found")

    result = runner.invoke(app, ["update", "999", "--title", "New Title"])
    assert result.exit_code == 1
    assert "Error: Issue with id 999 not found" in result.output
    mock_update_issue.assert_called_once_with(999, title="New Title")


@patch("rouge.cli.issue.update_issue")
def test_update_command_type_error(mock_update_issue) -> None:
    """Test update command handles TypeError."""
    mock_update_issue.side_effect = TypeError("Worker ID must be a string")

    result = runner.invoke(app, ["update", "123", "--assigned-to", "worker1"])
    assert result.exit_code == 1
    assert "Error: Worker ID must be a string" in result.output
    mock_update_issue.assert_called_once_with(123, assigned_to="worker1")


@patch("rouge.cli.issue.update_issue")
def test_update_command_unexpected_error(mock_update_issue) -> None:
    """Test update command handles unexpected errors."""
    mock_update_issue.side_effect = Exception("Database connection failed")

    result = runner.invoke(app, ["update", "123", "--title", "New Title"])
    assert result.exit_code == 1
    assert "Unexpected error: Database connection failed" in result.output
    mock_update_issue.assert_called_once_with(123, title="New Title")


# Tests for delete command


@patch("rouge.cli.issue.delete_issue")
def test_delete_command_with_force(mock_delete_issue) -> None:
    """Test delete command with --force flag (no confirmation)."""
    mock_delete_issue.return_value = True

    result = runner.invoke(app, ["delete", "123", "--force"])
    assert result.exit_code == 0
    assert "Issue 123 deleted successfully." in result.output
    mock_delete_issue.assert_called_once_with(123)


@patch("rouge.cli.issue.delete_issue")
def test_delete_command_with_confirmation_yes(mock_delete_issue) -> None:
    """Test delete command with confirmation (user answers yes)."""
    mock_delete_issue.return_value = True

    result = runner.invoke(app, ["delete", "456"], input="y\n")
    assert result.exit_code == 0
    assert "Delete issue 456?" in result.output
    assert "Issue 456 deleted successfully." in result.output
    mock_delete_issue.assert_called_once_with(456)


@patch("rouge.cli.issue.delete_issue")
def test_delete_command_with_confirmation_yes_full(mock_delete_issue) -> None:
    """Test delete command with confirmation (user answers 'yes' full word)."""
    mock_delete_issue.return_value = True

    result = runner.invoke(app, ["delete", "789"], input="yes\n")
    assert result.exit_code == 0
    assert "Delete issue 789?" in result.output
    assert "Issue 789 deleted successfully." in result.output
    mock_delete_issue.assert_called_once_with(789)


@patch("rouge.cli.issue.delete_issue")
def test_delete_command_with_confirmation_no(mock_delete_issue) -> None:
    """Test delete command with confirmation (user answers no)."""
    result = runner.invoke(app, ["delete", "111"], input="n\n")
    assert result.exit_code == 0
    assert "Delete issue 111?" in result.output
    mock_delete_issue.assert_not_called()


@patch("rouge.cli.issue.delete_issue")
def test_delete_command_with_confirmation_empty(mock_delete_issue) -> None:
    """Test delete command with confirmation (user enters just whitespace)."""
    result = runner.invoke(app, ["delete", "222"], input=" \n")
    assert result.exit_code == 0
    assert "Delete issue 222?" in result.output
    mock_delete_issue.assert_not_called()


@patch("rouge.cli.issue.delete_issue")
def test_delete_command_with_confirmation_invalid(mock_delete_issue) -> None:
    """Test delete command with confirmation (user answers something else)."""
    result = runner.invoke(app, ["delete", "333"], input="maybe\nn\n")
    assert result.exit_code == 0
    assert "Delete issue 333?" in result.output
    mock_delete_issue.assert_not_called()


@patch("rouge.cli.issue.delete_issue")
def test_delete_command_non_existent_issue(mock_delete_issue) -> None:
    """Test delete command with non-existent issue ID."""
    mock_delete_issue.side_effect = ValueError("Issue with id 999 not found")

    result = runner.invoke(app, ["delete", "999", "--force"])
    assert result.exit_code == 1
    assert "Error: Issue with id 999 not found" in result.output
    mock_delete_issue.assert_called_once_with(999)


@patch("rouge.cli.issue.delete_issue")
def test_delete_command_database_error(mock_delete_issue) -> None:
    """Test delete command handles database errors."""
    mock_delete_issue.side_effect = ValueError("Database error")

    result = runner.invoke(app, ["delete", "123", "--force"])
    assert result.exit_code == 1
    assert "Error: Database error" in result.output
    mock_delete_issue.assert_called_once_with(123)


@patch("rouge.cli.issue.delete_issue")
def test_delete_command_unexpected_error(mock_delete_issue) -> None:
    """Test delete command handles unexpected errors."""
    mock_delete_issue.side_effect = Exception("Unexpected failure")

    result = runner.invoke(app, ["delete", "123", "--force"])
    assert result.exit_code == 1
    assert "Unexpected error: Unexpected failure" in result.output
    mock_delete_issue.assert_called_once_with(123)
