"""Tests for the codereview workflow: registry, pipeline composition, and rerun behavior.

Complements tests in test_adw.py (workflow runner mechanics) and
test_workflow_registry.py (generic registry mechanics) by focusing on
codereview-specific registration, pipeline composition, and rerun_from behavior.
"""

import pathlib
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from rouge.core.workflow.pipeline import WorkflowRunner, get_code_review_pipeline
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.steps.code_quality_step import CodeQualityStep
from rouge.core.workflow.steps.code_review_step import CodeReviewStep
from rouge.core.workflow.steps.compose_commits_step import ComposeCommitsStep
from rouge.core.workflow.steps.fetch_issue_step import FetchIssueStep
from rouge.core.workflow.steps.review_fix_step import ReviewFixStep
from rouge.core.workflow.steps.review_plan_step import ReviewPlanStep
from rouge.core.workflow.types import StepResult
from rouge.core.workflow.workflow_registry import (
    get_pipeline_for_type,
    get_workflow_registry,
    reset_workflow_registry,
)


@pytest.fixture(autouse=True)
def _reset_registry() -> Generator[None, None, None]:
    """Reset the global workflow registry before and after each test."""
    reset_workflow_registry()
    yield
    reset_workflow_registry()


# ---------------------------------------------------------------------------
# Registry registration tests
# ---------------------------------------------------------------------------


class TestCodeReviewRegistration:
    """Verify the codereview workflow is registered in the global registry."""

    def test_codereview_is_registered(self) -> None:
        """The default registry should contain a 'codereview' workflow type."""
        registry = get_workflow_registry()

        assert registry.is_registered("codereview")

    def test_codereview_in_list_types(self) -> None:
        """'codereview' should appear in the registry's list of available types."""
        registry = get_workflow_registry()
        types = registry.list_types()

        assert "codereview" in types

    def test_registry_pipeline_returns_workflow_steps(self) -> None:
        """get_pipeline via the registry should return a list of WorkflowStep instances."""
        registry = get_workflow_registry()
        pipeline = registry.get_pipeline("codereview")

        assert isinstance(pipeline, list)
        assert len(pipeline) > 0
        assert all(isinstance(step, WorkflowStep) for step in pipeline)


# ---------------------------------------------------------------------------
# Pipeline structure tests
# ---------------------------------------------------------------------------


class TestCodeReviewPipeline:
    """Verify the codereview pipeline contains the correct steps in order."""

    def test_pipeline_contains_six_steps(self) -> None:
        """The codereview pipeline should contain exactly 6 steps."""
        pipeline = get_code_review_pipeline()

        assert len(pipeline) == 6

    def test_pipeline_step_order(self) -> None:
        """Steps should be: FetchIssueStep, ReviewPlanStep, CodeReviewStep, ReviewFixStep, CodeQualityStep, ComposeCommitsStep."""
        pipeline = get_code_review_pipeline()

        expected_types = [
            FetchIssueStep,
            ReviewPlanStep,
            CodeReviewStep,
            ReviewFixStep,
            CodeQualityStep,
            ComposeCommitsStep,
        ]

        for i, (step, expected_type) in enumerate(zip(pipeline, expected_types, strict=True)):
            assert isinstance(
                step, expected_type
            ), f"Step {i} should be {expected_type.__name__}, got {type(step).__name__}"

    def test_pipeline_step_names(self) -> None:
        """Each step should expose the expected human-readable name."""
        pipeline = get_code_review_pipeline()

        # Verify each step has a non-empty name
        for i, step in enumerate(pipeline):
            assert isinstance(step.name, str), f"Step {i} name should be a string"
            assert len(step.name) > 0, f"Step {i} name should not be empty"

    def test_critical_vs_best_effort_steps(self) -> None:
        """Verify which steps are critical vs best-effort in the pipeline.

        FetchIssueStep and ReviewPlanStep are critical (must succeed).
        Review/fix/quality/commits steps are best-effort (can fail gracefully).
        """
        pipeline = get_code_review_pipeline()

        # First two steps are critical
        assert pipeline[0].is_critical, "FetchIssueStep should be critical"
        assert pipeline[1].is_critical, "ReviewPlanStep should be critical"

        # Remaining steps are best-effort
        for step in pipeline[2:]:
            assert (
                not step.is_critical
            ), f"Step '{step.name}' should be best-effort (is_critical=False)"

    def test_pipeline_includes_fetch_issue_step(self) -> None:
        """Codereview pipeline should include FetchIssueStep as it is now issue-based."""
        pipeline = get_code_review_pipeline()

        assert isinstance(
            pipeline[0], FetchIssueStep
        ), "Codereview pipeline should start with FetchIssueStep"

    def test_pipeline_does_not_include_implementation_steps(self) -> None:
        """Codereview pipeline should not contain planning or implementation steps."""
        from rouge.core.workflow.steps import (
            PlanStep,
            ClassifyStep,
            ImplementStep,
            ComposeRequestStep,
            GitSetupStep,
            AcceptanceStep,
        )

        excluded_types = (
            GitSetupStep,
            ClassifyStep,
            PlanStep,
            ImplementStep,
            AcceptanceStep,
            ComposeRequestStep,
        )

        pipeline = get_code_review_pipeline()

        for step in pipeline:
            assert not isinstance(
                step, excluded_types
            ), f"Codereview pipeline should not contain {type(step).__name__}"


