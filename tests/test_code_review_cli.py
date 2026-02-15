"""Tests for the codereview CLI command."""

import subprocess
from unittest.mock import ANY, MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from rouge.cli.cli import app, resolve_to_sha

runner = CliRunner()


# ---------------------------------------------------------------------------
# Tests for resolve_to_sha()
# ---------------------------------------------------------------------------


class TestResolveToSha:
    """Tests for the resolve_to_sha helper function."""

    @patch("rouge.cli.cli.get_repo_path")
    @patch("rouge.cli.cli.subprocess.run")
    def test_successful_resolution(self, mock_run, mock_get_repo_path):
        """resolve_to_sha should return the stripped stdout from git rev-parse."""
        mock_get_repo_path.return_value = "/mock/repo/path"
        mock_run.return_value = MagicMock(
            stdout="abc123def456\n",
            returncode=0,
        )

        sha = resolve_to_sha("main")

        assert sha == "abc123def456"
        mock_run.assert_called_once_with(
            ["git", "rev-parse", "main"],
            cwd="/mock/repo/path",
            capture_output=True,
            text=True,
            check=True,
        )

    @patch("rouge.cli.cli.subprocess.run")
    def test_invalid_reference_raises_exit(self, mock_run):
        """resolve_to_sha should raise typer.Exit(1) for invalid git references."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=128,
            cmd=["git", "rev-parse", "nonexistent-ref"],
        )

        with pytest.raises(typer.Exit) as exc_info:
            resolve_to_sha("nonexistent-ref")

        assert exc_info.value.exit_code == 1

    @patch("rouge.cli.cli.subprocess.run")
    def test_git_not_found_raises_exit(self, mock_run):
        """resolve_to_sha should raise typer.Exit(1) when git is not installed."""
        mock_run.side_effect = FileNotFoundError("git not found")

        with pytest.raises(typer.Exit) as exc_info:
            resolve_to_sha("main")

        assert exc_info.value.exit_code == 1


# ---------------------------------------------------------------------------
# Tests for the codereview CLI command
# ---------------------------------------------------------------------------


class TestCodeReviewCommand:
    """Tests for the 'rouge codereview' CLI command."""

    @patch("rouge.cli.cli.execute_adw_workflow")
    def test_successful_execution(self, mock_execute):
        """Successful codereview invocation should exit 0 and call execute_adw_workflow."""
        mock_execute.return_value = (True, "cr-workflow-001")

        result = runner.invoke(app, ["codereview", "123"])

        assert result.exit_code == 0
        mock_execute.assert_called_once_with(
            123,
            ANY,
            workflow_type="codereview",
        )

    @patch("rouge.cli.cli.execute_adw_workflow")
    def test_workflow_failure_exits_nonzero(self, mock_execute):
        """When execute_adw_workflow returns success=False, the CLI should exit 1."""
        mock_execute.return_value = (False, "cr-workflow-002")

        result = runner.invoke(app, ["codereview", "456"])

        assert result.exit_code == 1

    @patch("rouge.cli.cli.execute_adw_workflow")
    def test_invalid_issue_id_error(self, mock_execute):
        """When execute_adw_workflow raises an exception, the CLI should exit 1."""
        mock_execute.side_effect = ValueError("Invalid issue ID")

        result = runner.invoke(app, ["codereview", "999"])

        assert result.exit_code == 1

    def test_issue_id_is_required(self):
        """The issue_id argument is required; omitting it should exit non-zero."""
        result = runner.invoke(app, ["codereview"])

        assert result.exit_code != 0
        # Typer should show a missing argument error
        assert "missing" in result.output.lower() or "required" in result.output.lower()

    @patch("rouge.cli.cli.execute_adw_workflow")
    def test_unexpected_exception_exits_nonzero(self, mock_execute):
        """An unexpected exception during workflow execution should exit 1."""
        mock_execute.side_effect = RuntimeError("unexpected failure")

        result = runner.invoke(app, ["codereview", "789"])

        assert result.exit_code == 1

    @patch("rouge.cli.cli.execute_adw_workflow")
    def test_issue_id_passed_through(self, mock_execute):
        """The issue_id argument should be passed to execute_adw_workflow."""
        mock_execute.return_value = (True, "cr-003")

        result = runner.invoke(app, ["codereview", "555"])

        assert result.exit_code == 0
        # Verify issue_id is passed as first positional argument
        call_args = mock_execute.call_args
        assert call_args[0][0] == 555
        # Verify workflow_type is passed as keyword argument
        assert call_args[1]["workflow_type"] == "codereview"
