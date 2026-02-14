"""Tests for workflow orchestration."""

from unittest.mock import Mock, patch

import pytest
from postgrest.exceptions import APIError

from rouge.core.models import CommentPayload, Issue
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.workflow import execute_workflow, update_status
from rouge.core.workflow.shared import derive_paths_from_plan
from rouge.core.workflow.steps.review import is_clean_review
from rouge.core.workflow.types import StepResult


@pytest.fixture
def sample_issue():
    """Create a sample issue for testing."""
    return Issue(id=1, description="Fix login bug", status="pending")


@patch("rouge.core.workflow.status.update_issue_status")
def test_update_status_success(mock_update_issue_status):
    """Test successful status update."""
    mock_issue = Mock()
    mock_issue.id = 1
    mock_update_issue_status.return_value = mock_issue

    update_status(1, "started")
    mock_update_issue_status.assert_called_once_with(1, "started")


@patch("rouge.core.workflow.status.update_issue_status")
def test_update_status_failure(mock_update_issue_status):
    """Test status update handles errors gracefully."""
    mock_update_issue_status.side_effect = APIError({"message": "Database error"})

    # Should not raise - best-effort
    update_status(1, "started")


@patch("rouge.core.notifications.comments.create_comment")
def test_emit_comment_from_payload_success(mock_create_comment):
    """Test successful progress comment insertion."""
    mock_comment = Mock()
    mock_comment.id = 1
    mock_create_comment.return_value = mock_comment

    payload = CommentPayload(
        issue_id=1,
        adw_id="",
        text="Test comment",
        source="system",
        kind="comment",
    )
    status, msg = emit_comment_from_payload(payload)
    assert status == "success"
    assert "Comment inserted: ID=1" in msg
    assert "Test comment" in msg
    mock_create_comment.assert_called_once()
    created_comment = mock_create_comment.call_args[0][0]
    assert created_comment.issue_id == 1
    assert created_comment.comment == "Test comment"
    assert created_comment.source == "system"
    assert created_comment.type == "comment"


@patch("rouge.core.notifications.comments.create_comment")
def test_emit_comment_from_payload_failure(mock_create_comment):
    """Test progress comment insertion handles errors gracefully."""
    mock_create_comment.side_effect = Exception("Database error")

    payload = CommentPayload(
        issue_id=1,
        adw_id="",
        text="Test comment",
        source="system",
        kind="comment",
    )
    status, msg = emit_comment_from_payload(payload)
    assert status == "error"
    assert "Failed to insert comment on issue 1" in msg
    assert "Database error" in msg


# REMOVED: Tests for classify_issue function (moved to step class in rouge.core.workflow.steps.classify)
# These tests tested a top-level function that no longer exists after refactoring.
# The business logic is now in ClassifyStep.run() method.
# To test classification logic, test ClassifyStep directly instead.


# REMOVED: Tests for build_plan function (moved to step class in rouge.core.workflow.steps.plan)
# This test tested a top-level function that no longer exists after refactoring.
# The business logic is now in PlanStep.run() method.
# To test plan building logic, test PlanStep directly instead.


# REMOVED: Tests for implement_plan function (moved to step class in rouge.core.workflow.steps.implement)
# This test tested a top-level function that no longer exists after refactoring.
# The business logic is now in ImplementStep.run() method.
# To test implementation logic, test ImplementStep directly instead.


@patch("rouge.core.workflow.runner.get_default_pipeline")
def test_execute_workflow_success(mock_get_pipeline):
    """Test successful complete workflow execution via pipeline."""
    # Create mock steps that all succeed
    mock_steps = []
    for i in range(12):  # 12 steps in the pipeline
        mock_step = Mock()
        mock_step.name = f"Step {i}"
        mock_step.is_critical = True
        mock_step.run.return_value = StepResult.ok(None)
        mock_steps.append(mock_step)

    mock_get_pipeline.return_value = mock_steps

    result = execute_workflow(1, "adw123")
    assert result is True

    # Verify all steps were executed
    for step in mock_steps:
        step.run.assert_called_once()


@patch("rouge.core.workflow.runner.get_default_pipeline")
def test_execute_workflow_fetch_failure(mock_get_pipeline):
    """Test workflow handles fetch failure (first step fails)."""
    # Create a mock first step that fails
    mock_fetch_step = Mock()
    mock_fetch_step.name = "Fetch Issue"
    mock_fetch_step.is_critical = True
    mock_fetch_step.run.return_value = StepResult.fail("Fetch failed")

    mock_get_pipeline.return_value = [mock_fetch_step]

    result = execute_workflow(999, "adw123")
    assert result is False


