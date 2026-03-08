"""Tests for GitBranchStep git environment setup."""

import subprocess
from typing import Generator
from unittest.mock import Mock, patch

import pytest

from rouge.core.models import Issue
from rouge.core.workflow.artifacts import ArtifactStore
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.git_branch_step import GIT_TIMEOUT, GitBranchStep
from rouge.core.workflow.types import StepResult


@pytest.fixture(autouse=True, scope="module")
def patch_external_helpers() -> Generator[None, None, None]:
    """Patch external helper functions to avoid side effects during tests.

    This fixture patches emit_artifact_comment and log_artifact_comment_status
    across all tests in this module to prevent actual comment emission.
    """
    with (
        patch("rouge.core.workflow.steps.git_branch_step.emit_artifact_comment") as mock_emit,
        patch("rouge.core.workflow.steps.git_branch_step.log_artifact_comment_status"),
    ):
        # Configure emit_artifact_comment to return success by default
        mock_emit.return_value = ("success", "ok")
        yield


@pytest.fixture
def context(tmp_path) -> WorkflowContext:
    """Create a sample workflow context for testing."""
    store = ArtifactStore(workflow_id="test123", base_path=tmp_path)
    return WorkflowContext(
        issue_id=1, adw_id="test123", artifact_store=store, repo_paths=["/path/to/repo"]
    )


# === Basic Step Properties Tests ===


def test_branch_step_name() -> None:
    """Test GitBranchStep has correct name."""
    step = GitBranchStep()
    assert step.name == "Setting up git environment"


def test_branch_step_is_critical() -> None:
    """Test GitBranchStep is marked as critical."""
    step = GitBranchStep()
    assert step.is_critical is True


# === Successful Execution Tests ===


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.log_artifact_comment_status")
@patch("rouge.core.workflow.steps.git_branch_step.emit_artifact_comment")
@patch("rouge.core.workflow.steps.git_branch_step.update_issue")
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_branch_step_success(
    mock_subprocess,
    _mock_update_branch,
    mock_emit_artifact_comment,
    mock_log_artifact_comment_status,
    context,
) -> None:
    """Test successful git setup with all commands succeeding."""

    # Mock all git commands succeeding
    mock_success = Mock()
    mock_success.returncode = 0
    mock_success.stdout = ""
    mock_success.stderr = ""

    # Mock show-ref returning non-zero (branch doesn't exist)
    mock_show_ref_fail = Mock()
    mock_show_ref_fail.returncode = 1
    mock_show_ref_fail.stdout = ""
    mock_show_ref_fail.stderr = ""

    mock_subprocess.side_effect = [
        mock_success,  # checkout
        mock_success,  # fetch
        mock_success,  # reset
        mock_show_ref_fail,  # show-ref (branch doesn't exist)
        mock_success,  # checkout -b
    ]
    mock_emit_artifact_comment.return_value = ("success", "ok")

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is True
    assert result.error is None
    assert mock_subprocess.call_count == 5

    # Verify git checkout main was called first
    checkout_call = mock_subprocess.call_args_list[0]
    assert checkout_call[0][0] == ["git", "checkout", "main"]
    assert checkout_call[1]["cwd"] == "/path/to/repo"
    assert checkout_call[1]["timeout"] == GIT_TIMEOUT

    # Verify git fetch was called second
    fetch_call = mock_subprocess.call_args_list[1]
    assert fetch_call[0][0] == ["git", "fetch", "--all", "--prune"]
    assert fetch_call[1]["cwd"] == "/path/to/repo"
    assert fetch_call[1]["timeout"] == GIT_TIMEOUT

    # Verify git reset was called third
    reset_call = mock_subprocess.call_args_list[2]
    assert reset_call[0][0] == ["git", "reset", "--hard", "origin/main"]
    assert reset_call[1]["cwd"] == "/path/to/repo"
    assert reset_call[1]["timeout"] == GIT_TIMEOUT

    # Verify git show-ref was called fourth
    show_ref_call = mock_subprocess.call_args_list[3]
    assert show_ref_call[0][0] == [
        "git",
        "show-ref",
        "--verify",
        "--quiet",
        "refs/heads/adw-test123",
    ]

    # Verify git checkout -b was called fifth (fallback branch name)
    branch_call = mock_subprocess.call_args_list[4]
    assert branch_call[0][0] == ["git", "checkout", "-b", "adw-test123"]
    assert branch_call[1]["cwd"] == "/path/to/repo"
    assert branch_call[1]["timeout"] == GIT_TIMEOUT


