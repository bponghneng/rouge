import logging
from unittest.mock import MagicMock

import pytest

from rouge.core.workflow.pipeline import (
    WorkflowRunner,
    get_default_pipeline,
    get_patch_pipeline,
)
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.steps import (
    AddressReviewStep,
    BuildPlanStep,
    ClassifyStep,
    CodeQualityStep,
    FetchIssueStep,
    FetchPatchStep,
    GenerateReviewStep,
    ImplementStep,
    PreparePullRequestStep,
    SetupStep,
    ValidateAcceptanceStep,
)
from rouge.core.workflow.steps.create_github_pr import CreateGitHubPullRequestStep
from rouge.core.workflow.steps.create_gitlab_pr import CreateGitLabPullRequestStep
from rouge.core.workflow.steps.patch_acceptance import ValidatePatchAcceptanceStep
from rouge.core.workflow.steps.patch_plan import BuildPatchPlanStep
from rouge.core.workflow.steps.update_pr_commits import UpdatePRCommitsStep
from rouge.core.workflow.types import StepResult


class DummyStep(WorkflowStep):
    def __init__(self, name: str, critical: bool = True):
        self._name = name
        self._critical = critical
        self.executed = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_critical(self) -> bool:
        return self._critical

    def run(self, context: WorkflowContext) -> StepResult:
        self.executed = True
        return StepResult.ok(None)


class FailingStep(WorkflowStep):
    def __init__(self, name: str, critical: bool = True):
        self._name = name
        self._critical = critical

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_critical(self) -> bool:
        return self._critical

    def run(self, context: WorkflowContext) -> StepResult:
        return StepResult.fail("Step failed")


class TestWorkflowContext:
    def test_init(self):
        context = WorkflowContext(issue_id=1, adw_id="test-adw")
        assert context.issue_id == 1
        assert context.adw_id == "test-adw"
        assert context.artifacts_enabled is False
        assert context.artifact_store is None

    def test_data_storage(self):
        context = WorkflowContext(issue_id=1, adw_id="test-adw")
        context.data["key"] = "value"
        assert context.data["key"] == "value"


class TestWorkflowRunner:
    def test_execute_pipeline_success(self, caplog, tmp_path):
        step1 = DummyStep("Step 1")
        step2 = DummyStep("Step 2")
        runner = WorkflowRunner([step1, step2])

        with caplog.at_level(logging.INFO):
            with pytest.MonkeyPatch.context() as mp:
                mp.setenv("ROUGE_DATA_DIR", str(tmp_path))
                success = runner.run(issue_id=1, adw_id="test-adw-1")

        assert success
        assert step1.executed
        assert step2.executed
        assert "Workflow completed successfully" in caplog.text

    def test_execute_pipeline_critical_failure(self, caplog, tmp_path):
        step1 = DummyStep("Step 1")
        step2 = FailingStep("Step 2", critical=True)
        step3 = DummyStep("Step 3")
        runner = WorkflowRunner([step1, step2, step3])

        with caplog.at_level(logging.ERROR):
            with pytest.MonkeyPatch.context() as mp:
                mp.setenv("ROUGE_DATA_DIR", str(tmp_path))
                success = runner.run(issue_id=1, adw_id="test-adw-2")

        assert not success
        assert step1.executed
        assert not step3.executed
        assert "Critical step 'Step 2' failed" in caplog.text

    def test_execute_pipeline_best_effort_failure(self, caplog, tmp_path):
        step1 = DummyStep("Step 1")
        step2 = FailingStep("Step 2", critical=False)
        step3 = DummyStep("Step 3")
        runner = WorkflowRunner([step1, step2, step3])

        with caplog.at_level(logging.WARNING):
            with pytest.MonkeyPatch.context() as mp:
                mp.setenv("ROUGE_DATA_DIR", str(tmp_path))
                success = runner.run(issue_id=1, adw_id="test-adw-3")

        assert success
        assert step1.executed
        assert step3.executed
        assert "Best-effort step 'Step 2' failed" in caplog.text

    def test_context_passed_to_steps(self, tmp_path):
        mock_step = MagicMock(spec=WorkflowStep)
        mock_step.name = "Mock Step"
        mock_step.is_critical = True
        mock_step.run.return_value = StepResult.ok(None)

        runner = WorkflowRunner([mock_step])
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("ROUGE_DATA_DIR", str(tmp_path))
            runner.run(issue_id=123, adw_id="test-adw-4")

        mock_step.run.assert_called_once()
        call_args = mock_step.run.call_args[0][0]
        assert isinstance(call_args, WorkflowContext)
        assert call_args.issue_id == 123
        assert call_args.adw_id == "test-adw-4"


