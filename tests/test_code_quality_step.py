"""Tests for CodeQualityStep.

Focuses on confirming that CodeQualityStep:
- Fires the orchestrator prompt once with no repo arguments
- Succeeds with valid JSON output
- Handles template failures gracefully
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rouge.core.workflow.artifacts import ArtifactStore
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.code_quality_step import CodeQualityStep


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(workflow_id="test-code-quality", base_path=tmp_path)


@pytest.fixture
def base_context(store: ArtifactStore) -> WorkflowContext:
    return WorkflowContext(
        adw_id="test-code-quality",
        issue_id=55,
        artifact_store=store,
    )


class TestCodeQualityStep:
    @patch("rouge.core.workflow.steps.code_quality_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.code_quality_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.code_quality_step.log_artifact_comment_status")
    @patch("rouge.core.workflow.steps.code_quality_step.execute_template")
    def test_fires_orchestrator_with_no_args(
        self,
        mock_exec,
        _mock_log,
        mock_emit_artifact,
        mock_emit,
        base_context: WorkflowContext,
    ) -> None:
        """CodeQualityStep passes no repo args — orchestrator discovers repos itself."""
        mock_response = Mock()
        mock_response.success = True
        mock_response.output = '{"output": "code-quality", "repos": [{"repo": "/repo", "issues": [], "tools": ["ruff"]}]}'
        mock_exec.return_value = mock_response
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")

        step = CodeQualityStep()
        result = step.run(base_context)

        assert result.success is True
        call_args = mock_exec.call_args[0][0]
        assert call_args.args == []

    @patch("rouge.core.workflow.steps.code_quality_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.code_quality_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.code_quality_step.log_artifact_comment_status")
    @patch("rouge.core.workflow.steps.code_quality_step.execute_template")
    def test_succeeds_with_valid_output(
        self,
        mock_exec,
        _mock_log,
        mock_emit_artifact,
        mock_emit,
        base_context: WorkflowContext,
    ) -> None:
        mock_response = Mock()
        mock_response.success = True
        mock_response.output = '{"output": "code-quality", "repos": [{"repo": "/repo", "issues": [], "tools": ["mypy"]}]}'
        mock_exec.return_value = mock_response
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")

        step = CodeQualityStep()
        result = step.run(base_context)

        assert result.success is True

    @patch("rouge.core.workflow.steps.code_quality_step.execute_template")
    def test_fails_when_template_fails(
        self,
        mock_exec,
        base_context: WorkflowContext,
    ) -> None:
        mock_response = Mock()
        mock_response.success = False
        mock_response.output = "claude timed out"
        mock_exec.return_value = mock_response

        step = CodeQualityStep()
        result = step.run(base_context)

        assert result.success is False

    def test_is_not_critical(self) -> None:
        assert CodeQualityStep().is_critical is False
