"""Tests for ComposeRequestStep ordering-only dependency contract.

Focuses on confirming that ComposeRequestStep:
- Does NOT read the acceptance artifact (ordering-only dependency)
- Proceeds with its own agent-based logic without reading acceptance data
"""

from typing import Any, Optional
from unittest.mock import Mock, patch

import pytest

from rouge.core.workflow.artifacts import ArtifactStore
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.compose_request_step import ComposeRequestStep


@pytest.fixture
def store(tmp_path) -> ArtifactStore:
    """Create a temporary artifact store with no acceptance artifact."""
    return ArtifactStore(workflow_id="test-compose-request", base_path=tmp_path)


@pytest.fixture
def base_context(store: ArtifactStore) -> WorkflowContext:
    """Create a workflow context with no acceptance artifact."""
    return WorkflowContext(
        adw_id="test-compose-request",
        issue_id=77,
        artifact_store=store,
    )


class TestComposeRequestOrderingOnlyDependency:
    """Tests that ComposeRequestStep does not read the acceptance artifact."""

    @patch("rouge.core.workflow.steps.compose_request_step.update_status")
    @patch("rouge.core.workflow.steps.compose_request_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.compose_request_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.compose_request_step.log_artifact_comment_status")
    @patch("rouge.core.workflow.steps.compose_request_step.execute_template")
    def test_does_not_read_acceptance_artifact(
        self,
        mock_exec,
        _mock_log,
        mock_emit_artifact,
        mock_emit,
        mock_update_status,
        base_context: WorkflowContext,
    ) -> None:
        """ComposeRequestStep never calls read_artifact('acceptance', ...)."""
        mock_response = Mock()
        mock_response.success = True
        mock_response.output = (
            '{"output": "pull-request", "title": "My PR", ' '"summary": "Summary", "commits": []}'
        )
        mock_exec.return_value = mock_response
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")
        mock_update_status.return_value = None

        read_calls: list[str] = []
        original_read = base_context.artifact_store.read_artifact

        def tracking_read(artifact_type: str, model_class: Optional[type] = None) -> Any:
            read_calls.append(artifact_type)
            return original_read(artifact_type, model_class)

        with patch.object(base_context.artifact_store, "read_artifact", side_effect=tracking_read):
            step = ComposeRequestStep()
            result = step.run(base_context)

        assert result.success is True
        # Assert acceptance artifact was never read
        assert "acceptance" not in read_calls

    @patch("rouge.core.workflow.steps.compose_request_step.update_status")
    @patch("rouge.core.workflow.steps.compose_request_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.compose_request_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.compose_request_step.log_artifact_comment_status")
    @patch("rouge.core.workflow.steps.compose_request_step.execute_template")
    def test_succeeds_without_acceptance_artifact(
        self,
        mock_exec,
        _mock_log,
        mock_emit_artifact,
        mock_emit,
        mock_update_status,
        base_context: WorkflowContext,
    ) -> None:
        """ComposeRequestStep succeeds even when no acceptance artifact exists."""
        mock_response = Mock()
        mock_response.success = True
        mock_response.output = (
            '{"output": "pull-request", "title": "My PR", ' '"summary": "Summary", "commits": []}'
        )
        mock_exec.return_value = mock_response
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")
        mock_update_status.return_value = None

        step = ComposeRequestStep()
        result = step.run(base_context)

        assert result.success is True

    def test_is_not_critical(self) -> None:
        """ComposeRequestStep is non-critical (best-effort)."""
        step = ComposeRequestStep()
        assert step.is_critical is False


class TestComposeRequestAffectedRepos:
    """Tests for ComposeRequestStep affected-repos filtering."""

    @patch("rouge.core.workflow.steps.compose_request_step.update_status")
    @patch("rouge.core.workflow.steps.compose_request_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.compose_request_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.compose_request_step.log_artifact_comment_status")
    @patch("rouge.core.workflow.steps.compose_request_step.execute_template")
    @patch("rouge.core.workflow.steps.compose_request_step.get_affected_repo_paths")
    def test_uses_filtered_repos_as_args(
        self,
        mock_get_affected,
        mock_exec,
        _mock_log,
        mock_emit_artifact,
        mock_emit,
        mock_update_status,
        base_context: WorkflowContext,
    ) -> None:
        """ComposeRequestStep passes filtered repos (not full context.repo_paths) to template."""
        mock_get_affected.return_value = ["/filtered/repo"]
        mock_response = Mock()
        mock_response.success = True
        mock_response.output = (
            '{"output": "pull-request", "title": "My PR", ' '"summary": "Summary", "commits": []}'
        )
        mock_exec.return_value = mock_response
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")
        mock_update_status.return_value = None

        step = ComposeRequestStep()
        result = step.run(base_context)

        assert result.success is True
        call_args = mock_exec.call_args[0][0]
        assert call_args.args == ["/filtered/repo"]

    @patch("rouge.core.workflow.steps.compose_request_step.get_affected_repo_paths")
    def test_skips_when_zero_affected_repos(
        self,
        mock_get_affected,
        base_context: WorkflowContext,
    ) -> None:
        """ComposeRequestStep skips gracefully when get_affected_repo_paths returns []."""
        mock_get_affected.return_value = []

        step = ComposeRequestStep()
        result = step.run(base_context)

        assert result.success is True
        # Verify a placeholder artifact was written
        artifact = base_context.artifact_store.read_artifact("compose-request")
        assert artifact.title == "No changes"
