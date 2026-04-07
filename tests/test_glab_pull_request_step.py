"""Tests for GlabPullRequestStep.

Focuses on:
- Adding --draft flag when pipeline_type is 'thin'
- Omitting --draft flag when pipeline_type is 'full' or 'patch'
- Posting attachment notes on newly created MRs
- Skipping attachment when fetch-issue/plan data are absent
- Updating existing attachment notes on rerun
- Graceful handling of attachment posting failures
"""

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from rouge.core.models import Issue
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.glab_pull_request_step import GlabPullRequestStep
from rouge.core.workflow.types import PlanData

# ---------------------------------------------------------------------------
# Fixtures and helpers for draft-flag tests
# ---------------------------------------------------------------------------


def _subprocess_side_effect(cmd: list[str], **kwargs: Any) -> MagicMock:
    """Simulate subprocess calls for glab MR creation flow."""
    result = MagicMock()
    if cmd[0] == "git" and cmd[1] == "rev-parse":
        result.returncode = 0
        result.stdout = "feature-branch"
    elif cmd[0] == "glab" and cmd[1] == "mr" and cmd[2] == "list":
        result.returncode = 0
        result.stdout = "[]"
    elif cmd[0] == "git" and cmd[1] == "push":
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
    elif cmd[0] == "glab" and cmd[1] == "mr" and cmd[2] == "create":
        result.returncode = 0
        result.stdout = "https://gitlab.com/org/repo/-/merge_requests/17"
    else:
        result.returncode = 0
        result.stdout = ""
    return result


def _make_context(pipeline_type: str) -> WorkflowContext:
    """Create a WorkflowContext with compose-request data and the given pipeline_type."""
    ctx = WorkflowContext(
        adw_id="test-glab-mr",
        issue_id=99,
        repo_paths=["/path/to/repo"],
        pipeline_type=pipeline_type,
    )
    ctx.data["pr_details"] = {
        "title": "MR Title",
        "summary": "MR Summary",
        "commits": [],
    }
    return ctx


def _find_glab_create_cmd(mock_run: MagicMock) -> list[str]:
    """Extract the glab mr create command from mock_run call history."""
    glab_create_calls = [
        call
        for call in mock_run.call_args_list
        if call[0][0][0] == "glab" and call[0][0][2] == "create"
    ]
    assert (
        len(glab_create_calls) == 1
    ), f"Expected exactly 1 glab mr create call, got {len(glab_create_calls)}"
    return glab_create_calls[0][0][0]


# ---------------------------------------------------------------------------
# Fixtures and helpers for attachment tests
# ---------------------------------------------------------------------------


@pytest.fixture
def base_context() -> WorkflowContext:
    """Create a workflow context without any data."""
    return WorkflowContext(
        adw_id="test-glab-pr",
        issue_id=42,
        repo_paths=["/path/to/repo"],
    )


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
    adopt: bool = False,
    existing_note_id: int | None = None,
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

        if "mr" in cmd_str and "list" in cmd_str:
            result = MagicMock()
            result.returncode = 0
            if adopt:
                result.stdout = json.dumps(
                    [{"web_url": "https://gitlab.com/org/repo/-/merge_requests/77", "iid": 77}]
                )
            else:
                result.stdout = "[]"
            return result

        if "push" in cmd_str:
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            return result

        if "mr" in cmd_str and "create" in cmd_str and "note" not in cmd_str:
            result = MagicMock()
            result.returncode = 0
            result.stdout = "https://gitlab.com/org/repo/-/merge_requests/99\n"
            return result

        if "api" in cmd_str and "notes" in cmd_str and "PUT" not in cmd_str:
            if attachment_error:
                raise OSError("network error")
            result = MagicMock()
            result.returncode = 0
            if existing_note_id:
                result.stdout = json.dumps(
                    [{"id": existing_note_id, "body": "<!-- rouge-review-context -->\nold content"}]
                )
            else:
                result.stdout = "[]"
            return result

        if "mr" in cmd_str and "note" in cmd_str:
            if attachment_error:
                raise OSError("network error")
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            return result

        if "api" in cmd_str and "PUT" in cmd_str:
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


