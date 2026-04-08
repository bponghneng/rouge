"""Tests for GitCheckoutStep git branch checkout."""

import subprocess
from typing import Generator
from unittest.mock import Mock, patch

import pytest

from rouge.core.models import Issue
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.git_checkout_step import GIT_TIMEOUT, GitCheckoutStep
from rouge.core.workflow.types import StepResult

@pytest.fixture(autouse=True, scope="module")
def patch_external_helpers() -> Generator[None, None, None]:
    """Patch external helper functions to avoid side effects during tests."""
    yield

def _make_issue(branch: str | None = "feature-branch") -> Issue:
    """Create a minimal Issue for testing."""
    return Issue(id=1, title="Test issue", description="A test issue", branch=branch)

def _removed_write_artifact() -> None:
    """Placeholder - artifact writes removed in Phase 3."""
    pass

@pytest.fixture
def issue() -> Issue:
    """Return a sample issue with a branch set."""
    return _make_issue(branch="feature-branch")

@pytest.fixture
def context(issue: Issue) -> WorkflowContext:
    """Create a sample workflow context with issue set."""
    ctx = WorkflowContext(
        issue_id=1, adw_id="test123",
        repo_paths=["/path/to/repo"],
    )
    ctx.issue = issue
    return ctx

# === Basic Step Properties ===

def test_checkout_step_name() -> None:
    """GitCheckoutStep has the expected human-readable name."""
    step = GitCheckoutStep()
    assert step.name == "Checking out git branch"

def test_checkout_step_is_critical() -> None:
    """GitCheckoutStep is marked as critical."""
    step = GitCheckoutStep()
    assert step.is_critical is True

# === Guard Conditions — artifact-based ===

def test_checkout_step_fails_when_fetch_patch_artifact_missing(tmp_path) -> None:
    """Step returns StepResult.fail when fetch-patch artifact is absent."""
    # Do NOT write fetch-patch artifact
    ctx = WorkflowContext(issue_id=1, adw_id="test123",
)
    step = GitCheckoutStep()
    result = step.run(ctx)

    assert result.success is False
    assert result.error is not None
    # StepInputError message mentions the artifact type
    assert "fetch-patch" in result.error

def test_checkout_step_fails_when_branch_is_none(tmp_path) -> None:
    """Step returns StepResult.fail when fetch-patch artifact has branch=None."""
    _write_fetch_patch_artifact(_make_issue(branch=None))
    ctx = WorkflowContext(issue_id=1, adw_id="test123",
)
    step = GitCheckoutStep()
    result = step.run(ctx)

    assert result.success is False
    assert "issue.branch is not set" in result.error

def test_checkout_step_fails_when_branch_is_empty_string(tmp_path) -> None:
    """Step returns StepResult.fail when fetch-patch artifact has branch=''."""
    _write_fetch_patch_artifact(_make_issue(branch=""))
    ctx = WorkflowContext(issue_id=1, adw_id="test123",
)
    step = GitCheckoutStep()
    result = step.run(ctx)

    assert result.success is False
    assert "issue.branch is not set" in result.error

@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "false"}, clear=False)
def test_checkout_step_loads_issue_from_fetch_patch_artifact(tmp_path) -> None:
    """Step loads the issue from the fetch-patch artifact, not from context.issue."""
    _write_fetch_patch_artifact(_make_issue(branch="artifact-branch"))
    # context.issue intentionally left as None to prove it is not used
    ctx = WorkflowContext(
        issue_id=1, adw_id="test123", issue=None,
 repo_paths=["/path/to/repo"]
    )

    with (
        patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run") as mock_sub,
    ):
        mock_checkout = Mock(returncode=0, stdout="", stderr="")
        mock_fetch = Mock(returncode=0, stdout="", stderr="")
        mock_pull = Mock(returncode=0, stdout="", stderr="")
        mock_sub.side_effect = [mock_fetch, mock_checkout, mock_pull]

        step = GitCheckoutStep()
        result = step.run(ctx)

    assert result.success is True
    # Verify branch from artifact was used
    checkout_call = mock_sub.call_args_list[1]
    assert "artifact-branch" in checkout_call[0][0]