@patch("rouge.core.workflow.runner.get_default_pipeline")
def test_execute_workflow_classify_failure(mock_get_pipeline):
    """Test workflow handles classification failure (second step fails)."""
    # Create mock steps where first succeeds, second fails
    mock_fetch_step = Mock()
    mock_fetch_step.name = "Fetch Issue"
    mock_fetch_step.is_critical = True
    mock_fetch_step.run.return_value = StepResult.ok(None)

    mock_classify_step = Mock()
    mock_classify_step.name = "Classify Issue"
    mock_classify_step.is_critical = True
    mock_classify_step.run.return_value = StepResult.fail("Classification failed")

    mock_get_pipeline.return_value = [mock_fetch_step, mock_classify_step]

    result = execute_workflow(1, "adw123")
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


# REMOVED: Tests for generate_review function (moved to step class in rouge.core.workflow.steps.code_review)
# These tests tested a top-level function that no longer exists after refactoring.
# The business logic is now in CodeReviewStep._generate_review() method.
# To test review generation logic, test CodeReviewStep directly instead.


# === is_clean_review Tests ===


def test_is_clean_review_clean_text():
    """Test is_clean_review returns True for clean review text."""
    review_text = "Review completed\nNo issues found. The code looks good."
    assert is_clean_review(review_text) is True


def test_is_clean_review_with_issues():
    """Test is_clean_review returns False when review contains file-level issues."""
    review_text = (
        "Review completed\nFile: src/main.py\nLine 42: Missing error handling for null case."
    )
    assert is_clean_review(review_text) is False


def test_is_clean_review_empty_text():
    """Test is_clean_review returns False for empty text."""
    assert is_clean_review("") is False


def test_is_clean_review_missing_review_completed_marker():
    """Test is_clean_review returns False when 'Review completed' marker is absent."""
    review_text = "All checks passed. No issues found."
    assert is_clean_review(review_text) is False


def test_is_clean_review_only_file_marker():
    """Test is_clean_review returns False when only 'File:' marker is present."""
    review_text = "File: src/utils.py\nLine 10: Unused import."
    assert is_clean_review(review_text) is False


def test_is_clean_review_both_markers_missing():
    """Test is_clean_review returns False when both markers are absent."""
    review_text = "Some random text without any markers."
    assert is_clean_review(review_text) is False


# REMOVED: Tests for address_review_issues function (moved to step class in rouge.core.workflow.steps.review_fix)
# This test tested a top-level function that no longer exists after refactoring.
# The business logic is now in ReviewFixStep.run() method.
# To test address review logic, test ReviewFixStep directly instead.


# REMOVED: Tests for notify_plan_acceptance function (moved to step class in rouge.core.workflow.steps.acceptance)
# This test tested a top-level function that no longer exists after refactoring.
# The business logic is now in AcceptanceStep.run() method.
# To test acceptance logic, test AcceptanceStep directly instead.


@patch("rouge.core.workflow.steps.code_quality_step.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.code_quality_step.execute_template")
def test_code_quality_step_passes_json_schema(mock_execute, mock_emit):
    """Test code quality step passes strict JSON schema to Claude template request."""
    from rouge.core.workflow.step_base import WorkflowContext
    from rouge.core.workflow.steps.code_quality_step import CodeQualityStep

    mock_emit.return_value = ("success", "ok")
    mock_response = Mock()
    mock_response.success = True
    mock_response.output = '{"issues":[],"output":"code-quality","tools":[]}'
    mock_execute.return_value = mock_response

    context = WorkflowContext(issue_id=1, adw_id="adw123")
    step = CodeQualityStep()
    result = step.run(context)

    assert result.success is True
    request = mock_execute.call_args[0][0]
    assert request.json_schema is not None
    assert '"const": "code-quality"' in request.json_schema


# REMOVED: More tests for address_review_issues function (moved to step class in rouge.core.workflow.steps.review_fix)
# These tests tested a top-level function that no longer exists after refactoring.
# The business logic is now in ReviewFixStep.run() method.
# To test address review logic, test ReviewFixStep directly instead.


# === CreatePullRequestStep Tests ===


