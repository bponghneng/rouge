"""Tests for ComposeRequestStep ordering-only dependency contract.

Focuses on confirming that ComposeRequestStep:
- Does NOT read the acceptance data (ordering-only dependency)
- Proceeds with its own agent-based logic without reading acceptance data
"""

from unittest.mock import Mock, patch

import pytest

from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.compose_request_step import ComposeRequestStep


@pytest.fixture
def base_context() -> WorkflowContext:
    """Create a workflow context with no acceptance data."""
    return WorkflowContext(
        adw_id="test-compose-request",
        issue_id=77,
    )


class TestComposeRequestOrderingOnlyDependency:
    """Tests that ComposeRequestStep does not read the acceptance data."""

    @patch("rouge.core.workflow.steps.compose_request_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.compose_request_step.execute_template")
    def test_succeeds_without_acceptance_data(
        self,
        mock_exec,
        mock_emit,
        base_context: WorkflowContext,
    ) -> None:
        """ComposeRequestStep succeeds even when no acceptance data exists."""
        mock_response = Mock()
        mock_response.success = True
        mock_response.output = (
            '{"output": "pull-request", "title": "My PR", "summary": "Summary", "commits": []}'
        )
        mock_exec.return_value = mock_response
        mock_emit.return_value = ("success", "ok")

        step = ComposeRequestStep()
        result = step.run(base_context)

        assert result.success is True

    def test_is_not_critical(self) -> None:
        """ComposeRequestStep is non-critical (best-effort)."""
        step = ComposeRequestStep()
        assert step.is_critical is False


class TestComposeRequestAffectedRepos:
    """Tests for ComposeRequestStep affected-repos filtering."""

    @patch("rouge.core.workflow.steps.compose_request_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.compose_request_step.execute_template")
    @patch("rouge.core.workflow.steps.compose_request_step.get_affected_repo_paths")
    def test_uses_filtered_repos_as_args(
        self,
        mock_get_affected,
        mock_exec,
        mock_emit,
        base_context: WorkflowContext,
    ) -> None:
        """ComposeRequestStep passes filtered repos (not full context.repo_paths) to template."""
        mock_get_affected.return_value = ["/filtered/repo"]
        mock_response = Mock()
        mock_response.success = True
        mock_response.output = (
            '{"output": "pull-request", "title": "My PR", "summary": "Summary", "commits": []}'
        )
        mock_exec.return_value = mock_response
        mock_emit.return_value = ("success", "ok")

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
        # Verify a placeholder was written to context.data
        assert base_context.data["compose-request"]["title"] == "No changes"
