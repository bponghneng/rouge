"""Tests for PatchPlanStep workflow step.

Tests verify that PatchPlanStep loads the patch issue from context.issue
(set by FetchPatchStep).
"""

from unittest.mock import patch

import pytest

from rouge.core.models import Issue
from rouge.core.prompts import PromptId
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.patch_plan_step import PatchPlanStep
from rouge.core.workflow.types import PlanData, StepResult


@pytest.fixture
def patch_issue() -> Issue:
    """Create a sample patch issue."""
    return Issue(
        id=10,
        description="Fix typo in README and update documentation links",
        status="pending",
        type="patch",
        adw_id="patch-abc123",
        branch="patch/fix-typo",
    )


@pytest.fixture
def context_with_issue(patch_issue: Issue) -> WorkflowContext:
    """Create a workflow context with context.issue set (as FetchPatchStep would)."""
    ctx = WorkflowContext(
        issue_id=10,
        adw_id="test-adw-patch-plan",
    )
    ctx.issue = patch_issue
    return ctx


@pytest.fixture
def context_without_issue() -> WorkflowContext:
    """Create a workflow context WITHOUT context.issue set."""
    return WorkflowContext(
        issue_id=10,
        adw_id="test-adw-patch-plan",
    )


class TestBuildPatchPlanStepLoadsFromContext:
    """Tests verifying PatchPlanStep loads the issue from context.issue."""

    @patch("rouge.core.workflow.steps.patch_plan_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.patch_plan_step.build_plan_from_template")
    def test_loads_issue_from_context(
        self,
        mock_build,
        mock_emit,
        context_with_issue,
        patch_issue,
    ) -> None:
        """Step loads the patch issue from context.issue."""
        plan_data = PlanData(
            plan="## Patch Plan\nFix typo",
            summary="Plan for patch: Fix typo in README",
        )
        mock_build.return_value = StepResult.ok(plan_data, metadata={"session_id": "sess-1"})
        mock_emit.return_value = ("success", "ok")

        step = PatchPlanStep()
        result = step.run(context_with_issue)

        assert result.success is True
        # Verify build_plan_from_template was called with the issue from context
        mock_build.assert_called_once_with(
            patch_issue,
            PromptId.PATCH_PLAN,
            context_with_issue.adw_id,
        )

    def test_fails_when_context_issue_is_none(self, context_without_issue) -> None:
        """Step fails when context.issue is None (required dependency)."""
        step = PatchPlanStep()
        result = step.run(context_without_issue)

        assert result.success is False
        assert "Cannot build patch plan" in result.error

    @patch("rouge.core.workflow.steps.patch_plan_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.patch_plan_step.build_plan_from_template")
    def test_stores_plan_data_in_context(
        self,
        mock_build,
        mock_emit,
        context_with_issue,
        patch_issue,
    ) -> None:
        """Step stores plan data in context.data['plan_data']."""
        plan_data = PlanData(
            plan="## Plan\nDo the thing",
            summary="Plan for patch: Fix typo",
        )
        mock_build.return_value = StepResult.ok(plan_data)
        mock_emit.return_value = ("success", "ok")

        step = PatchPlanStep()
        result = step.run(context_with_issue)

        assert result.success is True
        assert context_with_issue.data["plan_data"] == plan_data


class TestBuildPatchPlanStepProperties:
    """Tests for PatchPlanStep properties."""

    def test_step_name(self) -> None:
        """Test step has correct name."""
        step = PatchPlanStep()
        assert step.name == "Building patch plan"

    def test_step_is_critical(self) -> None:
        """Test step is critical."""
        step = PatchPlanStep()
        assert step.is_critical is True