# ---------------------------------------------------------------------------
# get_pipeline_for_type integration tests
# ---------------------------------------------------------------------------


class TestGetPipelineForTypeCodeReview:
    """Verify get_pipeline_for_type resolves 'codereview' correctly."""

    def test_returns_codereview_pipeline(self) -> None:
        """get_pipeline_for_type('codereview') should resolve via registry."""
        pipeline = get_pipeline_for_type("codereview")

        assert isinstance(pipeline, list)
        assert len(pipeline) == 6
        assert all(isinstance(step, WorkflowStep) for step in pipeline)

    def test_pipeline_matches_direct_call(self) -> None:
        """Pipeline from get_pipeline_for_type should match get_code_review_pipeline."""
        from_helper = get_pipeline_for_type("codereview")
        from_direct = get_code_review_pipeline()

        assert len(from_helper) == len(from_direct)
        for h, d in zip(from_helper, from_direct):
            assert type(h) is type(d)


# ---------------------------------------------------------------------------
# Rerun behavior tests
# ---------------------------------------------------------------------------


class TestCodeReviewRerunBehavior:
    """Test the rerun_from mechanism in the codereview pipeline.

    These tests verify that ReviewFixStep can request a rerun from CodeReviewStep,
    and that the WorkflowRunner correctly rewinds to that step.
    """

    def test_review_fix_step_returns_rerun_from_code_review(self) -> None:
        """ReviewFixStep should return rerun_from set to CodeReviewStep name when issues are addressed."""
        from rouge.core.workflow.artifacts import CodeReviewArtifact
        from rouge.core.workflow.steps.code_review_step import CODE_REVIEW_STEP_NAME

        # Create a mock context with review data
        mock_artifact_store = MagicMock()
        context = WorkflowContext(
            issue_id=123,
            adw_id="test-adw-001",
            artifact_store=mock_artifact_store,
        )

        # Set review data in context (not clean, has issues)
        from rouge.core.workflow.artifacts import ReviewData

        context.data["review_data"] = ReviewData(
            review_text="Some review feedback with issues",
            is_clean=False,
        )

        # Mock the address review issues method to succeed
        review_fix_step = ReviewFixStep()
        with patch.object(
            review_fix_step,
            "_address_review_issues",
            return_value=StepResult.ok(None, parsed_data={"issues": [], "summary": "Fixed"}),
        ):
            result = review_fix_step.run(context)

        # Should succeed and request rerun from CodeReviewStep
        assert result.success is True
        assert result.rerun_from == CODE_REVIEW_STEP_NAME

    def test_review_fix_step_does_not_rerun_when_clean(self) -> None:
        """ReviewFixStep should not request rerun when review is clean."""
        # Create a mock context with clean review
        mock_artifact_store = MagicMock()
        context = WorkflowContext(
            issue_id=123,
            adw_id="test-adw-002",
            artifact_store=mock_artifact_store,
        )

        # Set review_is_clean flag
        context.data["review_is_clean"] = True

        review_fix_step = ReviewFixStep()
        result = review_fix_step.run(context)

        # Should succeed without requesting rerun
        assert result.success is True
        assert result.rerun_from is None

    def test_review_fix_step_does_not_rerun_after_max_iterations(self) -> None:
        """ReviewFixStep should not request rerun after reaching max iterations."""
        from rouge.core.workflow.artifacts import ReviewData

        # Create a mock context with review data
        mock_artifact_store = MagicMock()
        context = WorkflowContext(
            issue_id=123,
            adw_id="test-adw-003",
            artifact_store=mock_artifact_store,
        )

        # Set review data and iteration count at max
        context.data["review_data"] = ReviewData(
            review_text="Some review feedback",
            is_clean=False,
        )
        context.data["review_fix_rerun_count"] = 4  # Will be incremented to 5 (max)

        # Mock the address review issues method to succeed
        review_fix_step = ReviewFixStep()
        with patch.object(
            review_fix_step,
            "_address_review_issues",
            return_value=StepResult.ok(None, parsed_data={"issues": [], "summary": "Fixed"}),
        ):
            result = review_fix_step.run(context)

        # Should succeed but NOT request rerun (max iterations reached)
        assert result.success is True
        assert result.rerun_from is None

    def test_workflow_runner_rewinds_on_rerun_from(self, tmp_path: pathlib.Path) -> None:
        """WorkflowRunner should rewind to the specified step when rerun_from is set."""
        from rouge.core.workflow.steps.code_review_step import CODE_REVIEW_STEP_NAME

        # Create mock steps
        mock_fetch = MagicMock(spec=WorkflowStep)
        mock_fetch.name = "Fetch issue"
        mock_fetch.is_critical = False
        mock_fetch.run.return_value = StepResult.ok(None)

        mock_review = MagicMock(spec=WorkflowStep)
        mock_review.name = CODE_REVIEW_STEP_NAME
        mock_review.is_critical = False
        mock_review.run.return_value = StepResult.ok(None)

        mock_fix = MagicMock(spec=WorkflowStep)
        mock_fix.name = "Addressing review issues"
        mock_fix.is_critical = False

        # First call: request rerun
        # Second call: don't request rerun (to prevent infinite loop)
        mock_fix.run.side_effect = [
            StepResult.ok(None, rerun_from=CODE_REVIEW_STEP_NAME),
            StepResult.ok(None),
        ]

        mock_quality = MagicMock(spec=WorkflowStep)
        mock_quality.name = "Code quality"
        mock_quality.is_critical = False
        mock_quality.run.return_value = StepResult.ok(None)

        # Create runner with mock steps
        pipeline = [mock_fetch, mock_review, mock_fix, mock_quality]
        runner = WorkflowRunner(pipeline)

        # Mock ArtifactStore to avoid filesystem operations
        with patch("rouge.core.workflow.pipeline.ArtifactStore") as mock_artifact_store_class:
            mock_store = MagicMock()
            mock_store.workflow_dir = tmp_path / "test-workflow"
            mock_artifact_store_class.return_value = mock_store

            success = runner.run(issue_id=123, adw_id="test-rerun-001")

        # Should complete successfully
        assert success is True

        # Verify execution order:
        # 1. Fetch runs once
        # 2. Review runs twice (initial + rerun)
        # 3. Fix runs twice (first time requests rerun, second time succeeds)
        # 4. Quality runs once (after second fix)
        assert mock_fetch.run.call_count == 1
        assert mock_review.run.call_count == 2
        assert mock_fix.run.call_count == 2
        assert mock_quality.run.call_count == 1
