"""Tests for top-level CLI commands.

This module tests the main CLI app entry point, including help, version,
and verification that legacy top-level commands have been removed in favor
of command groups (issue, workflow, etc.).

For command group tests, see:
- test_cli_issue.py: Tests for `rouge issue` commands
- test_cli_workflow.py: Tests for `rouge workflow` commands
- test_cli_comment.py: Tests for `rouge comment` commands
"""

from unittest.mock import patch

from typer.testing import CliRunner

from rouge.cli.cli import app
from rouge.cli.issue import app as issue_app
from rouge.core.models import Issue

runner = CliRunner()


# Tests for top-level CLI commands


def test_cli_help() -> None:
    """Test CLI help command shows grouped commands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Rouge CLI" in result.output
    # Verify all command groups are shown
    assert "issue" in result.output.lower()
    assert "workflow" in result.output.lower()
    assert "comment" in result.output.lower()
    assert "step" in result.output.lower()
    assert "artifact" in result.output.lower()


def test_cli_version() -> None:
    """Test version flag."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "version" in result.output.lower()


# Tests for legacy command removal (breaking change verification)


def test_legacy_new_command_fails() -> None:
    """Test that legacy 'rouge new' command no longer exists."""
    result = runner.invoke(app, ["new", "Some description"])
    assert result.exit_code != 0
    # Typer will report "No such command" or similar error
    assert "new" in result.output.lower() or "command" in result.output.lower()


def test_legacy_run_command_fails() -> None:
    """Test that legacy 'rouge run' command no longer exists."""
    result = runner.invoke(app, ["run", "123"])
    assert result.exit_code != 0
    assert "run" in result.output.lower() or "command" in result.output.lower()


def test_legacy_patch_command_fails() -> None:
    """Test that legacy 'rouge patch' command no longer exists."""
    result = runner.invoke(app, ["patch", "123"])
    assert result.exit_code != 0
    assert "patch" in result.output.lower() or "command" in result.output.lower()


def test_legacy_read_command_fails() -> None:
    """Test that legacy 'rouge read' command no longer exists."""
    result = runner.invoke(app, ["read", "123"])
    assert result.exit_code != 0
    assert "read" in result.output.lower() or "command" in result.output.lower()


def test_legacy_list_command_fails() -> None:
    """Test that legacy 'rouge list' command no longer exists."""
    result = runner.invoke(app, ["list"])
    assert result.exit_code != 0
    assert "list" in result.output.lower() or "command" in result.output.lower()


def test_legacy_update_command_fails() -> None:
    """Test that legacy 'rouge update' command no longer exists."""
    result = runner.invoke(app, ["update", "123", "--title", "New Title"])
    assert result.exit_code != 0
    assert "update" in result.output.lower() or "command" in result.output.lower()


def test_legacy_delete_command_fails() -> None:
    """Test that legacy 'rouge delete' command no longer exists."""
    result = runner.invoke(app, ["delete", "123", "--force"])
    assert result.exit_code != 0
    assert "delete" in result.output.lower() or "command" in result.output.lower()


# Tests for command group registration


def test_issue_command_group_exists() -> None:
    """Test that 'issue' command group is registered."""
    result = runner.invoke(app, ["issue", "--help"])
    assert result.exit_code == 0
    assert "issue" in result.output.lower()


def test_workflow_command_group_exists() -> None:
    """Test that 'workflow' command group is registered."""
    result = runner.invoke(app, ["workflow", "--help"])
    assert result.exit_code == 0
    assert "workflow" in result.output.lower()


def test_comment_command_group_exists() -> None:
    """Test that 'comment' command group is registered."""
    result = runner.invoke(app, ["comment", "--help"])
    assert result.exit_code == 0
    assert "comment" in result.output.lower()


def test_step_command_group_exists() -> None:
    """Test that 'step' command group is registered."""
    result = runner.invoke(app, ["step", "--help"])
    assert result.exit_code == 0
    assert "step" in result.output.lower()


def test_artifact_command_group_exists() -> None:
    """Test that 'artifact' command group is registered."""
    result = runner.invoke(app, ["artifact", "--help"])
    assert result.exit_code == 0
    assert "artifact" in result.output.lower()


# Tests for reset command (now under 'issue' subcommand)


def test_reset_command_exists() -> None:
    """Test that top-level 'rouge reset' no longer exists (legacy removal)."""
    result = runner.invoke(app, ["reset", "--help"])
    assert result.exit_code != 0


