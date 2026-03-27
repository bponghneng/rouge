"""Tests for workflow CLI commands."""

from unittest.mock import patch

from typer.testing import CliRunner

from rouge.cli.workflow import app

runner = CliRunner()


# Tests for run command


@patch("rouge.cli.workflow.setup_logger")
@patch("rouge.cli.workflow.execute_adw_workflow")
def test_run_command_success(mock_execute, mock_setup_logger) -> None:
    """Test successful workflow execution.

    Expected call: execute_adw_workflow(issue_id, adw_id)
    """
    mock_execute.return_value = (True, "some-workflow-id")

    result = runner.invoke(app, ["run", "123"])
    assert result.exit_code == 0
    mock_execute.assert_called_once()


@patch("rouge.cli.workflow.setup_logger")
@patch("rouge.cli.workflow.execute_adw_workflow")
def test_run_command_failure(mock_execute, mock_setup_logger) -> None:
    """Test workflow execution failure.

    Expected call: execute_adw_workflow(issue_id, adw_id)
    """
    mock_execute.return_value = (False, "some-workflow-id")

    result = runner.invoke(app, ["run", "123"])
    assert result.exit_code == 1


@patch("rouge.cli.workflow.setup_logger")
@patch("rouge.cli.workflow.execute_adw_workflow")
@patch("rouge.cli.utils.make_adw_id")
def test_run_command_with_adw_id(mock_make_adw_id, mock_execute, mock_setup_logger) -> None:
    """Test run command with custom ADW ID.

    Expected call: execute_adw_workflow(adw_id="custom123", issue_id=123)
    """
    mock_execute.return_value = (True, "some-workflow-id")

    result = runner.invoke(app, ["run", "123", "--adw-id", "custom123"])
    assert result.exit_code == 0
    # When custom ADW ID is provided, make_adw_id should not be called
    mock_make_adw_id.assert_not_called()
    # Verify the custom ADW ID was passed to execute_adw_workflow
    mock_execute.assert_called_once_with("custom123", 123, workflow_type="main")


def test_run_command_invalid_issue_id() -> None:
    """Test run command with invalid issue ID."""
    result = runner.invoke(app, ["run", "not-a-number"])
    assert result.exit_code != 0


# Tests for patch command


@patch("rouge.cli.workflow.setup_logger")
@patch("rouge.cli.workflow.execute_adw_workflow")
def test_patch_command_success(mock_execute, mock_setup_logger) -> None:
    """Test successful patch workflow execution.

    Expected call: execute_adw_workflow(issue_id, adw_id, workflow_type="patch")
    """
    mock_execute.return_value = (True, "some-workflow-id")

    result = runner.invoke(app, ["patch", "123"])
    assert result.exit_code == 0
    # Verify called once with workflow_type="patch" as keyword argument
    assert mock_execute.call_count == 1
    call_args = mock_execute.call_args
    assert call_args.kwargs.get("workflow_type") == "patch"


@patch("rouge.cli.workflow.setup_logger")
@patch("rouge.cli.workflow.execute_adw_workflow")
def test_patch_command_failure(mock_execute, mock_setup_logger) -> None:
    """Test patch workflow execution failure.

    Expected call: execute_adw_workflow(issue_id, adw_id, workflow_type="patch")
    """
    mock_execute.return_value = (False, "some-workflow-id")

    result = runner.invoke(app, ["patch", "123"])
    assert result.exit_code == 1


@patch("rouge.cli.workflow.setup_logger")
@patch("rouge.cli.workflow.execute_adw_workflow")
@patch("rouge.cli.utils.make_adw_id")
def test_patch_command_with_adw_id(mock_make_adw_id, mock_execute, mock_setup_logger) -> None:
    """Test patch command with custom ADW ID.

    Expected call: execute_adw_workflow(adw_id="custom123", issue_id=123, workflow_type="patch")
    """
    mock_execute.return_value = (True, "some-workflow-id")

    result = runner.invoke(app, ["patch", "123", "--adw-id", "custom123"])
    assert result.exit_code == 0
    # When custom ADW ID is provided, make_adw_id should not be called
    mock_make_adw_id.assert_not_called()
    # Verify the custom ADW ID and workflow_type were passed to execute_adw_workflow
    mock_execute.assert_called_once_with("custom123", 123, workflow_type="patch")


def test_patch_command_invalid_issue_id() -> None:
    """Test patch command with invalid issue ID."""
    result = runner.invoke(app, ["patch", "not-a-number"])
    assert result.exit_code != 0
