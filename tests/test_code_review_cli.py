"""Tests for the codereview CLI command."""

from unittest.mock import ANY, MagicMock, patch

from typer.testing import CliRunner

from rouge.cli.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Tests for the codereview CLI command
# ---------------------------------------------------------------------------


class TestCodeReviewCommand:
    """Tests for the 'rouge codereview' CLI command."""

    @patch("rouge.cli.workflow.execute_adw_workflow")
    def test_successful_execution(self, mock_execute: MagicMock) -> None:
        """Successful codereview invocation should exit 0 and call execute_adw_workflow."""
        mock_execute.return_value = (True, "cr-workflow-001")

        result = runner.invoke(app, ["workflow", "codereview", "123"])

        assert result.exit_code == 0
        mock_execute.assert_called_once_with(
            ANY,
            123,
            workflow_type="codereview",
        )

    @patch("rouge.cli.workflow.execute_adw_workflow")
    def test_workflow_failure_exits_nonzero(self, mock_execute: MagicMock) -> None:
        """When execute_adw_workflow returns success=False, the CLI should exit 1."""
        mock_execute.return_value = (False, "cr-workflow-002")

        result = runner.invoke(app, ["workflow", "codereview", "456"])

        assert result.exit_code == 1

    @patch("rouge.cli.workflow.execute_adw_workflow")
    def test_invalid_issue_id_error(self, mock_execute: MagicMock) -> None:
        """When execute_adw_workflow raises an exception, the CLI should exit 1."""
        mock_execute.side_effect = ValueError("Invalid issue ID")

        result = runner.invoke(app, ["workflow", "codereview", "999"])

        assert result.exit_code == 1

    def test_issue_id_is_required(self) -> None:
        """The issue_id argument is required; omitting it should exit non-zero."""
        result = runner.invoke(app, ["workflow", "codereview"])

        assert result.exit_code != 0
        # Typer should show an error (missing argument or similar)
        assert "error" in result.output.lower() or "argument" in result.output.lower()

    @patch("rouge.cli.workflow.execute_adw_workflow")
    def test_unexpected_exception_exits_nonzero(self, mock_execute: MagicMock) -> None:
        """An unexpected exception during workflow execution should exit 1."""
        mock_execute.side_effect = RuntimeError("unexpected failure")

        result = runner.invoke(app, ["workflow", "codereview", "789"])

        assert result.exit_code == 1

    @patch("rouge.cli.workflow.execute_adw_workflow")
    def test_issue_id_passed_through(self, mock_execute: MagicMock) -> None:
        """The issue_id argument should be passed to execute_adw_workflow."""
        mock_execute.return_value = (True, "cr-003")

        result = runner.invoke(app, ["workflow", "codereview", "555"])

        assert result.exit_code == 0
        # Verify issue_id is passed as second positional argument
        call_args = mock_execute.call_args
        assert call_args[0][1] == 555
        # Verify workflow_type is passed as keyword argument
        assert call_args[1]["workflow_type"] == "codereview"