@patch("rouge.core.workflow.steps.create_github_pull_request_step.shutil.which")
@patch("rouge.core.workflow.steps.create_github_pull_request_step.get_repo_path")
@patch("rouge.core.workflow.steps.create_github_pull_request_step.subprocess.run")
@patch("rouge.core.workflow.steps.create_github_pull_request_step.emit_comment_from_payload")
@patch.dict("os.environ", {"GITHUB_PAT": "test-token"})
def test_create_pr_step_success(mock_emit, mock_subprocess, mock_get_repo_path, mock_which):
    """Test successful PR creation with git push before gh pr create."""
    from rouge.core.workflow.step_base import WorkflowContext
    from rouge.core.workflow.steps.create_github_pull_request_step import CreateGitHubPullRequestStep

    # Mock shutil.which to indicate gh CLI is available
    mock_which.return_value = "/usr/bin/gh"

    # Mock get_repo_path to return a specific path
    mock_get_repo_path.return_value = "/path/to/repo"

    # Mock subprocess success for both git push and gh pr create
    mock_push_result = Mock()
    mock_push_result.returncode = 0
    mock_push_result.stdout = ""
    mock_push_result.stderr = ""

    mock_pr_result = Mock()
    mock_pr_result.returncode = 0
    mock_pr_result.stdout = "https://github.com/owner/repo/pull/123\n"

    mock_subprocess.side_effect = [mock_push_result, mock_pr_result]

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = WorkflowContext(issue_id=1, adw_id="adw123")
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This PR adds a new feature.",
        "commits": ["abc1234", "def5678"],
    }

    step = CreateGitHubPullRequestStep()
    result = step.run(context)

    assert result.success is True
    assert mock_subprocess.call_count == 2
    mock_emit.assert_called_once()

    # Verify git push was called first
    push_call = mock_subprocess.call_args_list[0]
    assert push_call[0][0] == ["git", "push", "--set-upstream", "origin", "HEAD"]
    assert push_call[1]["cwd"] == "/path/to/repo"

    # Verify gh pr create was called second
    pr_call = mock_subprocess.call_args_list[1]
    assert pr_call[0][0][0:3] == ["gh", "pr", "create"]
    assert pr_call[1]["cwd"] == "/path/to/repo"

    # Verify the emit call has correct data
    call_args = mock_emit.call_args
    payload = call_args[0][0]
    assert payload.issue_id == 1
    assert "https://github.com/owner/repo/pull/123" in payload.text
    assert payload.raw["output"] == "pull-request-created"
    assert payload.raw["url"] == "https://github.com/owner/repo/pull/123"


@patch.dict("os.environ", {}, clear=True)
@patch("rouge.core.workflow.steps.create_github_pull_request_step.emit_comment_from_payload")
def test_create_pr_step_missing_github_pat(mock_emit):
    """Test PR creation skipped when GITHUB_PAT is missing."""
    from rouge.core.workflow.step_base import WorkflowContext
    from rouge.core.workflow.steps.create_github_pull_request_step import CreateGitHubPullRequestStep

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = WorkflowContext(issue_id=1, adw_id="adw123")
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This PR adds a new feature.",
        "commits": [],
    }

    step = CreateGitHubPullRequestStep()
    result = step.run(context)

    assert result.success is True
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "pull-request-skipped"


@patch("rouge.core.workflow.steps.create_github_pull_request_step.emit_comment_from_payload")
def test_create_pr_step_missing_pr_details(mock_emit):
    """Test PR creation skipped when pr_details is missing."""
    from rouge.core.workflow.step_base import WorkflowContext
    from rouge.core.workflow.steps.create_github_pull_request_step import CreateGitHubPullRequestStep

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = WorkflowContext(issue_id=1, adw_id="adw123")
    # No pr_details in context

    step = CreateGitHubPullRequestStep()
    result = step.run(context)

    assert result.success is True
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "pull-request-skipped"


@patch("rouge.core.workflow.steps.create_github_pull_request_step.emit_comment_from_payload")
@patch.dict("os.environ", {"GITHUB_PAT": "test-token"})
def test_create_pr_step_empty_title(mock_emit):
    """Test PR creation skipped when title is empty."""
    from rouge.core.workflow.step_base import WorkflowContext
    from rouge.core.workflow.steps.create_github_pull_request_step import CreateGitHubPullRequestStep

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = WorkflowContext(issue_id=1, adw_id="adw123")
    context.data["pr_details"] = {
        "title": "",
        "summary": "Some summary",
        "commits": [],
    }

    step = CreateGitHubPullRequestStep()
    result = step.run(context)

    assert result.success is True
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "pull-request-skipped"


@patch("rouge.core.workflow.steps.create_github_pull_request_step.shutil.which")
@patch("rouge.core.workflow.steps.create_github_pull_request_step.get_repo_path")
@patch("rouge.core.workflow.steps.create_github_pull_request_step.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.create_github_pull_request_step.subprocess.run")
@patch.dict("os.environ", {"GITHUB_PAT": "test-token"})
def test_create_pr_step_already_exists_is_success(
    mock_subprocess, mock_emit, mock_get_repo_path, mock_which
):
    """Test PR creation is idempotent when gh reports existing PR."""
    from rouge.core.workflow.step_base import WorkflowContext
    from rouge.core.workflow.steps.create_github_pull_request_step import CreateGitHubPullRequestStep

    mock_which.return_value = "/usr/bin/gh"
    mock_get_repo_path.return_value = "/path/to/repo"

    mock_push_result = Mock(returncode=0, stdout="", stderr="")
    mock_pr_result = Mock(
        returncode=1,
        stderr=(
            'a pull request for branch "adw-64c59625" into branch "main" already exists:\n'
            "https://github.com/owner/repo/pull/123\n"
        ),
    )
    mock_subprocess.side_effect = [mock_push_result, mock_pr_result]
    mock_emit.return_value = ("success", "Comment inserted")

    context = WorkflowContext(issue_id=1, adw_id="adw123")
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This PR adds a new feature.",
        "commits": [],
    }

    step = CreateGitHubPullRequestStep()
    result = step.run(context)

    assert result.success is True
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "pull-request-created"
    assert mock_emit.call_args[0][0].raw["url"] == "https://github.com/owner/repo/pull/123"
    assert mock_emit.call_args[0][0].raw["existing"] is True