@patch.dict(
    "os.environ", {"DEFAULT_GIT_BRANCH": "develop", "ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"}
)
@patch("rouge.core.workflow.steps.git_branch_step.update_issue")
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_branch_step_custom_default_branch(mock_subprocess, _mock_update_branch, context) -> None:
    """Test setup uses custom DEFAULT_GIT_BRANCH from environment."""

    # Mock all git commands succeeding
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    mock_subprocess.return_value = mock_result

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is True

    # Verify custom branch was used in checkout
    checkout_call = mock_subprocess.call_args_list[0]
    assert checkout_call[0][0] == ["git", "checkout", "develop"]

    # Verify custom branch was used in reset
    reset_call = mock_subprocess.call_args_list[2]
    assert reset_call[0][0] == ["git", "reset", "--hard", "origin/develop"]


@patch("rouge.core.workflow.steps.git_branch_step.update_issue")
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_branch_step_default_branch_fallback(
    mock_subprocess, _mock_update_branch, context, monkeypatch
) -> None:
    """Test setup defaults to 'main' when DEFAULT_GIT_BRANCH is not set."""
    monkeypatch.delenv("DEFAULT_GIT_BRANCH", raising=False)
    monkeypatch.setenv("ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS", "true")

    # Mock all git commands succeeding
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    mock_subprocess.return_value = mock_result

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is True

    # Verify default 'main' branch was used
    checkout_call = mock_subprocess.call_args_list[0]
    assert checkout_call[0][0] == ["git", "checkout", "main"]

    reset_call = mock_subprocess.call_args_list[2]
    assert reset_call[0][0] == ["git", "reset", "--hard", "origin/main"]


# === Safety Check Tests ===


def test_branch_step_destructive_ops_not_allowed_by_default(context, monkeypatch) -> None:
    """Test setup fails when ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS is not set."""
    monkeypatch.delenv("ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS", raising=False)
    step = GitBranchStep()
    result = step.run(context)

    assert result.success is False
    assert "Destructive git operations not allowed" in result.error
    assert "ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS=true" in result.error


def test_branch_step_destructive_ops_explicitly_disabled(context, monkeypatch) -> None:
    """Test setup fails when ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS is explicitly set to false."""
    monkeypatch.setenv("ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS", "false")
    step = GitBranchStep()
    result = step.run(context)

    assert result.success is False
    assert "Destructive git operations not allowed" in result.error


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "True"})
@patch("rouge.core.workflow.steps.git_branch_step.update_issue")
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_branch_step_destructive_ops_case_insensitive(
    mock_subprocess, _mock_update_branch, context
) -> None:
    """Test setup accepts 'True' (capital T) for ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS."""

    # Mock all git commands succeeding
    mock_success = Mock()
    mock_success.returncode = 0
    mock_success.stdout = ""
    mock_success.stderr = ""

    # Mock show-ref returning non-zero (branch doesn't exist)
    mock_show_ref_fail = Mock()
    mock_show_ref_fail.returncode = 1
    mock_show_ref_fail.stdout = ""
    mock_show_ref_fail.stderr = ""

    mock_subprocess.side_effect = [
        mock_success,  # checkout
        mock_success,  # fetch
        mock_success,  # reset
        mock_show_ref_fail,  # show-ref
        mock_success,  # checkout -b
    ]

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is True
    assert mock_subprocess.call_count == 5


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "TRUE"})
@patch("rouge.core.workflow.steps.git_branch_step.update_issue")
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_branch_step_destructive_ops_uppercase(
    mock_subprocess, _mock_update_branch, context
) -> None:
    """Test setup accepts 'TRUE' (all caps) for ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS."""

    # Mock all git commands succeeding
    mock_success = Mock()
    mock_success.returncode = 0
    mock_success.stdout = ""
    mock_success.stderr = ""

    # Mock show-ref returning non-zero (branch doesn't exist)
    mock_show_ref_fail = Mock()
    mock_show_ref_fail.returncode = 1
    mock_show_ref_fail.stdout = ""
    mock_show_ref_fail.stderr = ""

    mock_subprocess.side_effect = [
        mock_success,  # checkout
        mock_success,  # fetch
        mock_success,  # reset
        mock_show_ref_fail,  # show-ref
        mock_success,  # checkout -b
    ]

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is True
    assert mock_subprocess.call_count == 5


