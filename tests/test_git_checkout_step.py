"""Tests for GitCheckoutStep git branch checkout."""

import subprocess
from typing import Generator
from unittest.mock import Mock, patch

import pytest

from rouge.core.models import Issue
from rouge.core.workflow.artifacts import ArtifactStore, FetchPatchArtifact, GitCheckoutArtifact
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.git_checkout_step import GIT_TIMEOUT, GitCheckoutStep
from rouge.core.workflow.types import StepResult


@pytest.fixture(autouse=True, scope="module")
def patch_external_helpers() -> Generator[None, None, None]:
    """Patch external helper functions to avoid side effects during tests.

    This fixture patches emit_artifact_comment and log_artifact_comment_status
    across all tests in this module to prevent actual comment emission.
    """
    with (
        patch("rouge.core.workflow.steps.git_checkout_step.emit_artifact_comment") as mock_emit,
        patch("rouge.core.workflow.steps.git_checkout_step.log_artifact_comment_status"),
    ):
        # Configure emit_artifact_comment to return success by default
        mock_emit.return_value = ("success", "ok")
        yield


def _make_issue(branch: str | None = "feature-branch") -> Issue:
    """Create a minimal Issue for testing."""
    return Issue(id=1, title="Test issue", description="A test issue", branch=branch)


def _write_fetch_patch_artifact(store: ArtifactStore, issue: Issue) -> None:
    """Write a FetchPatchArtifact to the store for a given issue."""
    artifact = FetchPatchArtifact(
        workflow_id=store.workflow_id,
        patch=issue,
    )
    store.write_artifact(artifact)


@pytest.fixture
def issue() -> Issue:
    """Return a sample issue with a branch set."""
    return _make_issue(branch="feature-branch")


@pytest.fixture
def store(tmp_path) -> ArtifactStore:
    """Create a temporary artifact store."""
    return ArtifactStore(workflow_id="test123", base_path=tmp_path)


@pytest.fixture
def context(issue: Issue, store: ArtifactStore) -> WorkflowContext:
    """Create a sample workflow context with fetch-patch artifact written."""
    _write_fetch_patch_artifact(store, issue)
    return WorkflowContext(issue_id=1, adw_id="test123", artifact_store=store, repo_paths=["/path/to/repo"])


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
    store = ArtifactStore(workflow_id="test123", base_path=tmp_path)
    # Do NOT write fetch-patch artifact
    ctx = WorkflowContext(issue_id=1, adw_id="test123", artifact_store=store)
    step = GitCheckoutStep()
    result = step.run(ctx)

    assert result.success is False
    assert result.error is not None
    # StepInputError message mentions the artifact type
    assert "fetch-patch" in result.error


def test_checkout_step_fails_when_branch_is_none(tmp_path) -> None:
    """Step returns StepResult.fail when fetch-patch artifact has branch=None."""
    store = ArtifactStore(workflow_id="test123", base_path=tmp_path)
    _write_fetch_patch_artifact(store, _make_issue(branch=None))
    ctx = WorkflowContext(issue_id=1, adw_id="test123", artifact_store=store)
    step = GitCheckoutStep()
    result = step.run(ctx)

    assert result.success is False
    assert "issue.branch is not set" in result.error


def test_checkout_step_fails_when_branch_is_empty_string(tmp_path) -> None:
    """Step returns StepResult.fail when fetch-patch artifact has branch=''."""
    store = ArtifactStore(workflow_id="test123", base_path=tmp_path)
    _write_fetch_patch_artifact(store, _make_issue(branch=""))
    ctx = WorkflowContext(issue_id=1, adw_id="test123", artifact_store=store)
    step = GitCheckoutStep()
    result = step.run(ctx)

    assert result.success is False
    assert "issue.branch is not set" in result.error


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "false"}, clear=False)
def test_checkout_step_loads_issue_from_fetch_patch_artifact(tmp_path) -> None:
    """Step loads the issue from the fetch-patch artifact, not from context.issue."""
    store = ArtifactStore(workflow_id="test123", base_path=tmp_path)
    _write_fetch_patch_artifact(store, _make_issue(branch="artifact-branch"))
    # context.issue intentionally left as None to prove it is not used
    ctx = WorkflowContext(issue_id=1, adw_id="test123", issue=None, artifact_store=store, repo_paths=["/path/to/repo"])

    with (
        patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run") as mock_sub,
        patch("rouge.core.workflow.steps.git_checkout_step.emit_artifact_comment") as mock_emit,
        patch("rouge.core.workflow.steps.git_checkout_step.log_artifact_comment_status"),
    ):
        mock_emit.return_value = ("ok", "ok")
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


