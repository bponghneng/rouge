"""Tests for workflow orchestration."""

import logging
from unittest.mock import Mock, patch

import pytest

from cape.core.models import AgentPromptResponse, CapeIssue
from cape.core.notifications import insert_progress_comment
from cape.core.workflow import (
    build_plan,
    classify_issue,
    execute_workflow,
    get_plan_file,
    implement_plan,
    update_status,
)


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    return Mock(spec=logging.Logger)


@pytest.fixture
def sample_issue():
    """Create a sample issue for testing."""
    return CapeIssue(id=1, description="Fix login bug", status="pending")


@patch("cape.core.workflow.update_issue_status")
def test_update_status_success(mock_update_issue_status, mock_logger):
    """Test successful status update."""
    mock_issue = Mock()
    mock_issue.id = 1
    mock_update_issue_status.return_value = mock_issue

    update_status(1, "started", mock_logger)
    mock_logger.debug.assert_called_once()
    mock_update_issue_status.assert_called_once_with(1, "started")


@patch("cape.core.workflow.update_issue_status")
def test_update_status_failure(mock_update_issue_status, mock_logger):
    """Test status update handles errors gracefully."""
    mock_update_issue_status.side_effect = Exception("Database error")

    update_status(1, "started", mock_logger)
    mock_logger.error.assert_called_once()


@patch("cape.core.notifications.create_comment")
def test_insert_progress_comment_success(mock_create_comment):
    """Test successful progress comment insertion."""
    mock_comment = Mock()
    mock_comment.id = 1
    mock_create_comment.return_value = mock_comment

    status, msg = insert_progress_comment(1, "Test comment")
    assert status == "success"
    assert "Comment inserted: ID=1" in msg
    assert "Test comment" in msg
    mock_create_comment.assert_called_once_with(1, "Test comment")


@patch("cape.core.notifications.create_comment")
def test_insert_progress_comment_failure(mock_create_comment):
    """Test progress comment insertion handles errors gracefully."""
    mock_create_comment.side_effect = Exception("Database error")

    status, msg = insert_progress_comment(1, "Test comment")
    assert status == "error"
    assert "Failed to insert comment on issue 1" in msg
    assert "Database error" in msg


@patch("cape.core.workflow.execute_template")
def test_classify_issue_success(mock_execute, mock_logger, sample_issue):
    """Test successful issue classification."""
    mock_execute.return_value = AgentPromptResponse(
        output='{"type": "feature", "level": "simple"}',
        success=True,
        session_id="test123",
    )

    command, classification, error = classify_issue(sample_issue, "adw123", mock_logger)
    assert command == "/triage:feature"
    assert classification == {"type": "feature", "level": "simple"}
    assert error is None


@patch("cape.core.workflow.execute_template")
def test_classify_issue_failure(mock_execute, mock_logger, sample_issue):
    """Test issue classification failure."""
    mock_execute.return_value = AgentPromptResponse(
        output="Error occurred", success=False, session_id=None
    )

    command, classification, error = classify_issue(sample_issue, "adw123", mock_logger)
    assert command is None
    assert classification is None
    assert error == "Error occurred"


@patch("cape.core.workflow.execute_template")
def test_classify_issue_invalid_command(mock_execute, mock_logger, sample_issue):
    """Test issue classification with invalid command."""
    mock_execute.return_value = AgentPromptResponse(
        output='{"type": "unsupported", "level": "simple"}',
        success=True,
        session_id="test123",
    )

    command, classification, error = classify_issue(sample_issue, "adw123", mock_logger)
    assert command is None
    assert classification is None
    assert "Invalid issue type" in error


@patch("cape.core.workflow.execute_template")
def test_classify_issue_invalid_json(mock_execute, mock_logger, sample_issue):
    """Test classification with invalid JSON output."""
    mock_execute.return_value = AgentPromptResponse(
        output="not-json", success=True, session_id="test123"
    )

    command, classification, error = classify_issue(sample_issue, "adw123", mock_logger)
    assert command is None
    assert classification is None
    assert "Invalid classification JSON" in error