# === Failure Handling Tests ===


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_branch_step_checkout_failure(mock_subprocess, context) -> None:
    """Test setup handles git checkout failure (non-pathspec error)."""

    # Mock checkout failure with a non-pathspec error
    mock_checkout_result = Mock()
    mock_checkout_result.returncode = 1
    mock_checkout_result.stdout = ""
    mock_checkout_result.stderr = "fatal: unable to read tree"
    mock_subprocess.return_value = mock_checkout_result

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is False
    assert "Failed to checkout default branch 'main'" in result.error
    assert mock_subprocess.call_count == 1  # Should stop after checkout fails


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_branch_step_reset_failure(mock_subprocess, context) -> None:
    """Test setup handles git reset failure."""

    # Mock checkout success, fetch success, reset failure
    mock_success = Mock()
    mock_success.returncode = 0
    mock_success.stdout = ""
    mock_success.stderr = ""

    mock_reset_result = Mock()
    mock_reset_result.returncode = 1
    mock_reset_result.stdout = ""
    mock_reset_result.stderr = "fatal: ambiguous argument 'origin/main'"

    mock_subprocess.side_effect = [mock_success, mock_success, mock_reset_result]

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is False
    assert "git reset --hard failed" in result.error
    assert mock_subprocess.call_count == 3  # Should stop after reset fails


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_branch_step_branch_creation_failure(mock_subprocess, context) -> None:
    """Test setup handles git checkout -b failure."""

    # Mock checkout, fetch, and reset success
    mock_success = Mock()
    mock_success.returncode = 0
    mock_success.stdout = ""
    mock_success.stderr = ""

    # Mock show-ref returning non-zero (branch doesn't exist)
    mock_show_ref_fail = Mock()
    mock_show_ref_fail.returncode = 1
    mock_show_ref_fail.stdout = ""
    mock_show_ref_fail.stderr = ""

    # Mock branch creation failure
    mock_branch_result = Mock()
    mock_branch_result.returncode = 128
    mock_branch_result.stdout = ""
    mock_branch_result.stderr = "fatal: not a valid object name: 'main'"

    mock_subprocess.side_effect = [
        mock_success,  # checkout
        mock_success,  # fetch
        mock_success,  # reset
        mock_show_ref_fail,  # show-ref (branch doesn't exist)
        mock_branch_result,  # checkout -b fails
    ]

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is False
    assert "Failed to create branch 'adw-test123'" in result.error
    assert mock_subprocess.call_count == 5


