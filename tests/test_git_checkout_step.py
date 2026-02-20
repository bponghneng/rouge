"""Tests for GitCheckoutStep git branch checkout."""

import subprocess
from unittest.mock import Mock, patch

import pytest

from rouge.core.models import Issue
from rouge.core.workflow.artifacts import ArtifactStore, FetchPatchArtifact, GitCheckoutArtifact
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.git_checkout_step import GIT_TIMEOUT, GitCheckoutStep
from rouge.core.workflow.types import StepResult


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
    return WorkflowContext(issue_id=1, adw_id="test123", artifact_store=store)


# === Basic Step Properties ===


def test_checkout_step_name():
    """GitCheckoutStep has the expected human-readable name."""
    step = GitCheckoutStep()
    assert step.name == "Checking out git branch"


def test_checkout_step_is_critical():
    """GitCheckoutStep is marked as critical."""
    step = GitCheckoutStep()
    assert step.is_critical is True


# === Guard Conditions — artifact-based ===


def test_checkout_step_fails_when_fetch_patch_artifact_missing(tmp_path):
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


def test_checkout_step_fails_when_branch_is_none(tmp_path):
    """Step returns StepResult.fail when fetch-patch artifact has branch=None."""
    store = ArtifactStore(workflow_id="test123", base_path=tmp_path)
    _write_fetch_patch_artifact(store, _make_issue(branch=None))
    ctx = WorkflowContext(issue_id=1, adw_id="test123", artifact_store=store)
    step = GitCheckoutStep()
    result = step.run(ctx)

    assert result.success is False
    assert "issue.branch is not set" in result.error


def test_checkout_step_fails_when_branch_is_empty_string(tmp_path):
    """Step returns StepResult.fail when fetch-patch artifact has branch=''."""
    store = ArtifactStore(workflow_id="test123", base_path=tmp_path)
    _write_fetch_patch_artifact(store, _make_issue(branch=""))
    ctx = WorkflowContext(issue_id=1, adw_id="test123", artifact_store=store)
    step = GitCheckoutStep()
    result = step.run(ctx)

    assert result.success is False
    assert "issue.branch is not set" in result.error


def test_checkout_step_loads_issue_from_fetch_patch_artifact(tmp_path):
    """Step loads the issue from the fetch-patch artifact, not from context.issue."""
    store = ArtifactStore(workflow_id="test123", base_path=tmp_path)
    _write_fetch_patch_artifact(store, _make_issue(branch="artifact-branch"))
    # context.issue intentionally left as None to prove it is not used
    ctx = WorkflowContext(issue_id=1, adw_id="test123", issue=None, artifact_store=store)

    with patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run") as mock_sub, \
         patch("rouge.core.workflow.steps.git_checkout_step.get_repo_path") as mock_repo, \
         patch("rouge.core.workflow.steps.git_checkout_step.emit_artifact_comment") as mock_emit, \
         patch("rouge.core.workflow.steps.git_checkout_step.log_artifact_comment_status"):
        mock_repo.return_value = "/repo"
        mock_emit.return_value = ("ok", "ok")
        mock_checkout = Mock(returncode=0, stdout="", stderr="")
        mock_pull = Mock(returncode=0, stdout="", stderr="")
        mock_sub.side_effect = [mock_checkout, mock_pull]

        step = GitCheckoutStep()
        result = step.run(ctx)

    assert result.success is True
    # Verify branch from artifact was used
    checkout_call = mock_sub.call_args_list[0]
    assert "artifact-branch" in checkout_call[0][0]


# === Happy Path ===


@patch("rouge.core.workflow.steps.git_checkout_step.emit_artifact_comment")
@patch("rouge.core.workflow.steps.git_checkout_step.log_artifact_comment_status")
@patch("rouge.core.workflow.steps.git_checkout_step.get_repo_path")
@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
def test_checkout_step_success(mock_subprocess, mock_get_repo_path, _mock_log_status, mock_emit_comment, context):
    """Happy path: both git commands succeed and GitCheckoutArtifact is written."""
    mock_get_repo_path.return_value = "/path/to/repo"

    mock_checkout = Mock()
    mock_checkout.returncode = 0
    mock_checkout.stdout = ""
    mock_checkout.stderr = ""

    mock_pull = Mock()
    mock_pull.returncode = 0
    mock_pull.stdout = ""
    mock_pull.stderr = ""

    mock_subprocess.side_effect = [mock_checkout, mock_pull]
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
    assert mock_subprocess.call_count == 2

    # Verify git checkout call
    checkout_call = mock_subprocess.call_args_list[0]
    assert checkout_call[0][0] == ["git", "checkout", "feature-branch"]
    assert checkout_call[1]["cwd"] == "/path/to/repo"
    assert checkout_call[1]["timeout"] == GIT_TIMEOUT
    assert checkout_call[1]["capture_output"] is True
    assert checkout_call[1]["text"] is True

    # Verify git pull --rebase call
    pull_call = mock_subprocess.call_args_list[1]
    assert pull_call[0][0] == ["git", "pull", "--rebase", "origin", "feature-branch"]
    assert pull_call[1]["cwd"] == "/path/to/repo"
    assert pull_call[1]["timeout"] == GIT_TIMEOUT

    # Verify artifact was written
    mock_store.write_artifact.assert_called_once()
    written_artifact = mock_store.write_artifact.call_args[0][0]
    assert isinstance(written_artifact, GitCheckoutArtifact)
    assert written_artifact.branch == "feature-branch"
    assert written_artifact.artifact_type == "git-checkout"



