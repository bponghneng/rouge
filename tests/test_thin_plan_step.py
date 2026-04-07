"""Tests for ThinPlanStep workflow step.

Tests verify that ThinPlanStep loads the issue from context.issue
and stores plan data in context.data.
"""

from unittest.mock import patch

import pytest

from rouge.core.models import Issue
from rouge.core.prompts import PromptId
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.thin_plan_step import ThinPlanStep
from rouge.core.workflow.types import PlanData, StepResult


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
def context_with_issue(issue: Issue) -> WorkflowContext:
    """Create a workflow context with the issue set on context."""
    ctx = WorkflowContext(
        issue_id=5,
        adw_id="test-adw-thin-plan",
    )
    ctx.issue = issue
    return ctx


@pytest.fixture
def context_without_issue() -> WorkflowContext:
    """Create a workflow context WITHOUT an issue."""
    return WorkflowContext(
        issue_id=5,
        adw_id="test-adw-thin-plan",
    )


class TestThinPlanStepLoadsFromContext:
    """Tests verifying ThinPlanStep loads the issue from context.issue."""

    @patch("rouge.core.workflow.steps.thin_plan_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.thin_plan_step.build_plan_from_template")
    def test_loads_issue_from_context(
        self,
        mock_build_template,
        mock_emit,
        context_with_issue,
        issue,
    ) -> None:
        """Step loads the issue from context.issue and stores plan data."""
        plan_data = PlanData(
            plan="## Thin Plan\nAdd utility function",
            summary="Plan for adding string sanitization utility",
        )
        mock_build_template.return_value = StepResult.ok(plan_data, metadata={"parsed_data": {}})
        mock_emit.return_value = ("success", "ok")

        step = ThinPlanStep()
        result = step.run(context_with_issue)

        assert result.success is True
        # Verify build_plan_from_template was called with the issue from context
        mock_build_template.assert_called_once_with(
            issue,
            PromptId.THIN_PLAN,
            context_with_issue.adw_id,
        )
        # Verify plan data was stored in context
        assert "plan_data" in context_with_issue.data
        assert context_with_issue.data["plan_data"] == plan_data

    def test_fails_when_issue_missing(
        self,
        context_without_issue,
    ) -> None:
        """Step fails when context.issue is None (required dependency)."""
        step = ThinPlanStep()
        result = step.run(context_without_issue)

        assert result.success is False
        assert result.error is not None
        assert "Cannot build thin plan" in result.error

    @patch("rouge.core.workflow.steps.thin_plan_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.thin_plan_step.build_plan_from_template")
    def test_calls_build_plan_with_thin_plan_prompt_id(
        self,
        mock_build_template,
        mock_emit,
        context_with_issue,
        issue,
    ) -> None:
        """build_plan_from_template is called with PromptId.THIN_PLAN."""
        plan_data = PlanData(
            plan="## Thin Plan\nImplement feature",
            summary="Summary",
        )
        mock_build_template.return_value = StepResult.ok(plan_data, metadata={"parsed_data": {}})
        mock_emit.return_value = ("success", "ok")

        step = ThinPlanStep()
        result = step.run(context_with_issue)

        assert result.success is True
        mock_build_template.assert_called_once_with(
            issue,
            PromptId.THIN_PLAN,
            context_with_issue.adw_id,
        )

    @patch("rouge.core.workflow.steps.thin_plan_step.build_plan_from_template")
    def test_fails_when_build_plan_fails(
        self,
        mock_build_template,
        context_with_issue,
    ) -> None:
        """Step returns failure when build_plan_from_template returns a failed StepResult."""
        mock_build_template.return_value = StepResult.fail("Template execution error")

        step = ThinPlanStep()
        result = step.run(context_with_issue)

        assert result.success is False
        assert result.error is not None
        assert "Error building thin plan" in result.error

    @patch("rouge.core.workflow.steps.thin_plan_step.build_plan_from_template")
    def test_fails_when_plan_data_is_none(
        self,
        mock_build_template,
        context_with_issue,
    ) -> None:
        """Step fails when plan succeeds but returns None data."""
        mock_build_template.return_value = StepResult.ok(None, metadata={"parsed_data": {}})

        step = ThinPlanStep()
        result = step.run(context_with_issue)

        assert result.success is False
        assert result.error is not None
        assert "no plan data" in result.error
        assert "plan_data" not in context_with_issue.data


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
