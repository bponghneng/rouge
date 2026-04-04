"""Tests for workflow orchestration."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from rouge.core.models import CommentPayload, Issue
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.workflow import execute_workflow, update_status
from rouge.core.workflow.artifacts import ArtifactStore, ImplementArtifact
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.types import ImplementData, StepResult


def _make_context(adw_id: str = "adw123", issue_id: int = 1, **kwargs) -> WorkflowContext:
    """Create a WorkflowContext with a temporary artifact store for testing."""
    tmp_dir = tempfile.TemporaryDirectory()
    store = ArtifactStore(workflow_id=adw_id, base_path=Path(tmp_dir.name))
    kwargs.setdefault("repo_paths", ["/path/to/repo"])
    context = WorkflowContext(issue_id=issue_id, adw_id=adw_id, artifact_store=store, **kwargs)
    context._tmp_dir = tmp_dir  # type: ignore[attr-defined]  # keeps dir alive until context is GC'd
    return context


def _write_implement_artifact(
    context: WorkflowContext, repo_paths: list[str] | None = None
) -> None:
    """Write an implement artifact so PR steps iterate the given repos."""
    affected = repo_paths if repo_paths is not None else context.repo_paths
    artifact = ImplementArtifact(
        workflow_id=context.adw_id,
        implement_data=ImplementData(output="done", affected_repos=affected),
    )
    context.artifact_store.write_artifact(artifact)


@pytest.fixture
def sample_issue() -> Issue:
    """Create a sample issue for testing."""
    return Issue(id=1, description="Fix login bug", status="pending")


@patch("rouge.core.workflow.status.update_issue")
def test_update_status_success(mock_update_issue) -> None:
    """Test successful status update."""
    mock_issue = Mock()
    mock_issue.id = 1
    mock_update_issue.return_value = mock_issue

    update_status(1, "started", adw_id="test-adw-id")
    mock_update_issue.assert_called_once_with(1, status="started")


@patch("rouge.core.workflow.status.update_issue")
def test_update_status_failure(mock_update_issue) -> None:
    """Test status update handles errors gracefully."""
    mock_update_issue.side_effect = ValueError("Database error")

    # Should not raise - best-effort
    update_status(1, "started", adw_id="test-adw-id")


@patch("rouge.core.notifications.comments.create_comment")
def test_emit_comment_from_payload_success(mock_create_comment) -> None:
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
def test_emit_comment_from_payload_failure(mock_create_comment) -> None:
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


# REMOVED: Legacy top-level classify_issue and build_plan functions were
# refactored into step classes and subsequently removed entirely.


# REMOVED: Tests for implement_plan function (moved to step class in
# rouge.core.workflow.steps.implement)
# This test tested a top-level function that no longer exists after refactoring.
# The business logic is now in ImplementStep.run() method.
# To test implementation logic, test ImplementStep directly instead.


@patch("rouge.core.workflow.runner.get_full_pipeline")
def test_execute_workflow_success(mock_get_pipeline) -> None:
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


@patch("rouge.core.workflow.runner.get_full_pipeline")
def test_execute_workflow_fetch_failure(mock_get_pipeline) -> None:
    """Test workflow handles fetch failure (first step fails)."""
    # Create a mock first step that fails
    mock_fetch_step = Mock()
    mock_fetch_step.name = "Fetch Issue"
    mock_fetch_step.is_critical = True
    mock_fetch_step.run.return_value = StepResult.fail("Fetch failed")

    mock_get_pipeline.return_value = [mock_fetch_step]

    result = execute_workflow(999, "adw123")
    assert result is False


@patch("rouge.core.workflow.runner.get_full_pipeline")
def test_execute_workflow_second_step_failure(mock_get_pipeline) -> None:
    """Test workflow handles second step failure."""
    # Create mock steps where first succeeds, second fails
    mock_fetch_step = Mock()
    mock_fetch_step.name = "Fetch Issue"
    mock_fetch_step.is_critical = True
    mock_fetch_step.run.return_value = StepResult.ok(None)

    mock_second_step = Mock()
    mock_second_step.name = "Plan Issue"
    mock_second_step.is_critical = True
    mock_second_step.run.return_value = StepResult.fail("Planning failed")

    mock_get_pipeline.return_value = [mock_fetch_step, mock_second_step]

    result = execute_workflow(1, "adw123")
    assert result is False


@patch("rouge.core.workflow.steps.code_quality_step.get_affected_repos")
@patch("rouge.core.workflow.step_utils.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.code_quality_step.execute_template")
def test_code_quality_step_passes_json_schema(mock_execute, mock_emit, mock_get_affected) -> None:
    """Test code quality step passes strict JSON schema to Claude template request."""

    from rouge.core.workflow.steps.code_quality_step import CodeQualityStep
    from rouge.core.workflow.types import ImplementData

    mock_emit.return_value = ("success", "ok")
    mock_response = Mock()
    mock_response.success = True
    mock_response.output = '{"issues":[],"output":"code-quality","tools":["ruff"]}'
    mock_execute.return_value = mock_response

    context = _make_context()
    mock_get_affected.return_value = (context.repo_paths, ImplementData(output="done"))
    step = CodeQualityStep()
    result = step.run(context)

    assert result.success is True
    request = mock_execute.call_args[0][0]
    assert request.json_schema is not None
    assert '"const": "code-quality"' in request.json_schema


# === GhPullRequestStep Tests ===


@patch("rouge.core.workflow.steps.gh_pull_request_step.shutil.which")
@patch("rouge.core.workflow.steps.gh_pull_request_step.subprocess.run")
@patch("rouge.core.workflow.step_utils.emit_comment_from_payload")
@patch.dict("os.environ", {"GITHUB_PAT": "test-token"})
def test_create_pr_step_success(mock_emit, mock_subprocess, mock_which) -> None:
    """Test successful PR creation: rev-parse, pr list (empty), push, pr create."""

    from rouge.core.workflow.steps.gh_pull_request_step import (
        GhPullRequestStep,
    )

    # Mock shutil.which to indicate gh CLI is available
    mock_which.return_value = "/usr/bin/gh"

    # Step calls: git rev-parse, gh pr list (empty), delta check (2), git push, gh pr create
    mock_rev_parse = Mock(returncode=0, stdout="my-branch\n", stderr="")
    mock_pr_list = Mock(returncode=0, stdout="[]", stderr="")
    mock_base_check = Mock(returncode=0, stdout="origin/HEAD\n", stderr="")
    mock_ahead_count = Mock(returncode=0, stdout="1\n", stderr="")
    mock_push_result = Mock(returncode=0, stdout="", stderr="")
    mock_pr_result = Mock(
        returncode=0, stdout="https://github.com/owner/repo/pull/123\n", stderr=""
    )

    mock_subprocess.side_effect = [
        mock_rev_parse,
        mock_pr_list,
        mock_base_check,
        mock_ahead_count,
        mock_push_result,
        mock_pr_result,
    ]

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = _make_context()
    _write_implement_artifact(context)
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This PR adds a new feature.",
        "commits": ["abc1234", "def5678"],
    }

    step = GhPullRequestStep()
    result = step.run(context)

    assert result.success is True
    assert mock_subprocess.call_count == 6
    mock_emit.assert_called_once()

    # Verify git push was called fifth
    push_call = mock_subprocess.call_args_list[4]
    assert push_call[0][0] == ["git", "push", "--set-upstream", "origin", "HEAD"]
    assert push_call[1]["cwd"] == "/path/to/repo"

    # Verify gh pr create was called sixth
    pr_call = mock_subprocess.call_args_list[5]
    assert pr_call[0][0][0:3] == ["gh", "pr", "create"]
    assert pr_call[1]["cwd"] == "/path/to/repo"

    # Verify the emit call has correct data
    call_args = mock_emit.call_args
    payload = call_args[0][0]
    assert payload.issue_id == 1
    assert "https://github.com/owner/repo/pull/123" in payload.text
    assert payload.raw["output"] == "pull-request-created"
    assert "https://github.com/owner/repo/pull/123" in payload.raw["urls"]


@patch.dict("os.environ", {}, clear=True)
@patch("rouge.core.workflow.step_utils.emit_comment_from_payload")
def test_create_pr_step_missing_github_pat(mock_emit) -> None:
    """Test PR creation skipped when GITHUB_PAT is missing."""

    from rouge.core.workflow.steps.gh_pull_request_step import (
        GhPullRequestStep,
    )

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = _make_context()
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This PR adds a new feature.",
        "commits": [],
    }

    step = GhPullRequestStep()
    result = step.run(context)

    assert result.success is True
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "pull-request-skipped"


@patch("rouge.core.workflow.step_utils.emit_comment_from_payload")
def test_create_pr_step_missing_pr_details(mock_emit) -> None:
    """Test PR creation skipped when pr_details is missing."""

    from rouge.core.workflow.steps.gh_pull_request_step import (
        GhPullRequestStep,
    )

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = _make_context()
    # No pr_details in context

    step = GhPullRequestStep()
    result = step.run(context)

    assert result.success is True
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "pull-request-skipped"


@patch("rouge.core.workflow.step_utils.emit_comment_from_payload")
@patch.dict("os.environ", {"GITHUB_PAT": "test-token"})
def test_create_pr_step_empty_title(mock_emit) -> None:
    """Test PR creation skipped when title is empty."""

    from rouge.core.workflow.steps.gh_pull_request_step import (
        GhPullRequestStep,
    )

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = _make_context()
    context.data["pr_details"] = {
        "title": "",
        "summary": "Some summary",
        "commits": [],
    }

    step = GhPullRequestStep()
    result = step.run(context)

    assert result.success is True
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "pull-request-skipped"


@patch("rouge.core.workflow.steps.gh_pull_request_step.shutil.which")
@patch("rouge.core.workflow.step_utils.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.gh_pull_request_step.subprocess.run")
@patch.dict("os.environ", {"GITHUB_PAT": "test-token"})
def test_create_pr_step_already_exists_is_success(mock_subprocess, mock_emit, mock_which) -> None:
    """Test PR creation is idempotent when gh pr list returns an existing PR (Layer 2 adopt)."""

    from rouge.core.workflow.steps.gh_pull_request_step import (
        GhPullRequestStep,
    )

    mock_which.return_value = "/usr/bin/gh"

    import json as _json

    # Step calls: git rev-parse, gh pr list (returns existing PR) → adopts, skips push/create
    mock_rev_parse = Mock(returncode=0, stdout="my-branch\n", stderr="")
    mock_pr_list = Mock(
        returncode=0,
        stdout=_json.dumps([{"url": "https://github.com/owner/repo/pull/123", "number": 123}]),
        stderr="",
    )
    mock_subprocess.side_effect = [mock_rev_parse, mock_pr_list]
    mock_emit.return_value = ("success", "Comment inserted")

    context = _make_context()
    _write_implement_artifact(context)
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This PR adds a new feature.",
        "commits": [],
    }

    step = GhPullRequestStep()
    result = step.run(context)

    assert result.success is True
    # Only rev-parse and pr list were called (no push or create)
    assert mock_subprocess.call_count == 2
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "pull-request-created"
    assert "https://github.com/owner/repo/pull/123" in mock_emit.call_args[0][0].raw["urls"]


@patch("rouge.core.workflow.steps.gh_pull_request_step.shutil.which")
@patch("rouge.core.workflow.step_utils.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.gh_pull_request_step.subprocess.run")
@patch.dict("os.environ", {"GITHUB_PAT": "test-token"})
def test_create_pr_step_gh_command_failure(mock_subprocess, mock_emit, mock_which) -> None:
    """Test PR creation handles gh command failure."""

    from rouge.core.workflow.steps.gh_pull_request_step import (
        GhPullRequestStep,
    )

    # Mock shutil.which to indicate gh CLI is available
    mock_which.return_value = "/usr/bin/gh"

    # Step calls: rev-parse, pr list (empty), delta check (2), push (success), pr create (failure)
    mock_rev_parse = Mock(returncode=0, stdout="my-branch\n", stderr="")
    mock_pr_list = Mock(returncode=0, stdout="[]", stderr="")
    mock_base_check = Mock(returncode=0, stdout="origin/HEAD\n", stderr="")
    mock_ahead_count = Mock(returncode=0, stdout="1\n", stderr="")
    mock_push_result = Mock(returncode=0, stdout="", stderr="")
    mock_pr_result = Mock(returncode=1, stderr="error: could not create pull request")

    mock_subprocess.side_effect = [
        mock_rev_parse,
        mock_pr_list,
        mock_base_check,
        mock_ahead_count,
        mock_push_result,
        mock_pr_result,
    ]

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = _make_context()
    _write_implement_artifact(context)
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This PR adds a new feature.",
        "commits": [],
    }

    step = GhPullRequestStep()
    result = step.run(context)

    # When all repos fail (only one repo), step returns success (best-effort)
    # No pull_requests were created so the success comment is not emitted
    assert result.success is True
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "pull-request-failed"


@patch("rouge.core.workflow.steps.gh_pull_request_step.shutil.which")
@patch("rouge.core.workflow.step_utils.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.gh_pull_request_step.subprocess.run")
@patch.dict("os.environ", {"GITHUB_PAT": "test-token"})
def test_create_pr_step_timeout(mock_subprocess, mock_emit, mock_which) -> None:
    """Test PR creation handles timeout on gh pr create (propagates to outer handler)."""
    import subprocess

    from rouge.core.workflow.steps.gh_pull_request_step import (
        GhPullRequestStep,
    )

    # Mock shutil.which to indicate gh CLI is available
    mock_which.return_value = "/usr/bin/gh"

    # Step calls: rev-parse, pr list (empty), push, gh pr create (timeout → propagates to outer)
    mock_rev_parse = Mock(returncode=0, stdout="my-branch\n", stderr="")
    mock_pr_list = Mock(returncode=0, stdout="[]", stderr="")
    mock_push_result = Mock(returncode=0, stdout="", stderr="")

    mock_subprocess.side_effect = [
        mock_rev_parse,
        mock_pr_list,
        mock_push_result,
        subprocess.TimeoutExpired(cmd="gh", timeout=120),
    ]

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = _make_context()
    _write_implement_artifact(context)
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This PR adds a new feature.",
        "commits": [],
    }

    step = GhPullRequestStep()
    result = step.run(context)

    assert result.success is False
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "pull-request-failed"


@patch("rouge.core.workflow.steps.gh_pull_request_step.shutil.which")
@patch("rouge.core.workflow.step_utils.emit_comment_from_payload")
@patch.dict("os.environ", {"GITHUB_PAT": "test-token"})
def test_create_pr_step_gh_not_found(mock_emit, mock_which) -> None:
    """Test PR creation handles gh CLI not found via proactive detection."""

    from rouge.core.workflow.steps.gh_pull_request_step import (
        GhPullRequestStep,
    )

    # Mock shutil.which to return None (gh not found)
    mock_which.return_value = None

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = _make_context()
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This PR adds a new feature.",
        "commits": [],
    }

    step = GhPullRequestStep()
    result = step.run(context)

    # Should return ok (skip) rather than fail since gh not found is handled proactively
    assert result.success is True
    mock_which.assert_called_once_with("gh")
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "pull-request-skipped"
    assert "gh CLI not found" in mock_emit.call_args[0][0].raw["reason"]


@patch("rouge.core.workflow.steps.gh_pull_request_step.shutil.which")
@patch("rouge.core.workflow.step_utils.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.gh_pull_request_step.subprocess.run")
@patch.dict("os.environ", {"GITHUB_PAT": "test-token"})
def test_create_pr_step_push_failure_continues_to_pr(
    mock_subprocess, mock_emit, mock_which
) -> None:
    """Test PR creation continues even when git push fails."""

    from rouge.core.workflow.steps.gh_pull_request_step import (
        GhPullRequestStep,
    )

    # Mock shutil.which to indicate gh CLI is available
    mock_which.return_value = "/usr/bin/gh"

    # Step calls: rev-parse, pr list (empty), delta check (2),
    # push (failure → best-effort), pr create (success)
    mock_rev_parse = Mock(returncode=0, stdout="my-branch\n", stderr="")
    mock_pr_list = Mock(returncode=0, stdout="[]", stderr="")
    mock_base_check = Mock(returncode=0, stdout="origin/HEAD\n", stderr="")
    mock_ahead_count = Mock(returncode=0, stdout="1\n", stderr="")
    mock_push_result = Mock(returncode=1, stdout="", stderr="error: failed to push some refs")
    mock_pr_result = Mock(returncode=0, stdout="https://github.com/owner/repo/pull/123\n")

    mock_subprocess.side_effect = [
        mock_rev_parse,
        mock_pr_list,
        mock_base_check,
        mock_ahead_count,
        mock_push_result,
        mock_pr_result,
    ]

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = _make_context()
    _write_implement_artifact(context)
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This PR adds a new feature.",
        "commits": [],
    }

    step = GhPullRequestStep()
    result = step.run(context)

    # PR should succeed even if push failed (branch may already exist on remote)
    assert result.success is True
    assert mock_subprocess.call_count == 6
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "pull-request-created"


@patch("rouge.core.workflow.steps.gh_pull_request_step.shutil.which")
@patch("rouge.core.workflow.step_utils.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.gh_pull_request_step.subprocess.run")
@patch.dict("os.environ", {"GITHUB_PAT": "test-token"})
def test_create_pr_step_push_timeout_continues_to_pr(
    mock_subprocess, mock_emit, mock_which
) -> None:
    """Test PR creation continues even when git push times out."""
    import subprocess

    from rouge.core.workflow.steps.gh_pull_request_step import (
        GhPullRequestStep,
    )

    # Mock shutil.which to indicate gh CLI is available
    mock_which.return_value = "/usr/bin/gh"

    # Step calls: rev-parse, pr list (empty), delta check (2),
    # push (timeout → caught, best-effort), pr create
    mock_rev_parse = Mock(returncode=0, stdout="my-branch\n", stderr="")
    mock_pr_list = Mock(returncode=0, stdout="[]", stderr="")
    mock_base_check = Mock(returncode=0, stdout="origin/HEAD\n", stderr="")
    mock_ahead_count = Mock(returncode=0, stdout="1\n", stderr="")
    mock_pr_result = Mock(returncode=0, stdout="https://github.com/owner/repo/pull/123\n")

    mock_subprocess.side_effect = [
        mock_rev_parse,
        mock_pr_list,
        mock_base_check,
        mock_ahead_count,
        subprocess.TimeoutExpired(cmd="git", timeout=60),
        mock_pr_result,
    ]

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = _make_context()
    _write_implement_artifact(context)
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This PR adds a new feature.",
        "commits": [],
    }

    step = GhPullRequestStep()
    result = step.run(context)

    # PR should succeed even if push timed out
    assert result.success is True
    assert mock_subprocess.call_count == 6
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "pull-request-created"


@patch("rouge.core.workflow.steps.gh_pull_request_step.shutil.which")
@patch("rouge.core.workflow.steps.gh_pull_request_step.subprocess.run")
@patch("rouge.core.workflow.step_utils.emit_comment_from_payload")
@patch.dict("os.environ", {"GITHUB_PAT": "test-token"})
def test_create_pr_step_multi_repo_success(mock_emit, mock_subprocess, mock_which) -> None:
    """Test successful PR creation across two repos: subprocess invoked once per repo."""

    from rouge.core.workflow.steps.gh_pull_request_step import GhPullRequestStep

    mock_which.return_value = "/usr/bin/gh"
    mock_emit.return_value = ("success", "Comment inserted")

    # Two repos: each needs rev-parse, pr list (empty), delta check (2),
    # push, pr create — 6 calls each = 12 total
    mock_rev_parse_a = Mock(returncode=0, stdout="my-branch\n", stderr="")
    mock_pr_list_a = Mock(returncode=0, stdout="[]", stderr="")
    mock_base_check_a = Mock(returncode=0, stdout="origin/HEAD\n", stderr="")
    mock_ahead_count_a = Mock(returncode=0, stdout="1\n", stderr="")
    mock_push_a = Mock(returncode=0, stdout="", stderr="")
    mock_pr_create_a = Mock(
        returncode=0, stdout="https://github.com/owner/repo-a/pull/1\n", stderr=""
    )

    mock_rev_parse_b = Mock(returncode=0, stdout="my-branch\n", stderr="")
    mock_pr_list_b = Mock(returncode=0, stdout="[]", stderr="")
    mock_base_check_b = Mock(returncode=0, stdout="origin/HEAD\n", stderr="")
    mock_ahead_count_b = Mock(returncode=0, stdout="1\n", stderr="")
    mock_push_b = Mock(returncode=0, stdout="", stderr="")
    mock_pr_create_b = Mock(
        returncode=0, stdout="https://github.com/owner/repo-b/pull/2\n", stderr=""
    )

    mock_subprocess.side_effect = [
        mock_rev_parse_a,
        mock_pr_list_a,
        mock_base_check_a,
        mock_ahead_count_a,
        mock_push_a,
        mock_pr_create_a,
        mock_rev_parse_b,
        mock_pr_list_b,
        mock_base_check_b,
        mock_ahead_count_b,
        mock_push_b,
        mock_pr_create_b,
    ]

    context = _make_context(repo_paths=["/repo/a", "/repo/b"])
    _write_implement_artifact(context, ["/repo/a", "/repo/b"])
    context.data["pr_details"] = {
        "title": "feat: multi-repo feature",
        "summary": "This PR spans two repos.",
        "commits": ["abc1234"],
    }

    step = GhPullRequestStep()
    result = step.run(context)

    assert result.success is True
    # Subprocess called 6 times per repo = 12 total
    assert mock_subprocess.call_count == 12

    # Verify each repo's push and pr-create used the correct cwd
    push_call_a = mock_subprocess.call_args_list[4]
    assert push_call_a[1]["cwd"] == "/repo/a"
    assert push_call_a[0][0] == ["git", "push", "--set-upstream", "origin", "HEAD"]

    pr_create_call_a = mock_subprocess.call_args_list[5]
    assert pr_create_call_a[1]["cwd"] == "/repo/a"
    assert pr_create_call_a[0][0][0:3] == ["gh", "pr", "create"]

    push_call_b = mock_subprocess.call_args_list[10]
    assert push_call_b[1]["cwd"] == "/repo/b"
    assert push_call_b[0][0] == ["git", "push", "--set-upstream", "origin", "HEAD"]

    pr_create_call_b = mock_subprocess.call_args_list[11]
    assert pr_create_call_b[1]["cwd"] == "/repo/b"
    assert pr_create_call_b[0][0][0:3] == ["gh", "pr", "create"]

    # emit_comment_from_payload called once at the end (final "pull-request-created" summary)
    mock_emit.assert_called_once()
    payload = mock_emit.call_args[0][0]
    assert payload.raw["output"] == "pull-request-created"
    # Both repo URLs appear in the emitted payload
    assert "https://github.com/owner/repo-a/pull/1" in payload.raw["urls"]
    assert "https://github.com/owner/repo-b/pull/2" in payload.raw["urls"]
    assert "/repo/a" in payload.text or "https://github.com/owner/repo-a/pull/1" in payload.text
    assert "/repo/b" in payload.text or "https://github.com/owner/repo-b/pull/2" in payload.text


@patch("rouge.core.workflow.steps.gh_pull_request_step.shutil.which")
@patch("rouge.core.workflow.steps.gh_pull_request_step.subprocess.run")
@patch("rouge.core.workflow.step_utils.emit_comment_from_payload")
@patch.dict("os.environ", {"GITHUB_PAT": "test-token"})
def test_create_pr_step_multi_repo_failure(mock_emit, mock_subprocess, mock_which) -> None:
    """Test PR creation with both repos failing: subprocess invoked once per repo,
    best-effort continues."""

    from rouge.core.workflow.steps.gh_pull_request_step import GhPullRequestStep

    mock_which.return_value = "/usr/bin/gh"
    mock_emit.return_value = ("success", "Comment inserted")

    # Two repos: each needs rev-parse, pr list (empty), delta check (2), push, pr create (fail)
    # — 6 calls each = 12 total
    mock_rev_parse_a = Mock(returncode=0, stdout="my-branch\n", stderr="")
    mock_pr_list_a = Mock(returncode=0, stdout="[]", stderr="")
    mock_base_check_a = Mock(returncode=0, stdout="origin/HEAD\n", stderr="")
    mock_ahead_count_a = Mock(returncode=0, stdout="1\n", stderr="")
    mock_push_a = Mock(returncode=0, stdout="", stderr="")
    mock_pr_fail_a = Mock(returncode=1, stdout="", stderr="error: could not create PR for repo-a")

    mock_rev_parse_b = Mock(returncode=0, stdout="my-branch\n", stderr="")
    mock_pr_list_b = Mock(returncode=0, stdout="[]", stderr="")
    mock_base_check_b = Mock(returncode=0, stdout="origin/HEAD\n", stderr="")
    mock_ahead_count_b = Mock(returncode=0, stdout="1\n", stderr="")
    mock_push_b = Mock(returncode=0, stdout="", stderr="")
    mock_pr_fail_b = Mock(returncode=1, stdout="", stderr="error: could not create PR for repo-b")

    mock_subprocess.side_effect = [
        mock_rev_parse_a,
        mock_pr_list_a,
        mock_base_check_a,
        mock_ahead_count_a,
        mock_push_a,
        mock_pr_fail_a,
        mock_rev_parse_b,
        mock_pr_list_b,
        mock_base_check_b,
        mock_ahead_count_b,
        mock_push_b,
        mock_pr_fail_b,
    ]

    context = _make_context(repo_paths=["/repo/a", "/repo/b"])
    _write_implement_artifact(context, ["/repo/a", "/repo/b"])
    context.data["pr_details"] = {
        "title": "feat: multi-repo feature",
        "summary": "This PR spans two repos.",
        "commits": [],
    }

    step = GhPullRequestStep()
    result = step.run(context)

    # Step is best-effort: returns success even when all repos fail
    assert result.success is True
    # Subprocess called 6 times per repo = 12 total (loop continues on per-repo failure)
    assert mock_subprocess.call_count == 12

    # Verify the step attempted both repos (push cwd per repo)
    push_call_a = mock_subprocess.call_args_list[4]
    assert push_call_a[1]["cwd"] == "/repo/a"

    push_call_b = mock_subprocess.call_args_list[10]
    assert push_call_b[1]["cwd"] == "/repo/b"

    # emit_comment_from_payload called once per failing repo = 2 total
    assert mock_emit.call_count == 2
    failure_outputs = [call[0][0].raw["output"] for call in mock_emit.call_args_list]
    assert failure_outputs == ["pull-request-failed", "pull-request-failed"]

    # Each failure payload references the corresponding repo
    assert (
        "/repo/a" in mock_emit.call_args_list[0][0][0].raw["error"]
        or "repo-a" in mock_emit.call_args_list[0][0][0].raw["error"]
    )
    assert (
        "/repo/b" in mock_emit.call_args_list[1][0][0].raw["error"]
        or "repo-b" in mock_emit.call_args_list[1][0][0].raw["error"]
    )


def test_create_pr_step_is_not_critical() -> None:
    """Test GhPullRequestStep is not critical."""
    from rouge.core.workflow.steps.gh_pull_request_step import (
        GhPullRequestStep,
    )

    step = GhPullRequestStep()
    assert step.is_critical is False


def test_create_pr_step_name() -> None:
    """Test GhPullRequestStep has correct name."""
    from rouge.core.workflow.steps.gh_pull_request_step import (
        GhPullRequestStep,
    )

    step = GhPullRequestStep()
    assert step.name == "Creating GitHub pull request"


# === GlabPullRequestStep Tests ===


@patch("rouge.core.workflow.steps.glab_pull_request_step.shutil.which")
@patch("rouge.core.workflow.steps.glab_pull_request_step.subprocess.run")
@patch("rouge.core.workflow.step_utils.emit_comment_from_payload")
@patch.dict("os.environ", {"GITLAB_PAT": "test-token"})
def test_create_gitlab_mr_step_success(mock_emit, mock_subprocess, mock_which) -> None:
    """Test successful MR creation: rev-parse, mr list (empty), push, mr create."""

    from rouge.core.workflow.steps.glab_pull_request_step import GlabPullRequestStep

    mock_which.return_value = "/usr/bin/glab"
    # Step calls: git rev-parse, glab mr list (empty), delta check (2), git push, glab mr create
    mock_rev_parse = Mock(returncode=0, stdout="my-branch\n", stderr="")
    mock_mr_list = Mock(returncode=0, stdout="[]", stderr="")
    mock_base_check = Mock(returncode=0, stdout="origin/HEAD\n", stderr="")
    mock_ahead_count = Mock(returncode=0, stdout="1\n", stderr="")
    mock_push_result = Mock(returncode=0, stdout="", stderr="")
    mock_mr_result = Mock(
        returncode=0, stdout="https://gitlab.com/owner/repo/-/merge_requests/123\n"
    )

    mock_subprocess.side_effect = [
        mock_rev_parse,
        mock_mr_list,
        mock_base_check,
        mock_ahead_count,
        mock_push_result,
        mock_mr_result,
    ]

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = _make_context()
    _write_implement_artifact(context)
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This MR adds a new feature.",
        "commits": ["abc1234", "def5678"],
    }

    step = GlabPullRequestStep()
    result = step.run(context)

    assert result.success is True
    assert mock_subprocess.call_count == 6
    mock_emit.assert_called_once()

    # Verify git push was called fifth
    push_call = mock_subprocess.call_args_list[4]
    assert push_call[0][0] == ["git", "push", "--set-upstream", "origin", "HEAD"]
    assert push_call[1]["cwd"] == "/path/to/repo"

    # Verify glab mr create was called sixth
    mr_call = mock_subprocess.call_args_list[5]
    assert mr_call[0][0][0:3] == ["glab", "mr", "create"]
    assert mr_call[1]["cwd"] == "/path/to/repo"

    # Verify the emit call has correct data
    call_args = mock_emit.call_args
    payload = call_args[0][0]
    assert payload.issue_id == 1
    assert "https://gitlab.com/owner/repo/-/merge_requests/123" in payload.text
    assert payload.raw["output"] == "merge-request-created"
    assert "https://gitlab.com/owner/repo/-/merge_requests/123" in payload.raw["urls"]


@patch.dict("os.environ", {}, clear=True)
@patch("rouge.core.workflow.step_utils.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.glab_pull_request_step.get_logger")
def test_create_gitlab_mr_step_missing_gitlab_pat(mock_get_logger, mock_emit) -> None:
    """Test MR creation skipped when GITLAB_PAT is missing."""

    from rouge.core.workflow.steps.glab_pull_request_step import GlabPullRequestStep

    # Mock the logger instance returned by get_logger
    mock_logger = MagicMock()
    mock_get_logger.return_value = mock_logger

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = _make_context()
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This MR adds a new feature.",
        "commits": [],
    }

    step = GlabPullRequestStep()
    result = step.run(context)

    assert result.success is True
    mock_logger.info.assert_called_with(
        "MR creation skipped: GITLAB_PAT environment variable not set"
    )
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "merge-request-skipped"


@patch("rouge.core.workflow.step_utils.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.glab_pull_request_step.get_logger")
def test_create_gitlab_mr_step_missing_pr_details(mock_get_logger, mock_emit) -> None:
    """Test MR creation skipped when pr_details is missing."""

    from rouge.core.workflow.steps.glab_pull_request_step import GlabPullRequestStep

    # Mock the logger instance returned by get_logger
    mock_logger = MagicMock()
    mock_get_logger.return_value = mock_logger

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = _make_context()
    # No pr_details in context

    step = GlabPullRequestStep()
    result = step.run(context)

    assert result.success is True
    mock_logger.info.assert_called_with("MR creation skipped: no PR details in context")
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "merge-request-skipped"


@patch("rouge.core.workflow.step_utils.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.glab_pull_request_step.get_logger")
@patch.dict("os.environ", {"GITLAB_PAT": "test-token"})
def test_create_gitlab_mr_step_empty_title(mock_get_logger, mock_emit) -> None:
    """Test MR creation skipped when title is empty."""

    from rouge.core.workflow.steps.glab_pull_request_step import GlabPullRequestStep

    # Mock the logger instance returned by get_logger
    mock_logger = MagicMock()
    mock_get_logger.return_value = mock_logger

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = _make_context()
    context.data["pr_details"] = {
        "title": "",
        "summary": "Some summary",
        "commits": [],
    }

    step = GlabPullRequestStep()
    result = step.run(context)

    assert result.success is True
    mock_logger.info.assert_called_with("MR creation skipped: MR title is empty")
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "merge-request-skipped"


@patch("rouge.core.workflow.steps.glab_pull_request_step.shutil.which")
@patch("rouge.core.workflow.step_utils.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.glab_pull_request_step.get_logger")
@patch("rouge.core.workflow.steps.glab_pull_request_step.subprocess.run")
@patch.dict("os.environ", {"GITLAB_PAT": "test-token"})
def test_create_gitlab_mr_step_glab_command_failure(
    mock_subprocess, mock_get_logger, mock_emit, mock_which
) -> None:
    """Test MR creation handles glab command failure (best-effort: returns success)."""

    from rouge.core.workflow.steps.glab_pull_request_step import GlabPullRequestStep

    mock_which.return_value = "/usr/bin/glab"
    # Mock the logger instance returned by get_logger
    mock_logger = MagicMock()
    mock_get_logger.return_value = mock_logger

    # Step calls: rev-parse, mr list (empty), delta check (2),
    # push (success), glab mr create (failure)
    mock_rev_parse = Mock(returncode=0, stdout="my-branch\n", stderr="")
    mock_mr_list = Mock(returncode=0, stdout="[]", stderr="")
    mock_base_check = Mock(returncode=0, stdout="origin/HEAD\n", stderr="")
    mock_ahead_count = Mock(returncode=0, stdout="1\n", stderr="")
    mock_push_result = Mock(returncode=0, stdout="", stderr="")
    mock_mr_result = Mock(returncode=1, stderr="error: could not create merge request")

    mock_subprocess.side_effect = [
        mock_rev_parse,
        mock_mr_list,
        mock_base_check,
        mock_ahead_count,
        mock_push_result,
        mock_mr_result,
    ]

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = _make_context()
    _write_implement_artifact(context)
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This MR adds a new feature.",
        "commits": [],
    }

    step = GlabPullRequestStep()
    result = step.run(context)

    # Per-repo failure continues loop; no MRs created → returns ok (best-effort step)
    assert result.success is True
    mock_logger.warning.assert_called()
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "merge-request-failed"


@patch("rouge.core.workflow.steps.glab_pull_request_step.shutil.which")
@patch("rouge.core.workflow.step_utils.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.glab_pull_request_step.get_logger")
@patch("rouge.core.workflow.steps.glab_pull_request_step.subprocess.run")
@patch.dict("os.environ", {"GITLAB_PAT": "test-token"})
def test_create_gitlab_mr_step_timeout(
    mock_subprocess, mock_get_logger, mock_emit, mock_which
) -> None:
    """Test MR creation handles timeout on glab mr create (caught per-repo, step continues)."""
    import subprocess

    from rouge.core.workflow.steps.glab_pull_request_step import GlabPullRequestStep

    mock_which.return_value = "/usr/bin/glab"
    # Mock the logger instance returned by get_logger
    mock_logger = MagicMock()
    mock_get_logger.return_value = mock_logger

    # Step calls: rev-parse, mr list (empty), delta check (2),
    # push, glab mr create (timeout caught per-repo)
    mock_rev_parse = Mock(returncode=0, stdout="my-branch\n", stderr="")
    mock_mr_list = Mock(returncode=0, stdout="[]", stderr="")
    mock_base_check = Mock(returncode=0, stdout="origin/HEAD\n", stderr="")
    mock_ahead_count = Mock(returncode=0, stdout="1\n", stderr="")
    mock_push_result = Mock(returncode=0, stdout="", stderr="")

    mock_subprocess.side_effect = [
        mock_rev_parse,
        mock_mr_list,
        mock_base_check,
        mock_ahead_count,
        mock_push_result,
        subprocess.TimeoutExpired(cmd="glab", timeout=120),
    ]

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = _make_context()
    _write_implement_artifact(context)
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This MR adds a new feature.",
        "commits": [],
    }

    step = GlabPullRequestStep()
    result = step.run(context)

    # Per-repo timeout is caught in the inner loop; step continues and returns success
    assert result.success is True
    mock_logger.warning.assert_called()
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "merge-request-failed"


@patch("rouge.core.workflow.steps.glab_pull_request_step.shutil.which")
@patch("rouge.core.workflow.step_utils.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.glab_pull_request_step.get_logger")
@patch("rouge.core.workflow.steps.glab_pull_request_step.subprocess.run")
@patch.dict("os.environ", {"GITLAB_PAT": "test-token"})
def test_create_gitlab_mr_step_glab_not_found(
    mock_subprocess, mock_get_logger, mock_emit, mock_which
) -> None:
    """Test MR creation handles glab CLI not found (propagates to outer
    FileNotFoundError handler)."""

    from rouge.core.workflow.steps.glab_pull_request_step import GlabPullRequestStep

    mock_which.return_value = "/usr/bin/glab"
    # Mock the logger instance returned by get_logger
    mock_logger = MagicMock()
    mock_get_logger.return_value = mock_logger

    # Step calls: git rev-parse, glab mr list (FileNotFoundError caught by inner loop),
    # git push (success), glab mr create (FileNotFoundError propagates to outer handler)
    mock_rev_parse = Mock(returncode=0, stdout="my-branch\n", stderr="")
    mock_push_result = Mock(returncode=0, stdout="", stderr="")

    mock_subprocess.side_effect = [
        mock_rev_parse,
        FileNotFoundError("glab not found"),  # glab mr list — caught internally
        mock_push_result,
        FileNotFoundError("glab not found"),  # glab mr create — propagates to outer handler
    ]

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = _make_context()
    _write_implement_artifact(context)
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This MR adds a new feature.",
        "commits": [],
    }

    step = GlabPullRequestStep()
    result = step.run(context)

    assert result.success is False
    mock_logger.exception.assert_called_with("glab CLI not found, skipping MR creation")
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "merge-request-failed"


@patch("rouge.core.workflow.steps.glab_pull_request_step.shutil.which")
@patch("rouge.core.workflow.step_utils.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.glab_pull_request_step.subprocess.run")
@patch.dict("os.environ", {"GITLAB_PAT": "test-token"})
def test_create_gitlab_mr_step_push_failure_continues_to_mr(
    mock_subprocess, mock_emit, mock_which
) -> None:
    """Test MR creation continues even when git push fails."""

    from rouge.core.workflow.steps.glab_pull_request_step import GlabPullRequestStep

    mock_which.return_value = "/usr/bin/glab"
    # Step calls: rev-parse, mr list (empty), delta check (2),
    # push (failure → best-effort), glab mr create (success)
    mock_rev_parse = Mock(returncode=0, stdout="my-branch\n", stderr="")
    mock_mr_list = Mock(returncode=0, stdout="[]", stderr="")
    mock_base_check = Mock(returncode=0, stdout="origin/HEAD\n", stderr="")
    mock_ahead_count = Mock(returncode=0, stdout="1\n", stderr="")
    mock_push_result = Mock(returncode=1, stdout="", stderr="error: failed to push some refs")
    mock_mr_result = Mock(
        returncode=0, stdout="https://gitlab.com/owner/repo/-/merge_requests/123\n"
    )

    mock_subprocess.side_effect = [
        mock_rev_parse,
        mock_mr_list,
        mock_base_check,
        mock_ahead_count,
        mock_push_result,
        mock_mr_result,
    ]

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = _make_context()
    _write_implement_artifact(context)
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This MR adds a new feature.",
        "commits": [],
    }

    step = GlabPullRequestStep()
    result = step.run(context)

    # MR should succeed even if push failed (branch may already exist on remote)
    assert result.success is True
    assert mock_subprocess.call_count == 6
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "merge-request-created"


@patch("rouge.core.workflow.steps.glab_pull_request_step.shutil.which")
@patch("rouge.core.workflow.step_utils.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.glab_pull_request_step.subprocess.run")
@patch.dict("os.environ", {"GITLAB_PAT": "test-token"})
def test_create_gitlab_mr_step_push_timeout_continues_to_mr(
    mock_subprocess, mock_emit, mock_which
) -> None:
    """Test MR creation continues even when git push times out."""
    import subprocess

    from rouge.core.workflow.steps.glab_pull_request_step import GlabPullRequestStep

    mock_which.return_value = "/usr/bin/glab"
    # Step calls: rev-parse, mr list (empty), delta check (2),
    # push (timeout → best-effort), glab mr create (success)
    mock_rev_parse = Mock(returncode=0, stdout="my-branch\n", stderr="")
    mock_mr_list = Mock(returncode=0, stdout="[]", stderr="")
    mock_base_check = Mock(returncode=0, stdout="origin/HEAD\n", stderr="")
    mock_ahead_count = Mock(returncode=0, stdout="1\n", stderr="")
    mock_mr_result = Mock(
        returncode=0, stdout="https://gitlab.com/owner/repo/-/merge_requests/123\n"
    )

    mock_subprocess.side_effect = [
        mock_rev_parse,
        mock_mr_list,
        mock_base_check,
        mock_ahead_count,
        subprocess.TimeoutExpired(cmd="git", timeout=60),
        mock_mr_result,
    ]

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    context = _make_context()
    _write_implement_artifact(context)
    context.data["pr_details"] = {
        "title": "feat: add new feature",
        "summary": "This MR adds a new feature.",
        "commits": [],
    }

    step = GlabPullRequestStep()
    result = step.run(context)

    # MR should succeed even if push timed out
    assert result.success is True
    assert mock_subprocess.call_count == 6
    mock_emit.assert_called_once()
    assert mock_emit.call_args[0][0].raw["output"] == "merge-request-created"


def test_create_gitlab_mr_step_is_not_critical() -> None:
    """Test GlabPullRequestStep is not critical."""
    from rouge.core.workflow.steps.glab_pull_request_step import GlabPullRequestStep

    step = GlabPullRequestStep()
    assert step.is_critical is False


def test_create_gitlab_mr_step_name() -> None:
    """Test GlabPullRequestStep has correct name."""
    from rouge.core.workflow.steps.glab_pull_request_step import GlabPullRequestStep

    step = GlabPullRequestStep()
    assert step.name == "Creating GitLab merge request"


# === ComposeRequestStep JSON parsing Tests ===


def test_prepare_pr_step_store_pr_details_success() -> None:
    """Test _store_pr_details stores validated dict correctly."""

    from rouge.core.workflow.steps.compose_request_step import ComposeRequestStep

    context = _make_context()
    step = ComposeRequestStep()

    # _store_pr_details expects a dict (pre-validated).
    # Commits must be dicts (per ComposeRequestArtifact schema).
    pr_data = {
        "title": "feat: add feature",
        "summary": "This adds a feature.",
        "commits": [{"message": "abc123"}, {"message": "def456"}],
    }
    step._store_pr_details(pr_data, context)

    assert "pr_details" in context.data
    assert context.data["pr_details"]["title"] == "feat: add feature"
    assert context.data["pr_details"]["summary"] == "This adds a feature."
    assert context.data["pr_details"]["commits"] == [{"message": "abc123"}, {"message": "def456"}]


def test_prepare_pr_step_store_pr_details_missing_fields() -> None:
    """Test _store_pr_details handles missing fields with defaults."""

    from rouge.core.workflow.steps.compose_request_step import ComposeRequestStep

    context = _make_context()
    step = ComposeRequestStep()

    # Dict with title and a non-empty summary (empty summary fails artifact validation).
    # Commits default to [] which is valid for ComposeRequestArtifact.
    pr_data = {"title": "only title", "summary": "Default summary"}
    step._store_pr_details(pr_data, context)

    assert "pr_details" in context.data
    assert context.data["pr_details"]["title"] == "only title"
    assert context.data["pr_details"]["summary"] == "Default summary"
    assert context.data["pr_details"]["commits"] == []


@patch("rouge.core.workflow.steps.compose_request_step.get_affected_repos")
@patch("rouge.core.workflow.step_utils.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.compose_request_step.execute_template")
@patch("rouge.core.workflow.steps.compose_request_step.update_status")
def test_prepare_pr_step_emits_raw_llm_response(
    mock_update_status, mock_execute, mock_emit, mock_get_affected
) -> None:
    """Test ComposeRequestStep emits raw LLM response for debugging."""

    from rouge.core.workflow.steps.compose_request_step import ComposeRequestStep
    from rouge.core.workflow.types import ImplementData

    # Mock emit_comment_from_payload success
    mock_emit.return_value = ("success", "Comment inserted")

    # Mock successful template execution with valid JSON
    # Commits must be dicts to pass ComposeRequestArtifact validation.
    pr_json = (
        '{"output": "pull_request", "title": "feat: test", '
        '"summary": "Test summary", "commits": [{"message": "abc123"}]}'
    )
    mock_response = Mock()
    mock_response.success = True
    mock_response.output = pr_json
    mock_execute.return_value = mock_response

    context = _make_context()
    mock_get_affected.return_value = (context.repo_paths, ImplementData(output="done"))
    step = ComposeRequestStep()
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
