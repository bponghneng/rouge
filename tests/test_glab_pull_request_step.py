"""Tests for GlabPullRequestStep.

Focuses on:
- Adding --draft flag when pipeline_type is 'thin'
- Omitting --draft flag when pipeline_type is 'full' or 'patch'
- Posting attachment notes on newly created MRs
- Posting attachment notes on adopted MRs
- Skipping attachment when fetch-issue/plan artifacts are absent
- Updating existing attachment notes on rerun
- Graceful handling of attachment posting failures
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from rouge.core.models import Issue
from rouge.core.workflow.artifacts import (
    ArtifactStore,
    ComposeRequestArtifact,
    FetchIssueArtifact,
    PlanArtifact,
)
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.glab_pull_request_step import GlabPullRequestStep
from rouge.core.workflow.types import PlanData

# ---------------------------------------------------------------------------
# Fixtures and helpers for draft-flag tests
# ---------------------------------------------------------------------------


@pytest.fixture
def store_mr(tmp_path: Path) -> ArtifactStore:
    """Create a temporary artifact store for draft-flag tests."""
    return ArtifactStore(workflow_id="test-glab-mr", base_path=tmp_path)


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


def _make_context(store: ArtifactStore, pipeline_type: str) -> WorkflowContext:
    """Create a WorkflowContext with a compose-request artifact and the given pipeline_type."""
    compose_artifact = ComposeRequestArtifact(
        workflow_id="test-glab-mr",
        title="MR Title",
        summary="MR Summary",
        commits=[],
    )
    store.write_artifact(compose_artifact)

    return WorkflowContext(
        adw_id="test-glab-mr",
        issue_id=99,
        artifact_store=store,
        repo_paths=["/path/to/repo"],
        pipeline_type=pipeline_type,
    )


def _find_glab_create_cmd(mock_run: MagicMock) -> list[str]:
    """Extract the glab mr create command from mock_run call history."""
    glab_create_calls = [
        call
        for call in mock_run.call_args_list
        if call[0][0][0] == "glab" and call[0][0][2] == "create"
    ]
    assert len(glab_create_calls) == 1, (
        f"Expected exactly 1 glab mr create call, got {len(glab_create_calls)}"
    )
    return glab_create_calls[0][0][0]


# ---------------------------------------------------------------------------
# Fixtures and helpers for attachment tests
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    """Create a temporary artifact store for attachment tests."""
    return ArtifactStore(workflow_id="test-glab-pr", base_path=tmp_path)


@pytest.fixture
def base_context(store: ArtifactStore) -> WorkflowContext:
    """Create a workflow context without any artifacts."""
    return WorkflowContext(
        adw_id="test-glab-pr",
        issue_id=42,
        artifact_store=store,
        repo_paths=["/path/to/repo"],
    )


def _write_fetch_issue_and_plan_artifacts(store: ArtifactStore) -> None:
    """Write fetch-issue and plan artifacts to the store for attachment tests."""
    issue = Issue(
        id=42,
        description="Implement feature X with Y integration",
        status="started",
        type="full",
    )
    store.write_artifact(FetchIssueArtifact(workflow_id="test-glab-pr", issue=issue))
    store.write_artifact(
        PlanArtifact(
            workflow_id="test-glab-pr",
            plan_data=PlanData(
                plan="1. Add module\n2. Write tests",
                summary="Add module and tests",
            ),
        )
    )


def _make_subprocess_side_effect(
    *,
    adopt: bool = False,
    existing_note_id: int | None = None,
    attachment_error: bool = False,
) -> object:
    """Build a side_effect callable for subprocess.run.

    Handles the standard sequence of subprocess calls made by the step:
    git rev-parse, glab mr list (adopt check), git push, glab mr create,
    glab api (note listing), and glab mr note / glab api PUT.

    Args:
        adopt: If True, glab mr list returns an existing MR to adopt.
        existing_note_id: If set, the notes listing returns a note with this
            ID containing the rouge-review-context marker, triggering a PUT.
        attachment_error: If True, raise OSError for attachment-related
            subprocess calls.
    """

    def _side_effect(cmd: list[str], **_kwargs: object) -> MagicMock:
        cmd_str = " ".join(cmd)

        # git rev-parse --abbrev-ref HEAD
        if "rev-parse" in cmd_str:
            result = MagicMock()
            result.returncode = 0
            result.stdout = "adw-test-branch\n"
            return result

        # glab mr list --source-branch ... (adopt check)
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

        # git push
        if "push" in cmd_str:
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            return result

        # glab mr create
        if "mr" in cmd_str and "create" in cmd_str and "note" not in cmd_str:
            result = MagicMock()
            result.returncode = 0
            result.stdout = "https://gitlab.com/org/repo/-/merge_requests/99\n"
            return result

        # glab api projects/:id/merge_requests/.../notes (list notes)
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

        # glab mr note (new attachment note)
        if "mr" in cmd_str and "note" in cmd_str:
            if attachment_error:
                raise OSError("network error")
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            return result

        # glab api --method PUT (update attachment note)
        if "api" in cmd_str and "PUT" in cmd_str:
            if attachment_error:
                raise OSError("network error")
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            return result

        # Fallback
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        return result

    return _side_effect


# Shared patch targets for attachment tests.
_STEP_MODULE = "rouge.core.workflow.steps.glab_pull_request_step"
_BASE_MODULE = "rouge.core.workflow.pull_request_step_base"
_ATTACHMENT_PATCHES = [
    f"{_BASE_MODULE}._emit_and_log",
    f"{_BASE_MODULE}.emit_artifact_comment",
    f"{_BASE_MODULE}.log_artifact_comment_status",
    f"{_BASE_MODULE}.subprocess.run",
]


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestGlabPullRequestStepAffectedRepos:
    """Tests for GlabPullRequestStep affected-repos filtering and branch-delta guard."""

    @patch(f"{_BASE_MODULE}._emit_and_log")
    @patch(f"{_BASE_MODULE}.emit_artifact_comment")
    @patch(f"{_BASE_MODULE}.log_artifact_comment_status")
    @patch(f"{_BASE_MODULE}.subprocess.run")
    @patch(f"{_BASE_MODULE}.get_affected_repo_paths")
    @patch.dict("os.environ", {"GITLAB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_only_affected_repos_are_iterated(
        self,
        mock_get_affected: MagicMock,
        mock_run: MagicMock,
        _mock_log: MagicMock,
        mock_emit_artifact: MagicMock,
        mock_emit: MagicMock,
        base_context: WorkflowContext,
        store: ArtifactStore,
    ) -> None:
        """Only repos returned by get_affected_repo_paths are processed."""
        store.write_artifact(
            ComposeRequestArtifact(
                workflow_id="test-glab-pr",
                title="Test MR",
                summary="Summary",
                commits=[],
            )
        )
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")

        # Context has two repos, but only one is affected
        base_context.repo_paths = ["/path/to/repo-a", "/path/to/repo-b"]
        mock_get_affected.return_value = ["/path/to/repo-b"]
        mock_run.side_effect = _subprocess_side_effect

        step = GlabPullRequestStep()
        result = step.run(base_context)

        assert result.success is True
        # All subprocess calls should use repo-b, not repo-a
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
        store: ArtifactStore,
    ) -> None:
        """Step returns success and writes empty artifact when no repos are affected."""
        store.write_artifact(
            ComposeRequestArtifact(
                workflow_id="test-glab-pr",
                title="Test MR",
                summary="Summary",
                commits=[],
            )
        )
        mock_get_affected.return_value = []

        step = GlabPullRequestStep()
        result = step.run(base_context)

        assert result.success is True
        artifact = store.read_artifact("glab-pull-request")
        assert artifact.pull_requests == []

    @patch(f"{_BASE_MODULE}._emit_and_log")
    @patch(f"{_BASE_MODULE}.emit_artifact_comment")
    @patch(f"{_BASE_MODULE}.log_artifact_comment_status")
    @patch(f"{_BASE_MODULE}.subprocess.run")
    @patch.dict("os.environ", {"GITLAB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_branch_delta_guard_prevents_empty_mr(
        self,
        mock_run: MagicMock,
        _mock_log: MagicMock,
        mock_emit_artifact: MagicMock,
        mock_emit: MagicMock,
        base_context: WorkflowContext,
        store: ArtifactStore,
    ) -> None:
        """When branch has zero commits ahead of base, MR creation is skipped."""
        store.write_artifact(
            ComposeRequestArtifact(
                workflow_id="test-glab-pr",
                title="Test MR",
                summary="Summary",
                commits=[],
            )
        )
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")

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
                # Zero commits ahead
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
        # No glab mr create call should have been made
        glab_create_calls = [
            c
            for c in mock_run.call_args_list
            if len(c[0][0]) >= 3 and c[0][0][0] == "glab" and c[0][0][2] == "create"
        ]
        assert len(glab_create_calls) == 0


class TestGlabPullRequestStepDraftFlag:
    """Tests verifying GlabPullRequestStep adds --draft flag based on pipeline_type."""

    @patch("rouge.core.workflow.pull_request_step_base._emit_and_log")
    @patch("rouge.core.workflow.pull_request_step_base.emit_artifact_comment")
    @patch("rouge.core.workflow.pull_request_step_base.log_artifact_comment_status")
    @patch("rouge.core.workflow.pull_request_step_base.subprocess.run")
    @patch("rouge.core.workflow.pull_request_step_base.os.environ", new_callable=dict)
    def test_thin_pipeline_includes_draft_flag(
        self,
        mock_environ,
        mock_run,
        _mock_log,
        mock_emit_artifact,
        mock_emit_and_log,
        store_mr: ArtifactStore,
    ) -> None:
        """When pipeline_type is 'thin', glab mr create command includes --draft."""
        mock_environ["GITLAB_PAT"] = "fake-token"
        mock_emit_artifact.return_value = ("success", "ok")
        mock_run.side_effect = _subprocess_side_effect

        context = _make_context(store_mr, pipeline_type="thin")

        step = GlabPullRequestStep()
        result = step.run(context)

        assert result.success is True
        cmd_args = _find_glab_create_cmd(mock_run)
        assert "--draft" in cmd_args

    @patch("rouge.core.workflow.pull_request_step_base._emit_and_log")
    @patch("rouge.core.workflow.pull_request_step_base.emit_artifact_comment")
    @patch("rouge.core.workflow.pull_request_step_base.log_artifact_comment_status")
    @patch("rouge.core.workflow.pull_request_step_base.subprocess.run")
    @patch("rouge.core.workflow.pull_request_step_base.os.environ", new_callable=dict)
    def test_full_pipeline_omits_draft_flag(
        self,
        mock_environ,
        mock_run,
        _mock_log,
        mock_emit_artifact,
        mock_emit_and_log,
        store_mr: ArtifactStore,
    ) -> None:
        """When pipeline_type is 'full', glab mr create command does not include --draft."""
        mock_environ["GITLAB_PAT"] = "fake-token"
        mock_emit_artifact.return_value = ("success", "ok")
        mock_run.side_effect = _subprocess_side_effect

        context = _make_context(store_mr, pipeline_type="full")

        step = GlabPullRequestStep()
        result = step.run(context)

        assert result.success is True
        cmd_args = _find_glab_create_cmd(mock_run)
        assert "--draft" not in cmd_args

    @patch("rouge.core.workflow.pull_request_step_base._emit_and_log")
    @patch("rouge.core.workflow.pull_request_step_base.emit_artifact_comment")
    @patch("rouge.core.workflow.pull_request_step_base.log_artifact_comment_status")
    @patch("rouge.core.workflow.pull_request_step_base.subprocess.run")
    @patch("rouge.core.workflow.pull_request_step_base.os.environ", new_callable=dict)
    def test_patch_pipeline_omits_draft_flag(
        self,
        mock_environ,
        mock_run,
        _mock_log,
        mock_emit_artifact,
        mock_emit_and_log,
        store_mr: ArtifactStore,
    ) -> None:
        """When pipeline_type is 'patch', glab mr create command does not include --draft."""
        mock_environ["GITLAB_PAT"] = "fake-token"
        mock_emit_artifact.return_value = ("success", "ok")
        mock_run.side_effect = _subprocess_side_effect

        context = _make_context(store_mr, pipeline_type="patch")

        step = GlabPullRequestStep()
        result = step.run(context)

        assert result.success is True
        cmd_args = _find_glab_create_cmd(mock_run)
        assert "--draft" not in cmd_args


class TestGlabPullRequestStepAttachment:
    """Tests for attachment note posting/updating on GitLab merge requests."""

    @patch(_ATTACHMENT_PATCHES[0])
    @patch(_ATTACHMENT_PATCHES[1])
    @patch(_ATTACHMENT_PATCHES[2])
    @patch(_ATTACHMENT_PATCHES[3])
    @patch.dict("os.environ", {"GITLAB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_attachment_note_posted_on_create(
        self,
        mock_subprocess: MagicMock,
        _mock_log: MagicMock,
        mock_emit_artifact: MagicMock,
        mock_emit: MagicMock,
        base_context: WorkflowContext,
        store: ArtifactStore,
    ) -> None:
        """When fetch-issue and plan artifacts exist, glab mr note is called
        after MR create."""
        _write_fetch_issue_and_plan_artifacts(store)
        store.write_artifact(
            ComposeRequestArtifact(
                workflow_id="test-glab-pr",
                title="Test MR",
                summary="Summary",
                commits=[],
            )
        )

        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")
        mock_subprocess.side_effect = _make_subprocess_side_effect()

        step = GlabPullRequestStep()
        result = step.run(base_context)

        assert result.success is True

        # Find the glab mr note call
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
        # Should contain the marker
        assert any("<!-- rouge-review-context -->" in arg for arg in note_cmd)
        # Should contain the MR number
        assert "99" in note_cmd
        # Regression: "create" must not appear in the note command
        assert "create" not in note_cmd

    @patch(_ATTACHMENT_PATCHES[0])
    @patch(_ATTACHMENT_PATCHES[1])
    @patch(_ATTACHMENT_PATCHES[2])
    @patch(_ATTACHMENT_PATCHES[3])
    @patch.dict("os.environ", {"GITLAB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_attachment_note_posted_on_adopt(
        self,
        mock_subprocess: MagicMock,
        _mock_log: MagicMock,
        mock_emit_artifact: MagicMock,
        mock_emit: MagicMock,
        base_context: WorkflowContext,
        store: ArtifactStore,
    ) -> None:
        """When an existing MR is adopted, attachment note is posted on the adopted MR."""
        _write_fetch_issue_and_plan_artifacts(store)
        store.write_artifact(
            ComposeRequestArtifact(
                workflow_id="test-glab-pr",
                title="Test MR",
                summary="Summary",
                commits=[],
            )
        )

        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")
        mock_subprocess.side_effect = _make_subprocess_side_effect(adopt=True)

        step = GlabPullRequestStep()
        result = step.run(base_context)

        assert result.success is True

        # Find the glab mr note call
        note_create_calls = [
            c
            for c in mock_subprocess.call_args_list
            if len(c[0][0]) >= 4
            and c[0][0][0] == "glab"
            and c[0][0][1] == "mr"
            and c[0][0][2] == "note"
            and c[0][0][3] == "77"
        ]
        assert len(note_create_calls) == 1
        note_cmd = note_create_calls[0][0][0]
        assert any("<!-- rouge-review-context -->" in arg for arg in note_cmd)
        # Should reference MR 77 (the adopted MR)
        assert "77" in note_cmd
        # Regression: "create" must not appear in the note command
        assert "create" not in note_cmd

    @patch(_ATTACHMENT_PATCHES[0])
    @patch(_ATTACHMENT_PATCHES[1])
    @patch(_ATTACHMENT_PATCHES[2])
    @patch(_ATTACHMENT_PATCHES[3])
    @patch.dict("os.environ", {"GITLAB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_attachment_skipped_when_artifacts_missing(
        self,
        mock_subprocess: MagicMock,
        _mock_log: MagicMock,
        mock_emit_artifact: MagicMock,
        mock_emit: MagicMock,
        base_context: WorkflowContext,
        store: ArtifactStore,
    ) -> None:
        """No attachment subprocess calls when fetch-issue/plan artifacts are absent."""
        # Only write compose-request -- no fetch-issue or plan
        store.write_artifact(
            ComposeRequestArtifact(
                workflow_id="test-glab-pr",
                title="Test MR",
                summary="Summary",
                commits=[],
            )
        )

        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")
        mock_subprocess.side_effect = _make_subprocess_side_effect()

        step = GlabPullRequestStep()
        result = step.run(base_context)

        assert result.success is True

        # No attachment-related calls: no notes listing, no note create, no api PUT
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
    @patch(_ATTACHMENT_PATCHES[2])
    @patch(_ATTACHMENT_PATCHES[3])
    @patch.dict("os.environ", {"GITLAB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_attachment_updated_on_rerun(
        self,
        mock_subprocess: MagicMock,
        _mock_log: MagicMock,
        mock_emit_artifact: MagicMock,
        mock_emit: MagicMock,
        base_context: WorkflowContext,
        store: ArtifactStore,
    ) -> None:
        """Existing attachment note found via glab api triggers PUT update."""
        _write_fetch_issue_and_plan_artifacts(store)
        store.write_artifact(
            ComposeRequestArtifact(
                workflow_id="test-glab-pr",
                title="Test MR",
                summary="Summary",
                commits=[],
            )
        )

        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")
        mock_subprocess.side_effect = _make_subprocess_side_effect(existing_note_id=5001)

        step = GlabPullRequestStep()
        result = step.run(base_context)

        assert result.success is True

        # Should have a glab api PUT call
        put_calls = [
            c
            for c in mock_subprocess.call_args_list
            if "api" in " ".join(c[0][0]) and "PUT" in " ".join(c[0][0])
        ]
        assert len(put_calls) == 1
        put_cmd = put_calls[0][0][0]
        # Should reference the existing note ID in the URL
        assert any("5001" in arg for arg in put_cmd)

        # Should NOT have a glab mr note call (note was updated via API PUT instead)
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
    @patch(_ATTACHMENT_PATCHES[2])
    @patch(_ATTACHMENT_PATCHES[3])
    @patch.dict("os.environ", {"GITLAB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_attachment_failure_does_not_fail_step(
        self,
        mock_subprocess: MagicMock,
        _mock_log: MagicMock,
        mock_emit_artifact: MagicMock,
        mock_emit: MagicMock,
        base_context: WorkflowContext,
        store: ArtifactStore,
    ) -> None:
        """Attachment posting failure is caught and the step still returns success."""
        _write_fetch_issue_and_plan_artifacts(store)
        store.write_artifact(
            ComposeRequestArtifact(
                workflow_id="test-glab-pr",
                title="Test MR",
                summary="Summary",
                commits=[],
            )
        )

        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")
        mock_subprocess.side_effect = _make_subprocess_side_effect(attachment_error=True)

        step = GlabPullRequestStep()
        result = step.run(base_context)

        # Step should still succeed despite attachment posting failure
        assert result.success is True