# === context.issue path (source-agnostic) ===

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "false"}, clear=False)
def test_checkout_step_uses_context_issue_when_no_artifact(mock_subprocess, tmp_path) -> None:
    """Step uses context.issue directly when no FetchPatchArtifact is present.

    Verifies that when context.issue is set the step proceeds to checkout
    without requiring a FetchPatchArtifact on disk, and that the branch
    from context.issue is passed to git checkout.
    """
    mock_fetch = Mock(returncode=0, stdout="", stderr="")
    mock_checkout = Mock(returncode=0, stdout="", stderr="")
    mock_pull = Mock(returncode=0, stdout="", stderr="")
    mock_subprocess.side_effect = [mock_fetch, mock_checkout, mock_pull]

    # Provide context.issue with a branch but NO FetchPatchArtifact in the store.
    issue = _make_issue(branch="context-issue-branch")
    # Intentionally do NOT write a FetchPatchArtifact to the store.
    ctx = WorkflowContext(
        issue_id=1, adw_id="test-ctx", issue=issue,
 repo_paths=["/repo"]
    )

    step = GitCheckoutStep()
    result = step.run(ctx)

    assert result.success is True

    # Verify that the branch from context.issue was used for git checkout.
    checkout_call = mock_subprocess.call_args_list[1]
    assert checkout_call[0][0] == ["git", "checkout", "context-issue-branch"]

# === Happy Path ===

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "false"}, clear=False)
def test_checkout_step_success(
    mock_subprocess, context
) -> None:
    """Happy path: all git commands succeed and GitCheckoutArtifact is written."""

    mock_checkout = Mock()
    mock_checkout.returncode = 0
    mock_checkout.stdout = ""
    mock_checkout.stderr = ""

    mock_fetch = Mock()
    mock_fetch.returncode = 0
    mock_fetch.stdout = ""
    mock_fetch.stderr = ""

    mock_pull = Mock()
    mock_pull.returncode = 0
    mock_pull.stdout = ""
    mock_pull.stderr = ""

    mock_subprocess.side_effect = [mock_fetch, mock_checkout, mock_pull]

    # Provide an artifact store so the artifact write path is exercised
    mock_store = Mock(spec=ArtifactStore)
    # The context fixture has already written the fetch-patch artifact to the real store;
    # replace with mock so we can assert write_artifact call, but first seed the context
    # data cache so load_required_artifact doesn't need the mock store to read
    context.data["fetch_patch_data"] = _make_issue(branch="feature-branch")

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is True
    assert result.error is None
    assert mock_subprocess.call_count == 3

    # Verify git fetch --all --prune call
    fetch_call = mock_subprocess.call_args_list[0]
    assert fetch_call[0][0] == ["git", "fetch", "--all", "--prune"]
    assert fetch_call[1]["cwd"] == "/path/to/repo"
    assert fetch_call[1]["timeout"] == GIT_TIMEOUT

    # Verify git checkout call
    checkout_call = mock_subprocess.call_args_list[1]
    assert checkout_call[0][0] == ["git", "checkout", "feature-branch"]
    assert checkout_call[1]["cwd"] == "/path/to/repo"
    assert checkout_call[1]["timeout"] == GIT_TIMEOUT
    assert checkout_call[1]["capture_output"] is True
    assert checkout_call[1]["text"] is True

    # Verify git pull --rebase call
    pull_call = mock_subprocess.call_args_list[2]
    assert pull_call[0][0] == ["git", "pull", "--rebase", "origin", "feature-branch"]
    assert pull_call[1]["cwd"] == "/path/to/repo"
    assert pull_call[1]["timeout"] == GIT_TIMEOUT

    pass  # artifact write assertions removed in Phase 3

# === git checkout Failure ===

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "false"}, clear=False)
def test_checkout_step_git_checkout_fails(mock_subprocess, context) -> None:
    """Step fails and stops immediately when git checkout returns non-zero exit code."""

    mock_checkout = Mock()
    mock_checkout.returncode = 1
    mock_checkout.stdout = ""
    mock_checkout.stderr = "error: permission denied"
    mock_fetch = Mock(returncode=0, stdout="", stderr="")
    mock_subprocess.side_effect = [mock_fetch, mock_checkout]

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is False
    assert "Failed to checkout branch" in result.error
    # Should stop after checkout fails (no fallback for non-pathspec errors)
    assert mock_subprocess.call_count == 2

