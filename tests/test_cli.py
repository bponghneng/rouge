"""Tests for top-level CLI commands.

This module tests the main CLI app entry point, including help, version,
and verification that legacy top-level commands have been removed in favor
of command groups (issue, workflow, etc.).

For command group tests, see:
- test_cli_issue.py: Tests for `rouge issue` commands
- test_cli_workflow.py: Tests for `rouge workflow` commands
- test_cli_comment.py: Tests for `rouge comment` commands
"""

from typer.testing import CliRunner

from rouge.cli.cli import app

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


def test_legacy_codereview_command_fails() -> None:
    """Test that legacy 'rouge codereview' command no longer exists."""
    result = runner.invoke(app, ["codereview", "123"])
    assert result.exit_code != 0
    assert "codereview" in result.output.lower() or "command" in result.output.lower()


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