@patch("rouge.core.workflow.steps.create_github_pull_request_step.shutil.which")
@patch("rouge.core.workflow.steps.create_github_pull_request_step.get_repo_path")
@patch("rouge.core.workflow.steps.create_github_pull_request_step.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.create_github_pull_request_step.subprocess.run")
@patch.dict("os.environ", {"GITHUB_PAT": "test-token"})
def test_create_pr_step_gh_command_failure(
    mock_subprocess, mock_emit, mock_get_repo_path, mock_which
):
    """Test PR creation handles gh command failure."""
    from rouge.core.workflow.step_base import WorkflowContext
    from rouge.core.workflow.steps.create_github_pull_request_step import CreateGitHubPullRequestStep

    # Mock shutil.which to indicate gh CLI is available
    mock_which.return_value = "/usr/bin/gh"

    mock_get_repo_path.return_value = "/path/to/repo"

    # Mock git push success, gh pr create failure
    mock_push_result = Mock()
    mock_push_result.returncode = 0
    mock_push_result.stdout = ""
    mock_push_result.stderr = ""

    mock_pr_result = Mock()
    mock_pr_result.returncode = 1
    mock_pr_result.stderr = "error: could not create pull request"

    mock_subprocess.side_effect = [mock_push_result, mock_pr_result]

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = WorkflowContext(issue_id=1, adw_id="adw123")
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This PR adds a new feature.",
        "commits": [],
    }

    step = CreateGitHubPullRequestStep()
    result = step.run(context)

    assert result.success is False
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "pull-request-failed"


@patch("rouge.core.workflow.steps.create_github_pull_request_step.shutil.which")
@patch("rouge.core.workflow.steps.create_github_pull_request_step.get_repo_path")
@patch("rouge.core.workflow.steps.create_github_pull_request_step.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.create_github_pull_request_step.subprocess.run")
@patch.dict("os.environ", {"GITHUB_PAT": "test-token"})
def test_create_pr_step_timeout(mock_subprocess, mock_emit, mock_get_repo_path, mock_which):
    """Test PR creation handles timeout on gh pr create."""
    import subprocess

    from rouge.core.workflow.step_base import WorkflowContext
    from rouge.core.workflow.steps.create_github_pull_request_step import CreateGitHubPullRequestStep

    # Mock shutil.which to indicate gh CLI is available
    mock_which.return_value = "/usr/bin/gh"

    mock_get_repo_path.return_value = "/path/to/repo"

    # Mock git push success, gh pr create timeout
    mock_push_result = Mock()
    mock_push_result.returncode = 0
    mock_push_result.stdout = ""
    mock_push_result.stderr = ""

    mock_subprocess.side_effect = [
        mock_push_result,
        subprocess.TimeoutExpired(cmd="gh", timeout=120),
    ]

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = WorkflowContext(issue_id=1, adw_id="adw123")
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This PR adds a new feature.",
        "commits": [],
    }

    step = CreateGitHubPullRequestStep()
    result = step.run(context)

    assert result.success is False
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "pull-request-failed"


@patch("rouge.core.workflow.steps.create_github_pull_request_step.shutil.which")
@patch("rouge.core.workflow.steps.create_github_pull_request_step.emit_comment_from_payload")
@patch.dict("os.environ", {"GITHUB_PAT": "test-token"})
def test_create_pr_step_gh_not_found(mock_emit, mock_which):
    """Test PR creation handles gh CLI not found via proactive detection."""
    from rouge.core.workflow.step_base import WorkflowContext
    from rouge.core.workflow.steps.create_github_pull_request_step import CreateGitHubPullRequestStep

    # Mock shutil.which to return None (gh not found)
    mock_which.return_value = None

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = WorkflowContext(issue_id=1, adw_id="adw123")
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This PR adds a new feature.",
        "commits": [],
    }

    step = CreateGitHubPullRequestStep()
    result = step.run(context)

    # Should return ok (skip) rather than fail since gh not found is handled proactively
    assert result.success is True
    mock_which.assert_called_once_with("gh")
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "pull-request-skipped"
    assert "gh CLI not found" in mock_emit.call_args[0][0].raw["reason"]