# === Dirty State Cleanup Tests ===

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
def test_checkout_step_dirty_state_cleanup_allowed(mock_subprocess, context) -> None:
    """When ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS=true, dirty state is cleaned before checkout."""

    # Mock successful reset, clean, fetch, checkout, and pull
    mock_reset = Mock(returncode=0, stdout="", stderr="")
    mock_clean = Mock(returncode=0, stdout="", stderr="")
    mock_fetch = Mock(returncode=0, stdout="", stderr="")
    mock_checkout = Mock(returncode=0, stdout="", stderr="")
    mock_pull = Mock(returncode=0, stdout="", stderr="")

    mock_subprocess.side_effect = [mock_reset, mock_clean, mock_fetch, mock_checkout, mock_pull]

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is True
    assert mock_subprocess.call_count == 5

    # Verify git reset --hard was called first
    reset_call = mock_subprocess.call_args_list[0]
    assert reset_call[0][0] == ["git", "reset", "--hard"]
    assert reset_call[1]["cwd"] == "/path/to/repo"
    assert reset_call[1]["timeout"] == GIT_TIMEOUT

    # Verify git clean -fd was called second
    clean_call = mock_subprocess.call_args_list[1]
    assert clean_call[0][0] == ["git", "clean", "-fd"]
    assert clean_call[1]["cwd"] == "/path/to/repo"
    assert clean_call[1]["timeout"] == GIT_TIMEOUT

    # Verify fetch was called third
    fetch_call = mock_subprocess.call_args_list[2]
    assert fetch_call[0][0] == ["git", "fetch", "--all", "--prune"]

    # Verify checkout was called fourth
    checkout_call = mock_subprocess.call_args_list[3]
    assert checkout_call[0][0] == ["git", "checkout", "feature-branch"]

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "false"})
def test_checkout_step_dirty_state_denial(mock_subprocess, context) -> None:
    """When destructive ops not allowed and dirty state detected, step fails with standard error."""

    # Simulate checkout failure due to dirty working tree (after a successful fetch)
    mock_fetch = Mock(returncode=0, stdout="", stderr="")
    mock_checkout = Mock()
    mock_checkout.returncode = 1
    mock_checkout.stdout = ""
    mock_checkout.stderr = (
        "error: Your local changes to the following files would be overwritten by checkout"
    )

    mock_subprocess.side_effect = [mock_fetch, mock_checkout]

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is False
    assert "Cannot checkout branch: working tree has uncommitted changes" in result.error
    assert "ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS=true" in result.error
    # Should fetch then attempt checkout once (no reset/clean since not allowed)
    assert mock_subprocess.call_count == 2

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
def test_checkout_step_dirty_state_uncommitted_changes(mock_subprocess, context) -> None:
    """Dirty state with 'uncommitted changes' error is handled when destructive ops allowed."""

    mock_reset = Mock(returncode=0, stdout="", stderr="")
    mock_clean = Mock(returncode=0, stdout="", stderr="")
    mock_checkout = Mock(returncode=0, stdout="", stderr="")
    mock_fetch = Mock(returncode=0, stdout="", stderr="")
    mock_pull = Mock(returncode=0, stdout="", stderr="")

    mock_subprocess.side_effect = [mock_reset, mock_clean, mock_fetch, mock_checkout, mock_pull]

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is True
    # Verify cleanup happened before checkout
    assert mock_subprocess.call_args_list[0][0][0] == ["git", "reset", "--hard"]
    assert mock_subprocess.call_args_list[1][0][0] == ["git", "clean", "-fd"]

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
def test_checkout_step_reset_hard_fails(mock_subprocess, context) -> None:
    """When git reset --hard fails, step fails immediately."""

    mock_reset = Mock()
    mock_reset.returncode = 128
    mock_reset.stdout = ""
    mock_reset.stderr = "fatal: not a git repository"

    mock_subprocess.return_value = mock_reset

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is False
    assert "git reset --hard failed" in result.error
    assert "exit code 128" in result.error
    assert mock_subprocess.call_count == 1

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
def test_checkout_step_clean_fd_fails(mock_subprocess, context) -> None:
    """When git clean -fd fails, step fails immediately."""

    mock_reset = Mock(returncode=0, stdout="", stderr="")
    mock_clean = Mock()
    mock_clean.returncode = 1
    mock_clean.stdout = ""
    mock_clean.stderr = "error: cannot clean files"

    mock_subprocess.side_effect = [mock_reset, mock_clean]

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is False
    assert "git clean -fd failed" in result.error
    assert "exit code 1" in result.error
    assert mock_subprocess.call_count == 2