@patch("cape.core.workflow.execute_template")
def test_build_plan_success(mock_execute, mock_logger, sample_issue):
    """Test successful plan building."""
    mock_execute.return_value = AgentPromptResponse(
        output="Plan created successfully", success=True, session_id="test123"
    )

    response = build_plan(sample_issue, "/triage:feature", "adw123", mock_logger)
    assert response.success is True
    assert response.output == "Plan created successfully"


@patch("cape.core.workflow.execute_template")
def test_get_plan_file_success(mock_execute, mock_logger):
    """Test successful plan file extraction."""
    mock_execute.return_value = AgentPromptResponse(
        output="specs/feature-plan.md", success=True, session_id="test123"
    )

    file_path, error = get_plan_file("Plan output", 1, "adw123", mock_logger)
    assert file_path == "specs/feature-plan.md"
    assert error is None


@patch("cape.core.workflow.execute_template")
def test_get_plan_file_not_found(mock_execute, mock_logger):
    """Test plan file not found."""
    mock_execute.return_value = AgentPromptResponse(output="0", success=True, session_id="test123")

    file_path, error = get_plan_file("Plan output", 1, "adw123", mock_logger)
    assert file_path is None
    assert "No plan file found" in error


@patch("cape.core.workflow.execute_template")
def test_implement_plan_success(mock_execute, mock_logger):
    """Test successful plan implementation."""
    mock_execute.return_value = AgentPromptResponse(
        output="Implementation complete", success=True, session_id="test123"
    )

    response = implement_plan("specs/plan.md", 1, "adw123", mock_logger)
    assert response.success is True


@patch("cape.core.workflow.fetch_issue")
@patch("cape.core.workflow.classify_issue")
@patch("cape.core.workflow.build_plan")
@patch("cape.core.workflow.get_plan_file")
@patch("cape.core.workflow.implement_plan")
@patch("cape.core.workflow.insert_progress_comment")
@patch("cape.core.workflow.update_status")
def test_execute_workflow_success(
    mock_update_status,
    mock_insert_comment,
    mock_implement,
    mock_get_file,
    mock_build,
    mock_classify,
    mock_fetch,
    mock_logger,
    sample_issue,
):
    """Test successful complete workflow execution."""
    mock_fetch.return_value = sample_issue
    mock_classify.return_value = ("/triage:feature", {"type": "feature", "level": "simple"}, None)
    mock_build.return_value = AgentPromptResponse(
        output="Plan created", success=True, session_id="test"
    )
    mock_get_file.return_value = ("specs/plan.md", None)
    mock_implement.return_value = AgentPromptResponse(
        output="Done", success=True, session_id="test"
    )
    # Mock insert_progress_comment to return success tuples
    mock_insert_comment.return_value = ("success", "Comment inserted successfully")

    result = execute_workflow(1, "adw123", mock_logger)
    assert result is True
    assert mock_insert_comment.call_count == 4  # 4 progress comments
    assert mock_update_status.call_count == 2  # status updated to "started" and "completed"
    mock_update_status.assert_any_call(1, "started", mock_logger)
    mock_update_status.assert_any_call(1, "completed", mock_logger)


@patch("cape.core.workflow.fetch_issue")
def test_execute_workflow_fetch_failure(mock_fetch, mock_logger):
    """Test workflow handles fetch failure."""
    mock_fetch.side_effect = ValueError("Issue not found")

    result = execute_workflow(999, "adw123", mock_logger)
    assert result is False
    mock_logger.error.assert_called()


@patch("cape.core.workflow.fetch_issue")
@patch("cape.core.workflow.classify_issue")
def test_execute_workflow_classify_failure(mock_classify, mock_fetch, mock_logger, sample_issue):
    """Test workflow handles classification failure."""
    mock_fetch.return_value = sample_issue
    mock_classify.return_value = (None, None, "Classification failed")

    result = execute_workflow(1, "adw123", mock_logger)
    assert result is False