@patch("rouge.core.workflow.steps.create_github_pull_request_step.shutil.which")
@patch("rouge.core.workflow.steps.create_github_pull_request_step.get_repo_path")
@patch("rouge.core.workflow.steps.create_github_pull_request_step.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.create_github_pull_request_step.subprocess.run")
@patch.dict("os.environ", {"GITHUB_PAT": "test-token"})
def test_create_pr_step_push_failure_continues_to_pr(
    mock_subprocess, mock_emit, mock_get_repo_path, mock_which
):
    """Test PR creation continues even when git push fails."""
    from rouge.core.workflow.step_base import WorkflowContext
    from rouge.core.workflow.steps.create_github_pull_request_step import CreateGitHubPullRequestStep

    # Mock shutil.which to indicate gh CLI is available
    mock_which.return_value = "/usr/bin/gh"

    mock_get_repo_path.return_value = "/path/to/repo"

    # Mock git push failure, gh pr create success
    mock_push_result = Mock()
    mock_push_result.returncode = 1
    mock_push_result.stdout = ""
    mock_push_result.stderr = "error: failed to push some refs"

    mock_pr_result = Mock()
    mock_pr_result.returncode = 0
    mock_pr_result.stdout = "https://github.com/owner/repo/pull/123\n"

    mock_subprocess.side_effect = [mock_push_result, mock_pr_result]

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = WorkflowContext(issue_id=1, adw_id="adw123")
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This PR adds a new feature.",
        "commits": [],
    }

    step = CreateGitHubPullRequestStep()
    result = step.run(context)

    # PR should succeed even if push failed (branch may already exist on remote)
    assert result.success is True
    assert mock_subprocess.call_count == 2
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "pull-request-created"


@patch("rouge.core.workflow.steps.create_github_pull_request_step.shutil.which")
@patch("rouge.core.workflow.steps.create_github_pull_request_step.get_repo_path")
@patch("rouge.core.workflow.steps.create_github_pull_request_step.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.create_github_pull_request_step.subprocess.run")
@patch.dict("os.environ", {"GITHUB_PAT": "test-token"})
def test_create_pr_step_push_timeout_continues_to_pr(
    mock_subprocess, mock_emit, mock_get_repo_path, mock_which
):
    """Test PR creation continues even when git push times out."""
    import subprocess

    from rouge.core.workflow.step_base import WorkflowContext
    from rouge.core.workflow.steps.create_github_pull_request_step import CreateGitHubPullRequestStep

    # Mock shutil.which to indicate gh CLI is available
    mock_which.return_value = "/usr/bin/gh"

    mock_get_repo_path.return_value = "/path/to/repo"

    # Mock git push timeout, gh pr create success
    mock_pr_result = Mock()
    mock_pr_result.returncode = 0
    mock_pr_result.stdout = "https://github.com/owner/repo/pull/123\n"

    mock_subprocess.side_effect = [
        subprocess.TimeoutExpired(cmd="git", timeout=60),
        mock_pr_result,
    ]

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = WorkflowContext(issue_id=1, adw_id="adw123")
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This PR adds a new feature.",
        "commits": [],
    }

    step = CreateGitHubPullRequestStep()
    result = step.run(context)

    # PR should succeed even if push timed out
    assert result.success is True
    assert mock_subprocess.call_count == 2
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "pull-request-created"


def test_create_pr_step_is_not_critical():
    """Test CreateGitHubPullRequestStep is not critical."""
    from rouge.core.workflow.steps.create_github_pull_request_step import CreateGitHubPullRequestStep

    step = CreateGitHubPullRequestStep()
    assert step.is_critical is False


def test_create_pr_step_name():
    """Test CreateGitHubPullRequestStep has correct name."""
    from rouge.core.workflow.steps.create_github_pull_request_step import CreateGitHubPullRequestStep

    step = CreateGitHubPullRequestStep()
    assert step.name == "Creating GitHub pull request"


# === CreateGitLabPullRequestStep Tests ===