# === Missing Local Branch Fallback Tests ===

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "false"}, clear=False)
def test_checkout_step_missing_local_branch_fallback_success(mock_subprocess, context) -> None:
    """When local branch missing, fallback to git checkout -t origin/<branch> succeeds."""

    # First checkout fails with pathspec error
    mock_checkout_fail = Mock()
    mock_checkout_fail.returncode = 1
    mock_checkout_fail.stdout = ""
    mock_checkout_fail.stderr = (
        "error: pathspec 'feature-branch' did not match any file(s) known to git"
    )

    # Fallback checkout succeeds
    mock_checkout_fallback = Mock(returncode=0, stdout="", stderr="")
    mock_fetch = Mock(returncode=0, stdout="", stderr="")
    mock_pull = Mock(returncode=0, stdout="", stderr="")

    mock_subprocess.side_effect = [
        mock_fetch,
        mock_checkout_fail,
        mock_checkout_fallback,
        mock_pull,
    ]

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is True
    assert mock_subprocess.call_count == 4

    # Verify fetch runs before checkout attempts
    fetch_call = mock_subprocess.call_args_list[0]
    assert fetch_call[0][0] == ["git", "fetch", "--all", "--prune"]

    # Verify first checkout attempt
    first_checkout = mock_subprocess.call_args_list[1]
    assert first_checkout[0][0] == ["git", "checkout", "feature-branch"]

    # Verify fallback checkout with tracking
    fallback_checkout = mock_subprocess.call_args_list[2]
    assert fallback_checkout[0][0] == ["git", "checkout", "-t", "origin/feature-branch"]
    assert fallback_checkout[1]["cwd"] == "/path/to/repo"
    assert fallback_checkout[1]["timeout"] == GIT_TIMEOUT

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "false"}, clear=False)
def test_checkout_step_missing_local_branch_fallback_fails(mock_subprocess, context) -> None:
    """When local branch missing and remote fallback fails, return standard error message."""

    # First checkout fails with pathspec error
    mock_checkout_fail = Mock()
    mock_checkout_fail.returncode = 1
    mock_checkout_fail.stdout = ""
    mock_checkout_fail.stderr = (
        "error: pathspec 'feature-branch' did not match any file(s) known to git"
    )

    # Fallback also fails
    mock_fallback_fail = Mock()
    mock_fallback_fail.returncode = 1
    mock_fallback_fail.stdout = ""
    mock_fallback_fail.stderr = "fatal: 'origin/feature-branch' is not a commit"

    mock_fetch = Mock(returncode=0, stdout="", stderr="")
    mock_subprocess.side_effect = [mock_fetch, mock_checkout_fail, mock_fallback_fail]

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is False
    assert "Branch 'feature-branch' not found locally or on remote." in result.error
    assert mock_subprocess.call_count == 3

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "false"}, clear=False)
def test_checkout_step_missing_local_branch_no_fallback_for_other_errors(
    mock_subprocess, context
) -> None:
    """When checkout fails with non-pathspec error, no fallback is attempted."""

    # Checkout fails with permission denied (not pathspec error)
    mock_checkout = Mock()
    mock_checkout.returncode = 1
    mock_checkout.stdout = ""
    mock_checkout.stderr = "error: permission denied"

    mock_fetch = Mock(returncode=0, stdout="", stderr="")
    mock_subprocess.side_effect = [mock_fetch, mock_checkout]

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is False
    assert "Failed to checkout branch" in result.error
    # Should fetch then call checkout once (no fallback for non-pathspec errors)
    assert mock_subprocess.call_count == 2

# === Fetch All Prune Tests ===

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "false"}, clear=False)
def test_checkout_step_fetch_all_prune_called(mock_subprocess, context) -> None:
    """git fetch --all --prune is called before checkout and before pull."""

    mock_checkout = Mock(returncode=0, stdout="", stderr="")
    mock_fetch = Mock(returncode=0, stdout="", stderr="")
    mock_pull = Mock(returncode=0, stdout="", stderr="")

    mock_subprocess.side_effect = [mock_fetch, mock_checkout, mock_pull]

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is True
    assert mock_subprocess.call_count == 3

    # Verify fetch was called before checkout and before pull
    fetch_call = mock_subprocess.call_args_list[0]
    assert fetch_call[0][0] == ["git", "fetch", "--all", "--prune"]
    assert fetch_call[1]["cwd"] == "/path/to/repo"
    assert fetch_call[1]["timeout"] == GIT_TIMEOUT

    checkout_call = mock_subprocess.call_args_list[1]
    assert checkout_call[0][0] == ["git", "checkout", "feature-branch"]

    pull_call = mock_subprocess.call_args_list[2]
    assert pull_call[0][0] == ["git", "pull", "--rebase", "origin", "feature-branch"]

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "false"}, clear=False)
def test_checkout_step_fetch_all_prune_fails(mock_subprocess, context) -> None:
    """When git fetch --all --prune fails, step fails immediately."""

    mock_fetch = Mock()
    mock_fetch.returncode = 1
    mock_fetch.stdout = ""
    mock_fetch.stderr = "error: unable to access remote"

    mock_subprocess.side_effect = [mock_fetch]

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is False
    assert "git fetch --all --prune failed" in result.error
    assert "exit code 1" in result.error
    # Should stop immediately when fetch fails (no checkout/pull attempt)
    assert mock_subprocess.call_count == 1