_BASE_MODULE = "rouge.core.workflow.pull_request_step_base"
_ATTACHMENT_PATCHES = [
    f"{_BASE_MODULE}._emit_and_log",
    f"{_BASE_MODULE}.subprocess.run",
]


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestGlabPullRequestStepAffectedRepos:
    """Tests for GlabPullRequestStep affected-repos filtering and branch-delta guard."""

    @patch(f"{_BASE_MODULE}._emit_and_log")
    @patch(f"{_BASE_MODULE}.subprocess.run")
    @patch(f"{_BASE_MODULE}.get_affected_repo_paths")
    @patch.dict("os.environ", {"GITLAB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_only_affected_repos_are_iterated(
        self,
        mock_get_affected: MagicMock,
        mock_run: MagicMock,
        mock_emit: MagicMock,
        base_context: WorkflowContext,
    ) -> None:
        """Only repos returned by get_affected_repo_paths are processed."""
        base_context.data["pr_details"] = {
            "title": "Test MR",
            "summary": "Summary",
            "commits": [],
        }
        mock_emit.return_value = ("success", "ok")

        base_context.repo_paths = ["/path/to/repo-a", "/path/to/repo-b"]
        mock_get_affected.return_value = ["/path/to/repo-b"]
        mock_run.side_effect = _subprocess_side_effect

        step = GlabPullRequestStep()
        result = step.run(base_context)

        assert result.success is True
        for call in mock_run.call_args_list:
            cwd = call[1].get("cwd", "")
            assert "repo-a" not in str(cwd)

    @patch(f"{_BASE_MODULE}._emit_and_log")
    @patch(f"{_BASE_MODULE}.get_affected_repo_paths")
    @patch.dict("os.environ", {"GITLAB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_skips_when_zero_affected_repos(
        self,
        mock_get_affected: MagicMock,
        mock_emit: MagicMock,
        base_context: WorkflowContext,
    ) -> None:
        """Step returns success and writes empty data when no repos are affected."""
        base_context.data["pr_details"] = {
            "title": "Test MR",
            "summary": "Summary",
            "commits": [],
        }
        mock_get_affected.return_value = []

        step = GlabPullRequestStep()
        result = step.run(base_context)

        assert result.success is True
        pr_data = base_context.data.get("glab-pull-request", {})
        assert pr_data.get("pull_requests") == []

    @patch(f"{_BASE_MODULE}._emit_and_log")
    @patch(f"{_BASE_MODULE}.subprocess.run")
    @patch.dict("os.environ", {"GITLAB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_branch_delta_guard_prevents_empty_mr(
        self,
        mock_run: MagicMock,
        mock_emit: MagicMock,
        base_context: WorkflowContext,
    ) -> None:
        """When branch has zero commits ahead of base, MR creation is skipped."""
        base_context.data["pr_details"] = {
            "title": "Test MR",
            "summary": "Summary",
            "commits": [],
        }
        mock_emit.return_value = ("success", "ok")

        def _delta_guard_side_effect(cmd: list[str], **_kwargs: Any) -> MagicMock:
            result = MagicMock()
            if cmd[0] == "git" and "rev-parse" in cmd:
                if "--abbrev-ref" in cmd and "origin/HEAD" in cmd:
                    result.returncode = 0
                    result.stdout = "origin/main\n"
                else:
                    result.returncode = 0
                    result.stdout = "feature-branch\n"
            elif cmd[0] == "glab" and cmd[1] == "mr" and cmd[2] == "list":
                result.returncode = 0
                result.stdout = "[]"
            elif cmd[0] == "git" and "rev-list" in cmd:
                result.returncode = 0
                result.stdout = "0\n"
            else:
                result.returncode = 0
                result.stdout = ""
            return result

        mock_run.side_effect = _delta_guard_side_effect

        step = GlabPullRequestStep()
        result = step.run(base_context)

        assert result.success is True
        glab_create_calls = [
            c
            for c in mock_run.call_args_list
            if len(c[0][0]) >= 3 and c[0][0][0] == "glab" and c[0][0][2] == "create"
        ]
        assert len(glab_create_calls) == 0


class TestGlabPullRequestStepDraftFlag:
    """Tests verifying GlabPullRequestStep adds --draft flag based on pipeline_type."""

    @patch("rouge.core.workflow.pull_request_step_base._emit_and_log")
    @patch("rouge.core.workflow.pull_request_step_base.subprocess.run")
    @patch("rouge.core.workflow.pull_request_step_base.os.environ", new_callable=dict)
    def test_thin_pipeline_includes_draft_flag(
        self,
        mock_environ,
        mock_run,
        mock_emit_and_log,
    ) -> None:
        """When pipeline_type is 'thin', glab mr create command includes --draft."""
        mock_environ["GITLAB_PAT"] = "fake-token"
        mock_run.side_effect = _subprocess_side_effect

        context = _make_context(pipeline_type="thin")

        step = GlabPullRequestStep()
        result = step.run(context)

        assert result.success is True
        cmd_args = _find_glab_create_cmd(mock_run)
        assert "--draft" in cmd_args

    @patch("rouge.core.workflow.pull_request_step_base._emit_and_log")
    @patch("rouge.core.workflow.pull_request_step_base.subprocess.run")
    @patch("rouge.core.workflow.pull_request_step_base.os.environ", new_callable=dict)
    def test_full_pipeline_omits_draft_flag(
        self,
        mock_environ,
        mock_run,
        mock_emit_and_log,
    ) -> None:
        """When pipeline_type is 'full', glab mr create command does not include --draft."""
        mock_environ["GITLAB_PAT"] = "fake-token"
        mock_run.side_effect = _subprocess_side_effect

        context = _make_context(pipeline_type="full")

        step = GlabPullRequestStep()
        result = step.run(context)

        assert result.success is True
        cmd_args = _find_glab_create_cmd(mock_run)
        assert "--draft" not in cmd_args

    @patch("rouge.core.workflow.pull_request_step_base._emit_and_log")
    @patch("rouge.core.workflow.pull_request_step_base.subprocess.run")
    @patch("rouge.core.workflow.pull_request_step_base.os.environ", new_callable=dict)
    def test_patch_pipeline_omits_draft_flag(
        self,
        mock_environ,
        mock_run,
        mock_emit_and_log,
    ) -> None:
        """When pipeline_type is 'patch', glab mr create command does not include --draft."""
        mock_environ["GITLAB_PAT"] = "fake-token"
        mock_run.side_effect = _subprocess_side_effect

        context = _make_context(pipeline_type="patch")

        step = GlabPullRequestStep()
        result = step.run(context)

        assert result.success is True
        cmd_args = _find_glab_create_cmd(mock_run)
        assert "--draft" not in cmd_args


class TestGlabPullRequestStepAttachment:
    """Tests for attachment note posting/updating on GitLab merge requests."""

    @patch(_ATTACHMENT_PATCHES[0])
    @patch(_ATTACHMENT_PATCHES[1])
    @patch.dict("os.environ", {"GITLAB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_attachment_note_posted_on_create(
        self,
        mock_subprocess: MagicMock,
        mock_emit: MagicMock,
        base_context: WorkflowContext,
    ) -> None:
        """When fetch-issue and plan data exist, glab mr note is called after MR create."""
        _write_fetch_issue_and_plan_to_context(base_context)
        base_context.data["pr_details"] = {
            "title": "Test MR",
            "summary": "Summary",
            "commits": [],
        }

        mock_emit.return_value = ("success", "ok")
        mock_subprocess.side_effect = _make_subprocess_side_effect()

        step = GlabPullRequestStep()
        result = step.run(base_context)

        assert result.success is True

        note_create_calls = [
            c
            for c in mock_subprocess.call_args_list
            if len(c[0][0]) >= 4
            and c[0][0][0] == "glab"
            and c[0][0][1] == "mr"
            and c[0][0][2] == "note"
            and c[0][0][3] == "99"
        ]
        assert len(note_create_calls) == 1
        note_cmd = note_create_calls[0][0][0]
        assert any("<!-- rouge-review-context -->" in arg for arg in note_cmd)
        assert "99" in note_cmd
        assert "create" not in note_cmd

    @patch(_ATTACHMENT_PATCHES[0])
    @patch(_ATTACHMENT_PATCHES[1])
    @patch.dict("os.environ", {"GITLAB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_attachment_skipped_when_data_missing(
        self,
        mock_subprocess: MagicMock,
        mock_emit: MagicMock,
        base_context: WorkflowContext,
    ) -> None:
        """No attachment subprocess calls when fetch-issue/plan data are absent."""
        base_context.data["pr_details"] = {
            "title": "Test MR",
            "summary": "Summary",
            "commits": [],
        }

        mock_emit.return_value = ("success", "ok")
        mock_subprocess.side_effect = _make_subprocess_side_effect()

        step = GlabPullRequestStep()
        result = step.run(base_context)

        assert result.success is True

        for c in mock_subprocess.call_args_list:
            cmd_str = " ".join(c[0][0])
            assert not (
                "api" in cmd_str and "notes" in cmd_str
            ), "glab api notes listing should not be called when attachment is None"
            has_note_cmd = (
                "glab" in cmd_str and "mr" in cmd_str and "note" in cmd_str and "api" not in cmd_str
            )
            assert not has_note_cmd, "glab mr note should not be called"
            has_api_put = "api" in cmd_str and "PUT" in cmd_str
            assert not has_api_put, "glab api PUT should not be called"

    @patch(_ATTACHMENT_PATCHES[0])
    @patch(_ATTACHMENT_PATCHES[1])
    @patch.dict("os.environ", {"GITLAB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_attachment_updated_on_rerun(
        self,
        mock_subprocess: MagicMock,
        mock_emit: MagicMock,
        base_context: WorkflowContext,
    ) -> None:
        """Existing attachment note found via glab api triggers PUT update."""
        _write_fetch_issue_and_plan_to_context(base_context)
        base_context.data["pr_details"] = {
            "title": "Test MR",
            "summary": "Summary",
            "commits": [],
        }

        mock_emit.return_value = ("success", "ok")
        mock_subprocess.side_effect = _make_subprocess_side_effect(existing_note_id=5001)

        step = GlabPullRequestStep()
        result = step.run(base_context)

        assert result.success is True

        put_calls = [
            c
            for c in mock_subprocess.call_args_list
            if "api" in " ".join(c[0][0]) and "PUT" in " ".join(c[0][0])
        ]
        assert len(put_calls) == 1
        put_cmd = put_calls[0][0][0]
        assert any("5001" in arg for arg in put_cmd)

        note_create_calls = [
            c
            for c in mock_subprocess.call_args_list
            if len(c[0][0]) >= 4
            and c[0][0][0] == "glab"
            and c[0][0][1] == "mr"
            and c[0][0][2] == "note"
            and c[0][0][3].isdigit()
        ]
        assert len(note_create_calls) == 0

    @patch(_ATTACHMENT_PATCHES[0])
    @patch(_ATTACHMENT_PATCHES[1])
    @patch.dict("os.environ", {"GITLAB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_attachment_failure_does_not_fail_step(
        self,
        mock_subprocess: MagicMock,
        mock_emit: MagicMock,
        base_context: WorkflowContext,
    ) -> None:
        """Attachment posting failure is caught and the step still returns success."""
        _write_fetch_issue_and_plan_to_context(base_context)
        base_context.data["pr_details"] = {
            "title": "Test MR",
            "summary": "Summary",
            "commits": [],
        }

        mock_emit.return_value = ("success", "ok")
        mock_subprocess.side_effect = _make_subprocess_side_effect(attachment_error=True)

        step = GlabPullRequestStep()
        result = step.run(base_context)

        assert result.success is True