@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.get_repo_path")
@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.subprocess.run")
@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.emit_comment_from_payload")
@patch.dict("os.environ", {"GITLAB_PAT": "test-token"})
def test_create_gitlab_mr_step_success(mock_emit, mock_subprocess, mock_get_repo_path):
    """Test successful MR creation with git push before glab mr create."""
    from rouge.core.workflow.step_base import WorkflowContext
    from rouge.core.workflow.steps.create_gitlab_pull_request_step import CreateGitLabPullRequestStep

    # Mock get_repo_path to return a specific path
    mock_get_repo_path.return_value = "/path/to/repo"

    # Mock subprocess success for both git push and glab mr create
    mock_push_result = Mock()
    mock_push_result.returncode = 0
    mock_push_result.stdout = ""
    mock_push_result.stderr = ""

    mock_mr_result = Mock()
    mock_mr_result.returncode = 0
    mock_mr_result.stdout = "https://gitlab.com/owner/repo/-/merge_requests/123\n"

    mock_subprocess.side_effect = [mock_push_result, mock_mr_result]

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = WorkflowContext(issue_id=1, adw_id="adw123")
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This MR adds a new feature.",
        "commits": ["abc1234", "def5678"],
    }

    step = CreateGitLabPullRequestStep()
    result = step.run(context)

    assert result.success is True
    assert mock_subprocess.call_count == 2
    mock_emit.assert_called_once()

    # Verify git push was called first
    push_call = mock_subprocess.call_args_list[0]
    assert push_call[0][0] == ["git", "push", "--set-upstream", "origin", "HEAD"]
    assert push_call[1]["cwd"] == "/path/to/repo"

    # Verify glab mr create was called second
    mr_call = mock_subprocess.call_args_list[1]
    assert mr_call[0][0][0:3] == ["glab", "mr", "create"]
    assert mr_call[1]["cwd"] == "/path/to/repo"

    # Verify the emit call has correct data
    call_args = mock_emit.call_args
    payload = call_args[0][0]
    assert payload.issue_id == 1
    assert "https://gitlab.com/owner/repo/-/merge_requests/123" in payload.text
    assert payload.raw["output"] == "merge-request-created"
    assert payload.raw["url"] == "https://gitlab.com/owner/repo/-/merge_requests/123"


@patch.dict("os.environ", {}, clear=True)
@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.logger")
def test_create_gitlab_mr_step_missing_gitlab_pat(mock_logger, mock_emit):
    """Test MR creation skipped when GITLAB_PAT is missing."""
    from rouge.core.workflow.step_base import WorkflowContext
    from rouge.core.workflow.steps.create_gitlab_pull_request_step import CreateGitLabPullRequestStep

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = WorkflowContext(issue_id=1, adw_id="adw123")
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This MR adds a new feature.",
        "commits": [],
    }

    step = CreateGitLabPullRequestStep()
    result = step.run(context)

    assert result.success is True
    mock_logger.info.assert_called_with(
        "MR creation skipped: GITLAB_PAT environment variable not set"
    )
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "merge-request-skipped"


@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.logger")
def test_create_gitlab_mr_step_missing_pr_details(mock_logger, mock_emit):
    """Test MR creation skipped when pr_details is missing."""
    from rouge.core.workflow.step_base import WorkflowContext
    from rouge.core.workflow.steps.create_gitlab_pull_request_step import CreateGitLabPullRequestStep

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = WorkflowContext(issue_id=1, adw_id="adw123")
    # No pr_details in context

    step = CreateGitLabPullRequestStep()
    result = step.run(context)

    assert result.success is True
    mock_logger.info.assert_called_with("MR creation skipped: no PR details in context")
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "merge-request-skipped"


@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.logger")
@patch.dict("os.environ", {"GITLAB_PAT": "test-token"})
def test_create_gitlab_mr_step_empty_title(mock_logger, mock_emit):
    """Test MR creation skipped when title is empty."""
    from rouge.core.workflow.step_base import WorkflowContext
    from rouge.core.workflow.steps.create_gitlab_pull_request_step import CreateGitLabPullRequestStep

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = WorkflowContext(issue_id=1, adw_id="adw123")
    context.data["pr_details"] = {
        "title": "",
        "summary": "Some summary",
        "commits": [],
    }

    step = CreateGitLabPullRequestStep()
    result = step.run(context)

    assert result.success is True
    mock_logger.info.assert_called_with("MR creation skipped: MR title is empty")
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "merge-request-skipped"


@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.get_repo_path")
@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.logger")
@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.subprocess.run")
@patch.dict("os.environ", {"GITLAB_PAT": "test-token"})
def test_create_gitlab_mr_step_glab_command_failure(
    mock_subprocess, mock_logger, mock_emit, mock_get_repo_path
):
    """Test MR creation handles glab command failure."""
    from rouge.core.workflow.step_base import WorkflowContext
    from rouge.core.workflow.steps.create_gitlab_pull_request_step import CreateGitLabPullRequestStep

    mock_get_repo_path.return_value = "/path/to/repo"

    # Mock git push success, glab mr create failure
    mock_push_result = Mock()
    mock_push_result.returncode = 0
    mock_push_result.stdout = ""
    mock_push_result.stderr = ""

    mock_mr_result = Mock()
    mock_mr_result.returncode = 1
    mock_mr_result.stderr = "error: could not create merge request"

    mock_subprocess.side_effect = [mock_push_result, mock_mr_result]

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = WorkflowContext(issue_id=1, adw_id="adw123")
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This MR adds a new feature.",
        "commits": [],
    }

    step = CreateGitLabPullRequestStep()
    result = step.run(context)

    assert result.success is False
    mock_logger.warning.assert_called()
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "merge-request-failed"


