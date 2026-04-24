"""Tests for ClaudeCodePlanStep workflow step.

After the Phase 5 refactor, ClaudeCodePlanStep is a zero-argument shim that
subclasses :class:`PromptJsonStep` with the built-in claude-code-plan
configuration.  These tests verify the shim preserves the original behaviour
of the legacy plan step:

- Loads the issue from the fetch-issue artifact
- Executes the claude-code-plan prompt via the agent layer
- Writes a :class:`PlanArtifact` and mirrors plan data into context
- Emits an artifact comment and a progress comment sourced from ``task``
- Surfaces input errors, agent failures, and JSON-parse failures as
  :class:`StepResult` failures without writing an artifact
"""

from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from rouge.core.agents.claude import ClaudeAgentPromptResponse
from rouge.core.models import Issue
from rouge.core.workflow.artifacts import ArtifactStore, FetchIssueArtifact, PlanArtifact
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.claude_code_plan_step import ClaudeCodePlanStep


@pytest.fixture
def issue() -> Issue:
    """Create a sample issue."""
    return Issue(
        id=42,
        description="Add dark mode toggle to settings page",
        status="pending",
        type="full",
        adw_id="full-abc123",
        branch="feature/dark-mode",
    )


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    """Create a temporary artifact store."""
    return ArtifactStore(workflow_id="test-adw-full", base_path=tmp_path)


@pytest.fixture
def context_with_artifact(issue: Issue, store: ArtifactStore) -> WorkflowContext:
    """Create a workflow context with fetch-issue artifact written to the store."""
    artifact = FetchIssueArtifact(
        workflow_id=store.workflow_id,
        issue=issue,
    )
    store.write_artifact(artifact)
    return WorkflowContext(
        issue_id=42,
        adw_id="test-adw-full",
        artifact_store=store,
    )


@pytest.fixture
def context_without_artifact(store: ArtifactStore) -> WorkflowContext:
    """Create a workflow context WITHOUT fetch-issue artifact."""
    return WorkflowContext(
        issue_id=42,
        adw_id="test-adw-full",
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
        patch(
            "rouge.core.workflow.executors.prompt_json_step.log_artifact_comment_status"
        ) as mock_log_status,
    ):
        mock_emit_artifact.return_value = ("success", "ok")
        mock_emit_payload.return_value = ("success", "ok")
        yield {
            "execute_template": mock_execute,
            "emit_artifact_comment": mock_emit_artifact,
            "emit_comment_from_payload": mock_emit_payload,
            "log_artifact_comment_status": mock_log_status,
        }


class TestClaudeCodePlanStepHappyPath:
    """Tests for successful plan building flow."""

    def test_happy_path(
        self,
        context_with_artifact: WorkflowContext,
        patched_executor: dict,
        issue: Issue,
    ) -> None:
        """Agent succeeds, PlanArtifact written with correct data."""
        mock_execute: MagicMock = patched_executor["execute_template"]
        mock_execute.return_value = _make_response(
            success=True,
            output=(
                '{"task": "Add dark mode toggle", "output": "plan", '
                '"plan": "## Implementation Plan\\n- Add toggle component\\n- Wire up state", '
                '"summary": "Plan for adding dark mode toggle to settings"}'
            ),
            session_id="sess-abc123",
        )

        step = ClaudeCodePlanStep()
        result = step.run(context_with_artifact)

        # Verify success
        assert result.success is True
        assert result.error is None

        # Verify execute_template was called with the issue description.
        mock_execute.assert_called_once()
        request = mock_execute.call_args.args[0]
        assert request.args == [issue.description]
        assert request.issue_id == issue.id

        # Verify PlanArtifact written to store
        assert context_with_artifact.artifact_store.artifact_exists("plan")
        saved_artifact = context_with_artifact.artifact_store.read_artifact(
            "plan", model_class=None
        )
        assert isinstance(saved_artifact, PlanArtifact)
        assert saved_artifact.artifact_type == "plan"
        assert (
            saved_artifact.plan_data.plan
            == "## Implementation Plan\n- Add toggle component\n- Wire up state"
        )
        assert saved_artifact.plan_data.summary == "Plan for adding dark mode toggle to settings"
        assert saved_artifact.plan_data.session_id == "sess-abc123"

        # Verify plan data mirrored into context
        assert "plan_data" in context_with_artifact.data

        # Verify artifact comment emitted
        patched_executor["emit_artifact_comment"].assert_called_once()

    def test_succeeds_when_context_issue_is_none_but_artifact_present(
        self,
        context_with_artifact: WorkflowContext,
        patched_executor: dict,
    ) -> None:
        """Step succeeds even when context.issue is None if fetch-issue artifact exists."""
        # Explicitly verify context.issue is None
        assert context_with_artifact.issue is None

        patched_executor["execute_template"].return_value = _make_response(
            success=True,
            output=(
                '{"task": "Task title", "output": "plan", '
                '"plan": "## Plan\\nDo the thing", "summary": "Summary"}'
            ),
        )

        step = ClaudeCodePlanStep()
        result = step.run(context_with_artifact)

        assert result.success is True