# === git checkout Failure ===


@patch("rouge.core.workflow.steps.git_checkout_step.get_repo_path")
@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
def test_checkout_step_git_checkout_fails(mock_subprocess, mock_get_repo_path, context):
    """Step fails and stops immediately when git checkout returns non-zero exit code."""
    mock_get_repo_path.return_value = "/path/to/repo"

    mock_checkout = Mock()
    mock_checkout.returncode = 1
    mock_checkout.stdout = ""
    mock_checkout.stderr = "error: pathspec 'feature-branch' did not match any file(s)"
    mock_subprocess.return_value = mock_checkout

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is False
    assert "git checkout feature-branch failed" in result.error
    assert "exit code 1" in result.error
    assert "pathspec 'feature-branch' did not match" in result.error
    # Should stop after first command fails
    assert mock_subprocess.call_count == 1


# === git pull --rebase Failure ===


@patch("rouge.core.workflow.steps.git_checkout_step.get_repo_path")
@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
def test_checkout_step_git_pull_fails(mock_subprocess, mock_get_repo_path, context):
    """Step fails when git pull --rebase returns non-zero exit code."""
    mock_get_repo_path.return_value = "/path/to/repo"

    mock_checkout = Mock()
    mock_checkout.returncode = 0
    mock_checkout.stdout = ""
    mock_checkout.stderr = ""

    mock_pull = Mock()
    mock_pull.returncode = 1
    mock_pull.stdout = ""
    mock_pull.stderr = "error: could not apply abc1234... commit message"

    mock_subprocess.side_effect = [mock_checkout, mock_pull]

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is False
    assert "git pull --rebase failed" in result.error
    assert "exit code 1" in result.error
    assert "could not apply" in result.error
    assert mock_subprocess.call_count == 2


# === Timeout Handling ===


@patch("rouge.core.workflow.steps.git_checkout_step.get_repo_path")
@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
def test_checkout_step_checkout_timeout(mock_subprocess, mock_get_repo_path, context):
    """Step handles TimeoutExpired from git checkout."""
    mock_get_repo_path.return_value = "/path/to/repo"

    mock_subprocess.side_effect = subprocess.TimeoutExpired(
        cmd=["git", "checkout", "feature-branch"], timeout=GIT_TIMEOUT
    )

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is False
    assert "timed out after" in result.error
    assert str(GIT_TIMEOUT) in result.error


@patch("rouge.core.workflow.steps.git_checkout_step.get_repo_path")
@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
def test_checkout_step_pull_timeout(mock_subprocess, mock_get_repo_path, context):
    """Step handles TimeoutExpired from git pull --rebase."""
    mock_get_repo_path.return_value = "/path/to/repo"

    mock_checkout = Mock()
    mock_checkout.returncode = 0
    mock_checkout.stdout = ""
    mock_checkout.stderr = ""

    mock_subprocess.side_effect = [
        mock_checkout,
        subprocess.TimeoutExpired(cmd=["git", "pull", "--rebase"], timeout=GIT_TIMEOUT),
    ]

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is False
    assert "timed out after" in result.error
    assert str(GIT_TIMEOUT) in result.error


# === Error Handling ===


@patch("rouge.core.workflow.steps.git_checkout_step.get_repo_path")
@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
def test_checkout_step_git_not_found(mock_subprocess, mock_get_repo_path, context):
    """Step handles git binary not found."""
    mock_get_repo_path.return_value = "/path/to/repo"

    mock_subprocess.side_effect = FileNotFoundError("git not found")

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is False
    assert "git command not found" in result.error
    assert "ensure git is installed" in result.error


@patch("rouge.core.workflow.steps.git_checkout_step.get_repo_path")
@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
def test_checkout_step_unexpected_error(mock_subprocess, mock_get_repo_path, context):
    """Step handles unexpected exceptions."""
    mock_get_repo_path.return_value = "/path/to/repo"

    mock_subprocess.side_effect = RuntimeError("Unexpected system error")

    step = GitCheckoutStep()
    result = step.run(context)

    assert result.success is False
    assert "Unexpected error during git checkout" in result.error
    assert "RuntimeError" in result.error
    assert "Unexpected system error" in result.error


# === StepResult Type Checks ===


@patch("rouge.core.workflow.steps.git_checkout_step.get_repo_path")
@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
def test_checkout_step_returns_step_result_ok(mock_subprocess, mock_get_repo_path, context):
    """Successful execution returns StepResult with success=True."""
    mock_get_repo_path.return_value = "/path/to/repo"

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


@patch("rouge.core.workflow.steps.git_checkout_step.get_repo_path")
@patch("rouge.core.workflow.steps.git_checkout_step.subprocess.run")
def test_checkout_step_returns_step_result_fail(mock_subprocess, mock_get_repo_path, context):
    """Failed execution returns StepResult with success=False and non-empty error."""
    mock_get_repo_path.return_value = "/path/to/repo"

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
