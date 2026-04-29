"""Tests for ComposeRequestStep.

Focuses on confirming that ComposeRequestStep:
- Does NOT read the acceptance artifact (ordering-only dependency)
- Fires the orchestrator prompt once with no repo arguments
- Succeeds with valid JSON output
"""

from pathlib import Path
from typing import Any, Optional
from unittest.mock import Mock, patch

import pytest

from rouge.core.workflow.artifacts import ArtifactStore
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.compose_request_step import ComposeRequestStep

VALID_OUTPUT = (
    '{"output": "pull-request", "repos": ['
    '{"repo": "/srv/app", "title": "feat: add thing", "summary": "## Description\\nAdds thing", "commits": []}'
    ']}'
)


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(workflow_id="test-compose-request", base_path=tmp_path)


@pytest.fixture
def base_context(store: ArtifactStore) -> WorkflowContext:
    return WorkflowContext(
        adw_id="test-compose-request",
        issue_id=77,
        artifact_store=store,
    )


class TestComposeRequestOrderingOnlyDependency:
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
        base_context: WorkflowContext,
    ) -> None:
        """ComposeRequestStep never calls read_artifact('acceptance', ...)."""
        mock_response = Mock()
        mock_response.success = True
        mock_response.output = VALID_OUTPUT
        mock_exec.return_value = mock_response
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")

        read_calls: list[str] = []
        original_read = base_context.artifact_store.read_artifact

        def tracking_read(artifact_type: str, model_class: Optional[type] = None) -> Any:
            read_calls.append(artifact_type)
            return original_read(artifact_type, model_class)

        with patch.object(base_context.artifact_store, "read_artifact", side_effect=tracking_read):
            step = ComposeRequestStep()
            result = step.run(base_context)

        assert result.success is True
        assert "acceptance" not in read_calls

    @patch("rouge.core.workflow.steps.compose_request_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.compose_request_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.compose_request_step.log_artifact_comment_status")
    @patch("rouge.core.workflow.steps.compose_request_step.execute_template")
    def test_fires_orchestrator_with_no_args(
        self,
        mock_exec,
        _mock_log,
        mock_emit_artifact,
        mock_emit,
        base_context: WorkflowContext,
    ) -> None:
        """ComposeRequestStep passes no repo args — orchestrator discovers repos itself."""
        mock_response = Mock()
        mock_response.success = True
        mock_response.output = VALID_OUTPUT
        mock_exec.return_value = mock_response
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")

        step = ComposeRequestStep()
        result = step.run(base_context)

        assert result.success is True
        call_args = mock_exec.call_args[0][0]
        assert call_args.args == []

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
        base_context: WorkflowContext,
    ) -> None:
        mock_response = Mock()
        mock_response.success = True
        mock_response.output = VALID_OUTPUT
        mock_exec.return_value = mock_response
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")

        step = ComposeRequestStep()
        result = step.run(base_context)

        assert result.success is True

    def test_is_not_critical(self) -> None:
        assert ComposeRequestStep().is_critical is False
