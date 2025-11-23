"""Tests for workflow orchestration."""

import logging
from unittest.mock import Mock, patch

import pytest

from cape.core.agents.claude import ClaudeAgentPromptResponse
from cape.core.models import CapeComment, CapeIssue
from cape.core.notifications import insert_progress_comment
from cape.core.workflow import (
    build_plan,
    classify_issue,
    execute_workflow,
    get_plan_file,
    implement_plan,
    update_status,
)
from cape.core.workflow.implement import parse_implement_output
from cape.core.workflow.shared import derive_paths_from_plan


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    return Mock(spec=logging.Logger)


@pytest.fixture
def sample_issue():
    """Create a sample issue for testing."""
    return CapeIssue(id=1, description="Fix login bug", status="pending")


@patch("cape.core.workflow.status.update_issue_status")
def test_update_status_success(mock_update_issue_status, mock_logger):
    """Test successful status update."""
    mock_issue = Mock()
    mock_issue.id = 1
    mock_update_issue_status.return_value = mock_issue

    update_status(1, "started", mock_logger)
    mock_logger.debug.assert_called_once()
    mock_update_issue_status.assert_called_once_with(1, "started")


@patch("cape.core.workflow.status.update_issue_status")
def test_update_status_failure(mock_update_issue_status, mock_logger):
    """Test status update handles errors gracefully."""
    mock_update_issue_status.side_effect = Exception("Database error")

    update_status(1, "started", mock_logger)
    mock_logger.error.assert_called_once()


@patch("cape.core.notifications.comments.create_comment")
def test_insert_progress_comment_success(mock_create_comment):
    """Test successful progress comment insertion."""
    mock_comment = Mock()
    mock_comment.id = 1
    mock_create_comment.return_value = mock_comment

    comment = CapeComment(
        issue_id=1,
        comment="Test comment",
        raw={},
        source="test",
        type="comment"
    )
    status, msg = insert_progress_comment(comment)
    assert status == "success"
    assert "Comment inserted: ID=1" in msg
    assert "Test comment" in msg
    mock_create_comment.assert_called_once_with(comment)


@patch("cape.core.notifications.comments.create_comment")
def test_insert_progress_comment_failure(mock_create_comment):
    """Test progress comment insertion handles errors gracefully."""
    mock_create_comment.side_effect = Exception("Database error")

    comment = CapeComment(
        issue_id=1,
        comment="Test comment",
        raw={},
        source="test",
        type="comment"
    )
    status, msg = insert_progress_comment(comment)
    assert status == "error"
    assert "Failed to insert comment on issue 1" in msg
    assert "Database error" in msg


@patch("cape.core.workflow.classify.execute_template")
def test_classify_issue_success(mock_execute, mock_logger, sample_issue):
    """Test successful issue classification."""
    mock_execute.return_value = ClaudeAgentPromptResponse(
        output='{"type": "feature", "level": "simple"}',
        success=True,
        session_id="test123",
    )

    command, classification, error = classify_issue(sample_issue, "adw123", mock_logger)
    assert command == "/triage:feature"
    assert classification == {"type": "feature", "level": "simple"}
    assert error is None


@patch("cape.core.workflow.classify.execute_template")
def test_classify_issue_failure(mock_execute, mock_logger, sample_issue):
    """Test issue classification failure."""
    mock_execute.return_value = ClaudeAgentPromptResponse(
        output="Error occurred", success=False, session_id=None
    )

    command, classification, error = classify_issue(sample_issue, "adw123", mock_logger)
    assert command is None
    assert classification is None
    assert error == "Error occurred"


@patch("cape.core.workflow.classify.execute_template")
def test_classify_issue_invalid_command(mock_execute, mock_logger, sample_issue):
    """Test issue classification with invalid command."""
    mock_execute.return_value = ClaudeAgentPromptResponse(
        output='{"type": "unsupported", "level": "simple"}',
        success=True,
        session_id="test123",
    )

    command, classification, error = classify_issue(sample_issue, "adw123", mock_logger)
    assert command is None
    assert classification is None
    assert "Invalid issue type" in error


@patch("cape.core.workflow.classify.execute_template")
def test_classify_issue_invalid_json(mock_execute, mock_logger, sample_issue):
    """Test classification with invalid JSON output."""
    mock_execute.return_value = ClaudeAgentPromptResponse(
        output="not-json", success=True, session_id="test123"
    )

    command, classification, error = classify_issue(sample_issue, "adw123", mock_logger)
    assert command is None
    assert classification is None
    assert "Invalid classification JSON" in error


@patch("cape.core.workflow.plan.execute_template")
def test_build_plan_success(mock_execute, mock_logger, sample_issue):
    """Test successful plan building."""
    mock_execute.return_value = ClaudeAgentPromptResponse(
        output="Plan created successfully", success=True, session_id="test123"
    )

    response = build_plan(sample_issue, "/triage:feature", "adw123", mock_logger)
    assert response.success is True
    assert response.output == "Plan created successfully"


