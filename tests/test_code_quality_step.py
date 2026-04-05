"""Tests for CodeQualityStep optional dependency contract.

Focuses on confirming that CodeQualityStep:
- Reads the implement artifact to get affected repo paths (optional dependency)
- Succeeds without any implement artifact being present (falls back to all repos)
- Skips when no affected repos are found
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rouge.core.workflow.artifacts import ArtifactStore
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.code_quality_step import CodeQualityStep


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
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


class TestCodeQualityOptionalDependency:
    """Tests that CodeQualityStep reads the implement artifact as optional."""

    @patch("rouge.core.workflow.steps.code_quality_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.code_quality_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.code_quality_step.log_artifact_comment_status")
    @patch("rouge.core.workflow.steps.code_quality_step.execute_template")
    def test_reads_implement_artifact_for_affected_repos(
        self,
        mock_exec,
        _mock_log,
        mock_emit_artifact,
        mock_emit,
        base_context: WorkflowContext,
    ) -> None:
        """CodeQualityStep reads implement artifact to get affected repos."""
        mock_response = Mock()
        mock_response.success = True
        mock_response.output = '{"output": "code-quality", "tools": ["ruff"], "issues": []}'
        mock_exec.return_value = mock_response
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")

        step = CodeQualityStep()
        result = step.run(base_context)

        # Step succeeds, and passes affected repos (falls back to all repos)
        assert result.success is True
        # Verify args were passed to the template request
        call_args = mock_exec.call_args[0][0]
        assert call_args.args == list(base_context.repo_paths)

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
        mock_response.output = '{"output": "code-quality", "tools": ["mypy"], "issues": []}'
        mock_exec.return_value = mock_response
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")

        step = CodeQualityStep()
        result = step.run(base_context)

        assert result.success is True

    @patch("rouge.core.workflow.steps.code_quality_step.get_affected_repo_paths")
    def test_skips_when_zero_affected_repos(
        self,
        mock_get_affected,
        base_context: WorkflowContext,
    ) -> None:
        """CodeQualityStep skips gracefully when get_affected_repo_paths returns []."""
        mock_get_affected.return_value = []

        step = CodeQualityStep()
        result = step.run(base_context)

        assert result.success is True
        # Verify a "skipped" artifact was written
        artifact = base_context.artifact_store.read_artifact("code-quality")
        assert artifact.output == "skipped"

    def test_is_not_critical(self) -> None:
        """CodeQualityStep is non-critical (best-effort)."""
        step = CodeQualityStep()
        assert step.is_critical is False
