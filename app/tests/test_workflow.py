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
from cape.core.workflow.address_review import address_review_issues
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

    comment = CapeComment(issue_id=1, comment="Test comment", raw={}, source="test", type="comment")
    status, msg = insert_progress_comment(comment)
    assert status == "success"
    assert "Comment inserted: ID=1" in msg
    assert "Test comment" in msg
    mock_create_comment.assert_called_once_with(comment)


@patch("cape.core.notifications.comments.create_comment")
def test_insert_progress_comment_failure(mock_create_comment):
    """Test progress comment insertion handles errors gracefully."""
    mock_create_comment.side_effect = Exception("Database error")

    comment = CapeComment(issue_id=1, comment="Test comment", raw={}, source="test", type="comment")
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

    result = classify_issue(sample_issue, "adw123", mock_logger)
    assert result.success
    assert result.data.command == "/adw-feature-plan"
    assert result.data.classification == {"type": "feature", "level": "simple"}
    assert result.error is None


@patch("cape.core.workflow.classify.execute_template")
def test_classify_issue_failure(mock_execute, mock_logger, sample_issue):
    """Test issue classification failure."""
    mock_execute.return_value = ClaudeAgentPromptResponse(
        output="Error occurred", success=False, session_id=None
    )

    result = classify_issue(sample_issue, "adw123", mock_logger)
    assert not result.success
    assert result.data is None
    assert result.error == "Error occurred"


@patch("cape.core.workflow.classify.execute_template")
def test_classify_issue_invalid_command(mock_execute, mock_logger, sample_issue):
    """Test issue classification with invalid command."""
    mock_execute.return_value = ClaudeAgentPromptResponse(
        output='{"type": "unsupported", "level": "simple"}',
        success=True,
        session_id="test123",
    )

    result = classify_issue(sample_issue, "adw123", mock_logger)
    assert not result.success
    assert result.data is None
    assert "Invalid issue type" in result.error


@patch("cape.core.workflow.classify.execute_template")
def test_classify_issue_invalid_json(mock_execute, mock_logger, sample_issue):
    """Test classification with invalid JSON output."""
    mock_execute.return_value = ClaudeAgentPromptResponse(
        output="not-json", success=True, session_id="test123"
    )

    result = classify_issue(sample_issue, "adw123", mock_logger)
    assert not result.success
    assert result.data is None
    assert "Invalid classification JSON" in result.error


@patch("cape.core.workflow.plan.execute_template")
def test_build_plan_success(mock_execute, mock_logger, sample_issue):
    """Test successful plan building."""
    mock_execute.return_value = ClaudeAgentPromptResponse(
        output="Plan created successfully", success=True, session_id="test123"
    )

    result = build_plan(sample_issue, "/adw-feature-plan", "adw123", mock_logger)
    assert result.success
    assert result.data.output == "Plan created successfully"


@patch("cape.core.workflow.plan_file.execute_template")
def test_get_plan_file_success(mock_execute, mock_logger):
    """Test successful plan file extraction."""
    mock_execute.return_value = ClaudeAgentPromptResponse(
        output="specs/feature-plan.md", success=True, session_id="test123"
    )

    result = get_plan_file("Plan output", 1, "adw123", mock_logger)
    assert result.success
    assert result.data.file_path == "specs/feature-plan.md"
    assert result.error is None


@patch("cape.core.workflow.plan_file.execute_template")
def test_get_plan_file_not_found(mock_execute, mock_logger):
    """Test plan file not found."""
    mock_execute.return_value = ClaudeAgentPromptResponse(
        output="0", success=True, session_id="test123"
    )

    result = get_plan_file("Plan output", 1, "adw123", mock_logger)
    assert not result.success
    assert result.data is None
    assert "No plan file found" in result.error


@patch("cape.core.workflow.implement.execute_implement_plan")
def test_implement_plan_success(mock_execute, mock_logger):
    """Test successful plan implementation."""
    mock_execute.return_value = Mock(
        output="Implementation complete",
        success=True,
        session_id="test123",
    )

    result = implement_plan("specs/plan.md", 1, "adw123", mock_logger)
    assert result.success
    assert result.data.output == "Implementation complete"


