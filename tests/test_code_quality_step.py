"""Tests for CodeQualityStep behavior.

Covers:
- Repo filtering via get_affected_repos (skip when no repos affected)
- Passing affected repos as template args
- Non-critical step classification
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rouge.core.workflow.artifacts import ArtifactStore
from rouge.core.workflow.step_base import StepInputError, WorkflowContext
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


class TestCodeQualityOrderingOnlyDependency:
    """Tests that CodeQualityStep raises when the implement artifact is missing."""

    def test_raises_without_implement_artifact(
        self,
        base_context: WorkflowContext,
    ) -> None:
        """CodeQualityStep raises StepInputError when the implement artifact is absent.

        The implement dependency is declared as required in the step registry.
        The pipeline framework handles non-critical steps that raise StepInputError
        without aborting the workflow.
        """
        step = CodeQualityStep()
        with pytest.raises(StepInputError, match="Required artifact 'implement' not found"):
            step.run(base_context)

    def test_is_not_critical(self) -> None:
        """CodeQualityStep is non-critical (best-effort)."""
        step = CodeQualityStep()
        assert step.is_critical is False


class TestCodeQualityAffectedRepos:
    """Tests for CodeQualityStep repo filtering behavior."""

    @patch("rouge.core.workflow.step_utils.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.code_quality_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.code_quality_step.log_artifact_comment_status")
    @patch("rouge.core.workflow.steps.code_quality_step.execute_template")
    @patch("rouge.core.workflow.steps.code_quality_step.get_affected_repos")
    def test_passes_affected_repos_as_args(
        self,
        mock_get_affected,
        mock_exec,
        _mock_log,
        mock_emit_artifact,
        mock_emit,
        base_context: WorkflowContext,
    ) -> None:
        """Affected repos are passed as template args."""
        from rouge.core.workflow.types import ImplementData

        mock_get_affected.return_value = (
            ["/repo/a", "/repo/b"],
            ImplementData(output="done"),
        )

        mock_response = Mock()
        mock_response.success = True
        mock_response.output = '{"output": "code-quality", "tools": ["ruff"], "issues": []}'
        mock_exec.return_value = mock_response
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")

        step = CodeQualityStep()
        result = step.run(base_context)

        assert result.success is True
        # Verify args passed to template
        call_args = mock_exec.call_args[0][0]
        assert call_args.args == ["/repo/a", "/repo/b"]

    @patch("rouge.core.workflow.steps.code_quality_step.get_affected_repos")
    def test_writes_skip_artifact_when_no_affected_repos(
        self, mock_get_affected, base_context: WorkflowContext
    ) -> None:
        """Writes skip artifact when no repos affected."""
        from rouge.core.workflow.types import ImplementData

        mock_get_affected.return_value = ([], ImplementData(output="done"))

        step = CodeQualityStep()
        result = step.run(base_context)

        assert result.success is True
        # Verify skip artifact was written
        artifact = base_context.artifact_store.read_artifact("code-quality")
        assert artifact.tools == ["skipped"]
        assert artifact.parsed_data == {"skipped": True, "reason": "no affected repos"}