# === Standardized Error Messages Tests ===

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "false"}, clear=False)
def test_checkout_step_standardized_error_missing_branch(mock_subprocess, context) -> None:
    """Missing branch error returns standardized message."""

    # Both local and remote checkout fail
    mock_checkout_fail = Mock()
    mock_checkout_fail.returncode = 1
    mock_checkout_fail.stdout = ""
    mock_checkout_fail.stderr = "error: pathspec 'feature-branch' did not match any file(s)"

    mock_fallback_fail = Mock()
    mock_fallback_fail.returncode = 1
    mock_fallback_fail.stdout = ""
    mock_fallback_fail.stderr = "error: remote branch not found"

    mock_fetch = Mock(returncode=0, stdout="", stderr="")
    mock_subprocess.side_effect = [mock_fetch, mock_checkout_fail, mock_fallback_fail]

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is False
    assert result.error == "Branch 'feature-branch' not found locally or on remote."

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "false"})
def test_checkout_step_standardized_error_dirty_tree(mock_subprocess, context) -> None:
    """Dirty tree error returns standardized message."""

    mock_checkout = Mock()
    mock_checkout.returncode = 1
    mock_checkout.stdout = ""
    mock_checkout.stderr = "error: Your local changes would be overwritten by checkout"

    mock_fetch = Mock(returncode=0, stdout="", stderr="")
    mock_subprocess.side_effect = [mock_fetch, mock_checkout]

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is False
    expected_error = (
        "Cannot checkout branch: working tree has uncommitted changes. "
        "Set ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS=true to allow cleanup."
    )
    assert result.error == expected_error

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "false"}, clear=False)
def test_checkout_step_standardized_error_pull_rebase_conflict(mock_subprocess, context) -> None:
    """Pull-rebase conflict error returns standardized message."""

    mock_fetch = Mock(returncode=0, stdout="", stderr="")
    mock_checkout = Mock(returncode=0, stdout="", stderr="")
    mock_pull = Mock()
    mock_pull.returncode = 1
    mock_pull.stdout = ""
    mock_pull.stderr = "error: could not apply commit... CONFLICT (content): merge conflict"

    mock_subprocess.side_effect = [mock_fetch, mock_checkout, mock_pull]

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is False
    assert result.error == "Pull-rebase failed with conflicts."

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
def test_checkout_step_standardized_error_timeout(mock_subprocess, context) -> None:
    """Timeout error returns standardized message."""

    mock_subprocess.side_effect = subprocess.TimeoutExpired(
        cmd=["git", "checkout", "feature-branch"], timeout=GIT_TIMEOUT
    )

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is False
    assert result.error == f"Git operation timed out after {GIT_TIMEOUT} seconds."

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
def test_checkout_step_standardized_error_git_not_found(mock_subprocess, context) -> None:
    """Git not found error returns standardized message."""

    mock_subprocess.side_effect = FileNotFoundError("git not found")

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is False
    assert result.error == "git command not found - ensure git is installed and in PATH"

# === git pull --rebase Failure ===

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "false"}, clear=False)
def test_checkout_step_git_pull_fails(mock_subprocess, context) -> None:
    """Step fails when git pull --rebase returns non-zero exit code."""

    mock_checkout = Mock()
    mock_checkout.returncode = 0
    mock_checkout.stdout = ""
    mock_checkout.stderr = ""

    mock_fetch = Mock()
    mock_fetch.returncode = 0
    mock_fetch.stdout = ""
    mock_fetch.stderr = ""

    mock_pull = Mock()
    mock_pull.returncode = 1
    mock_pull.stdout = ""
    mock_pull.stderr = "error: could not apply abc1234... commit message"

    mock_subprocess.side_effect = [mock_fetch, mock_checkout, mock_pull]

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is False
    assert "git pull --rebase failed" in result.error
    assert mock_subprocess.call_count == 3

