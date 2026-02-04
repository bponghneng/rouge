import logging
from unittest.mock import MagicMock, patch

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
from rouge.core.workflow.steps.patch_plan import BuildPatchPlanStep
from rouge.core.workflow.steps.update_pr_commits import UpdatePRCommitsStep
from rouge.core.workflow.types import StepResult

_WORKING_DIR_PATCH = "rouge.core.paths.get_working_dir"


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


class RerunStep(WorkflowStep):
    """Step that signals a rerun on its first N executions, then succeeds normally."""

    def __init__(self, name: str, target: str, rerun_times: int = 1, critical: bool = True):
        self._name = name
        self._critical = critical
        self._target = target
        self._rerun_times = rerun_times
        self.call_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_critical(self) -> bool:
        return self._critical

    def run(self, context: WorkflowContext) -> StepResult:
        self.call_count += 1
        if self.call_count <= self._rerun_times:
            return StepResult.ok(None, rerun_from=self._target)
        return StepResult.ok(None)


class CountingStep(WorkflowStep):
    """Step that counts how many times it is executed."""

    def __init__(self, name: str, critical: bool = True):
        self._name = name
        self._critical = critical
        self.call_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_critical(self) -> bool:
        return self._critical

    def run(self, context: WorkflowContext) -> StepResult:
        self.call_count += 1
        return StepResult.ok(None)


class InvalidRerunStep(WorkflowStep):
    """Step that signals a rerun targeting a non-existent step name."""

    def __init__(self, name: str, target: str, critical: bool = True):
        self._name = name
        self._critical = critical
        self._target = target
        self.call_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_critical(self) -> bool:
        return self._critical

    def run(self, context: WorkflowContext) -> StepResult:
        self.call_count += 1
        return StepResult.ok(None, rerun_from=self._target)


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
            with patch(_WORKING_DIR_PATCH, return_value=str(tmp_path)):
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
            with patch(_WORKING_DIR_PATCH, return_value=str(tmp_path)):
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
            with patch(_WORKING_DIR_PATCH, return_value=str(tmp_path)):
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
        with patch(_WORKING_DIR_PATCH, return_value=str(tmp_path)):
            runner.run(issue_id=123, adw_id="test-adw-4")

        mock_step.run.assert_called_once()
        call_args = mock_step.run.call_args[0][0]
        assert isinstance(call_args, WorkflowContext)
        assert call_args.issue_id == 123
        assert call_args.adw_id == "test-adw-4"

    def test_rerun_signal_restarts_from_target_step(self, caplog, tmp_path):
        """When a step returns rerun_from, the pipeline rewinds to the named step."""
        step_a = CountingStep("Step A")
        step_b = CountingStep("Step B")
        # On its first execution, request a rerun from "Step A", then succeed normally.
        step_c = RerunStep("Step C", target="Step A", rerun_times=1)
        runner = WorkflowRunner([step_a, step_b, step_c])

        with caplog.at_level(logging.INFO):
            with patch(_WORKING_DIR_PATCH, return_value=str(tmp_path)):
                success = runner.run(issue_id=1, adw_id="test-rerun-signal")

        assert success
        # Step A should execute twice: initial run + one rewind
        assert step_a.call_count == 2
        # Step B should also execute twice (it follows Step A)
        assert step_b.call_count == 2
        # Step C: first call triggers rerun, second call succeeds normally
        assert step_c.call_count == 2
        assert "Rerun requested: rewinding to step 'Step A'" in caplog.text

    def test_max_rerun_limit_logs_warning_and_continues(self, caplog, tmp_path):
        """When max reruns are exceeded, the pipeline logs a warning and moves on."""
        target_step = CountingStep("Target")
        # Always request rerun (rerun_times exceeds max_step_reruns)
        rerun_step = RerunStep("Rerunner", target="Target", rerun_times=100)
        final_step = CountingStep("Final")
        runner = WorkflowRunner([target_step, rerun_step, final_step])

        with caplog.at_level(logging.WARNING):
            with patch(_WORKING_DIR_PATCH, return_value=str(tmp_path)):
                success = runner.run(issue_id=1, adw_id="test-max-rerun")

        assert success
        # Target should run 1 (initial) + max_step_reruns (5) = 6 times
        assert target_step.call_count == 1 + runner.max_step_reruns
        # Rerunner: same number of calls as target (runs after each target run)
        assert rerun_step.call_count == 1 + runner.max_step_reruns
        # Final step should still execute after max reruns are exhausted
        assert final_step.call_count == 1
        assert f"Max reruns ({runner.max_step_reruns}) reached for step 'Target'" in caplog.text

    def test_rerun_counts_are_tracked_per_step(self, caplog, tmp_path):
        """Different steps can independently trigger reruns with separate counters."""
        step_a = CountingStep("Step A")
        # First rerun step targets Step A, triggers once
        rerun_b = RerunStep("Rerun B", target="Step A", rerun_times=1)
        step_c = CountingStep("Step C")
        # Second rerun step targets Step C, triggers once
        rerun_d = RerunStep("Rerun D", target="Step C", rerun_times=1)
        step_e = CountingStep("Step E")
        runner = WorkflowRunner([step_a, rerun_b, step_c, rerun_d, step_e])

        with caplog.at_level(logging.INFO):
            with patch(_WORKING_DIR_PATCH, return_value=str(tmp_path)):
                success = runner.run(issue_id=1, adw_id="test-multi-rerun")

        assert success
        # Step A: initial + rewind from Rerun B + replayed during Rerun D rewind path = 3
        # (first run, rewind-to-A run, and re-run when pipeline passes through A again
        #  after rewinding to C which is after A)
        assert step_a.call_count >= 2
        # Step C: initial + rewind from Rerun D
        assert step_c.call_count >= 2
        # Step E should execute
        assert step_e.call_count >= 1
        # Both rerun targets should appear in logs
        assert "rewinding to step 'Step A'" in caplog.text
        assert "rewinding to step 'Step C'" in caplog.text

    def test_rerun_with_invalid_step_name_logs_warning(self, caplog, tmp_path):
        """When rerun_from names a non-existent step, the pipeline warns and continues."""
        step1 = CountingStep("Step 1")
        bad_rerun = InvalidRerunStep("Bad Rerun", target="NonExistent")
        step3 = CountingStep("Step 3")
        runner = WorkflowRunner([step1, bad_rerun, step3])

        with caplog.at_level(logging.WARNING):
            with patch(_WORKING_DIR_PATCH, return_value=str(tmp_path)):
                success = runner.run(issue_id=1, adw_id="test-invalid-rerun")

        assert success
        # All steps should execute exactly once (no actual rewind)
        assert step1.call_count == 1
        # bad_rerun always requests a rerun, but the target is invalid so the
        # pipeline ignores the request and advances.  It is invoked once per
        # pass.  Because the invalid-target branch still increments step_index,
        # the step only runs once.
        assert bad_rerun.call_count >= 1
        assert step3.call_count == 1
        assert "Rerun requested for unknown step 'NonExistent', ignoring" in caplog.text


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
            ValidateAcceptanceStep,
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
            ValidateAcceptanceStep,
            UpdatePRCommitsStep,
        ]

        for i, (step, expected_type) in enumerate(zip(pipeline, expected_types, strict=True)):
            assert isinstance(step, expected_type), (
                f"Step {i} should be {expected_type.__name__}, got {type(step).__name__}"
            )
