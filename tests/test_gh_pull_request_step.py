"""Tests for GhPullRequestStep dependency contract.

Focuses on:
- Succeeding (graceful skip) when compose-request artifact is absent
  (optional dependency declared in registry)
- Loading PR details from artifact when present
- Adding --draft flag based on pipeline_type
- Attachment comment posting, updating, and error handling
"""

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
def store(tmp_path) -> ArtifactStore:
    """Create a temporary artifact store."""
    return ArtifactStore(workflow_id="test-gh-pr", base_path=tmp_path)


@pytest.fixture
def base_context(store: ArtifactStore) -> WorkflowContext:
    """Create a workflow context without any artifacts."""
    return WorkflowContext(
        adw_id="test-gh-pr",
        issue_id=42,
        artifact_store=store,
        repo_paths=["/path/to/repo"],
    )


class TestGhPullRequestStepOptionalDependency:
    """Tests verifying GhPullRequestStep handles absent compose-request artifact gracefully."""

    @patch("rouge.core.workflow.steps.gh_pull_request_step._emit_and_log")
    def test_succeeds_when_compose_request_artifact_absent(
        self, mock_emit, base_context: WorkflowContext
    ) -> None:
        """Step returns success when compose-request artifact is missing (optional dep)."""

        step = GhPullRequestStep()
        result = step.run(base_context)

        # Must succeed (not fail) — optional dependency is missing
        assert result.success is True
        assert result.error is None

    @patch("rouge.core.workflow.steps.gh_pull_request_step._emit_and_log")
    def test_emits_skip_comment_when_artifact_absent(
        self, mock_emit, base_context: WorkflowContext
    ) -> None:
        """Step emits an informative skip comment when compose-request artifact is missing."""

        step = GhPullRequestStep()
        result = step.run(base_context)

        assert result.success is True
        assert mock_emit.called
        text = mock_emit.call_args[0][2]
        # Message should indicate skip reason
        assert "skip" in text.lower() or "no pr details" in text.lower()

    @patch("rouge.core.workflow.steps.gh_pull_request_step._emit_and_log")
    def test_loads_pr_details_via_optional_artifact(
        self, mock_emit, base_context: WorkflowContext, store: ArtifactStore
    ) -> None:
        """load_optional_artifact is used (not a guard-and-fail pattern)."""

        # Track read calls to confirm artifact loading is attempted
        read_calls: list[str] = []
        original_read = store.read_artifact

        def tracking_read(artifact_type, model_class=None):
            read_calls.append(artifact_type)
            return original_read(artifact_type, model_class)

        with patch.object(store, "read_artifact", side_effect=tracking_read):
            step = GhPullRequestStep()
            result = step.run(base_context)

        assert result.success is True
        # Artifact loading was attempted for compose-request
        assert "compose-request" in read_calls

    @patch("rouge.core.workflow.steps.gh_pull_request_step._emit_and_log")
    def test_does_not_raise_when_artifact_absent(
        self, mock_emit, base_context: WorkflowContext
    ) -> None:
        """No exception is raised when compose-request artifact is absent."""

        step = GhPullRequestStep()
        # Should not raise
        result = step.run(base_context)
        assert result is not None


class TestGhPullRequestStepWithArtifact:
    """Tests verifying GhPullRequestStep uses compose-request artifact when present."""

    @patch("rouge.core.workflow.steps.gh_pull_request_step._emit_and_log")
    @patch("rouge.core.workflow.steps.gh_pull_request_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.gh_pull_request_step.log_artifact_comment_status")
    @patch("rouge.core.workflow.steps.gh_pull_request_step.shutil.which")
    def test_uses_compose_request_artifact_when_present(
        self,
        mock_which,
        _mock_log,
        mock_emit_artifact,
        mock_emit,
        base_context: WorkflowContext,
        store: ArtifactStore,
    ) -> None:
        """Step reads PR details from compose-request artifact when it exists."""
        # Write compose-request artifact
        compose_artifact = ComposeRequestArtifact(
            workflow_id="test-gh-pr",
            title="My PR Title",
            summary="My PR Summary",
            commits=[],
        )
        store.write_artifact(compose_artifact)

        mock_emit_artifact.return_value = ("success", "ok")
        mock_which.return_value = None  # gh CLI not found → graceful skip

        step = GhPullRequestStep()
        result = step.run(base_context)

        # Step should succeed (either skip due to missing gh or GITHUB_PAT)
        assert result.success is True