@patch("cape.core.workflow.plan_file.execute_template")
def test_get_plan_file_success(mock_execute, mock_logger):
    """Test successful plan file extraction."""
    mock_execute.return_value = ClaudeAgentPromptResponse(
        output="specs/feature-plan.md", success=True, session_id="test123"
    )

    file_path, error = get_plan_file("Plan output", 1, "adw123", mock_logger)
    assert file_path == "specs/feature-plan.md"
    assert error is None


@patch("cape.core.workflow.plan_file.execute_template")
def test_get_plan_file_not_found(mock_execute, mock_logger):
    """Test plan file not found."""
    mock_execute.return_value = ClaudeAgentPromptResponse(output="0", success=True, session_id="test123")

    file_path, error = get_plan_file("Plan output", 1, "adw123", mock_logger)
    assert file_path is None
    assert "No plan file found" in error


@patch("cape.core.workflow.implement.execute_implement_plan")
def test_implement_plan_success(mock_execute, mock_logger):
    """Test successful plan implementation."""
    mock_execute.return_value = Mock(
        output="Implementation complete",
        success=True,
        session_id="test123",
    )

    response = implement_plan("specs/plan.md", 1, "adw123", mock_logger)
    assert response.success is True


@patch("cape.core.workflow.runner.fetch_issue")
@patch("cape.core.workflow.runner.classify_issue")
@patch("cape.core.workflow.runner.build_plan")
@patch("cape.core.workflow.runner.get_plan_file")
@patch("cape.core.workflow.runner.implement_plan")
@patch("cape.core.workflow.runner.insert_progress_comment")
@patch("cape.core.workflow.runner.update_status")
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
    mock_build.return_value = ClaudeAgentPromptResponse(
        output="Plan created", success=True, session_id="test"
    )
    mock_get_file.return_value = ("specs/plan.md", None)
    mock_implement.return_value = ClaudeAgentPromptResponse(
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


@patch("cape.core.workflow.runner.fetch_issue")
def test_execute_workflow_fetch_failure(mock_fetch, mock_logger):
    """Test workflow handles fetch failure."""
    mock_fetch.side_effect = ValueError("Issue not found")

    result = execute_workflow(999, "adw123", mock_logger)
    assert result is False
    mock_logger.error.assert_called()


@patch("cape.core.workflow.runner.fetch_issue")
@patch("cape.core.workflow.runner.classify_issue")
def test_execute_workflow_classify_failure(mock_classify, mock_fetch, mock_logger, sample_issue):
    """Test workflow handles classification failure."""
    mock_fetch.return_value = sample_issue
    mock_classify.return_value = (None, None, "Classification failed")

    result = execute_workflow(1, "adw123", mock_logger)
    assert result is False


def test_parse_implement_output_success(mock_logger):
    """Test successful parsing of implementation output."""
    output = """{
        "summary": "Fixed the bug",
        "files_modified": ["file1.py", "file2.py"],
        "path": "specs/chore-fix-bug-plan.md",
        "git_diff_stat": "2 files changed, 10 insertions(+), 5 deletions(-)",
        "status": "completed"
    }"""

    result = parse_implement_output(output, mock_logger)
    assert result is not None
    assert result["summary"] == "Fixed the bug"
    assert len(result["files_modified"]) == 2
    assert result["path"] == "specs/chore-fix-bug-plan.md"


def test_parse_implement_output_invalid_json(mock_logger):
    """Test parsing with invalid JSON."""
    output = "not valid json"

    result = parse_implement_output(output, mock_logger)
    assert result is None
    mock_logger.error.assert_called()


def test_parse_implement_output_missing_fields(mock_logger):
    """Test parsing with missing required fields."""
    output = """{
        "summary": "Fixed the bug",
        "files_modified": ["file1.py"]
    }"""

    result = parse_implement_output(output, mock_logger)
    assert result is None
    mock_logger.error.assert_called()


def test_derive_paths_from_plan():
    """Test deriving paths from plan file name."""
    # Test typical case
    result = derive_paths_from_plan("specs/chore-fix-login-plan.md")
    assert result["type"] == "chore"
    assert result["slug"] == "fix-login"
    assert result["plan_file"] == "specs/chore-fix-login-plan.md"
    assert result["review_file"] == "specs/chore-fix-login-review.txt"

    # Test feature type
    result = derive_paths_from_plan("specs/feature-add-auth-plan.md")
    assert result["type"] == "feature"
    assert result["slug"] == "add-auth"
    assert result["review_file"] == "specs/feature-add-auth-review.txt"

    # Test bug type
    result = derive_paths_from_plan("specs/bug-memory-leak-plan.md")
    assert result["type"] == "bug"
    assert result["slug"] == "memory-leak"

    # Test edge case with no slug
    result = derive_paths_from_plan("specs/chore-plan.md")
    assert result["type"] == "chore"
    assert result["slug"] == ""
    assert result["plan_file"] == "specs/chore-plan.md"
    assert result["review_file"] == "specs/chore-review.txt"


@patch("cape.core.workflow.review.subprocess.run")
@patch("cape.core.workflow.review.insert_progress_comment")
@patch("cape.core.workflow.review.os.makedirs")
@patch("cape.core.workflow.review.os.path.dirname")
def test_generate_review_success(
    mock_dirname, mock_makedirs, mock_insert_comment, mock_subprocess, mock_logger, tmp_path
):
    """Test successful CodeRabbit review generation."""
    # Mock subprocess result
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "CodeRabbit review output"
    mock_subprocess.return_value = mock_result

    # Mock directory name
    mock_dirname.return_value = "specs"

    # Mock insert_progress_comment success
    mock_insert_comment.return_value = ("success", "Comment inserted")

    from cape.core.workflow.review import generate_review

    # Use a temporary file for the test
    review_file = tmp_path / "chore-test-review.txt"

    success, review_text = generate_review(
        review_file=str(review_file),
        working_dir="/working/dir",
        repo_path="/repo/path",
        issue_id=123,
        logger=mock_logger
    )

    assert success is True
    assert review_text == "CodeRabbit review output"
    mock_subprocess.assert_called_once()

    # Verify the file was written
    assert review_file.exists()
    assert review_file.read_text() == "CodeRabbit review output"


@patch("cape.core.workflow.review.subprocess.run")
def test_generate_review_subprocess_failure(mock_subprocess, mock_logger):
    """Test CodeRabbit review generation handles subprocess failures."""
    # Mock subprocess failure
    mock_result = Mock()
    mock_result.returncode = 1
    mock_result.stderr = "CodeRabbit error"
    mock_subprocess.return_value = mock_result

    from cape.core.workflow.review import generate_review

    success, review_text = generate_review(
        review_file="specs/chore-test-review.txt",
        working_dir="/working/dir",
        repo_path="/repo/path",
        issue_id=123,
        logger=mock_logger
    )

    assert success is False
    assert review_text is None
    mock_logger.error.assert_called()


@patch("cape.core.workflow.review.subprocess.run")
def test_generate_review_timeout(mock_subprocess, mock_logger):
    """Test CodeRabbit review generation handles timeout."""
    import subprocess
    mock_subprocess.side_effect = subprocess.TimeoutExpired(cmd="coderabbit", timeout=300)

    from cape.core.workflow.review import generate_review

    success, review_text = generate_review(
        review_file="specs/chore-test-review.txt",
        working_dir="/working/dir",
        repo_path="/repo/path",
        issue_id=123,
        logger=mock_logger
    )

    assert success is False
    assert review_text is None
    mock_logger.error.assert_called_with("CodeRabbit review timed out after 300 seconds")


@patch("cape.core.workflow.review.execute_template")
@patch("cape.core.workflow.review.insert_progress_comment")
@patch("cape.core.workflow.review.os.path.exists")
@patch("cape.core.workflow.review.ClaudeAgentTemplateRequest")
def test_notify_review_template_success(
    mock_request_class, mock_exists, mock_insert_comment, mock_execute, mock_logger
):
    """Test successful notification of review template."""
    # Mock file exists
    mock_exists.return_value = True

    # Mock the request object
    mock_request = Mock()
    mock_request_class.return_value = mock_request

    # Mock successful template execution
    mock_response = Mock()
    mock_response.success = True
    mock_response.output = "Template executed successfully"
    mock_execute.return_value = mock_response

    # Mock insert_progress_comment success
    mock_insert_comment.return_value = ("success", "Comment inserted")

    from cape.core.workflow.review import notify_review_template

    success = notify_review_template(
        review_file="specs/chore-test-review.txt",
        issue_id=123,
        adw_id="adw123",
        logger=mock_logger
    )

    assert success is True
    mock_exists.assert_called_once_with("specs/chore-test-review.txt")
    mock_execute.assert_called_once_with(mock_request)
    mock_insert_comment.assert_called_once()


@patch("cape.core.workflow.review.os.path.exists")
def test_notify_review_template_file_not_found(mock_exists, mock_logger):
    """Test notification handles missing review file."""
    mock_exists.return_value = False

    from cape.core.workflow.review import notify_review_template

    success = notify_review_template(
        review_file="specs/missing-review.txt",
        issue_id=123,
        adw_id="adw123",
        logger=mock_logger
    )

    assert success is False
    mock_logger.error.assert_called_with("Review file does not exist: specs/missing-review.txt")


@patch("cape.core.workflow.review.execute_template")
@patch("cape.core.workflow.review.os.path.exists")
@patch("cape.core.workflow.review.ClaudeAgentTemplateRequest")
def test_notify_review_template_execution_failure(
    mock_request_class, mock_exists, mock_execute, mock_logger
):
    """Test notification handles template execution failure."""
    mock_exists.return_value = True

    # Mock the request object
    mock_request = Mock()
    mock_request_class.return_value = mock_request

    # Mock failed template execution
    mock_response = Mock()
    mock_response.success = False
    mock_response.output = "Template execution failed"
    mock_execute.return_value = mock_response

    from cape.core.workflow.review import notify_review_template

    success = notify_review_template(
        review_file="specs/chore-test-review.txt",
        issue_id=123,
        adw_id="adw123",
        logger=mock_logger
    )

    assert success is False
    mock_logger.error.assert_called()