class TestClaudeCodePlanStepFailureCases:
    """Tests for error handling scenarios."""

    def test_missing_fetch_issue_artifact(
        self,
        context_without_artifact: WorkflowContext,
        patched_executor: dict,
    ) -> None:
        """Step fails when FetchIssueArtifact is missing."""
        step = ClaudeCodePlanStep()
        result = step.run(context_without_artifact)

        assert result.success is False
        assert result.error is not None
        assert "fetch-issue" in result.error

    def test_agent_failure(
        self,
        context_with_artifact: WorkflowContext,
        patched_executor: dict,
    ) -> None:
        """Step fails when agent returns failure, no artifact written."""
        patched_executor["execute_template"].return_value = _make_response(
            success=False,
            output="Agent execution failed",
        )

        step = ClaudeCodePlanStep()
        result = step.run(context_with_artifact)

        # Verify step failed
        assert result.success is False
        assert result.error is not None
        assert "Agent execution failed" in result.error

        # Verify no artifact was written
        assert not context_with_artifact.artifact_store.artifact_exists("plan")

        # Verify no comments emitted
        patched_executor["emit_artifact_comment"].assert_not_called()
        patched_executor["emit_comment_from_payload"].assert_not_called()

    def test_json_parse_failure(
        self,
        context_with_artifact: WorkflowContext,
        patched_executor: dict,
    ) -> None:
        """Step fails when JSON parsing fails."""
        # Output missing the required ``task`` field.
        patched_executor["execute_template"].return_value = _make_response(
            success=True,
            output=(
                '{"output": "plan", "plan": "## Plan\\nbody", ' '"summary": "Summary without task"}'
            ),
        )

        step = ClaudeCodePlanStep()
        result = step.run(context_with_artifact)

        # Verify step failed
        assert result.success is False
        assert result.error is not None

        # Verify no artifact was written
        assert not context_with_artifact.artifact_store.artifact_exists("plan")


class TestClaudeCodePlanStepCommentTitleExtraction:
    """Tests for comment title extraction from 'task' field."""

    def test_task_key_in_comment(
        self,
        context_with_artifact: WorkflowContext,
        patched_executor: dict,
    ) -> None:
        """Verify 'task' field is used for comment title extraction."""
        patched_executor["execute_template"].return_value = _make_response(
            success=True,
            output=(
                '{"task": "Add authentication feature", "output": "plan", '
                '"plan": "## Plan\\nImplementation details here", '
                '"summary": "Summary of the plan"}'
            ),
        )

        step = ClaudeCodePlanStep()
        result = step.run(context_with_artifact)

        assert result.success is True

        # Verify emit_comment_from_payload was called with the task title.
        mock_emit: MagicMock = patched_executor["emit_comment_from_payload"]
        mock_emit.assert_called_once()
        payload = mock_emit.call_args.args[0]

        # Verify the comment text includes the task title.
        assert "Add authentication feature" in payload.text
        assert "Summary of the plan" in payload.text

        # Verify parsed data is stored in raw field.
        assert payload.raw["parsed"]["task"] == "Add authentication feature"
        assert payload.raw["parsed"]["summary"] == "Summary of the plan"


class TestClaudeCodePlanStepProperties:
    """Tests for ClaudeCodePlanStep properties."""

    def test_step_name(self) -> None:
        """Test step has correct name."""
        step = ClaudeCodePlanStep()
        assert step.name == "Building task-oriented implementation plan"

    def test_step_is_critical(self) -> None:
        """Test step is critical."""
        step = ClaudeCodePlanStep()
        assert step.is_critical is True

    def test_step_id(self) -> None:
        """Step exposes the claude-code-plan slug as ``step_id``."""
        step = ClaudeCodePlanStep()
        assert step.step_id == "claude-code-plan"


class TestClaudeCodePlanStepArtifactHandling:
    """Tests for artifact reading and writing behavior."""

    def test_loads_issue_from_fetch_issue_artifact(
        self,
        context_with_artifact: WorkflowContext,
        patched_executor: dict,
        issue: Issue,
    ) -> None:
        """Step loads the issue from the fetch-issue artifact, not context.issue."""
        patched_executor["execute_template"].return_value = _make_response(
            success=True,
            output=(
                '{"task": "Task", "output": "plan", '
                '"plan": "## Plan\\nImplementation", "summary": "Plan summary"}'
            ),
        )

        step = ClaudeCodePlanStep()
        result = step.run(context_with_artifact)

        assert result.success is True
        # Verify execute_template was called with the issue description from the artifact.
        request = patched_executor["execute_template"].call_args.args[0]
        assert request.args == [issue.description]
        assert request.issue_id == issue.id

    def test_does_not_read_other_artifacts(
        self,
        context_with_artifact: WorkflowContext,
        patched_executor: dict,
    ) -> None:
        """Step reads only the fetch-issue artifact, not fetch-patch or plan artifacts."""
        patched_executor["execute_template"].return_value = _make_response(
            success=True,
            output=(
                '{"task": "Task", "output": "plan", '
                '"plan": "## Plan\\nFix", "summary": "Fix things"}'
            ),
        )

        read_calls: list[str] = []
        original_read = context_with_artifact.artifact_store.read_artifact

        def tracking_read(artifact_type: str, model_class: object = None) -> object:
            read_calls.append(artifact_type)
            return original_read(artifact_type, model_class)

        with patch.object(
            context_with_artifact.artifact_store,
            "read_artifact",
            side_effect=tracking_read,
        ):
            step = ClaudeCodePlanStep()
            step.run(context_with_artifact)

        # Only fetch-issue should be read.
        assert "fetch-patch" not in read_calls
        assert "plan" not in read_calls
        # fetch-issue may be read (it's the declared dependency).
        assert all(t == "fetch-issue" for t in read_calls)