class TestGhPullRequestStepDraftFlag:
    """Tests verifying GhPullRequestStep adds --draft flag based on pipeline_type."""

    @patch("rouge.core.workflow.steps.gh_pull_request_step._emit_and_log")
    @patch("rouge.core.workflow.steps.gh_pull_request_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.gh_pull_request_step.log_artifact_comment_status")
    @patch("rouge.core.workflow.steps.gh_pull_request_step.shutil.which")
    @patch("rouge.core.workflow.steps.gh_pull_request_step.subprocess.run")
    @patch("rouge.core.workflow.steps.gh_pull_request_step.os.environ", new_callable=dict)
    def test_thin_pipeline_includes_draft_flag(
        self,
        mock_environ,
        mock_run,
        mock_which,
        _mock_log,
        mock_emit_artifact,
        mock_emit,
        store: ArtifactStore,
    ) -> None:
        """When pipeline_type is 'thin', gh pr create command includes --draft."""
        mock_environ["GITHUB_PAT"] = "fake-token"
        mock_environ["PATH"] = "/usr/bin"
        mock_which.return_value = "/usr/bin/gh"
        mock_emit_artifact.return_value = ("success", "ok")

        # Write compose-request artifact so the step proceeds to PR creation
        compose_artifact = ComposeRequestArtifact(
            workflow_id="test-gh-pr",
            title="Draft PR",
            summary="Summary",
            commits=[],
        )
        store.write_artifact(compose_artifact)

        context = WorkflowContext(
            adw_id="test-gh-pr",
            issue_id=42,
            artifact_store=store,
            repo_paths=["/path/to/repo"],
            pipeline_type="thin",
        )

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

    @patch("rouge.core.workflow.steps.gh_pull_request_step._emit_and_log")
    @patch("rouge.core.workflow.steps.gh_pull_request_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.gh_pull_request_step.log_artifact_comment_status")
    @patch("rouge.core.workflow.steps.gh_pull_request_step.shutil.which")
    @patch("rouge.core.workflow.steps.gh_pull_request_step.subprocess.run")
    @patch("rouge.core.workflow.steps.gh_pull_request_step.os.environ", new_callable=dict)
    def test_full_pipeline_omits_draft_flag(
        self,
        mock_environ,
        mock_run,
        mock_which,
        _mock_log,
        mock_emit_artifact,
        mock_emit,
        store: ArtifactStore,
    ) -> None:
        """When pipeline_type is 'full', gh pr create command does not include --draft."""
        mock_environ["GITHUB_PAT"] = "fake-token"
        mock_environ["PATH"] = "/usr/bin"
        mock_which.return_value = "/usr/bin/gh"
        mock_emit_artifact.return_value = ("success", "ok")

        compose_artifact = ComposeRequestArtifact(
            workflow_id="test-gh-pr",
            title="Full PR",
            summary="Summary",
            commits=[],
        )
        store.write_artifact(compose_artifact)

        context = WorkflowContext(
            adw_id="test-gh-pr",
            issue_id=42,
            artifact_store=store,
            repo_paths=["/path/to/repo"],
            pipeline_type="full",
        )

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