@patch("cape.core.workflow.runner.get_default_pipeline")
def test_execute_workflow_success(mock_get_pipeline, mock_logger):
    """Test successful complete workflow execution via pipeline."""
    # Create mock steps that all succeed
    mock_steps = []
    for i in range(12):  # 12 steps in the pipeline
        mock_step = Mock()
        mock_step.name = f"Step {i}"
        mock_step.is_critical = True
        mock_step.run.return_value = True
        mock_steps.append(mock_step)

    mock_get_pipeline.return_value = mock_steps

    result = execute_workflow(1, "adw123", mock_logger)
    assert result is True

    # Verify all steps were executed
    for step in mock_steps:
        step.run.assert_called_once()


@patch("cape.core.workflow.runner.get_default_pipeline")
def test_execute_workflow_fetch_failure(mock_get_pipeline, mock_logger):
    """Test workflow handles fetch failure (first step fails)."""
    # Create a mock first step that fails
    mock_fetch_step = Mock()
    mock_fetch_step.name = "Fetch Issue"
    mock_fetch_step.is_critical = True
    mock_fetch_step.run.return_value = False

    mock_get_pipeline.return_value = [mock_fetch_step]

    result = execute_workflow(999, "adw123", mock_logger)
    assert result is False
    mock_logger.error.assert_called()


@patch("cape.core.workflow.runner.get_default_pipeline")
def test_execute_workflow_classify_failure(mock_get_pipeline, mock_logger):
    """Test workflow handles classification failure (second step fails)."""
    # Create mock steps where first succeeds, second fails
    mock_fetch_step = Mock()
    mock_fetch_step.name = "Fetch Issue"
    mock_fetch_step.is_critical = True
    mock_fetch_step.run.return_value = True

    mock_classify_step = Mock()
    mock_classify_step.name = "Classify Issue"
    mock_classify_step.is_critical = True
    mock_classify_step.run.return_value = False

    mock_get_pipeline.return_value = [mock_fetch_step, mock_classify_step]

    result = execute_workflow(1, "adw123", mock_logger)
    assert result is False


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

    result = generate_review(
        review_file=str(review_file),
        working_dir="/working/dir",
        repo_path="/repo/path",
        issue_id=123,
        logger=mock_logger,
    )

    assert result.success
    assert result.data.review_text == "CodeRabbit review output"
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

    result = generate_review(
        review_file="specs/chore-test-review.txt",
        working_dir="/working/dir",
        repo_path="/repo/path",
        issue_id=123,
        logger=mock_logger,
    )

    assert not result.success
    assert result.data is None
    mock_logger.error.assert_called()


@patch("cape.core.workflow.review.subprocess.run")
def test_generate_review_timeout(mock_subprocess, mock_logger):
    """Test CodeRabbit review generation handles timeout."""
    import subprocess

    mock_subprocess.side_effect = subprocess.TimeoutExpired(cmd="coderabbit", timeout=300)

    from cape.core.workflow.review import generate_review

    result = generate_review(
        review_file="specs/chore-test-review.txt",
        working_dir="/working/dir",
        repo_path="/repo/path",
        issue_id=123,
        logger=mock_logger,
    )

    assert not result.success
    assert result.data is None
    mock_logger.error.assert_called_with("CodeRabbit review timed out after 300 seconds")