@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.get_repo_path")
@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.logger")
@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.subprocess.run")
@patch.dict("os.environ", {"GITLAB_PAT": "test-token"})
def test_create_gitlab_mr_step_timeout(mock_subprocess, mock_logger, mock_emit, mock_get_repo_path):
    """Test MR creation handles timeout on glab mr create."""
    import subprocess

    from rouge.core.workflow.step_base import WorkflowContext
    from rouge.core.workflow.steps.create_gitlab_pull_request_step import CreateGitLabPullRequestStep

    mock_get_repo_path.return_value = "/path/to/repo"

    # Mock git push success, glab mr create timeout
    mock_push_result = Mock()
    mock_push_result.returncode = 0
    mock_push_result.stdout = ""
    mock_push_result.stderr = ""

    mock_subprocess.side_effect = [
        mock_push_result,
        subprocess.TimeoutExpired(cmd="glab", timeout=120),
    ]

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = WorkflowContext(issue_id=1, adw_id="adw123")
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This MR adds a new feature.",
        "commits": [],
    }

    step = CreateGitLabPullRequestStep()
    result = step.run(context)

    assert result.success is False
    mock_logger.exception.assert_called_with("glab mr create timed out after 120 seconds")
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "merge-request-failed"


@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.get_repo_path")
@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.logger")
@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.subprocess.run")
@patch.dict("os.environ", {"GITLAB_PAT": "test-token"})
def test_create_gitlab_mr_step_glab_not_found(
    mock_subprocess, mock_logger, mock_emit, mock_get_repo_path
):
    """Test MR creation handles glab CLI not found."""
    from rouge.core.workflow.step_base import WorkflowContext
    from rouge.core.workflow.steps.create_gitlab_pull_request_step import CreateGitLabPullRequestStep

    mock_get_repo_path.return_value = "/path/to/repo"

    # Mock git push success, glab not found
    mock_push_result = Mock()
    mock_push_result.returncode = 0
    mock_push_result.stdout = ""
    mock_push_result.stderr = ""

    mock_subprocess.side_effect = [mock_push_result, FileNotFoundError("glab not found")]

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = WorkflowContext(issue_id=1, adw_id="adw123")
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This MR adds a new feature.",
        "commits": [],
    }

    step = CreateGitLabPullRequestStep()
    result = step.run(context)

    assert result.success is False
    mock_logger.exception.assert_called_with("glab CLI not found, skipping MR creation")
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "merge-request-failed"


@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.get_repo_path")
@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.subprocess.run")
@patch.dict("os.environ", {"GITLAB_PAT": "test-token"})
def test_create_gitlab_mr_step_push_failure_continues_to_mr(
    mock_subprocess, mock_emit, mock_get_repo_path
):
    """Test MR creation continues even when git push fails."""
    from rouge.core.workflow.step_base import WorkflowContext
    from rouge.core.workflow.steps.create_gitlab_pull_request_step import CreateGitLabPullRequestStep

    mock_get_repo_path.return_value = "/path/to/repo"

    # Mock git push failure, glab mr create success
    mock_push_result = Mock()
    mock_push_result.returncode = 1
    mock_push_result.stdout = ""
    mock_push_result.stderr = "error: failed to push some refs"

    mock_mr_result = Mock()
    mock_mr_result.returncode = 0
    mock_mr_result.stdout = "https://gitlab.com/owner/repo/-/merge_requests/123\n"

    mock_subprocess.side_effect = [mock_push_result, mock_mr_result]

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = WorkflowContext(issue_id=1, adw_id="adw123")
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This MR adds a new feature.",
        "commits": [],
    }

    step = CreateGitLabPullRequestStep()
    result = step.run(context)

    # MR should succeed even if push failed (branch may already exist on remote)
    assert result.success is True
    assert mock_subprocess.call_count == 2
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "merge-request-created"