@patch("rouge.cli.reset.update_issue")
@patch("rouge.cli.reset.fetch_issue")
def test_reset_command_with_failed_issue_succeeds(mock_fetch_issue, mock_update_issue) -> None:
    """Test 'rouge issue reset' with failed issue succeeds."""
    # Mock a failed main issue
    mock_issue = Issue(
        id=123,
        description="Test issue",
        status="failed",
        type="full",
        assigned_to="local-1",
        branch="feature/test",
    )
    mock_fetch_issue.return_value = mock_issue

    # Mock the updated issue
    updated_issue = Issue(
        id=123,
        description="Test issue",
        status="pending",
        type="full",
        assigned_to=None,
        branch=None,
    )
    mock_update_issue.return_value = updated_issue

    result = runner.invoke(issue_app, ["reset", "123"])
    assert result.exit_code == 0
    assert "123" in result.output
    mock_fetch_issue.assert_called_once_with(123)
    mock_update_issue.assert_called_once_with(
        123,
        assigned_to=None,
        status="pending",
        branch=None,
    )


@patch("rouge.cli.reset.update_issue")
@patch("rouge.cli.reset.fetch_issue")
def test_reset_command_with_pending_issue_succeeds(mock_fetch_issue, mock_update_issue) -> None:
    """Test 'rouge issue reset' with pending issue succeeds (clears assignment/branch)."""
    # Mock a pending main issue with assignment and branch
    mock_issue = Issue(
        id=456,
        description="Test pending issue",
        status="pending",
        type="full",
        assigned_to="local-2",
        branch="feature/pending-test",
    )
    mock_fetch_issue.return_value = mock_issue

    # Mock the updated issue (assignment and branch cleared)
    updated_issue = Issue(
        id=456,
        description="Test pending issue",
        status="pending",
        type="full",
        assigned_to=None,
        branch=None,
    )
    mock_update_issue.return_value = updated_issue

    result = runner.invoke(issue_app, ["reset", "456"])
    assert result.exit_code == 0
    assert "456" in result.output
    mock_fetch_issue.assert_called_once_with(456)
    mock_update_issue.assert_called_once_with(
        456,
        assigned_to=None,
        status="pending",
        branch=None,
    )


@patch("rouge.cli.reset.update_issue")
@patch("rouge.cli.reset.fetch_issue")
def test_reset_command_with_non_failed_issue_fails(mock_fetch_issue, mock_update_issue) -> None:
    """Test 'rouge issue reset' with non-failed/non-pending issue fails with clear error."""
    # Mock a started issue
    mock_issue = Issue(
        id=456,
        description="Test issue",
        status="started",
        type="full",
    )
    mock_fetch_issue.return_value = mock_issue

    result = runner.invoke(issue_app, ["reset", "456"])
    assert result.exit_code == 1
    assert (
        "Error: Issue 456 has status 'started', can only reset 'failed' or 'pending' issues"
        in result.output
    )
    mock_fetch_issue.assert_called_once_with(456)
    mock_update_issue.assert_not_called()


@patch("rouge.cli.reset.update_issue")
@patch("rouge.cli.reset.fetch_issue")
def test_reset_command_with_started_issue_fails(mock_fetch_issue, mock_update_issue) -> None:
    """Test 'rouge issue reset' with started issue fails."""
    # Mock a started issue
    mock_issue = Issue(
        id=789,
        description="Test issue",
        status="started",
        type="full",
    )
    mock_fetch_issue.return_value = mock_issue

    result = runner.invoke(issue_app, ["reset", "789"])
    assert result.exit_code == 1
    assert (
        "Error: Issue 789 has status 'started', can only reset 'failed' or 'pending' issues"
        in result.output
    )
    mock_fetch_issue.assert_called_once_with(789)
    mock_update_issue.assert_not_called()


@patch("rouge.cli.reset.update_issue")
@patch("rouge.cli.reset.fetch_issue")
def test_reset_command_with_completed_issue_fails(mock_fetch_issue, mock_update_issue) -> None:
    """Test 'rouge issue reset' with completed issue fails."""
    # Mock a completed issue
    mock_issue = Issue(
        id=321,
        description="Test issue",
        status="completed",
        type="full",
    )
    mock_fetch_issue.return_value = mock_issue

    result = runner.invoke(issue_app, ["reset", "321"])
    assert result.exit_code == 1
    assert (
        "Error: Issue 321 has status 'completed', can only reset 'failed' or 'pending' issues"
        in result.output
    )
    mock_fetch_issue.assert_called_once_with(321)
    mock_update_issue.assert_not_called()


