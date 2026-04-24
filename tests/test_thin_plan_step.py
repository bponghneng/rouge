"""Tests for ThinPlanStep workflow step.

After the Phase 5 refactor, ThinPlanStep is a zero-argument shim that
subclasses :class:`PromptJsonStep` with the built-in thin-plan
configuration.  These tests verify the shim preserves the original behaviour
of the legacy step: it loads the issue from the fetch-issue artifact and
writes a :class:`PlanArtifact`.
"""

from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from rouge.core.agents.claude import ClaudeAgentPromptResponse
from rouge.core.models import Issue
from rouge.core.prompts import PromptId
from rouge.core.workflow.artifacts import ArtifactStore, FetchIssueArtifact
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.thin_plan_step import ThinPlanStep


@pytest.fixture
def issue() -> Issue:
    """Create a sample issue."""
    return Issue(
        id=5,
        description="Add a new utility function for string sanitization",
        status="pending",
        type="full",
        adw_id="thin-abc123",
        branch="feature/string-sanitization",
    )


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    """Create a temporary artifact store."""
    return ArtifactStore(workflow_id="test-adw-thin-plan", base_path=tmp_path)


@pytest.fixture
def context_with_artifact(issue: Issue, store: ArtifactStore) -> WorkflowContext:
    """Create a workflow context with fetch-issue artifact written to the store."""
    artifact = FetchIssueArtifact(
        workflow_id=store.workflow_id,
        issue=issue,
    )
    store.write_artifact(artifact)
    return WorkflowContext(
        issue_id=5,
        adw_id="test-adw-thin-plan",
        artifact_store=store,
    )


@pytest.fixture
def context_without_artifact(store: ArtifactStore) -> WorkflowContext:
    """Create a workflow context WITHOUT fetch-issue artifact."""
    return WorkflowContext(
        issue_id=5,
        adw_id="test-adw-thin-plan",
        artifact_store=store,
    )


def _make_response(
    *,
    success: bool,
    output: str,
    session_id: str | None = "sess-xyz",
) -> ClaudeAgentPromptResponse:
    """Build a ClaudeAgentPromptResponse for mocking execute_template."""
    return ClaudeAgentPromptResponse(
        output=output,
        success=success,
        session_id=session_id,
    )


@pytest.fixture
def patched_executor() -> Generator[dict, None, None]:
    """Patch helpers and execute_template inside the PromptJsonStep executor module."""
    with (
        patch("rouge.core.workflow.executors.prompt_json_step.execute_template") as mock_execute,
        patch(
            "rouge.core.workflow.executors.prompt_json_step.emit_artifact_comment"
        ) as mock_emit_artifact,
        patch(
            "rouge.core.workflow.executors.prompt_json_step.emit_comment_from_payload"
        ) as mock_emit_payload,
        patch("rouge.core.workflow.executors.prompt_json_step.log_artifact_comment_status"),
    ):
        mock_emit_artifact.return_value = ("success", "ok")
        mock_emit_payload.return_value = ("success", "ok")
        yield {
            "execute_template": mock_execute,
            "emit_artifact_comment": mock_emit_artifact,
            "emit_comment_from_payload": mock_emit_payload,
        }


class TestThinPlanStepLoadsFromArtifact:
    """Tests verifying ThinPlanStep loads the issue from fetch-issue artifact."""

    def test_loads_issue_from_fetch_issue_artifact(
        self,
        context_with_artifact: WorkflowContext,
        patched_executor: dict,
        issue: Issue,
    ) -> None:
        """Step loads the issue from the fetch-issue artifact and writes a PlanArtifact."""
        patched_executor["execute_template"].return_value = _make_response(
            success=True,
            output=(
                '{"type": "chore", "output": "plan", '
                '"plan": "## Thin Plan\\nAdd utility function", '
                '"summary": "Plan for adding string sanitization utility"}'
            ),
        )

        step = ThinPlanStep()
        result = step.run(context_with_artifact)

        assert result.success is True
        # Verify execute_template was called with the issue description.
        request = patched_executor["execute_template"].call_args.args[0]
        assert request.args == [issue.description]
        assert request.issue_id == issue.id
        # Verify a PlanArtifact was saved.
        assert context_with_artifact.artifact_store.artifact_exists("plan")

    def test_fails_when_fetch_issue_artifact_missing(
        self,
        context_without_artifact: WorkflowContext,
        patched_executor: dict,
    ) -> None:
        """Step fails when fetch-issue artifact is absent (required dependency)."""
        step = ThinPlanStep()
        result = step.run(context_without_artifact)

        assert result.success is False
        assert result.error is not None
        assert "fetch-issue" in result.error

    def test_calls_execute_template_with_thin_plan_prompt_id(
        self,
        context_with_artifact: WorkflowContext,
        patched_executor: dict,
        issue: Issue,
    ) -> None:
        """execute_template is called with PromptId.THIN_PLAN."""
        patched_executor["execute_template"].return_value = _make_response(
            success=True,
            output=(
                '{"type": "feature", "output": "plan", '
                '"plan": "## Thin Plan\\nImplement feature", "summary": "Summary"}'
            ),
        )

        step = ThinPlanStep()
        result = step.run(context_with_artifact)

        assert result.success is True
        request = patched_executor["execute_template"].call_args.args[0]
        assert request.prompt_id == PromptId.THIN_PLAN
        assert request.args == [issue.description]

    def test_fails_when_execute_template_fails(
        self,
        context_with_artifact: WorkflowContext,
        patched_executor: dict,
    ) -> None:
        """Step returns failure when execute_template reports a failed response."""
        patched_executor["execute_template"].return_value = _make_response(
            success=False,
            output="Template execution error",
        )

        step = ThinPlanStep()
        result = step.run(context_with_artifact)

        assert result.success is False
        assert result.error is not None
        assert "Template execution error" in result.error

    def test_fails_when_output_is_empty(
        self,
        context_with_artifact: WorkflowContext,
        patched_executor: dict,
    ) -> None:
        """Step fails when the agent response has empty output (no artifact written)."""
        patched_executor["execute_template"].return_value = _make_response(
            success=True,
            output="",
        )

        step = ThinPlanStep()
        result = step.run(context_with_artifact)

        assert result.success is False
        assert result.error is not None
        assert "No output" in result.error
        assert not context_with_artifact.artifact_store.artifact_exists("plan")


class TestThinPlanStepProperties:
    """Tests for ThinPlanStep properties."""

    def test_step_name(self) -> None:
        """Test step has correct name."""
        step = ThinPlanStep()
        assert step.name == "Building thin implementation plan"

    def test_step_is_critical(self) -> None:
        """Test step is critical."""
        step = ThinPlanStep()
        assert step.is_critical is True

    def test_step_id(self) -> None:
        """Step exposes the thin-plan slug as ``step_id``."""
        step = ThinPlanStep()
        assert step.step_id == "thin-plan"


# Silence unused-MagicMock import lint warnings in environments where the
# helper is referenced only implicitly; MagicMock is kept here for type-check
# clarity when fixtures return dicts of mocks.
_ = MagicMock
