"""Tests for GhPullRequestStep dependency contract.

Focuses on:
- Succeeding (graceful skip) when compose-request data is absent
  (optional dependency declared in registry)
- Loading PR details from context data when present
- Adding --draft flag based on pipeline_type
- Attachment comment posting, updating, and error handling
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from rouge.core.models import Issue
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.gh_pull_request_step import GhPullRequestStep
from rouge.core.workflow.types import PlanData


def _gh_subprocess_side_effect(cmd: list[str], **kwargs: Any) -> MagicMock:
    """Simulate subprocess calls for gh PR creation flow."""
    result = MagicMock()
    if cmd[0] == "git" and cmd[1] == "rev-parse":
        result.returncode = 0
        result.stdout = "feature-branch"
    elif cmd[0] == "gh" and cmd[1] == "pr" and cmd[2] == "list":
        result.returncode = 0
        result.stdout = "[]"
    elif cmd[0] == "git" and cmd[1] == "push":
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
    elif cmd[0] == "gh" and cmd[1] == "pr" and cmd[2] == "create":
        result.returncode = 0
        result.stdout = "https://github.com/org/repo/pull/42"
    else:
        result.returncode = 0
        result.stdout = ""
    return result


@pytest.fixture
def base_context() -> WorkflowContext:
    """Create a workflow context without any data."""
    return WorkflowContext(
        adw_id="test-gh-pr",
        issue_id=42,
        repo_paths=["/path/to/repo"],
    )


class TestGhPullRequestStepOptionalDependency:
    """Tests verifying GhPullRequestStep handles absent compose-request data gracefully."""

    @patch("rouge.core.workflow.pull_request_step_base._emit_and_log")
    def test_succeeds_when_compose_request_data_absent(
        self, mock_emit, base_context: WorkflowContext
    ) -> None:
        """Step returns success when compose-request data is missing (optional dep)."""

        step = GhPullRequestStep()
        result = step.run(base_context)

        # Must succeed (not fail) — optional dependency is missing
        assert result.success is True
        assert result.error is None

    @patch("rouge.core.workflow.pull_request_step_base._emit_and_log")
    def test_emits_skip_comment_when_data_absent(
        self, mock_emit, base_context: WorkflowContext
    ) -> None:
        """Step emits an informative skip comment when compose-request data is missing."""

        step = GhPullRequestStep()
        result = step.run(base_context)

        assert result.success is True
        assert mock_emit.called
        text = mock_emit.call_args[0][2]
        # Message should indicate skip reason
        assert "skip" in text.lower() or "no pr details" in text.lower()

    @patch("rouge.core.workflow.pull_request_step_base._emit_and_log")
    def test_does_not_raise_when_data_absent(
        self, mock_emit, base_context: WorkflowContext
    ) -> None:
        """No exception is raised when compose-request data is absent."""

        step = GhPullRequestStep()
        # Should not raise
        result = step.run(base_context)
        assert result is not None


class TestGhPullRequestStepWithData:
    """Tests verifying GhPullRequestStep uses compose-request data when present."""

    @patch("rouge.core.workflow.pull_request_step_base._emit_and_log")
    @patch("rouge.core.workflow.steps.gh_pull_request_step.shutil.which")
    def test_uses_compose_request_data_when_present(
        self,
        mock_which,
        mock_emit,
        base_context: WorkflowContext,
    ) -> None:
        """Step reads PR details from context data when it exists."""
        # Write compose-request data to context
        base_context.data["pr_details"] = {
            "title": "My PR Title",
            "summary": "My PR Summary",
            "commits": [],
        }

        mock_which.return_value = None  # gh CLI not found - graceful skip

        step = GhPullRequestStep()
        result = step.run(base_context)

        # Step should succeed (either skip due to missing gh or GITHUB_PAT)
        assert result.success is True


class TestGhPullRequestStepDraftFlag:
    """Tests verifying GhPullRequestStep adds --draft flag based on pipeline_type."""

    @patch("rouge.core.workflow.pull_request_step_base._emit_and_log")
    @patch("rouge.core.workflow.steps.gh_pull_request_step.shutil.which")
    @patch("rouge.core.workflow.pull_request_step_base.subprocess.run")
    @patch("rouge.core.workflow.pull_request_step_base.os.environ", new_callable=dict)
    def test_thin_pipeline_includes_draft_flag(
        self,
        mock_environ,
        mock_run,
        mock_which,
        mock_emit,
    ) -> None:
        """When pipeline_type is 'thin', gh pr create command includes --draft."""
        mock_environ["GITHUB_PAT"] = "fake-token"
        mock_environ["PATH"] = "/usr/bin"
        mock_which.return_value = "/usr/bin/gh"

        context = WorkflowContext(
            adw_id="test-gh-pr",
            issue_id=42,
            repo_paths=["/path/to/repo"],
            pipeline_type="thin",
        )
        context.data["pr_details"] = {
            "title": "Draft PR",
            "summary": "Summary",
            "commits": [],
        }

        mock_run.side_effect = _gh_subprocess_side_effect

        step = GhPullRequestStep()
        result = step.run(context)

        assert result.success is True

        # Find the gh pr create call and verify --draft is present
        gh_create_calls = [
            call
            for call in mock_run.call_args_list
            if call[0][0][0] == "gh" and call[0][0][2] == "create"
        ]
        assert len(gh_create_calls) == 1
        cmd_args = gh_create_calls[0][0][0]
        assert "--draft" in cmd_args

    @patch("rouge.core.workflow.pull_request_step_base._emit_and_log")
    @patch("rouge.core.workflow.steps.gh_pull_request_step.shutil.which")
    @patch("rouge.core.workflow.pull_request_step_base.subprocess.run")
    @patch("rouge.core.workflow.pull_request_step_base.os.environ", new_callable=dict)
    def test_full_pipeline_omits_draft_flag(
        self,
        mock_environ,
        mock_run,
        mock_which,
        mock_emit,
    ) -> None:
        """When pipeline_type is 'full', gh pr create command does not include --draft."""
        mock_environ["GITHUB_PAT"] = "fake-token"
        mock_environ["PATH"] = "/usr/bin"
        mock_which.return_value = "/usr/bin/gh"

        context = WorkflowContext(
            adw_id="test-gh-pr",
            issue_id=42,
            repo_paths=["/path/to/repo"],
            pipeline_type="full",
        )
        context.data["pr_details"] = {
            "title": "Full PR",
            "summary": "Summary",
            "commits": [],
        }

        mock_run.side_effect = _gh_subprocess_side_effect

        step = GhPullRequestStep()
        result = step.run(context)

        assert result.success is True

        # Find the gh pr create call and verify --draft is NOT present
        gh_create_calls = [
            call
            for call in mock_run.call_args_list
            if call[0][0][0] == "gh" and call[0][0][2] == "create"
        ]
        assert len(gh_create_calls) == 1
        cmd_args = gh_create_calls[0][0][0]
        assert "--draft" not in cmd_args


class TestGhPullRequestStepAffectedRepos:
    """Tests for GhPullRequestStep affected-repos filtering and branch-delta guard."""

    @patch("rouge.core.workflow.pull_request_step_base._emit_and_log")
    @patch("rouge.core.workflow.steps.gh_pull_request_step.shutil.which")
    @patch("rouge.core.workflow.pull_request_step_base.subprocess.run")
    @patch("rouge.core.workflow.pull_request_step_base.get_affected_repo_paths")
    @patch.dict("os.environ", {"GITHUB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_only_affected_repos_are_iterated(
        self,
        mock_get_affected: MagicMock,
        mock_run: MagicMock,
        mock_which: MagicMock,
        mock_emit: MagicMock,
        base_context: WorkflowContext,
    ) -> None:
        """Only repos returned by get_affected_repo_paths are processed."""
        base_context.data["pr_details"] = {
            "title": "Test PR",
            "summary": "Summary",
            "commits": [],
        }
        mock_which.return_value = "/usr/bin/gh"

        # Context has two repos, but only one is affected
        base_context.repo_paths = ["/path/to/repo-a", "/path/to/repo-b"]
        mock_get_affected.return_value = ["/path/to/repo-b"]
        mock_run.side_effect = _gh_subprocess_side_effect

        step = GhPullRequestStep()
        result = step.run(base_context)

        assert result.success is True
        # All subprocess calls should use repo-b, not repo-a
        for call in mock_run.call_args_list:
            cwd = call[1].get("cwd", "")
            assert "repo-a" not in str(cwd)

    @patch("rouge.core.workflow.pull_request_step_base._emit_and_log")
    @patch("rouge.core.workflow.pull_request_step_base.get_affected_repo_paths")
    def test_skips_when_zero_affected_repos(
        self,
        mock_get_affected: MagicMock,
        mock_emit: MagicMock,
        base_context: WorkflowContext,
    ) -> None:
        """Step returns success and writes empty data when no repos are affected."""
        base_context.data["pr_details"] = {
            "title": "Test PR",
            "summary": "Summary",
            "commits": [],
        }
        mock_get_affected.return_value = []

        with patch.dict("os.environ", {"GITHUB_PAT": "tok"}, clear=False):
            with patch("rouge.core.workflow.steps.gh_pull_request_step.shutil.which") as mock_which:
                mock_which.return_value = "/usr/bin/gh"
                step = GhPullRequestStep()
                result = step.run(base_context)

        assert result.success is True
        pr_data = base_context.data.get("gh-pull-request", {})
        assert pr_data.get("pull_requests") == []

    @patch("rouge.core.workflow.pull_request_step_base._emit_and_log")
    @patch("rouge.core.workflow.steps.gh_pull_request_step.shutil.which")
    @patch("rouge.core.workflow.pull_request_step_base.subprocess.run")
    @patch.dict("os.environ", {"GITHUB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_branch_delta_guard_prevents_empty_pr(
        self,
        mock_run: MagicMock,
        mock_which: MagicMock,
        mock_emit: MagicMock,
        base_context: WorkflowContext,
    ) -> None:
        """When branch has zero commits ahead of base, PR creation is skipped."""
        base_context.data["pr_details"] = {
            "title": "Test PR",
            "summary": "Summary",
            "commits": [],
        }
        mock_which.return_value = "/usr/bin/gh"

        def _delta_guard_side_effect(cmd: list[str], **_kwargs: Any) -> MagicMock:
            result = MagicMock()
            if cmd[0] == "git" and "rev-parse" in cmd:
                if "--abbrev-ref" in cmd and "origin/HEAD" in cmd:
                    result.returncode = 0
                    result.stdout = "origin/main\n"
                else:
                    result.returncode = 0
                    result.stdout = "feature-branch\n"
            elif cmd[0] == "gh" and cmd[1] == "pr" and cmd[2] == "list":
                result.returncode = 0
                result.stdout = "[]"
            elif cmd[0] == "git" and "rev-list" in cmd:
                # Zero commits ahead
                result.returncode = 0
                result.stdout = "0\n"
            else:
                result.returncode = 0
                result.stdout = ""
            return result

        mock_run.side_effect = _delta_guard_side_effect

        step = GhPullRequestStep()
        result = step.run(base_context)

        assert result.success is True
        # No gh pr create call should have been made
        gh_create_calls = [
            c
            for c in mock_run.call_args_list
            if len(c[0][0]) >= 3 and c[0][0][0] == "gh" and c[0][0][2] == "create"
        ]
        assert len(gh_create_calls) == 0


def _write_fetch_issue_and_plan_to_context(context: WorkflowContext) -> None:
    """Write fetch-issue and plan data to context for attachment tests."""
    issue = Issue(
        id=42,
        description="Implement feature X with Y integration",
        status="started",
        type="full",
    )
    context.data["issue_data"] = {"description": issue.description}
    context.data["plan_data"] = PlanData(
        plan="1. Add module\n2. Write tests",
        summary="Add module and tests",
    )


def _make_subprocess_side_effect(
    *,
    existing_comment_id: str | None = None,
    attachment_error: bool = False,
) -> object:
    """Build a side_effect callable for subprocess.run."""

    def _side_effect(cmd: list[str], **_kwargs: object) -> MagicMock:
        cmd_str = " ".join(cmd)

        if "rev-parse" in cmd_str:
            result = MagicMock()
            result.returncode = 0
            result.stdout = "adw-test-branch\n"
            return result

        if "pr" in cmd_str and "list" in cmd_str:
            result = MagicMock()
            result.returncode = 0
            result.stdout = "[]"
            return result

        if "push" in cmd_str:
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            return result

        if "pr" in cmd_str and "create" in cmd_str:
            result = MagicMock()
            result.returncode = 0
            result.stdout = "https://github.com/org/repo/pull/99\n"
            return result

        if "pr" in cmd_str and "view" in cmd_str:
            if attachment_error:
                raise OSError("network error")
            result = MagicMock()
            result.returncode = 0
            result.stdout = existing_comment_id or ""
            return result

        if "pr" in cmd_str and "comment" in cmd_str:
            if attachment_error:
                raise OSError("network error")
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            return result

        if "api" in cmd_str and "PATCH" in cmd_str:
            if attachment_error:
                raise OSError("network error")
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            return result

        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        return result

    return _side_effect


_ATTACHMENT_PATCHES = [
    "rouge.core.workflow.pull_request_step_base._emit_and_log",
    "rouge.core.workflow.steps.gh_pull_request_step.shutil.which",
    "rouge.core.workflow.pull_request_step_base.subprocess.run",
]


class TestGhPullRequestStepAttachment:
    """Tests for attachment comment posting/updating on pull requests."""

    @patch(_ATTACHMENT_PATCHES[0])
    @patch(_ATTACHMENT_PATCHES[1])
    @patch(_ATTACHMENT_PATCHES[2])
    @patch.dict("os.environ", {"GITHUB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_attachment_comment_posted_on_create(
        self,
        mock_subprocess,
        mock_which,
        mock_emit,
        base_context: WorkflowContext,
    ) -> None:
        """When fetch-issue and plan data exist, gh pr comment is called after PR create."""
        _write_fetch_issue_and_plan_to_context(base_context)
        base_context.data["pr_details"] = {
            "title": "Test PR",
            "summary": "Summary",
            "commits": [],
        }

        mock_which.return_value = "/usr/bin/gh"
        mock_subprocess.side_effect = _make_subprocess_side_effect()

        step = GhPullRequestStep()
        result = step.run(base_context)

        assert result.success is True

        comment_calls = [
            c for c in mock_subprocess.call_args_list if c[0][0][:3] == ["gh", "pr", "comment"]
        ]
        assert len(comment_calls) == 1
        comment_cmd = comment_calls[0][0][0]
        assert any("<!-- rouge-review-context -->" in arg for arg in comment_cmd)
        assert "99" in comment_cmd

    @patch(_ATTACHMENT_PATCHES[0])
    @patch(_ATTACHMENT_PATCHES[1])
    @patch(_ATTACHMENT_PATCHES[2])
    @patch.dict("os.environ", {"GITHUB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_attachment_skipped_when_data_missing(
        self,
        mock_subprocess,
        mock_which,
        mock_emit,
        base_context: WorkflowContext,
    ) -> None:
        """No attachment subprocess calls when fetch-issue/plan data are absent."""
        # Only write pr_details -- no fetch-issue or plan
        base_context.data["pr_details"] = {
            "title": "Test PR",
            "summary": "Summary",
            "commits": [],
        }

        mock_which.return_value = "/usr/bin/gh"
        mock_subprocess.side_effect = _make_subprocess_side_effect()

        step = GhPullRequestStep()
        result = step.run(base_context)

        assert result.success is True

        for c in mock_subprocess.call_args_list:
            cmd_str = " ".join(c[0][0])
            assert not (
                "pr" in cmd_str and "view" in cmd_str
            ), "gh pr view should not be called when attachment is None"
            has_attachment_comment = (
                "pr" in cmd_str and "comment" in cmd_str and "rouge-review-context" in cmd_str
            )
            assert not has_attachment_comment, "gh pr comment for attachment should not be called"

    @patch(_ATTACHMENT_PATCHES[0])
    @patch(_ATTACHMENT_PATCHES[1])
    @patch(_ATTACHMENT_PATCHES[2])
    @patch.dict("os.environ", {"GITHUB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_attachment_updated_on_rerun(
        self,
        mock_subprocess,
        mock_which,
        mock_emit,
        base_context: WorkflowContext,
    ) -> None:
        """Existing attachment comment found via gh pr view triggers PATCH update."""
        _write_fetch_issue_and_plan_to_context(base_context)
        base_context.data["pr_details"] = {
            "title": "Test PR",
            "summary": "Summary",
            "commits": [],
        }

        mock_which.return_value = "/usr/bin/gh"
        mock_subprocess.side_effect = _make_subprocess_side_effect(existing_comment_id="12345678")

        step = GhPullRequestStep()
        result = step.run(base_context)

        assert result.success is True

        patch_calls = [
            c
            for c in mock_subprocess.call_args_list
            if "api" in " ".join(c[0][0]) and "PATCH" in " ".join(c[0][0])
        ]
        assert len(patch_calls) == 1
        patch_cmd = patch_calls[0][0][0]
        assert any("12345678" in arg for arg in patch_cmd)

        new_comment_calls = [
            c for c in mock_subprocess.call_args_list if c[0][0][:3] == ["gh", "pr", "comment"]
        ]
        assert len(new_comment_calls) == 0

    @patch(_ATTACHMENT_PATCHES[0])
    @patch(_ATTACHMENT_PATCHES[1])
    @patch(_ATTACHMENT_PATCHES[2])
    @patch.dict("os.environ", {"GITHUB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_attachment_failure_does_not_fail_step(
        self,
        mock_subprocess,
        mock_which,
        mock_emit,
        base_context: WorkflowContext,
    ) -> None:
        """Attachment posting failure is caught and the step still returns success."""
        _write_fetch_issue_and_plan_to_context(base_context)
        base_context.data["pr_details"] = {
            "title": "Test PR",
            "summary": "Summary",
            "commits": [],
        }

        mock_which.return_value = "/usr/bin/gh"
        mock_subprocess.side_effect = _make_subprocess_side_effect(
            attachment_error=True,
        )

        step = GhPullRequestStep()
        result = step.run(base_context)

        assert result.success is True