# === Happy Path ===


@patch("rouge.core.workflow.steps.git_checkout_step.emit_artifact_comment")
@patch("rouge.core.workflow.steps.git_checkout_step.log_artifact_comment_status")
@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "false"}, clear=False)
def test_checkout_step_success(
    mock_subprocess, _mock_log_status, mock_emit_comment, context
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
    mock_emit_comment.return_value = ("ok", "comment posted")

    # Provide an artifact store so the artifact write path is exercised
    mock_store = Mock(spec=ArtifactStore)
    # The context fixture has already written the fetch-patch artifact to the real store;
    # replace with mock so we can assert write_artifact call, but first seed the context
    # data cache so load_required_artifact doesn't need the mock store to read
    context.data["fetch_patch_data"] = _make_issue(branch="feature-branch")
    context.artifact_store = mock_store

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

    # Verify artifact was written
    mock_store.write_artifact.assert_called_once()
    written_artifact = mock_store.write_artifact.call_args[0][0]
    assert isinstance(written_artifact, GitCheckoutArtifact)
    assert written_artifact.branch == "feature-branch"
    assert written_artifact.artifact_type == "git-checkout"


@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "false"}, clear=False)
def test_checkout_step_success_no_artifact_store(
    mock_subprocess, context
) -> None:
    """Happy path without an artifact store: no artifact write is attempted."""

    mock_checkout = Mock(returncode=0, stdout="", stderr="")
    mock_fetch = Mock(returncode=0, stdout="", stderr="")
    mock_pull = Mock(returncode=0, stdout="", stderr="")
    mock_subprocess.side_effect = [mock_fetch, mock_checkout, mock_pull]

    # No artifact_store set on context; use cached fetch-patch data
    context.data["fetch_patch_data"] = _make_issue(branch="feature-branch")
    context.artifact_store = None
    assert context.artifact_store is None

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is True
    assert mock_subprocess.call_count == 3  # fetch, checkout, pull


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
def test_checkout_step_dirty_state_cleanup_allowed(
    mock_subprocess, context
) -> None:
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
def test_checkout_step_dirty_state_uncommitted_changes(
    mock_subprocess, context
) -> None:
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
def test_checkout_step_missing_local_branch_fallback_success(
    mock_subprocess, context
) -> None:
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
def test_checkout_step_missing_local_branch_fallback_fails(
    mock_subprocess, context
) -> None:
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
def test_checkout_step_standardized_error_missing_branch(
    mock_subprocess, context
) -> None:
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
def test_checkout_step_standardized_error_dirty_tree(
    mock_subprocess, context
) -> None:
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
def test_checkout_step_standardized_error_pull_rebase_conflict(
    mock_subprocess, context
) -> None:
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
def test_checkout_step_standardized_error_timeout(
    mock_subprocess, context
) -> None:
    """Timeout error returns standardized message."""

    mock_subprocess.side_effect = subprocess.TimeoutExpired(
        cmd=["git", "checkout", "feature-branch"], timeout=GIT_TIMEOUT
    )

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is False
    assert result.error == f"Git operation timed out after {GIT_TIMEOUT} seconds."


@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
def test_checkout_step_standardized_error_git_not_found(
    mock_subprocess, context
) -> None:
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

    mock_subprocess.side_effect = [mock_checkout, mock_fetch, mock_pull]

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
def test_checkout_step_returns_step_result_fail(
    mock_subprocess, context
) -> None:
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
