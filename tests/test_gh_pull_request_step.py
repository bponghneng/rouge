"""Tests for GhPullRequestStep dependency contract.

Focuses on:
- Succeeding (graceful skip) when compose-request artifact is absent
  (optional dependency declared in registry)
- Loading PR details from artifact when present
"""

from unittest.mock import patch

import pytest

from rouge.core.workflow.artifacts import ArtifactStore, ComposeRequestArtifact
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.gh_pull_request_step import GhPullRequestStep


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

    @patch("rouge.core.workflow.steps.gh_pull_request_step.emit_comment_from_payload")
    def test_succeeds_when_compose_request_artifact_absent(
        self, mock_emit, base_context: WorkflowContext
    ) -> None:
        """Step returns success when compose-request artifact is missing (optional dep)."""
        mock_emit.return_value = ("success", "ok")

        step = GhPullRequestStep()
        result = step.run(base_context)

        # Must succeed (not fail) — optional dependency is missing
        assert result.success is True
        assert result.error is None

    @patch("rouge.core.workflow.steps.gh_pull_request_step.emit_comment_from_payload")
    def test_emits_skip_comment_when_artifact_absent(
        self, mock_emit, base_context: WorkflowContext
    ) -> None:
        """Step emits an informative skip comment when compose-request artifact is missing."""
        mock_emit.return_value = ("success", "ok")

        step = GhPullRequestStep()
        result = step.run(base_context)

        assert result.success is True
        assert mock_emit.called
        payload = mock_emit.call_args[0][0]
        # Message should indicate skip reason
        assert "skip" in payload.text.lower() or "no pr details" in payload.text.lower()

    @patch("rouge.core.workflow.steps.gh_pull_request_step.emit_comment_from_payload")
    def test_loads_pr_details_via_optional_artifact(
        self, mock_emit, base_context: WorkflowContext, store: ArtifactStore
    ) -> None:
        """load_optional_artifact is used (not a guard-and-fail pattern)."""
        mock_emit.return_value = ("success", "ok")

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

    @patch("rouge.core.workflow.steps.gh_pull_request_step.emit_comment_from_payload")
    def test_does_not_raise_when_artifact_absent(
        self, mock_emit, base_context: WorkflowContext
    ) -> None:
        """No exception is raised when compose-request artifact is absent."""
        mock_emit.return_value = ("success", "ok")

        step = GhPullRequestStep()
        # Should not raise
        result = step.run(base_context)
        assert result is not None


class TestGhPullRequestStepWithArtifact:
    """Tests verifying GhPullRequestStep uses compose-request artifact when present."""

    @patch("rouge.core.workflow.steps.gh_pull_request_step.emit_comment_from_payload")
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

        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")
        mock_which.return_value = None  # gh CLI not found → graceful skip

        step = GhPullRequestStep()
        result = step.run(base_context)

        # Step should succeed (either skip due to missing gh or GITHUB_PAT)
        assert result.success is True


class TestGhPullRequestStepDraftFlag:
    """Tests verifying GhPullRequestStep adds --draft flag based on pipeline_type."""

    @patch("rouge.core.workflow.steps.gh_pull_request_step.emit_comment_from_payload")
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
        mock_emit.return_value = ("success", "ok")
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

        # Simulate subprocess calls: git rev-parse, gh pr list, git push, gh pr create
        from unittest.mock import MagicMock

        def run_side_effect(cmd, **kwargs):
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

        mock_run.side_effect = run_side_effect

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

    @patch("rouge.core.workflow.steps.gh_pull_request_step.emit_comment_from_payload")
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
        mock_emit.return_value = ("success", "ok")
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

        from unittest.mock import MagicMock

        def run_side_effect(cmd, **kwargs):
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

        mock_run.side_effect = run_side_effect

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