def _write_fetch_issue_and_plan_artifacts(store: ArtifactStore) -> None:
    """Write fetch-issue and plan artifacts to the store for attachment tests."""
    issue = Issue(
        id=42,
        description="Implement feature X with Y integration",
        status="started",
        type="full",
    )
    store.write_artifact(FetchIssueArtifact(workflow_id="test-gh-pr", issue=issue))
    store.write_artifact(
        PlanArtifact(
            workflow_id="test-gh-pr",
            plan_data=PlanData(
                plan="1. Add module\n2. Write tests",
                summary="Add module and tests",
            ),
        )
    )


def _make_subprocess_side_effect(
    *,
    existing_comment_id: str | None = None,
    attachment_error: bool = False,
) -> object:
    """Build a side_effect callable for subprocess.run.

    Handles the standard sequence of subprocess calls made by the step:
    git rev-parse, gh pr list (adopt check), git push, gh pr create,
    gh pr view (attachment list), and gh pr comment / gh api PATCH.

    Args:
        existing_comment_id: If set, the ``gh pr view`` call returns this
            comment ID so the step uses PATCH instead of a new comment.
        attachment_error: If True, raise OSError for the attachment comment
            subprocess call.
    """

    def _side_effect(cmd: list[str], **_kwargs: object) -> MagicMock:
        cmd_str = " ".join(cmd)

        # git rev-parse --abbrev-ref HEAD
        if "rev-parse" in cmd_str:
            result = MagicMock()
            result.returncode = 0
            result.stdout = "adw-test-branch\n"
            return result

        # gh pr list --head ... (adopt check) — no existing PR
        if "pr" in cmd_str and "list" in cmd_str:
            result = MagicMock()
            result.returncode = 0
            result.stdout = "[]"
            return result

        # git push
        if "push" in cmd_str:
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            return result

        # gh pr create
        if "pr" in cmd_str and "create" in cmd_str:
            result = MagicMock()
            result.returncode = 0
            result.stdout = "https://github.com/org/repo/pull/99\n"
            return result

        # gh pr view (attachment comment listing)
        if "pr" in cmd_str and "view" in cmd_str:
            if attachment_error:
                raise OSError("network error")
            result = MagicMock()
            result.returncode = 0
            result.stdout = existing_comment_id or ""
            return result

        # gh pr comment (new attachment comment)
        if "pr" in cmd_str and "comment" in cmd_str:
            if attachment_error:
                raise OSError("network error")
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            return result

        # gh api PATCH (update attachment comment)
        if "api" in cmd_str and "PATCH" in cmd_str:
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


# Shared patch decorator stack for attachment tests — patches external
# helpers and env so the step reaches the PR-creation / adopt path.
_ATTACHMENT_PATCHES = [
    "rouge.core.workflow.steps.gh_pull_request_step._emit_and_log",
    "rouge.core.workflow.steps.gh_pull_request_step.emit_artifact_comment",
    "rouge.core.workflow.steps.gh_pull_request_step.log_artifact_comment_status",
    "rouge.core.workflow.steps.gh_pull_request_step.shutil.which",
    "rouge.core.workflow.steps.gh_pull_request_step.subprocess.run",
]


