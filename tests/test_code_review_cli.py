"""Tests for the codereview CLI command."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from rouge.cli.cli import _resolve_to_sha, app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Tests for _resolve_to_sha()
# ---------------------------------------------------------------------------


class TestResolveToSha:
    """Tests for the _resolve_to_sha helper function."""

    @patch("rouge.cli.cli.get_repo_path")
    @patch("rouge.cli.cli.subprocess.run")
    def test_successful_resolution(self, mock_run, mock_get_repo_path):
        """_resolve_to_sha should return the stripped stdout from git rev-parse."""
        mock_get_repo_path.return_value = "/mock/repo/path"
        mock_run.return_value = MagicMock(
            stdout="abc123def456\n",
            returncode=0,
        )

        sha = _resolve_to_sha("main")

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
        """_resolve_to_sha should raise typer.Exit(1) for invalid git references."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=128,
            cmd=["git", "rev-parse", "nonexistent-ref"],
        )

        with pytest.raises(typer.Exit) as exc_info:
            _resolve_to_sha("nonexistent-ref")

        assert exc_info.value.exit_code == 1

    @patch("rouge.cli.cli.subprocess.run")
    def test_git_not_found_raises_exit(self, mock_run):
        """_resolve_to_sha should raise typer.Exit(1) when git is not installed."""
        mock_run.side_effect = FileNotFoundError("git not found")

        with pytest.raises(typer.Exit) as exc_info:
            _resolve_to_sha("main")

        assert exc_info.value.exit_code == 1


# ---------------------------------------------------------------------------
# Tests for the codereview CLI command
# ---------------------------------------------------------------------------


class TestCodereviewCommand:
    """Tests for the 'rouge codereview' CLI command."""

    @patch("rouge.cli.cli.execute_adw_workflow")
    @patch("rouge.cli.cli._resolve_to_sha")
    def test_successful_execution_with_base_commit(self, mock_resolve, mock_execute):
        """Successful codereview invocation with --base-commit should exit 0."""
        mock_resolve.return_value = "deadbeef1234"
        mock_execute.return_value = (True, "cr-workflow-001")

        result = runner.invoke(app, ["codereview", "--base-commit", "main"])

        assert result.exit_code == 0
        assert "deadbeef1234" in result.output
        assert "cr-workflow-001" in result.output
        mock_resolve.assert_called_once_with("main")
        mock_execute.assert_called_once_with(
            adw_id=None,
            workflow_type="codereview",
            config={"base_commit": "deadbeef1234"},
        )

    @patch("rouge.cli.cli.execute_adw_workflow")
    def test_successful_execution_without_base_commit(self, mock_execute):
        """Successful codereview invocation without --base-commit should exit 0."""
        mock_execute.return_value = (True, "cr-workflow-002")

        result = runner.invoke(app, ["codereview"])

        assert result.exit_code == 0
        assert "cr-workflow-002" in result.output
        mock_execute.assert_called_once_with(
            adw_id=None,
            workflow_type="codereview",
            config=None,
        )

    @patch("rouge.cli.cli.execute_adw_workflow")
    @patch("rouge.cli.cli._resolve_to_sha")
    def test_workflow_failure_exits_nonzero(self, mock_resolve, mock_execute):
        """When execute_adw_workflow returns success=False, the CLI should exit 1."""
        mock_resolve.return_value = "deadbeef1234"
        mock_execute.return_value = (False, "cr-workflow-003")

        result = runner.invoke(app, ["codereview", "--base-commit", "main"])

        assert result.exit_code == 1
        assert "failed" in result.output.lower()

    @patch("rouge.cli.cli._resolve_to_sha")
    def test_invalid_git_reference_error(self, mock_resolve):
        """When _resolve_to_sha raises typer.Exit, the CLI should propagate the error."""
        mock_resolve.side_effect = typer.Exit(1)

        result = runner.invoke(app, ["codereview", "--base-commit", "bad-ref"])

        assert result.exit_code == 1

    @patch("rouge.cli.cli.execute_adw_workflow")
    def test_codereview_without_arguments(self, mock_execute):
        """Codereview can be invoked without any arguments."""
        mock_execute.return_value = (True, "cr-workflow-default")

        result = runner.invoke(app, ["codereview"])

        assert result.exit_code == 0
        mock_execute.assert_called_once_with(
            adw_id=None,
            workflow_type="codereview",
            config=None,
        )

    @patch("rouge.cli.cli.execute_adw_workflow")
    @patch("rouge.cli.cli._resolve_to_sha")
    def test_unexpected_exception_exits_nonzero(self, mock_resolve, mock_execute):
        """An unexpected exception during workflow execution should exit 1."""
        mock_resolve.return_value = "abc123"
        mock_execute.side_effect = RuntimeError("unexpected failure")

        result = runner.invoke(app, ["codereview", "--base-commit", "main"])

        assert result.exit_code == 1
        assert "error" in result.output.lower()

    @patch("rouge.cli.cli.execute_adw_workflow")
    @patch("rouge.cli.cli._resolve_to_sha")
    def test_base_commit_sha_passed_through(self, mock_resolve, mock_execute):
        """The resolved SHA (not the original ref) should be passed as base_commit."""
        mock_resolve.return_value = "full-sha-from-rev-parse"
        mock_execute.return_value = (True, "cr-004")

        result = runner.invoke(app, ["codereview", "--base-commit", "v1.0.0"])

        assert result.exit_code == 0
        mock_resolve.assert_called_once_with("v1.0.0")
        call_kwargs = mock_execute.call_args
        assert call_kwargs[1]["config"]["base_commit"] == "full-sha-from-rev-parse"
