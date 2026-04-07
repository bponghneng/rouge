"""Tests for ClaudeCodePlanStep workflow step.

Tests verify that ClaudeCodePlanStep:
- Loads issue from context.issue
- Builds task-oriented plan via _build_plan
- Stores result in context.data
- Extracts comment title from 'task' field
"""

from unittest.mock import patch

import pytest

from rouge.core.models import Issue
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
        type="full",
        adw_id="full-abc123",
        branch="feature/dark-mode",
    )


@pytest.fixture
def context_with_issue(issue: Issue) -> WorkflowContext:
    """Create a workflow context with the issue set on context."""
    ctx = WorkflowContext(
        issue_id=42,
        adw_id="test-adw-full",
    )
    ctx.issue = issue
    return ctx


@pytest.fixture
def context_without_issue() -> WorkflowContext:
    """Create a workflow context WITHOUT an issue."""
    return WorkflowContext(
        issue_id=42,
        adw_id="test-adw-full",
    )


class TestClaudeCodePlanStepHappyPath:
    """Tests for successful plan building flow."""

    @patch("rouge.core.workflow.steps.claude_code_plan_step.emit_comment_from_payload")
    @patch.object(ClaudeCodePlanStep, "_build_plan")
    def test_happy_path(
        self,
        mock_build,
        mock_emit,
        context_with_issue,
        issue,
    ) -> None:
        """Agent succeeds, plan data written to context."""
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

        step = ClaudeCodePlanStep()
        result = step.run(context_with_issue)

        # Verify success
        assert result.success is True
        assert result.error is None

        # Verify _build_plan was called with correct issue
        mock_build.assert_called_once_with(issue, context_with_issue.adw_id)

        # Verify plan data stored in context
        assert "plan_data" in context_with_issue.data
        assert context_with_issue.data["plan_data"] == plan_data

    @patch("rouge.core.workflow.steps.claude_code_plan_step.emit_comment_from_payload")
    @patch.object(ClaudeCodePlanStep, "_build_plan")
    def test_succeeds_with_issue_on_context(
        self,
        mock_build,
        mock_emit,
        context_with_issue,
        issue,
    ) -> None:
        """Step succeeds when context.issue is set."""
        plan_data = PlanData(plan="## Plan\nDo the thing", summary="Summary")
        parsed_data = {
            "task": "Task title",
            "output": "plan",
            "plan": "## Plan\nDo the thing",
            "summary": "Summary",
        }
        mock_build.return_value = StepResult.ok(plan_data, parsed_data=parsed_data)
        mock_emit.return_value = ("success", "ok")

        step = ClaudeCodePlanStep()
        result = step.run(context_with_issue)

        assert result.success is True


class TestClaudeCodePlanStepFailureCases:
    """Tests for error handling scenarios."""

    def test_missing_issue(self, context_without_issue) -> None:
        """Step fails when context.issue is None."""
        step = ClaudeCodePlanStep()
        result = step.run(context_without_issue)

        assert result.success is False
        assert "no issue in context" in result.error

    @patch("rouge.core.workflow.steps.claude_code_plan_step.emit_comment_from_payload")
    @patch.object(ClaudeCodePlanStep, "_build_plan")
    def test_agent_failure(
        self,
        mock_build,
        mock_emit,
        context_with_issue,
    ) -> None:
        """Step fails when agent returns failure, no plan data written."""
        # Simulate agent failure
        mock_build.return_value = StepResult.fail("Agent execution failed")

        step = ClaudeCodePlanStep()
        result = step.run(context_with_issue)

        # Verify step failed
        assert result.success is False
        assert "Error building plan" in result.error
        assert "Agent execution failed" in result.error

        # Verify no plan data was stored
        assert "plan_data" not in context_with_issue.data

        # Verify no comments emitted
        mock_emit.assert_not_called()

    @patch("rouge.core.workflow.steps.claude_code_plan_step.emit_comment_from_payload")
    @patch.object(ClaudeCodePlanStep, "_build_plan")
    def test_json_parse_failure(
        self,
        mock_build,
        mock_emit,
        context_with_issue,
    ) -> None:
        """Step fails when JSON parsing fails."""
        # Mock _build_plan to return a parse failure
        mock_build.return_value = StepResult.fail("Missing required field: task")

        step = ClaudeCodePlanStep()
        result = step.run(context_with_issue)

        # Verify step failed
        assert result.success is False
        assert "Error building plan" in result.error
        assert "Missing required field" in result.error

        # Verify no plan data was stored
        assert "plan_data" not in context_with_issue.data


class TestClaudeCodePlanStepCommentTitleExtraction:
    """Tests for comment title extraction from 'task' field."""

    @patch("rouge.core.workflow.steps.claude_code_plan_step.emit_comment_from_payload")
    @patch.object(ClaudeCodePlanStep, "_build_plan")
    def test_task_key_in_comment(
        self,
        mock_build,
        mock_emit,
        context_with_issue,
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

        step = ClaudeCodePlanStep()
        result = step.run(context_with_issue)

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
    @patch.object(ClaudeCodePlanStep, "_build_plan")
    def test_task_key_fallback_when_missing(
        self,
        mock_build,
        mock_emit,
        context_with_issue,
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

        step = ClaudeCodePlanStep()
        result = step.run(context_with_issue)

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


class TestClaudeCodePlanStepDataHandling:
    """Tests for data reading and writing behavior."""

    @patch("rouge.core.workflow.steps.claude_code_plan_step.emit_comment_from_payload")
    @patch.object(ClaudeCodePlanStep, "_build_plan")
    def test_loads_issue_from_context(
        self,
        mock_build,
        mock_emit,
        context_with_issue,
        issue,
    ) -> None:
        """Step loads the issue from context.issue."""
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

        step = ClaudeCodePlanStep()
        result = step.run(context_with_issue)

        assert result.success is True
        # Verify _build_plan was called with the issue from context
        mock_build.assert_called_once_with(
            issue,
            context_with_issue.adw_id,
        )
