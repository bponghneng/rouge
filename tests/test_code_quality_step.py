"""Tests for CodeQualityStep ordering-only dependency contract.

Focuses on confirming that CodeQualityStep:
- Does NOT read the implement artifact (ordering-only dependency)
- Succeeds without any implement artifact being present
- Only reads artifacts from its own execution (writes code-quality artifact)
"""

from typing import Any, Optional
from unittest.mock import Mock, patch

import pytest

from rouge.core.workflow.artifacts import ArtifactStore
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.code_quality_step import CodeQualityStep


@pytest.fixture
def store(tmp_path) -> ArtifactStore:
    """Create a temporary artifact store with no implement artifact."""
    return ArtifactStore(workflow_id="test-code-quality", base_path=tmp_path)


@pytest.fixture
def base_context(store: ArtifactStore) -> WorkflowContext:
    """Create a workflow context with no implement artifact."""
    return WorkflowContext(
        adw_id="test-code-quality",
        issue_id=55,
        artifact_store=store,
    )


class TestCodeQualityOrderingOnlyDependency:
    """Tests that CodeQualityStep does not read the implement artifact."""

    @patch("rouge.core.workflow.steps.code_quality_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.code_quality_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.code_quality_step.log_artifact_comment_status")
    @patch("rouge.core.workflow.steps.code_quality_step.execute_template")
    def test_does_not_read_implement_artifact(
        self,
        mock_exec,
        _mock_log,
        mock_emit_artifact,
        mock_emit,
        base_context: WorkflowContext,
    ) -> None:
        """CodeQualityStep never calls read_artifact('implement', ...)."""
        mock_response = Mock()
        mock_response.success = True
        mock_response.output = (
            '{"output": "code-quality", "tools": ["ruff"], "issues": []}'
        )
        mock_exec.return_value = mock_response
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")

        read_calls: list[str] = []
        original_read = base_context.artifact_store.read_artifact

        def tracking_read(artifact_type: str, model_class: Optional[type] = None) -> Any:
            read_calls.append(artifact_type)
            return original_read(artifact_type, model_class)

        with patch.object(
            base_context.artifact_store, "read_artifact", side_effect=tracking_read
        ):
            step = CodeQualityStep()
            step.run(base_context)

        # Assert implement artifact was never read
        assert "implement" not in read_calls

    @patch("rouge.core.workflow.steps.code_quality_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.code_quality_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.code_quality_step.log_artifact_comment_status")
    @patch("rouge.core.workflow.steps.code_quality_step.execute_template")
    def test_succeeds_without_implement_artifact(
        self,
        mock_exec,
        _mock_log,
        mock_emit_artifact,
        mock_emit,
        base_context: WorkflowContext,
    ) -> None:
        """CodeQualityStep succeeds even when no implement artifact exists."""
        mock_response = Mock()
        mock_response.success = True
        mock_response.output = (
            '{"output": "code-quality", "tools": ["mypy"], "issues": []}'
        )
        mock_exec.return_value = mock_response
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")

        step = CodeQualityStep()
        result = step.run(base_context)

        assert result.success is True

    def test_is_not_critical(self) -> None:
        """CodeQualityStep is non-critical (best-effort)."""
        step = CodeQualityStep()
        assert step.is_critical is False