@patch("cape.core.workflow.address_review.execute_template")
@patch("cape.core.workflow.address_review.insert_progress_comment")
@patch("cape.core.workflow.address_review.os.path.exists")
@patch("cape.core.workflow.address_review.ClaudeAgentTemplateRequest")
def test_address_review_issues_success(
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

    result = address_review_issues(
        review_file="specs/chore-test-review.txt", issue_id=123, adw_id="adw123", logger=mock_logger
    )

    assert result.success
    mock_exists.assert_called_once_with("specs/chore-test-review.txt")
    mock_execute.assert_called_once_with(mock_request, stream_handler=None)
    mock_insert_comment.assert_called_once()


@patch("cape.core.workflow.address_review.os.path.exists")
def test_address_review_issues_file_not_found(mock_exists, mock_logger):
    """Test notification handles missing review file."""
    mock_exists.return_value = False

    result = address_review_issues(
        review_file="specs/missing-review.txt", issue_id=123, adw_id="adw123", logger=mock_logger
    )

    assert not result.success
    mock_logger.error.assert_called_with("Review file does not exist: specs/missing-review.txt")


@patch("cape.core.workflow.address_review.execute_template")
@patch("cape.core.workflow.address_review.os.path.exists")
@patch("cape.core.workflow.address_review.ClaudeAgentTemplateRequest")
def test_address_review_issues_execution_failure(
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

    result = address_review_issues(
        review_file="specs/chore-test-review.txt", issue_id=123, adw_id="adw123", logger=mock_logger
    )

    assert not result.success
    mock_logger.error.assert_called()


# === CreatePullRequestStep Tests ===


@patch("cape.core.workflow.steps.create_pr.subprocess.run")
@patch("cape.core.workflow.steps.create_pr.emit_progress_comment")
@patch.dict("os.environ", {"GITHUB_PAT": "test-token"})
def test_create_pr_step_success(mock_emit, mock_subprocess, mock_logger):
    """Test successful PR creation."""
    from cape.core.workflow.step_base import WorkflowContext
    from cape.core.workflow.steps.create_pr import CreatePullRequestStep

    # Mock subprocess success
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = "https://github.com/owner/repo/pull/123\n"
    mock_subprocess.return_value = mock_result

    # Mock emit_progress_comment success
    mock_emit.return_value = ("success", "Comment inserted")

    context = WorkflowContext(issue_id=1, adw_id="adw123", logger=mock_logger)
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This PR adds a new feature.",
        "commits": ["abc1234", "def5678"],
    }

    step = CreatePullRequestStep()
    result = step.run(context)

    assert result is True
    mock_subprocess.assert_called_once()
    mock_emit.assert_called_once()

    # Verify the emit call has correct data
    call_args = mock_emit.call_args
    assert call_args[0][0] == 1  # issue_id
    assert "https://github.com/owner/repo/pull/123" in call_args[0][1]
    assert call_args[1]["raw"]["output"] == "pull-request-created"
    assert call_args[1]["raw"]["url"] == "https://github.com/owner/repo/pull/123"


@patch.dict("os.environ", {}, clear=True)
def test_create_pr_step_missing_github_pat(mock_logger):
    """Test PR creation skipped when GITHUB_PAT is missing."""
    from cape.core.workflow.step_base import WorkflowContext
    from cape.core.workflow.steps.create_pr import CreatePullRequestStep

    context = WorkflowContext(issue_id=1, adw_id="adw123", logger=mock_logger)
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This PR adds a new feature.",
        "commits": [],
    }

    step = CreatePullRequestStep()
    result = step.run(context)

    assert result is False
    mock_logger.warning.assert_called_with(
        "GITHUB_PAT environment variable not set, skipping PR creation"
    )


def test_create_pr_step_missing_pr_details(mock_logger):
    """Test PR creation skipped when pr_details is missing."""
    from cape.core.workflow.step_base import WorkflowContext
    from cape.core.workflow.steps.create_pr import CreatePullRequestStep

    context = WorkflowContext(issue_id=1, adw_id="adw123", logger=mock_logger)
    # No pr_details in context

    step = CreatePullRequestStep()
    result = step.run(context)

    assert result is False
    mock_logger.warning.assert_called_with("No PR details found in context, skipping PR creation")


@patch.dict("os.environ", {"GITHUB_PAT": "test-token"})
def test_create_pr_step_empty_title(mock_logger):
    """Test PR creation skipped when title is empty."""
    from cape.core.workflow.step_base import WorkflowContext
    from cape.core.workflow.steps.create_pr import CreatePullRequestStep

    context = WorkflowContext(issue_id=1, adw_id="adw123", logger=mock_logger)
    context.data["pr_details"] = {
        "title": "",
        "summary": "Some summary",
        "commits": [],
    }

    step = CreatePullRequestStep()
    result = step.run(context)

    assert result is False
    mock_logger.warning.assert_called_with("PR title is empty, skipping PR creation")


@patch("cape.core.workflow.steps.create_pr.subprocess.run")
@patch.dict("os.environ", {"GITHUB_PAT": "test-token"})
def test_create_pr_step_gh_command_failure(mock_subprocess, mock_logger):
    """Test PR creation handles gh command failure."""
    from cape.core.workflow.step_base import WorkflowContext
    from cape.core.workflow.steps.create_pr import CreatePullRequestStep

    # Mock subprocess failure
    mock_result = Mock()
    mock_result.returncode = 1
    mock_result.stderr = "error: could not create pull request"
    mock_subprocess.return_value = mock_result

    context = WorkflowContext(issue_id=1, adw_id="adw123", logger=mock_logger)
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This PR adds a new feature.",
        "commits": [],
    }

    step = CreatePullRequestStep()
    result = step.run(context)

    assert result is False
    mock_logger.warning.assert_called()


