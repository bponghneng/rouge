"""Tests for BuildPatchPlanStep workflow step.

Tests verify that BuildPatchPlanStep works independently from parent
workflow artifacts, using only context.issue (set by FetchPatchStep).
"""

from unittest.mock import Mock, patch

import pytest

from rouge.core.models import Issue
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.patch_plan import BuildPatchPlanStep
from rouge.core.workflow.types import PlanData, StepResult


@pytest.fixture
def mock_context():
    """Create a mock workflow context."""
    context = Mock(spec=WorkflowContext)
    context.issue_id = 10
    context.require_issue_id = 10
    context.adw_id = "test-adw-patch-plan"
    context.data = {}
    context.artifacts_enabled = True
    context.artifact_store = Mock()
    return context


@pytest.fixture
def patch_issue():
    """Create a sample patch issue."""
    return Issue(
        id=10,
        description="Fix typo in README and update documentation links",
        status="pending",
        type="patch",
        adw_id="patch-abc123",
    )


class TestBuildPatchPlanStepWithoutParentArtifacts:
    """Tests verifying BuildPatchPlanStep works without parent artifacts."""

    @patch("rouge.core.workflow.steps.patch_plan.emit_comment_from_payload")
    @patch.object(BuildPatchPlanStep, "_build_plan")
    def test_uses_context_issue_directly(
        self,
        mock_build,
        mock_emit,
        mock_context,
        patch_issue,
    ):
        """Test that BuildPatchPlanStep uses context.issue directly, not parent artifacts."""
        mock_context.issue = patch_issue
        plan_data = PlanData(
            plan="## Patch Plan\nFix typo",
            summary="Plan for patch: Fix typo in README",
        )
        mock_build.return_value = StepResult.ok(plan_data, metadata={"session_id": "sess-1"})
        mock_emit.return_value = ("success", "ok")

        step = BuildPatchPlanStep()
        result = step.run(mock_context)

        assert result.success is True
        # Verify _build_plan was called with the issue from context
        mock_build.assert_called_once_with(
            patch_issue,
            "/adw-patch-plan",
            mock_context.adw_id,
        )
        # Verify plan_data was stored in context
        assert mock_context.data["plan_data"] == plan_data

    def test_fails_when_issue_not_set(self, mock_context):
        """Test that step fails when context.issue is None (no parent dependency)."""
        mock_context.issue = None

        step = BuildPatchPlanStep()
        result = step.run(mock_context)

        assert result.success is False
        assert "patch issue not available" in result.error

    @patch("rouge.core.workflow.steps.patch_plan.emit_comment_from_payload")
    @patch.object(BuildPatchPlanStep, "_build_plan")
    def test_saves_plan_artifact_not_patch_plan_artifact(
        self,
        mock_build,
        mock_emit,
        mock_context,
        patch_issue,
    ):
        """Test that step saves a PlanArtifact, not a PatchPlanArtifact."""
        mock_context.issue = patch_issue
        plan_data = PlanData(
            plan="## Plan\nDo the thing",
            summary="Plan for patch: Fix typo",
        )
        mock_build.return_value = StepResult.ok(plan_data)
        mock_emit.return_value = ("success", "ok")

        step = BuildPatchPlanStep()
        result = step.run(mock_context)

        assert result.success is True
        # Verify the artifact saved is a PlanArtifact
        mock_context.artifact_store.write_artifact.assert_called_once()
        saved_artifact = mock_context.artifact_store.write_artifact.call_args[0][0]
        assert saved_artifact.artifact_type == "plan"
        assert saved_artifact.plan_data == plan_data

    @patch("rouge.core.workflow.steps.patch_plan.emit_comment_from_payload")
    @patch.object(BuildPatchPlanStep, "_build_plan")
    def test_no_parent_artifact_loading(
        self,
        mock_build,
        mock_emit,
        mock_context,
        patch_issue,
    ):
        """Test that step does not attempt to load any parent workflow artifacts.

        The step should only use context.issue (set by FetchPatchStep).
        It should NOT call load_artifact_if_missing or access artifact_store.read_artifact.
        """
        mock_context.issue = patch_issue
        plan_data = PlanData(plan="## Plan\nFix", summary="Fix things")
        mock_build.return_value = StepResult.ok(plan_data)
        mock_emit.return_value = ("success", "ok")

        step = BuildPatchPlanStep()
        result = step.run(mock_context)

        assert result.success is True
        # Verify no read operations on artifact store (only write)
        mock_context.artifact_store.read_artifact.assert_not_called()
        # Verify load_artifact_if_missing was not called
        if hasattr(mock_context, "load_artifact_if_missing"):
            mock_context.load_artifact_if_missing.assert_not_called()


class TestBuildPatchPlanStepProperties:
    """Tests for BuildPatchPlanStep properties."""

    def test_step_name(self):
        """Test step has correct name."""
        step = BuildPatchPlanStep()
        assert step.name == "Building patch plan"

    def test_step_is_critical(self):
        """Test step is critical."""
        step = BuildPatchPlanStep()
        assert step.is_critical is True