# === Timeout Handling Tests ===


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_branch_step_checkout_timeout(mock_subprocess, context) -> None:
    """Test setup handles timeout on git checkout."""

    mock_subprocess.side_effect = subprocess.TimeoutExpired(
        cmd=["git", "checkout", "main"], timeout=GIT_TIMEOUT
    )

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is False
    assert "timed out after" in result.error
    assert str(GIT_TIMEOUT) in result.error


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_branch_step_reset_timeout(mock_subprocess, context) -> None:
    """Test setup handles timeout on git reset."""

    # Mock checkout success, fetch success, reset timeout
    mock_checkout_result = Mock()
    mock_checkout_result.returncode = 0
    mock_checkout_result.stdout = ""
    mock_checkout_result.stderr = ""

    mock_fetch_result = Mock()
    mock_fetch_result.returncode = 0
    mock_fetch_result.stdout = ""
    mock_fetch_result.stderr = ""

    mock_subprocess.side_effect = [
        mock_checkout_result,
        mock_fetch_result,
        subprocess.TimeoutExpired(
            cmd=["git", "reset", "--hard", "origin/main"], timeout=GIT_TIMEOUT
        ),
    ]

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is False
    assert "timed out after" in result.error


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_branch_step_branch_creation_timeout(mock_subprocess, context) -> None:
    """Test setup handles timeout on git checkout -b."""

    # Mock checkout, fetch, and reset success, branch creation timeout
    mock_checkout_result = Mock()
    mock_checkout_result.returncode = 0
    mock_checkout_result.stdout = ""
    mock_checkout_result.stderr = ""

    mock_fetch_result = Mock()
    mock_fetch_result.returncode = 0
    mock_fetch_result.stdout = ""
    mock_fetch_result.stderr = ""

    mock_reset_result = Mock()
    mock_reset_result.returncode = 0
    mock_reset_result.stdout = ""
    mock_reset_result.stderr = ""

    mock_show_ref_result = Mock()
    mock_show_ref_result.returncode = 0
    mock_show_ref_result.stdout = ""
    mock_show_ref_result.stderr = ""

    mock_delete_result = Mock()
    mock_delete_result.returncode = 0
    mock_delete_result.stdout = ""
    mock_delete_result.stderr = ""

    mock_subprocess.side_effect = [
        mock_checkout_result,
        mock_fetch_result,
        mock_reset_result,
        mock_show_ref_result,
        mock_delete_result,
        subprocess.TimeoutExpired(
            cmd=["git", "checkout", "-b", "adw-test123"], timeout=GIT_TIMEOUT
        ),
    ]

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is False
    assert "timed out after" in result.error


# === Error Handling Tests ===


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_branch_step_git_not_found(mock_subprocess, context) -> None:
    """Test setup handles git command not found."""

    mock_subprocess.side_effect = FileNotFoundError("git not found")

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is False
    assert "git command not found" in result.error
    assert "ensure git is installed" in result.error


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_branch_step_unexpected_error(mock_subprocess, context) -> None:
    """Test setup handles unexpected exceptions."""

    mock_subprocess.side_effect = RuntimeError("Unexpected system error")

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is False
    assert "Unexpected error during git setup" in result.error
    assert "RuntimeError" in result.error
    assert "Unexpected system error" in result.error