@patch("cape.core.workflow.steps.create_pr.subprocess.run")
@patch.dict("os.environ", {"GITHUB_PAT": "test-token"})
def test_create_pr_step_timeout(mock_subprocess, mock_logger):
    """Test PR creation handles timeout."""
    import subprocess

    from cape.core.workflow.step_base import WorkflowContext
    from cape.core.workflow.steps.create_pr import CreatePullRequestStep

    mock_subprocess.side_effect = subprocess.TimeoutExpired(cmd="gh", timeout=120)

    context = WorkflowContext(issue_id=1, adw_id="adw123", logger=mock_logger)
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This PR adds a new feature.",
        "commits": [],
    }

    step = CreatePullRequestStep()
    result = step.run(context)

    assert result is False
    mock_logger.warning.assert_called_with("gh pr create timed out after 120 seconds")


@patch("cape.core.workflow.steps.create_pr.subprocess.run")
@patch.dict("os.environ", {"GITHUB_PAT": "test-token"})
def test_create_pr_step_gh_not_found(mock_subprocess, mock_logger):
    """Test PR creation handles gh CLI not found."""
    from cape.core.workflow.step_base import WorkflowContext
    from cape.core.workflow.steps.create_pr import CreatePullRequestStep

    mock_subprocess.side_effect = FileNotFoundError("gh not found")

    context = WorkflowContext(issue_id=1, adw_id="adw123", logger=mock_logger)
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This PR adds a new feature.",
        "commits": [],
    }

    step = CreatePullRequestStep()
    result = step.run(context)

    assert result is False
    mock_logger.warning.assert_called_with("gh CLI not found, skipping PR creation")


def test_create_pr_step_is_not_critical():
    """Test CreatePullRequestStep is not critical."""
    from cape.core.workflow.steps.create_pr import CreatePullRequestStep

    step = CreatePullRequestStep()
    assert step.is_critical is False


def test_create_pr_step_name():
    """Test CreatePullRequestStep has correct name."""
    from cape.core.workflow.steps.create_pr import CreatePullRequestStep

    step = CreatePullRequestStep()
    assert step.name == "Creating pull request"


# === PreparePullRequestStep JSON parsing Tests ===


def test_prepare_pr_step_store_pr_details_success(mock_logger):
    """Test _store_pr_details parses and stores JSON correctly."""
    from cape.core.workflow.step_base import WorkflowContext
    from cape.core.workflow.steps.pr import PreparePullRequestStep

    context = WorkflowContext(issue_id=1, adw_id="adw123", logger=mock_logger)
    step = PreparePullRequestStep()

    output = (
        '{"title": "feat: add feature", "summary": "This adds a feature.", '
        '"commits": ["abc123", "def456"]}'
    )
    step._store_pr_details(output, context, mock_logger)

    assert "pr_details" in context.data
    assert context.data["pr_details"]["title"] == "feat: add feature"
    assert context.data["pr_details"]["summary"] == "This adds a feature."
    assert context.data["pr_details"]["commits"] == ["abc123", "def456"]


def test_prepare_pr_step_store_pr_details_malformed_json(mock_logger):
    """Test _store_pr_details handles malformed JSON gracefully."""
    from cape.core.workflow.step_base import WorkflowContext
    from cape.core.workflow.steps.pr import PreparePullRequestStep

    context = WorkflowContext(issue_id=1, adw_id="adw123", logger=mock_logger)
    step = PreparePullRequestStep()

    output = "not valid json"
    step._store_pr_details(output, context, mock_logger)

    assert "pr_details" not in context.data
    mock_logger.warning.assert_called()


def test_prepare_pr_step_store_pr_details_missing_fields(mock_logger):
    """Test _store_pr_details handles missing fields with defaults."""
    from cape.core.workflow.step_base import WorkflowContext
    from cape.core.workflow.steps.pr import PreparePullRequestStep

    context = WorkflowContext(issue_id=1, adw_id="adw123", logger=mock_logger)
    step = PreparePullRequestStep()

    output = '{"title": "only title"}'
    step._store_pr_details(output, context, mock_logger)

    assert "pr_details" in context.data
    assert context.data["pr_details"]["title"] == "only title"
    assert context.data["pr_details"]["summary"] == ""
    assert context.data["pr_details"]["commits"] == []