@patch("rouge.cli.reset.update_issue")
@patch("rouge.cli.reset.fetch_issue")
def test_reset_command_with_non_existent_issue_fails(mock_fetch_issue, mock_update_issue) -> None:
    """Test 'rouge issue reset' with non-existent issue fails."""
    # Mock fetch_issue to raise ValueError
    mock_fetch_issue.side_effect = ValueError("Issue with id 999 not found")

    result = runner.invoke(issue_app, ["reset", "999"])
    assert result.exit_code == 1
    assert "Error: Issue with id 999 not found" in result.output
    mock_fetch_issue.assert_called_once_with(999)
    mock_update_issue.assert_not_called()


@patch("rouge.cli.reset.update_issue")
@patch("rouge.cli.reset.fetch_issue")
def test_reset_command_with_failed_main_issue_clears_branch(
    mock_fetch_issue, mock_update_issue
) -> None:
    """Test 'rouge issue reset' with failed main issue clears branch."""
    # Mock a failed main issue with branch
    mock_issue = Issue(
        id=111,
        description="Test main issue",
        status="failed",
        type="full",
        assigned_to="local-1",
        branch="feature/main-branch",
    )
    mock_fetch_issue.return_value = mock_issue

    # Mock the updated issue
    updated_issue = Issue(
        id=111,
        description="Test main issue",
        status="pending",
        type="full",
        assigned_to=None,
        branch=None,
    )
    mock_update_issue.return_value = updated_issue

    result = runner.invoke(issue_app, ["reset", "111"])
    assert result.exit_code == 0
    assert "111" in result.output
    mock_fetch_issue.assert_called_once_with(111)
    # Verify branch is set to None for main issues
    mock_update_issue.assert_called_once_with(
        111,
        assigned_to=None,
        status="pending",
        branch=None,
    )


@patch("rouge.cli.reset.update_issue")
@patch("rouge.cli.reset.fetch_issue")
def test_reset_command_with_failed_patch_issue_preserves_branch(
    mock_fetch_issue, mock_update_issue
) -> None:
    """Test 'rouge issue reset' with failed patch issue preserves branch."""
    # Mock a failed patch issue with branch
    mock_issue = Issue(
        id=333,
        description="Test patch issue",
        status="failed",
        type="patch",
        assigned_to="local-3",
        branch="feature/patch-branch",
    )
    mock_fetch_issue.return_value = mock_issue

    # Mock the updated issue (branch preserved)
    updated_issue = Issue(
        id=333,
        description="Test patch issue",
        status="pending",
        type="patch",
        assigned_to=None,
        branch="feature/patch-branch",
    )
    mock_update_issue.return_value = updated_issue

    result = runner.invoke(issue_app, ["reset", "333"])
    assert result.exit_code == 0
    assert "333" in result.output
    mock_fetch_issue.assert_called_once_with(333)
    # Verify branch is NOT in kwargs (preserves existing value)
    mock_update_issue.assert_called_once_with(
        333,
        assigned_to=None,
        status="pending",
    )


@patch("rouge.cli.reset.update_issue")
@patch("rouge.cli.reset.fetch_issue")
def test_reset_command_invalid_issue_id_zero(mock_fetch_issue, mock_update_issue) -> None:
    """Test 'rouge issue reset' with issue_id of 0 fails."""
    result = runner.invoke(issue_app, ["reset", "0"])
    assert result.exit_code == 1
    assert "Error: issue_id must be greater than 0, got 0" in result.output
    mock_fetch_issue.assert_not_called()
    mock_update_issue.assert_not_called()


@patch("rouge.cli.reset.update_issue")
@patch("rouge.cli.reset.fetch_issue")
def test_reset_command_unexpected_error(mock_fetch_issue, mock_update_issue) -> None:
    """Test 'rouge issue reset' handles unexpected errors."""
    mock_fetch_issue.side_effect = Exception("Database connection failed")

    result = runner.invoke(issue_app, ["reset", "123"])
    assert result.exit_code == 1
    assert "Unexpected error: Database connection failed" in result.output
    mock_fetch_issue.assert_called_once_with(123)
    mock_update_issue.assert_not_called()