# === Branch Name Logic Tests ===


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.update_issue")
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_branch_step_uses_issue_branch_when_set(
    mock_subprocess, mock_update_issue, tmp_path
) -> None:
    """Test that branch name comes from context.issue.branch when set."""

    mock_success = Mock()
    mock_success.returncode = 0
    mock_success.stdout = ""
    mock_success.stderr = ""

    # Mock show-ref returning non-zero (branch doesn't exist)
    mock_show_ref_fail = Mock()
    mock_show_ref_fail.returncode = 1
    mock_show_ref_fail.stdout = ""
    mock_show_ref_fail.stderr = ""

    mock_subprocess.side_effect = [
        mock_success,  # checkout
        mock_success,  # fetch
        mock_success,  # reset
        mock_show_ref_fail,  # show-ref
        mock_success,  # checkout -b
    ]

    issue = Issue(id=1, title="Test issue", description="A test issue", branch="my-feature")
    store = ArtifactStore(workflow_id="abc123", base_path=tmp_path)
    ctx = WorkflowContext(issue_id=1, adw_id="abc123", issue=issue, artifact_store=store)

    step = GitBranchStep()
    result = step.run(ctx)

    assert result.success is True

    branch_call = mock_subprocess.call_args_list[4]
    assert branch_call[0][0] == ["git", "checkout", "-b", "my-feature"]

    mock_update_issue.assert_called_once_with(1, branch="my-feature")


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.update_issue")
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_branch_step_falls_back_to_adw_id_when_issue_branch_is_none(
    mock_subprocess, mock_update_issue, tmp_path
) -> None:
    """Test that branch name falls back to adw-<id> when context.issue.branch is None."""

    mock_success = Mock()
    mock_success.returncode = 0
    mock_success.stdout = ""
    mock_success.stderr = ""

    # Mock show-ref returning non-zero (branch doesn't exist)
    mock_show_ref_fail = Mock()
    mock_show_ref_fail.returncode = 1
    mock_show_ref_fail.stdout = ""
    mock_show_ref_fail.stderr = ""

    mock_subprocess.side_effect = [
        mock_success,  # checkout
        mock_success,  # fetch
        mock_success,  # reset
        mock_show_ref_fail,  # show-ref
        mock_success,  # checkout -b
    ]

    issue = Issue(id=1, title="Test issue", description="A test issue", branch=None)
    store = ArtifactStore(workflow_id="xyz789", base_path=tmp_path)
    ctx = WorkflowContext(issue_id=1, adw_id="xyz789", issue=issue, artifact_store=store)

    step = GitBranchStep()
    result = step.run(ctx)

    assert result.success is True

    branch_call = mock_subprocess.call_args_list[4]
    assert branch_call[0][0] == ["git", "checkout", "-b", "adw-xyz789"]

    mock_update_issue.assert_called_once_with(1, branch="adw-xyz789")


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.update_issue")
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_branch_step_branch_name_format(mock_subprocess, _mock_update_branch, tmp_path) -> None:
    """Test that branch name is correctly formatted from adw_id when no issue branch."""

    # Mock all git commands succeeding
    mock_success = Mock()
    mock_success.returncode = 0
    mock_success.stdout = ""
    mock_success.stderr = ""

    # Mock show-ref returning non-zero (branch doesn't exist)
    mock_show_ref_fail = Mock()
    mock_show_ref_fail.returncode = 1
    mock_show_ref_fail.stdout = ""
    mock_show_ref_fail.stderr = ""

    # Test with various adw_id values (no issue set, so falls back to adw-<id>)
    test_cases = [
        ("abc123", "adw-abc123"),
        ("workflow-456", "adw-workflow-456"),
        ("12345", "adw-12345"),
    ]

    for adw_id, expected_branch in test_cases:
        mock_subprocess.reset_mock()
        mock_subprocess.side_effect = [
            mock_success,  # checkout
            mock_success,  # fetch
            mock_success,  # reset
            mock_show_ref_fail,  # show-ref
            mock_success,  # checkout -b
        ]
        store = ArtifactStore(workflow_id=adw_id, base_path=tmp_path / adw_id)
        context = WorkflowContext(issue_id=1, adw_id=adw_id, artifact_store=store)

        step = GitBranchStep()
        result = step.run(context)

        assert result.success is True
        branch_call = mock_subprocess.call_args_list[4]
        assert branch_call[0][0] == ["git", "checkout", "-b", expected_branch]


# === Subprocess Options Tests ===


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.update_issue")
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_branch_step_subprocess_options(mock_subprocess, _mock_update_branch, context) -> None:
    """Test that subprocess.run is called with correct options."""

    # Mock all git commands succeeding
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    mock_subprocess.return_value = mock_result

    step = GitBranchStep()
    step.run(context)

    # All calls should have these common options
    for call in mock_subprocess.call_args_list:
        kwargs = call[1]
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["timeout"] == GIT_TIMEOUT
        assert kwargs["cwd"] == "/path/to/repo"