class TestGetDefaultPipeline:
    def test_pipeline_structure_no_platform(self, monkeypatch):
        monkeypatch.delenv("DEV_SEC_OPS_PLATFORM", raising=False)
        pipeline = get_default_pipeline()

        # Check step count (should be 10 without PR step)
        assert len(pipeline) == 10

        # Verify order and types
        expected_types = [
            SetupStep,
            FetchIssueStep,
            ClassifyStep,
            BuildPlanStep,
            ImplementStep,
            GenerateReviewStep,
            AddressReviewStep,
            CodeQualityStep,
            ValidateAcceptanceStep,
            PreparePullRequestStep,
        ]

        for i, (step, expected_type) in enumerate(zip(pipeline, expected_types, strict=True)):
            assert isinstance(step, expected_type), (
                f"Step {i} should be {expected_type.__name__}, got {type(step).__name__}"
            )

        # Verify critical flags
        assert pipeline[0].is_critical  # Setup
        assert pipeline[1].is_critical  # Fetch
        assert pipeline[2].is_critical  # Classify
        assert pipeline[3].is_critical  # Plan
        assert pipeline[4].is_critical  # Implement
        assert not pipeline[7].is_critical  # Quality

    def test_pipeline_structure_github(self, monkeypatch):
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        pipeline = get_default_pipeline()

        assert len(pipeline) == 11
        assert isinstance(pipeline[-1], CreateGitHubPullRequestStep)
        assert not pipeline[-1].is_critical  # PR creation is best effort

    def test_pipeline_structure_gitlab(self, monkeypatch):
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "gitlab")
        pipeline = get_default_pipeline()

        assert len(pipeline) == 11
        assert isinstance(pipeline[-1], CreateGitLabPullRequestStep)
        assert not pipeline[-1].is_critical


class TestGetPatchPipeline:
    def test_patch_pipeline_structure_no_platform(self, monkeypatch):
        monkeypatch.delenv("DEV_SEC_OPS_PLATFORM", raising=False)
        pipeline = get_patch_pipeline()

        # Check step count (should be 8 steps)
        assert len(pipeline) == 8

        # Verify order and types
        expected_types = [
            FetchPatchStep,
            BuildPatchPlanStep,
            ImplementStep,
            GenerateReviewStep,
            AddressReviewStep,
            CodeQualityStep,
            ValidatePatchAcceptanceStep,
            UpdatePRCommitsStep,
        ]

        for i, (step, expected_type) in enumerate(zip(pipeline, expected_types, strict=True)):
            assert isinstance(step, expected_type), (
                f"Step {i} should be {expected_type.__name__}, got {type(step).__name__}"
            )

        # Verify critical flags
        assert pipeline[0].is_critical  # Fetch patch
        assert pipeline[1].is_critical  # Build patch plan
        assert pipeline[2].is_critical  # Implement
        assert not pipeline[3].is_critical  # Review (best effort)
        assert not pipeline[4].is_critical  # Address review (best effort)
        assert not pipeline[5].is_critical  # Code quality
        assert not pipeline[6].is_critical  # Validate patch acceptance (best effort)
        assert not pipeline[7].is_critical  # Update PR commits (best effort)

    def test_patch_pipeline_excludes_create_pr_steps(self, monkeypatch):
        """Verify patch pipeline never includes PR creation steps."""
        # Even with platform set
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        pipeline = get_patch_pipeline()

        pr_step_types = (CreateGitHubPullRequestStep, CreateGitLabPullRequestStep)
        for step in pipeline:
            assert not isinstance(step, pr_step_types), (
                "Patch pipeline should not include PR creation steps"
            )

    def test_patch_pipeline_includes_update_commits_step(self, monkeypatch):
        """Verify patch pipeline ends with UpdatePRCommitsStep."""
        monkeypatch.delenv("DEV_SEC_OPS_PLATFORM", raising=False)
        pipeline = get_patch_pipeline()

        assert isinstance(pipeline[-1], UpdatePRCommitsStep)
        assert not pipeline[-1].is_critical  # Should be best effort

    def test_patch_pipeline_step_order(self, monkeypatch):
        """Verify the exact sequence of steps in the patch pipeline."""
        monkeypatch.delenv("DEV_SEC_OPS_PLATFORM", raising=False)
        pipeline = get_patch_pipeline()

        expected_types = [
            FetchPatchStep,
            BuildPatchPlanStep,
            ImplementStep,
            GenerateReviewStep,
            AddressReviewStep,
            CodeQualityStep,
            ValidatePatchAcceptanceStep,
            UpdatePRCommitsStep,
        ]

        for i, (step, expected_type) in enumerate(zip(pipeline, expected_types, strict=True)):
            assert isinstance(step, expected_type), (
                f"Step {i} should be {expected_type.__name__}, got {type(step).__name__}"
            )