# === Timeout Handling ===

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
def test_checkout_step_checkout_timeout(mock_subprocess, context) -> None:
    """Step handles TimeoutExpired from git checkout."""

    mock_subprocess.side_effect = subprocess.TimeoutExpired(
        cmd=["git", "checkout", "feature-branch"], timeout=GIT_TIMEOUT
    )

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is False
    assert "timed out after" in result.error
    assert str(GIT_TIMEOUT) in result.error

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
def test_checkout_step_pull_timeout(mock_subprocess, context) -> None:
    """Step handles TimeoutExpired from git pull --rebase."""

    mock_checkout = Mock()
    mock_checkout.returncode = 0
    mock_checkout.stdout = ""
    mock_checkout.stderr = ""

    mock_fetch = Mock()
    mock_fetch.returncode = 0
    mock_fetch.stdout = ""
    mock_fetch.stderr = ""

    mock_subprocess.side_effect = [
        mock_checkout,
        mock_fetch,
        subprocess.TimeoutExpired(cmd=["git", "pull", "--rebase"], timeout=GIT_TIMEOUT),
    ]

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is False
    assert "timed out after" in result.error
    assert str(GIT_TIMEOUT) in result.error

# === Error Handling ===

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
def test_checkout_step_git_not_found(mock_subprocess, context) -> None:
    """Step handles git binary not found."""

    mock_subprocess.side_effect = FileNotFoundError("git not found")

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is False
    assert "git command not found" in result.error
    assert "ensure git is installed" in result.error

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
def test_checkout_step_unexpected_error(mock_subprocess, context) -> None:
    """Step handles unexpected exceptions."""

    mock_subprocess.side_effect = RuntimeError("Unexpected system error")

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is False
    assert "Unexpected error during git checkout" in result.error
    assert "RuntimeError" in result.error
    assert "Unexpected system error" in result.error

# === StepResult Type Checks ===

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "false"}, clear=False)
def test_checkout_step_returns_step_result_ok(mock_subprocess, context) -> None:
    """Successful execution returns StepResult with success=True."""

    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    mock_subprocess.return_value = mock_result

    step = GitCheckoutStep()
    result = step.run(context)

    assert isinstance(result, StepResult)
    assert result.success is True
    assert result.data is None
    assert result.error is None

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "false"}, clear=False)
def test_checkout_step_returns_step_result_fail(mock_subprocess, context) -> None:
    """Failed execution returns StepResult with success=False and non-empty error."""

    mock_result = Mock()
    mock_result.returncode = 128
    mock_result.stdout = ""
    mock_result.stderr = "fatal: not a git repository"
    mock_subprocess.return_value = mock_result

    step = GitCheckoutStep()
    result = step.run(context)

    assert isinstance(result, StepResult)
    assert result.success is False
    assert result.data is None
    assert result.error is not None
    assert len(result.error) > 0

# === Multiple Repository Tests ===

@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "false"}, clear=False)
def test_git_checkout_multiple_repos(mock_subprocess, tmp_path) -> None:
    """Step runs fetch+checkout+pull for each repo when multiple repo_paths are provided."""
    _write_fetch_patch_artifact(_make_issue(branch="feature-branch"))
    ctx = WorkflowContext(
        issue_id=1,
        adw_id="test123",
        repo_paths=["/repo/a", "/repo/b"],
    )

    # 3 calls per repo (fetch, checkout, pull) x 2 repos = 6 total
    mock_success = Mock(returncode=0, stdout="", stderr="")
    mock_subprocess.side_effect = [
        mock_success,  # /repo/a: fetch
        mock_success,  # /repo/a: checkout
        mock_success,  # /repo/a: pull
        mock_success,  # /repo/b: fetch
        mock_success,  # /repo/b: checkout
        mock_success,  # /repo/b: pull
    ]

    step = GitCheckoutStep()
    result = step.run(ctx)

    assert result.success is True
    assert mock_subprocess.call_count == 6

    # Verify /repo/a appears as cwd in its three calls
    assert mock_subprocess.call_args_list[0][1]["cwd"] == "/repo/a"
    assert mock_subprocess.call_args_list[1][1]["cwd"] == "/repo/a"
    assert mock_subprocess.call_args_list[2][1]["cwd"] == "/repo/a"

    # Verify /repo/b appears as cwd in its three calls
    assert mock_subprocess.call_args_list[3][1]["cwd"] == "/repo/b"
    assert mock_subprocess.call_args_list[4][1]["cwd"] == "/repo/b"
    assert mock_subprocess.call_args_list[5][1]["cwd"] == "/repo/b"