@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.get_repo_path")
@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.create_gitlab_pull_request_step.subprocess.run")
@patch.dict("os.environ", {"GITLAB_PAT": "test-token"})
def test_create_gitlab_mr_step_push_timeout_continues_to_mr(
    mock_subprocess, mock_emit, mock_get_repo_path
):
    """Test MR creation continues even when git push times out."""
    import subprocess

    from rouge.core.workflow.step_base import WorkflowContext
    from rouge.core.workflow.steps.create_gitlab_pull_request_step import CreateGitLabPullRequestStep

    mock_get_repo_path.return_value = "/path/to/repo"

    # Mock git push timeout, glab mr create success
    mock_mr_result = Mock()
    mock_mr_result.returncode = 0
    mock_mr_result.stdout = "https://gitlab.com/owner/repo/-/merge_requests/123\n"

    mock_subprocess.side_effect = [
        subprocess.TimeoutExpired(cmd="git", timeout=60),
        mock_mr_result,
    ]

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = WorkflowContext(issue_id=1, adw_id="adw123")
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This MR adds a new feature.",
        "commits": [],
    }

    step = CreateGitLabPullRequestStep()
    result = step.run(context)

    # MR should succeed even if push timed out
    assert result.success is True
    assert mock_subprocess.call_count == 2
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "merge-request-created"


def test_create_gitlab_mr_step_is_not_critical():
    """Test CreateGitLabPullRequestStep is not critical."""
    from rouge.core.workflow.steps.create_gitlab_pull_request_step import CreateGitLabPullRequestStep

    step = CreateGitLabPullRequestStep()
    assert step.is_critical is False


def test_create_gitlab_mr_step_name():
    """Test CreateGitLabPullRequestStep has correct name."""
    from rouge.core.workflow.steps.create_gitlab_pull_request_step import CreateGitLabPullRequestStep

    step = CreateGitLabPullRequestStep()
    assert step.name == "Creating GitLab merge request"


# === PreparePullRequestStep JSON parsing Tests ===


def test_prepare_pr_step_store_pr_details_success():
    """Test _store_pr_details stores validated dict correctly."""
    from rouge.core.workflow.step_base import WorkflowContext
    from rouge.core.workflow.steps.pr import PreparePullRequestStep

    context = WorkflowContext(issue_id=1, adw_id="adw123")
    step = PreparePullRequestStep()

    # Now _store_pr_details expects a dict (pre-validated), not a JSON string
    pr_data = {
        "title": "feat: add feature",
        "summary": "This adds a feature.",
        "commits": ["abc123", "def456"],
    }
    step._store_pr_details(pr_data, context)

    assert "pr_details" in context.data
    assert context.data["pr_details"]["title"] == "feat: add feature"
    assert context.data["pr_details"]["summary"] == "This adds a feature."
    assert context.data["pr_details"]["commits"] == ["abc123", "def456"]


def test_prepare_pr_step_store_pr_details_missing_fields():
    """Test _store_pr_details handles missing fields with defaults."""
    from rouge.core.workflow.step_base import WorkflowContext
    from rouge.core.workflow.steps.pr import PreparePullRequestStep

    context = WorkflowContext(issue_id=1, adw_id="adw123")
    step = PreparePullRequestStep()

    # Dict with only title - note this would normally fail JSON validation
    # but _store_pr_details is now called after validation, so this tests
    # that defaults are still applied for extra safety
    pr_data = {"title": "only title"}
    step._store_pr_details(pr_data, context)

    assert "pr_details" in context.data
    assert context.data["pr_details"]["title"] == "only title"
    assert context.data["pr_details"]["summary"] == ""
    assert context.data["pr_details"]["commits"] == []


@patch("rouge.core.workflow.steps.pr.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.pr.execute_template")
@patch("rouge.core.workflow.steps.pr.update_status")
def test_prepare_pr_step_emits_raw_llm_response(mock_update_status, mock_execute, mock_emit):
    """Test PreparePullRequestStep emits raw LLM response for debugging."""
    from rouge.core.workflow.step_base import WorkflowContext
    from rouge.core.workflow.steps.pr import PreparePullRequestStep

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    # Mock successful template execution with valid JSON
    pr_json = (
        '{"output": "pull_request", "title": "feat: test", '
        '"summary": "Test summary", "commits": ["abc123"]}'
    )
    mock_response = Mock()
    mock_response.success = True
    mock_response.output = pr_json
    mock_execute.return_value = mock_response

    context = WorkflowContext(issue_id=1, adw_id="adw123")
    step = PreparePullRequestStep()
    result = step.run(context)

    assert result.success is True
    request = mock_execute.call_args[0][0]
    assert request.json_schema is not None
    assert '"pull-request"' in request.json_schema

    # Verify emit_comment_from_payload was called with raw LLM response
    # It should be called at least twice - once for raw response, once for "PR prepared"
    assert mock_emit.call_count >= 2

    # Find the call with the raw LLM response
    llm_response_call = None
    for call in mock_emit.call_args_list:
        payload = call[0][0]  # Get the CommentPayload from positional args
        if payload.raw and payload.raw.get("output") == "pr-preparation-response":
            llm_response_call = call
            break

    assert (
        llm_response_call is not None
    ), "Expected emit_comment_from_payload call with pr-preparation-response"
    assert llm_response_call[0][0].raw["llm_response"] == pr_json


# Patch status transition tests removed - using update_issue_status instead