# === Integration with StepResult Tests ===


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.update_issue")
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_branch_step_returns_step_result_ok(mock_subprocess, _mock_update_branch, context) -> None:
    """Test successful execution returns StepResult.ok()."""

    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    mock_subprocess.return_value = mock_result

    step = GitBranchStep()
    result = step.run(context)

    assert isinstance(result, StepResult)
    assert result.success is True
    assert result.data is None
    assert result.error is None


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_branch_step_returns_step_result_fail(mock_subprocess, context) -> None:
    """Test failed execution returns StepResult.fail()."""

    mock_result = Mock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "error message"
    mock_subprocess.return_value = mock_result

    step = GitBranchStep()
    result = step.run(context)

    assert isinstance(result, StepResult)
    assert result.success is False
    assert result.data is None
    assert result.error is not None
    assert len(result.error) > 0


# === New Feature Tests (Steps 6-9) ===


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.update_issue")
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_fetch_all_prune_command(mock_subprocess, _mock_update_issue, context) -> None:
    """Test that git fetch --all --prune is called instead of git fetch origin."""

    # Mock all git commands succeeding
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    mock_subprocess.return_value = mock_result

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is True

    # Verify git fetch --all --prune was called (second command)
    fetch_call = mock_subprocess.call_args_list[1]
    assert fetch_call[0][0] == ["git", "fetch", "--all", "--prune"]
    assert fetch_call[1]["cwd"] == "/path/to/repo"
    assert fetch_call[1]["timeout"] == GIT_TIMEOUT


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.update_issue")
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_missing_default_branch_fallback(mock_subprocess, _mock_update_issue, context) -> None:
    """Test fallback to git checkout -t origin/<default> when local branch is missing."""

    # Mock checkout failure with "pathspec did not match" error
    mock_checkout_fail = Mock()
    mock_checkout_fail.returncode = 1
    mock_checkout_fail.stdout = ""
    mock_checkout_fail.stderr = "error: pathspec 'main' did not match any file(s) known to git"

    # Mock successful fallback checkout
    mock_checkout_fallback = Mock()
    mock_checkout_fallback.returncode = 0
    mock_checkout_fallback.stdout = ""
    mock_checkout_fallback.stderr = ""

    # Mock remaining git commands succeeding
    mock_success = Mock()
    mock_success.returncode = 0
    mock_success.stdout = ""
    mock_success.stderr = ""

    # Mock show-ref returning non-zero (branch doesn't exist)
    mock_show_ref_fail = Mock()
    mock_show_ref_fail.returncode = 1
    mock_show_ref_fail.stdout = ""
    mock_show_ref_fail.stderr = ""

    mock_subprocess.side_effect = [
        mock_checkout_fail,  # First checkout fails
        mock_checkout_fallback,  # Fallback checkout succeeds
        mock_success,  # fetch
        mock_success,  # reset
        mock_show_ref_fail,  # show-ref (branch doesn't exist)
        mock_success,  # checkout -b
    ]

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is True

    # Verify fallback command was called
    fallback_call = mock_subprocess.call_args_list[1]
    assert fallback_call[0][0] == ["git", "checkout", "-t", "origin/main"]
    assert fallback_call[1]["cwd"] == "/path/to/repo"
    assert fallback_call[1]["timeout"] == GIT_TIMEOUT


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_missing_default_branch_fallback_also_fails(mock_subprocess, context) -> None:
    """Test failure when both local and remote default branch checkouts fail."""

    # Mock both checkout attempts failing
    mock_checkout_fail = Mock()
    mock_checkout_fail.returncode = 1
    mock_checkout_fail.stdout = ""
    mock_checkout_fail.stderr = "error: pathspec 'main' did not match any file(s) known to git"

    mock_checkout_fallback_fail = Mock()
    mock_checkout_fallback_fail.returncode = 1
    mock_checkout_fallback_fail.stdout = ""
    mock_checkout_fallback_fail.stderr = "fatal: 'origin/main' is not a commit"

    mock_subprocess.side_effect = [
        mock_checkout_fail,  # First checkout fails
        mock_checkout_fallback_fail,  # Fallback also fails
    ]

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is False
    assert "Default branch 'main' not found locally or on remote" in result.error


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.update_issue")
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_existing_workflow_branch_deletion(mock_subprocess, _mock_update_issue, context) -> None:
    """Test that existing workflow branch is deleted before recreation."""

    # Mock all git commands succeeding
    mock_success = Mock()
    mock_success.returncode = 0
    mock_success.stdout = ""
    mock_success.stderr = ""

    mock_subprocess.return_value = mock_success

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is True

    # Verify git show-ref was called to check for existing branch
    show_ref_call = mock_subprocess.call_args_list[3]
    assert show_ref_call[0][0] == [
        "git",
        "show-ref",
        "--verify",
        "--quiet",
        "refs/heads/adw-test123",
    ]

    # Verify git branch -D was called to delete existing branch
    delete_call = mock_subprocess.call_args_list[4]
    assert delete_call[0][0] == ["git", "branch", "-D", "adw-test123"]
    assert delete_call[1]["cwd"] == "/path/to/repo"
    assert delete_call[1]["timeout"] == GIT_TIMEOUT

    # Verify git checkout -b was called to create new branch
    create_call = mock_subprocess.call_args_list[5]
    assert create_call[0][0] == ["git", "checkout", "-b", "adw-test123"]


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.update_issue")
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_no_reuse_guarantee(mock_subprocess, _mock_update_issue, context) -> None:
    """Test that when workflow branch exists, it is deleted and recreated (not reused)."""

    # Mock all git commands succeeding, including show-ref returning 0 (branch exists)
    mock_success = Mock()
    mock_success.returncode = 0
    mock_success.stdout = ""
    mock_success.stderr = ""

    mock_subprocess.return_value = mock_success

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is True

    # Verify deletion was called before creation
    call_list = [call[0][0] for call in mock_subprocess.call_args_list]

    # Find the indices of relevant commands
    show_ref_idx = None
    delete_idx = None
    create_idx = None

    for i, cmd in enumerate(call_list):
        if cmd[0] == "git" and "show-ref" in cmd:
            show_ref_idx = i
        elif cmd[0] == "git" and "branch" in cmd and "-D" in cmd:
            delete_idx = i
        elif cmd[0] == "git" and "checkout" in cmd and "-b" in cmd:
            create_idx = i

    # Verify the sequence: show-ref -> delete -> create
    assert show_ref_idx is not None, "show-ref command not found"
    assert delete_idx is not None, "branch -D command not found"
    assert create_idx is not None, "checkout -b command not found"
    assert show_ref_idx < delete_idx < create_idx, "Commands not in correct order"


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_branch_deletion_failure(mock_subprocess, context) -> None:
    """Test error handling when branch deletion fails."""

    # Mock success for initial commands
    mock_success = Mock()
    mock_success.returncode = 0
    mock_success.stdout = ""
    mock_success.stderr = ""

    # Mock failure for branch deletion
    mock_delete_fail = Mock()
    mock_delete_fail.returncode = 1
    mock_delete_fail.stdout = ""
    mock_delete_fail.stderr = (
        "error: Cannot delete branch 'adw-test123' checked out at '/path/to/repo'"
    )

    mock_subprocess.side_effect = [
        mock_success,  # checkout
        mock_success,  # fetch
        mock_success,  # reset
        mock_success,  # show-ref (branch exists)
        mock_delete_fail,  # branch -D fails
    ]

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is False
    assert "Failed to delete existing branch 'adw-test123'" in result.error


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_standardized_error_message_missing_default_branch(mock_subprocess, context) -> None:
    """Test standardized error message for missing default branch."""

    # Mock both checkout attempts failing
    mock_fail = Mock()
    mock_fail.returncode = 1
    mock_fail.stdout = ""
    mock_fail.stderr = "error: pathspec 'main' did not match any file(s)"

    mock_subprocess.side_effect = [mock_fail, mock_fail]

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is False
    # Check for standardized error message format
    assert "Default branch 'main' not found locally or on remote" in result.error


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_standardized_error_message_checkout_failed(mock_subprocess, context) -> None:
    """Test standardized error message for checkout failure (non-pathspec error)."""

    mock_fail = Mock()
    mock_fail.returncode = 1
    mock_fail.stdout = ""
    mock_fail.stderr = "fatal: unable to read tree"

    mock_subprocess.return_value = mock_fail

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is False
    assert "Failed to checkout default branch 'main'" in result.error


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_standardized_error_message_fetch_failed(mock_subprocess, context) -> None:
    """Test standardized error message for fetch failure."""

    mock_success = Mock()
    mock_success.returncode = 0
    mock_success.stdout = ""
    mock_success.stderr = ""

    mock_fetch_fail = Mock()
    mock_fetch_fail.returncode = 1
    mock_fetch_fail.stdout = ""
    mock_fetch_fail.stderr = "fatal: unable to access 'https://github.com/repo.git/'"

    mock_subprocess.side_effect = [mock_success, mock_fetch_fail]

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is False
    assert "git fetch --all --prune failed" in result.error


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_standardized_error_message_reset_failed(mock_subprocess, context) -> None:
    """Test standardized error message for reset failure."""

    mock_success = Mock()
    mock_success.returncode = 0
    mock_success.stdout = ""
    mock_success.stderr = ""

    mock_reset_fail = Mock()
    mock_reset_fail.returncode = 1
    mock_reset_fail.stdout = ""
    mock_reset_fail.stderr = "fatal: Failed to resolve 'origin/main'"

    mock_subprocess.side_effect = [mock_success, mock_success, mock_reset_fail]

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is False
    assert "git reset --hard failed" in result.error


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_standardized_error_message_create_branch_failed(mock_subprocess, context) -> None:
    """Test standardized error message for branch creation failure."""

    mock_success = Mock()
    mock_success.returncode = 0
    mock_success.stdout = ""
    mock_success.stderr = ""

    # Mock show-ref returning non-zero (branch doesn't exist)
    mock_show_ref_fail = Mock()
    mock_show_ref_fail.returncode = 1
    mock_show_ref_fail.stdout = ""
    mock_show_ref_fail.stderr = ""

    mock_create_fail = Mock()
    mock_create_fail.returncode = 128
    mock_create_fail.stdout = ""
    mock_create_fail.stderr = "fatal: not a valid object name: 'main'"

    mock_subprocess.side_effect = [
        mock_success,  # checkout
        mock_success,  # fetch
        mock_success,  # reset
        mock_show_ref_fail,  # show-ref (branch doesn't exist)
        mock_create_fail,  # checkout -b fails
    ]

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is False
    assert "Failed to create branch 'adw-test123'" in result.error


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_standardized_error_message_timeout(mock_subprocess, context) -> None:
    """Test standardized error message for timeout."""

    mock_subprocess.side_effect = subprocess.TimeoutExpired(
        cmd=["git", "checkout", "main"], timeout=GIT_TIMEOUT
    )

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is False
    assert "Git operation timed out after 60 seconds" in result.error


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.git_branch_step.subprocess.run")
def test_standardized_error_message_delete_branch_failed(mock_subprocess, context) -> None:
    """Test standardized error message for branch deletion failure."""

    mock_success = Mock()
    mock_success.returncode = 0
    mock_success.stdout = ""
    mock_success.stderr = ""

    mock_delete_fail = Mock()
    mock_delete_fail.returncode = 1
    mock_delete_fail.stdout = ""
    mock_delete_fail.stderr = "error: Cannot delete branch"

    mock_subprocess.side_effect = [
        mock_success,  # checkout
        mock_success,  # fetch
        mock_success,  # reset
        mock_success,  # show-ref (branch exists)
        mock_delete_fail,  # branch -D fails
    ]

    step = GitBranchStep()
    result = step.run(context)

    assert result.success is False
    assert "Failed to delete existing branch 'adw-test123'" in result.error
