"""Tests for PatchPlanStep workflow step.

Tests verify that PatchPlanStep loads the patch issue from the fetch-patch
artifact (not from context.issue directly).
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from rouge.core.models import Issue
from rouge.core.prompts import PromptId
from rouge.core.workflow.artifacts import ArtifactStore, FetchPatchArtifact
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
def store(tmp_path: Path) -> ArtifactStore:
    """Create a temporary artifact store."""
    return ArtifactStore(workflow_id="test-adw-patch-plan", base_path=tmp_path)


@pytest.fixture
def context_with_artifact(patch_issue: Issue, store: ArtifactStore) -> WorkflowContext:
    """Create a workflow context with fetch-patch artifact written to the store."""
    artifact = FetchPatchArtifact(
        workflow_id=store.workflow_id,
        patch=patch_issue,
    )
    store.write_artifact(artifact)
    return WorkflowContext(
        issue_id=10,
        adw_id="test-adw-patch-plan",
        artifact_store=store,
    )


@pytest.fixture
def context_without_artifact(store: ArtifactStore) -> WorkflowContext:
    """Create a workflow context WITHOUT fetch-patch artifact."""
    return WorkflowContext(
        issue_id=10,
        adw_id="test-adw-patch-plan",
        artifact_store=store,
    )


class TestBuildPatchPlanStepLoadsFromArtifact:
    """Tests verifying PatchPlanStep loads the issue from fetch-patch artifact."""

    @patch("rouge.core.workflow.steps.patch_plan_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.patch_plan_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.patch_plan_step.build_plan_from_template")
    def test_loads_issue_from_fetch_patch_artifact(
        self,
        mock_build,
        mock_emit_artifact,
        mock_emit,
        context_with_artifact,
        patch_issue,
    ) -> None:
        """Step loads the patch issue from the fetch-patch artifact, not context.issue."""
        plan_data = PlanData(
            plan="## Patch Plan\nFix typo",
            summary="Plan for patch: Fix typo in README",
        )
        mock_build.return_value = StepResult.ok(plan_data, metadata={"session_id": "sess-1"})
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")

        step = PatchPlanStep()
        result = step.run(context_with_artifact)

        assert result.success is True
        # Verify build_plan_from_template was called with the issue from the artifact
        mock_build.assert_called_once_with(
            patch_issue,
            PromptId.PATCH_PLAN,
            context_with_artifact.adw_id,
        )

    @patch("rouge.core.workflow.steps.patch_plan_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.patch_plan_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.patch_plan_step.build_plan_from_template")
    def test_succeeds_when_context_issue_is_none_but_artifact_present(
        self,
        mock_build,
        mock_emit_artifact,
        mock_emit,
        context_with_artifact,
        patch_issue,
    ) -> None:
        """Step succeeds even when context.issue is None if fetch-patch artifact exists."""
        # Explicitly leave context.issue as None (the default)
        assert context_with_artifact.issue is None

        plan_data = PlanData(plan="## Plan\nDo the thing", summary="Summary")
        mock_build.return_value = StepResult.ok(plan_data)
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")

        step = PatchPlanStep()
        result = step.run(context_with_artifact)

        assert result.success is True

    def test_fails_when_fetch_patch_artifact_missing(self, context_without_artifact) -> None:
        """Step fails when fetch-patch artifact is absent (required dependency)."""
        step = PatchPlanStep()
        result = step.run(context_without_artifact)

        assert result.success is False
        assert "Cannot build patch plan" in result.error

    @patch("rouge.core.workflow.steps.patch_plan_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.patch_plan_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.patch_plan_step.build_plan_from_template")
    def test_saves_plan_artifact_not_patch_plan_artifact(
        self,
        mock_build,
        mock_emit_artifact,
        mock_emit,
        context_with_artifact,
        patch_issue,
    ) -> None:
        """Step saves a PlanArtifact (not a PatchPlanArtifact)."""
        plan_data = PlanData(
            plan="## Plan\nDo the thing",
            summary="Plan for patch: Fix typo",
        )
        mock_build.return_value = StepResult.ok(plan_data)
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")

        step = PatchPlanStep()
        result = step.run(context_with_artifact)

        assert result.success is True
        # Verify the artifact saved is a PlanArtifact
        assert context_with_artifact.artifact_store.artifact_exists("plan")

    @patch("rouge.core.workflow.steps.patch_plan_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.patch_plan_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.patch_plan_step.build_plan_from_template")
    def test_does_not_read_other_artifacts(
        self,
        mock_build,
        mock_emit_artifact,
        mock_emit,
        context_with_artifact,
    ) -> None:
        """Step reads only the fetch-patch artifact, not fetch-issue or plan artifacts."""
        plan_data = PlanData(plan="## Plan\nFix", summary="Fix things")
        mock_build.return_value = StepResult.ok(plan_data)
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
            step = PatchPlanStep()
            step.run(context_with_artifact)

        # Only fetch-patch should be read
        assert "fetch-issue" not in read_calls
        assert "plan" not in read_calls
        # fetch-patch may be read (it's the declared dependency)
        assert all(t == "fetch-patch" for t in read_calls)


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