class TestGhPullRequestStepAttachment:
    """Tests for attachment comment posting/updating on pull requests."""

    @patch(_ATTACHMENT_PATCHES[0])
    @patch(_ATTACHMENT_PATCHES[1])
    @patch(_ATTACHMENT_PATCHES[2])
    @patch(_ATTACHMENT_PATCHES[3])
    @patch(_ATTACHMENT_PATCHES[4])
    @patch.dict("os.environ", {"GITHUB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_attachment_comment_posted_on_create(
        self,
        mock_subprocess,
        mock_which,
        _mock_log,
        mock_emit_artifact,
        mock_emit,
        base_context: WorkflowContext,
        store: ArtifactStore,
    ) -> None:
        """When fetch-issue and plan artifacts exist, gh pr comment is called after PR create."""
        _write_fetch_issue_and_plan_artifacts(store)
        store.write_artifact(
            ComposeRequestArtifact(
                workflow_id="test-gh-pr",
                title="Test PR",
                summary="Summary",
                commits=[],
            )
        )

        mock_emit_artifact.return_value = ("success", "ok")
        mock_which.return_value = "/usr/bin/gh"
        mock_subprocess.side_effect = _make_subprocess_side_effect()

        step = GhPullRequestStep()
        result = step.run(base_context)

        assert result.success is True

        # Find the gh pr comment call (attachment posting) — filter by
        # the literal "comment" subcommand appearing right after "pr"
        comment_calls = [
            c for c in mock_subprocess.call_args_list if c[0][0][:3] == ["gh", "pr", "comment"]
        ]
        assert len(comment_calls) == 1
        comment_cmd = comment_calls[0][0][0]
        # Should contain the marker
        assert any("<!-- rouge-review-context -->" in arg for arg in comment_cmd)
        # Should contain the PR number
        assert "99" in comment_cmd

    @patch(_ATTACHMENT_PATCHES[0])
    @patch(_ATTACHMENT_PATCHES[1])
    @patch(_ATTACHMENT_PATCHES[2])
    @patch(_ATTACHMENT_PATCHES[3])
    @patch(_ATTACHMENT_PATCHES[4])
    @patch.dict("os.environ", {"GITHUB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_attachment_comment_posted_on_adopt(
        self,
        mock_subprocess,
        mock_which,
        _mock_log,
        mock_emit_artifact,
        mock_emit,
        base_context: WorkflowContext,
        store: ArtifactStore,
    ) -> None:
        """When an existing PR is adopted, attachment comment is posted on the adopted PR."""
        _write_fetch_issue_and_plan_artifacts(store)
        store.write_artifact(
            ComposeRequestArtifact(
                workflow_id="test-gh-pr",
                title="Test PR",
                summary="Summary",
                commits=[],
            )
        )

        mock_emit_artifact.return_value = ("success", "ok")
        mock_which.return_value = "/usr/bin/gh"

        def _adopt_side_effect(cmd: list[str], **_kwargs: object) -> MagicMock:
            cmd_str = " ".join(cmd)

            if "rev-parse" in cmd_str:
                r = MagicMock()
                r.returncode = 0
                r.stdout = "adw-test-branch\n"
                return r

            # gh pr list returns an existing PR to adopt
            if "pr" in cmd_str and "list" in cmd_str:
                r = MagicMock()
                r.returncode = 0
                r.stdout = '[{"url": "https://github.com/org/repo/pull/77", "number": 77}]'
                return r

            # gh pr view (attachment comment listing) — no existing comment
            if "pr" in cmd_str and "view" in cmd_str:
                r = MagicMock()
                r.returncode = 0
                r.stdout = ""
                return r

            # gh pr comment (new attachment)
            if "pr" in cmd_str and "comment" in cmd_str:
                r = MagicMock()
                r.returncode = 0
                r.stdout = ""
                return r

            r = MagicMock()
            r.returncode = 0
            r.stdout = ""
            return r

        mock_subprocess.side_effect = _adopt_side_effect

        step = GhPullRequestStep()
        result = step.run(base_context)

        assert result.success is True

        comment_calls = [
            c for c in mock_subprocess.call_args_list if c[0][0][:3] == ["gh", "pr", "comment"]
        ]
        assert len(comment_calls) == 1
        comment_cmd = comment_calls[0][0][0]
        assert any("<!-- rouge-review-context -->" in arg for arg in comment_cmd)
        assert "77" in comment_cmd

    @patch(_ATTACHMENT_PATCHES[0])
    @patch(_ATTACHMENT_PATCHES[1])
    @patch(_ATTACHMENT_PATCHES[2])
    @patch(_ATTACHMENT_PATCHES[3])
    @patch(_ATTACHMENT_PATCHES[4])
    @patch.dict("os.environ", {"GITHUB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_attachment_skipped_when_artifacts_missing(
        self,
        mock_subprocess,
        mock_which,
        _mock_log,
        mock_emit_artifact,
        mock_emit,
        base_context: WorkflowContext,
        store: ArtifactStore,
    ) -> None:
        """No attachment subprocess calls when fetch-issue/plan artifacts are absent."""
        # Only write compose-request — no fetch-issue or plan
        store.write_artifact(
            ComposeRequestArtifact(
                workflow_id="test-gh-pr",
                title="Test PR",
                summary="Summary",
                commits=[],
            )
        )

        mock_emit_artifact.return_value = ("success", "ok")
        mock_which.return_value = "/usr/bin/gh"
        mock_subprocess.side_effect = _make_subprocess_side_effect()

        step = GhPullRequestStep()
        result = step.run(base_context)

        assert result.success is True

        # No attachment-related calls: no gh pr view (comments), no gh pr comment, no gh api PATCH
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
    @patch(_ATTACHMENT_PATCHES[3])
    @patch(_ATTACHMENT_PATCHES[4])
    @patch.dict("os.environ", {"GITHUB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_attachment_updated_on_rerun(
        self,
        mock_subprocess,
        mock_which,
        _mock_log,
        mock_emit_artifact,
        mock_emit,
        base_context: WorkflowContext,
        store: ArtifactStore,
    ) -> None:
        """Existing attachment comment found via gh pr view triggers PATCH update."""
        _write_fetch_issue_and_plan_artifacts(store)
        store.write_artifact(
            ComposeRequestArtifact(
                workflow_id="test-gh-pr",
                title="Test PR",
                summary="Summary",
                commits=[],
            )
        )

        mock_emit_artifact.return_value = ("success", "ok")
        mock_which.return_value = "/usr/bin/gh"
        # Existing comment ID returned by gh pr view
        mock_subprocess.side_effect = _make_subprocess_side_effect(existing_comment_id="12345678")

        step = GhPullRequestStep()
        result = step.run(base_context)

        assert result.success is True

        # Should have a gh api PATCH call
        patch_calls = [
            c
            for c in mock_subprocess.call_args_list
            if "api" in " ".join(c[0][0]) and "PATCH" in " ".join(c[0][0])
        ]
        assert len(patch_calls) == 1
        patch_cmd = patch_calls[0][0][0]
        # Should reference the existing comment ID
        assert any("12345678" in arg for arg in patch_cmd)

        # Should NOT have a gh pr comment call (new comment)
        new_comment_calls = [
            c for c in mock_subprocess.call_args_list if c[0][0][:3] == ["gh", "pr", "comment"]
        ]
        assert len(new_comment_calls) == 0

    @patch(_ATTACHMENT_PATCHES[0])
    @patch(_ATTACHMENT_PATCHES[1])
    @patch(_ATTACHMENT_PATCHES[2])
    @patch(_ATTACHMENT_PATCHES[3])
    @patch(_ATTACHMENT_PATCHES[4])
    @patch.dict("os.environ", {"GITHUB_PAT": "tok", "PATH": "/usr/bin"}, clear=True)
    def test_attachment_failure_does_not_fail_step(
        self,
        mock_subprocess,
        mock_which,
        _mock_log,
        mock_emit_artifact,
        mock_emit,
        base_context: WorkflowContext,
        store: ArtifactStore,
    ) -> None:
        """Attachment posting failure is caught and the step still returns success."""
        _write_fetch_issue_and_plan_artifacts(store)
        store.write_artifact(
            ComposeRequestArtifact(
                workflow_id="test-gh-pr",
                title="Test PR",
                summary="Summary",
                commits=[],
            )
        )

        mock_emit_artifact.return_value = ("success", "ok")
        mock_which.return_value = "/usr/bin/gh"
        mock_subprocess.side_effect = _make_subprocess_side_effect(
            attachment_error=True,
        )

        step = GhPullRequestStep()
        result = step.run(base_context)

        # Step should still succeed despite attachment posting failure
        assert result.success is True
