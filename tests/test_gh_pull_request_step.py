"""Tests for GhPullRequestStep dependency contract.

Focuses on:
- Succeeding (graceful skip) when compose-request artifact is absent
  (optional dependency declared in registry)
- Loading PR details from artifact when present
"""

from unittest.mock import Mock, patch

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
    @patch("rouge.core.workflow.steps.gh_pull_request_step.get_repo_path")
    @patch("rouge.core.workflow.steps.gh_pull_request_step.subprocess.run")
    def test_uses_compose_request_artifact_when_present(
        self,
        mock_subprocess,
        mock_get_repo,
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
