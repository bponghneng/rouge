"""Tests for ClaudeCodePlanStep workflow step.

Tests verify that ClaudeCodePlanStep:
- Loads issue from fetch-issue artifact
- Builds task-oriented plan via /adw-claude-code-plan
- Stores result as PlanArtifact
- Extracts comment title from 'task' field
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from rouge.core.models import Issue
from rouge.core.workflow.artifacts import ArtifactStore, FetchIssueArtifact
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.claude_code_plan_step import ClaudeCodePlanStep
from rouge.core.workflow.types import PlanData, StepResult


@pytest.fixture
def issue() -> Issue:
    """Create a sample issue."""
    return Issue(
        id=42,
        description="Add dark mode toggle to settings page",
        status="pending",
        type="main",
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


class TestClaudeCodePlanStepHappyPath:
    """Tests for successful plan building flow."""

    @patch("rouge.core.workflow.steps.claude_code_plan_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.claude_code_plan_step.emit_artifact_comment")
    @patch.object(ClaudeCodePlanStep, "_build_plan")
    def test_happy_path(
        self,
        mock_build,
        mock_emit_artifact,
        mock_emit,
        context_with_artifact,
        issue,
    ) -> None:
        """Agent succeeds, PlanArtifact written with correct data."""
        plan_data = PlanData(
            plan="## Implementation Plan\n- Add toggle component\n- Wire up state",
            summary="Plan for adding dark mode toggle to settings",
            session_id="sess-abc123",
        )
        parsed_data = {
            "task": "Add dark mode toggle",
            "output": "plan",
            "plan": "## Implementation Plan\n- Add toggle component\n- Wire up state",
            "summary": "Plan for adding dark mode toggle to settings",
        }
        mock_build.return_value = StepResult.ok(
            plan_data, session_id="sess-abc123", parsed_data=parsed_data
        )
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")

        step = ClaudeCodePlanStep()
        result = step.run(context_with_artifact)

        # Verify success
        assert result.success is True
        assert result.error is None

        # Verify _build_plan was called with correct issue
        mock_build.assert_called_once_with(issue, context_with_artifact.adw_id)

        # Verify plan data stored in context
        assert "plan_data" in context_with_artifact.data
        assert context_with_artifact.data["plan_data"] == plan_data

        # Verify PlanArtifact written to store
        assert context_with_artifact.artifact_store.artifact_exists("plan")
        saved_artifact = context_with_artifact.artifact_store.read_artifact(
            "plan", model_class=None
        )
        assert saved_artifact.artifact_type == "plan"
        assert saved_artifact.plan_data.plan == plan_data.plan
        assert saved_artifact.plan_data.summary == plan_data.summary
        assert saved_artifact.plan_data.session_id == "sess-abc123"

        # Verify artifact comment emitted
        mock_emit_artifact.assert_called_once()

    @patch("rouge.core.workflow.steps.claude_code_plan_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.claude_code_plan_step.emit_artifact_comment")
    @patch.object(ClaudeCodePlanStep, "_build_plan")
    def test_succeeds_when_context_issue_is_none_but_artifact_present(
        self,
        mock_build,
        mock_emit_artifact,
        mock_emit,
        context_with_artifact,
        issue,
    ) -> None:
        """Step succeeds even when context.issue is None if fetch-issue artifact exists."""
        # Explicitly verify context.issue is None
        assert context_with_artifact.issue is None

        plan_data = PlanData(plan="## Plan\nDo the thing", summary="Summary")
        parsed_data = {
            "task": "Task title",
            "output": "plan",
            "plan": "## Plan\nDo the thing",
            "summary": "Summary",
        }
        mock_build.return_value = StepResult.ok(plan_data, parsed_data=parsed_data)
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")

        step = ClaudeCodePlanStep()
        result = step.run(context_with_artifact)

        assert result.success is True


class TestClaudeCodePlanStepFailureCases:
    """Tests for error handling scenarios."""

    def test_missing_fetch_issue_artifact(self, context_without_artifact) -> None:
        """Step fails when FetchIssueArtifact is missing."""
        step = ClaudeCodePlanStep()
        result = step.run(context_without_artifact)

        assert result.success is False
        assert "issue not fetched" in result.error

    @patch("rouge.core.workflow.steps.claude_code_plan_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.claude_code_plan_step.emit_artifact_comment")
    @patch.object(ClaudeCodePlanStep, "_build_plan")
    def test_agent_failure(
        self,
        mock_build,
        mock_emit_artifact,
        mock_emit,
        context_with_artifact,
    ) -> None:
        """Step fails when agent returns failure, no artifact written."""
        # Simulate agent failure
        mock_build.return_value = StepResult.fail("Agent execution failed")

        step = ClaudeCodePlanStep()
        result = step.run(context_with_artifact)

        # Verify step failed
        assert result.success is False
        assert "Error building plan" in result.error
        assert "Agent execution failed" in result.error

        # Verify no artifact was written
        assert not context_with_artifact.artifact_store.artifact_exists("plan")

        # Verify no comments emitted
        mock_emit_artifact.assert_not_called()
        mock_emit.assert_not_called()

    @patch("rouge.core.workflow.steps.claude_code_plan_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.claude_code_plan_step.emit_artifact_comment")
    @patch.object(ClaudeCodePlanStep, "_build_plan")
    def test_json_parse_failure(
        self,
        mock_build,
        mock_emit_artifact,
        mock_emit,
        context_with_artifact,
    ) -> None:
        """Step fails when JSON parsing fails."""
        # Mock _build_plan to return a parse failure
        mock_build.return_value = StepResult.fail("Missing required field: task")

        step = ClaudeCodePlanStep()
        result = step.run(context_with_artifact)

        # Verify step failed
        assert result.success is False
        assert "Error building plan" in result.error
        assert "Missing required field" in result.error

        # Verify no artifact was written
        assert not context_with_artifact.artifact_store.artifact_exists("plan")


class TestClaudeCodePlanStepCommentTitleExtraction:
    """Tests for comment title extraction from 'task' field."""

    @patch("rouge.core.workflow.steps.claude_code_plan_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.claude_code_plan_step.emit_artifact_comment")
    @patch.object(ClaudeCodePlanStep, "_build_plan")
    def test_task_key_in_comment(
        self,
        mock_build,
        mock_emit_artifact,
        mock_emit,
        context_with_artifact,
    ) -> None:
        """Verify 'task' field is used for comment title extraction."""
        plan_data = PlanData(
            plan="## Plan\nImplementation details here",
            summary="Summary of the plan",
        )
        parsed_data = {
            "task": "Add authentication feature",
            "output": "plan",
            "plan": "## Plan\nImplementation details here",
            "summary": "Summary of the plan",
        }
        mock_build.return_value = StepResult.ok(plan_data, parsed_data=parsed_data)
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")

        step = ClaudeCodePlanStep()
        result = step.run(context_with_artifact)

        assert result.success is True

        # Verify emit_comment_from_payload was called
        mock_emit.assert_called_once()
        payload = mock_emit.call_args[0][0]

        # Verify the comment text includes the task title
        assert "Add authentication feature" in payload.text
        assert "Summary of the plan" in payload.text

        # Verify parsed data is stored in raw field
        assert payload.raw["parsed"] == parsed_data

    @patch("rouge.core.workflow.steps.claude_code_plan_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.claude_code_plan_step.emit_artifact_comment")
    @patch.object(ClaudeCodePlanStep, "_build_plan")
    def test_task_key_fallback_when_missing(
        self,
        mock_build,
        mock_emit_artifact,
        mock_emit,
        context_with_artifact,
    ) -> None:
        """Verify fallback title when 'task' field is missing from parsed_data."""
        plan_data = PlanData(
            plan="## Plan\nDetails",
            summary="Summary",
        )
        # parsed_data without 'task' key
        parsed_data = {
            "output": "plan",
            "plan": "## Plan\nDetails",
            "summary": "Summary",
        }
        mock_build.return_value = StepResult.ok(plan_data, parsed_data=parsed_data)
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")

        step = ClaudeCodePlanStep()
        result = step.run(context_with_artifact)

        assert result.success is True

        # Verify fallback title is used when task key is missing
        mock_emit.assert_called_once()
        payload = mock_emit.call_args[0][0]
        assert "Implementation plan created" in payload.text
        assert "Summary" in payload.text


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


class TestClaudeCodePlanStepArtifactHandling:
    """Tests for artifact reading and writing behavior."""

    @patch("rouge.core.workflow.steps.claude_code_plan_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.claude_code_plan_step.emit_artifact_comment")
    @patch.object(ClaudeCodePlanStep, "_build_plan")
    def test_loads_issue_from_fetch_issue_artifact(
        self,
        mock_build,
        mock_emit_artifact,
        mock_emit,
        context_with_artifact,
        issue,
    ) -> None:
        """Step loads the issue from the fetch-issue artifact, not context.issue."""
        plan_data = PlanData(
            plan="## Plan\nImplementation",
            summary="Plan summary",
        )
        parsed_data = {
            "task": "Task",
            "output": "plan",
            "plan": "## Plan\nImplementation",
            "summary": "Plan summary",
        }
        mock_build.return_value = StepResult.ok(plan_data, parsed_data=parsed_data)
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")

        step = ClaudeCodePlanStep()
        result = step.run(context_with_artifact)

        assert result.success is True
        # Verify _build_plan was called with the issue from the artifact
        mock_build.assert_called_once_with(
            issue,
            context_with_artifact.adw_id,
        )

    @patch("rouge.core.workflow.steps.claude_code_plan_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.claude_code_plan_step.emit_artifact_comment")
    @patch.object(ClaudeCodePlanStep, "_build_plan")
    def test_does_not_read_other_artifacts(
        self,
        mock_build,
        mock_emit_artifact,
        mock_emit,
        context_with_artifact,
    ) -> None:
        """Step reads only the fetch-issue artifact, not fetch-patch or plan artifacts."""
        plan_data = PlanData(plan="## Plan\nFix", summary="Fix things")
        parsed_data = {
            "task": "Task",
            "output": "plan",
            "plan": "## Plan\nFix",
            "summary": "Fix things",
        }
        mock_build.return_value = StepResult.ok(plan_data, parsed_data=parsed_data)
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")

        read_calls: list[str] = []
        original_read = context_with_artifact.artifact_store.read_artifact

        def tracking_read(artifact_type, model_class=None):
            read_calls.append(artifact_type)
            return original_read(artifact_type, model_class)

        with patch.object(
            context_with_artifact.artifact_store, "read_artifact", side_effect=tracking_read
        ):
            step = ClaudeCodePlanStep()
            step.run(context_with_artifact)

        # Only fetch-issue should be read
        assert "fetch-patch" not in read_calls
        assert "plan" not in read_calls
        # fetch-issue may be read (it's the declared dependency)
        assert all(t == "fetch-issue" for t in read_calls)
