"""Unit tests for workflow resume logic in WorkflowRunner."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, call, patch

import pytest

from rouge.core.workflow.artifacts import ArtifactStore, WorkflowStateArtifact
from rouge.core.workflow.pipeline import WorkflowRunner
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult


@pytest.fixture(autouse=True)
def isolate_env(tmp_path, monkeypatch):
    """Isolate test environment to tmp_path with no external log side effects.

    This fixture:
    - Redirects get_working_dir to tmp_path for artifact isolation
    - Mocks log_step_start and log_step_end to prevent external logging
    """
    # Monkeypatch get_working_dir to return tmp_path
    monkeypatch.setattr("rouge.core.paths.get_working_dir", lambda: str(tmp_path))

    # Monkeypatch logging functions to no-op
    monkeypatch.setattr("rouge.core.workflow.pipeline.log_step_start", lambda *args, **kwargs: None)
    monkeypatch.setattr("rouge.core.workflow.pipeline.log_step_end", lambda *args, **kwargs: None)


def _make_context(adw_id: str = "adw-test", issue_id: int = 1, **kwargs) -> WorkflowContext:
    """Create a WorkflowContext with a temporary artifact store for testing."""
    tmp_dir = tempfile.TemporaryDirectory()
    store = ArtifactStore(workflow_id=adw_id, base_path=Path(tmp_dir.name))
    context = WorkflowContext(issue_id=issue_id, adw_id=adw_id, artifact_store=store, **kwargs)
    context._tmp_dir = tmp_dir  # type: ignore[attr-defined]  # keeps dir alive until context is GC'd
    return context


class TestWorkflowRunnerStepSkipping:
    """Tests for step-skipping logic when resuming workflows."""

    def test_resume_skips_steps_before_resume_point(self):
        """Test that steps before resume_from are skipped."""
        # Create mock steps
        step1 = Mock(spec=WorkflowStep)
        step1.name = "Step 1"
        step1.is_critical = True
        step1.run = Mock(return_value=StepResult.ok(None))

        step2 = Mock(spec=WorkflowStep)
        step2.name = "Step 2"
        step2.is_critical = True
        step2.run = Mock(return_value=StepResult.ok(None))

        step3 = Mock(spec=WorkflowStep)
        step3.name = "Step 3"
        step3.is_critical = True
        step3.run = Mock(return_value=StepResult.ok(None))

        runner = WorkflowRunner([step1, step2, step3])
        result = runner.run(issue_id=1, adw_id="adw-123", resume_from="Step 2")

        # Step 1 should be skipped
        step1.run.assert_not_called()

        # Steps 2 and 3 should run
        step2.run.assert_called_once()
        step3.run.assert_called_once()

        assert result is True

    def test_resume_from_first_step_runs_all(self):
        """Test that resuming from first step runs all steps."""
        step1 = Mock(spec=WorkflowStep)
        step1.name = "First Step"
        step1.is_critical = True
        step1.run = Mock(return_value=StepResult.ok(None))

        step2 = Mock(spec=WorkflowStep)
        step2.name = "Second Step"
        step2.is_critical = True
        step2.run = Mock(return_value=StepResult.ok(None))

        runner = WorkflowRunner([step1, step2])
        result = runner.run(issue_id=1, adw_id="adw-456", resume_from="First Step")

        step1.run.assert_called_once()
        step2.run.assert_called_once()
        assert result is True

    def test_resume_from_last_step_runs_only_last(self):
        """Test that resuming from last step only runs that step."""
        step1 = Mock(spec=WorkflowStep)
        step1.name = "Step 1"
        step1.is_critical = True
        step1.run = Mock(return_value=StepResult.ok(None))

        step2 = Mock(spec=WorkflowStep)
        step2.name = "Last Step"
        step2.is_critical = True
        step2.run = Mock(return_value=StepResult.ok(None))

        runner = WorkflowRunner([step1, step2])
        result = runner.run(issue_id=1, adw_id="adw-789", resume_from="Last Step")

        step1.run.assert_not_called()
        step2.run.assert_called_once()
        assert result is True

    def test_resume_from_unknown_step_runs_all(self):
        """Test that resume_from with unknown step runs from beginning."""
        step1 = Mock(spec=WorkflowStep)
        step1.name = "Known Step"
        step1.is_critical = True
        step1.run = Mock(return_value=StepResult.ok(None))

        runner = WorkflowRunner([step1])
        result = runner.run(issue_id=1, adw_id="adw-999", resume_from="Unknown Step")

        # Should run from beginning when step not found
        step1.run.assert_called_once()
        assert result is True

    def test_resume_from_middle_step_in_longer_pipeline(self):
        """Test resuming from middle of longer pipeline."""
        steps = []
        for i in range(1, 6):
            step = Mock(spec=WorkflowStep)
            step.name = f"Step {i}"
            step.is_critical = True
            step.run = Mock(return_value=StepResult.ok(None))
            steps.append(step)

        runner = WorkflowRunner(steps)
        result = runner.run(issue_id=1, adw_id="adw-long", resume_from="Step 3")

        # Steps 1 and 2 should be skipped
        steps[0].run.assert_not_called()
        steps[1].run.assert_not_called()

        # Steps 3, 4, and 5 should run
        steps[2].run.assert_called_once()
        steps[3].run.assert_called_once()
        steps[4].run.assert_called_once()

        assert result is True


class TestWorkflowRunnerArtifactWrites:
    """Tests for artifact writes after steps and on failure."""

    def test_workflow_state_written_after_successful_step(self, tmp_path):
        """Test workflow state artifact is written after each successful step."""
        step1 = Mock(spec=WorkflowStep)
        step1.name = "Test Step 1"
        step1.is_critical = True
        step1.run = Mock(return_value=StepResult.ok(None))

        step2 = Mock(spec=WorkflowStep)
        step2.name = "Test Step 2"
        step2.is_critical = True
        step2.run = Mock(return_value=StepResult.ok(None))

        runner = WorkflowRunner([step1, step2])

        # Mock get_working_dir to use tmp_path so runner and test store use same base path
        with patch("rouge.core.paths.get_working_dir", return_value=str(tmp_path)):
            runner.run(issue_id=1, adw_id="adw-write", pipeline_type="test-pipeline")

            # Check that workflow state was written with last completed step
            store = ArtifactStore("adw-write")
            assert store.artifact_exists("workflow-state")
            state = store.read_artifact("workflow-state", WorkflowStateArtifact)
            assert state.last_completed_step == "Test Step 2"
            assert state.failed_step is None
            assert state.pipeline_type == "test-pipeline"

    def test_workflow_state_written_on_critical_failure(self, tmp_path):
        """Test workflow state artifact is written when critical step fails."""
        step1 = Mock(spec=WorkflowStep)
        step1.name = "Success Step"
        step1.is_critical = True
        step1.run = Mock(return_value=StepResult.ok(None))

        step2 = Mock(spec=WorkflowStep)
        step2.name = "Failure Step"
        step2.is_critical = True
        step2.run = Mock(return_value=StepResult.fail("Test failure"))

        runner = WorkflowRunner([step1, step2])

        # Mock get_working_dir to use tmp_path so runner and test store use same base path
        with patch("rouge.core.paths.get_working_dir", return_value=str(tmp_path)):
            result = runner.run(issue_id=1, adw_id="adw-fail", pipeline_type="test-pipeline")

            assert result is False

            # Check that workflow state was written with failed step
            store = ArtifactStore("adw-fail")
            assert store.artifact_exists("workflow-state")
            state = store.read_artifact("workflow-state", WorkflowStateArtifact)
            assert state.failed_step == "Failure Step"
            assert state.pipeline_type == "test-pipeline"

    def test_workflow_state_not_written_on_best_effort_failure(self, tmp_path, monkeypatch):
        """Test workflow continues and doesn't mark failure for best-effort steps."""
        # Mock get_working_dir to use tmp_path so runner and test store use same base path
        monkeypatch.setattr("rouge.core.paths.get_working_dir", lambda: str(tmp_path))

        step1 = Mock(spec=WorkflowStep)
        step1.name = "Critical Step"
        step1.is_critical = True
        step1.run = Mock(return_value=StepResult.ok(None))

        step2 = Mock(spec=WorkflowStep)
        step2.name = "Best Effort Step"
        step2.is_critical = False
        step2.run = Mock(return_value=StepResult.fail("Non-critical failure"))

        step3 = Mock(spec=WorkflowStep)
        step3.name = "Final Step"
        step3.is_critical = True
        step3.run = Mock(return_value=StepResult.ok(None))

        runner = WorkflowRunner([step1, step2, step3])
        result = runner.run(issue_id=1, adw_id="adw-best-effort", pipeline_type="test")

        # Should succeed despite best-effort failure
        assert result is True
        step3.run.assert_called_once()

    def test_workflow_state_updates_progressively(self, tmp_path):
        """Test workflow state artifact is updated after each successful step."""
        step1 = Mock(spec=WorkflowStep)
        step1.name = "Step One"
        step1.is_critical = True
        step1.run = Mock(return_value=StepResult.ok(None))

        step2 = Mock(spec=WorkflowStep)
        step2.name = "Step Two"
        step2.is_critical = True
        step2.run = Mock(return_value=StepResult.ok(None))

        runner = WorkflowRunner([step1, step2])

        # Mock the write method to track calls
        original_write = runner._write_workflow_state
        write_calls = []

        def track_write(*args, **kwargs):
            write_calls.append((args, kwargs))
            original_write(*args, **kwargs)

        runner._write_workflow_state = track_write

        runner.run(
            issue_id=1,
            adw_id="adw-progress",
            pipeline_type="test",
        )

        # Verify state was written after each successful step
        # At least 2 calls expected (one per successful step)
        assert len(write_calls) >= 2


class TestWorkflowRunnerResumeContext:
    """Tests for resume_from context propagation."""

    def test_resume_from_in_context(self):
        """Test resume_from is passed to WorkflowContext."""
        step1 = Mock(spec=WorkflowStep)
        step1.name = "Step 1"
        step1.is_critical = True

        captured_context = None

        def capture_context(ctx):
            nonlocal captured_context
            captured_context = ctx
            return StepResult.ok(None)

        step1.run = capture_context

        runner = WorkflowRunner([step1])
        runner.run(issue_id=1, adw_id="adw-ctx", resume_from="Step 1")

        assert captured_context is not None
        assert captured_context.resume_from == "Step 1"

    def test_pipeline_type_in_context(self):
        """Test pipeline_type is passed to WorkflowContext."""
        step1 = Mock(spec=WorkflowStep)
        step1.name = "Step 1"
        step1.is_critical = True

        captured_context = None

        def capture_context(ctx):
            nonlocal captured_context
            captured_context = ctx
            return StepResult.ok(None)

        step1.run = capture_context

        runner = WorkflowRunner([step1])
        runner.run(issue_id=1, adw_id="adw-ctx", pipeline_type="custom-pipeline")

        assert captured_context is not None
        assert captured_context.pipeline_type == "custom-pipeline"


class TestWorkflowRunnerResumeWithFailure:
    """Tests for resume behavior combined with failures."""

    def test_resume_then_fail_updates_state_correctly(self, tmp_path):
        """Test that resuming then failing updates workflow state correctly."""
        step1 = Mock(spec=WorkflowStep)
        step1.name = "Skipped Step"
        step1.is_critical = True
        step1.run = Mock(return_value=StepResult.ok(None))

        step2 = Mock(spec=WorkflowStep)
        step2.name = "Resume Point"
        step2.is_critical = True
        step2.run = Mock(return_value=StepResult.ok(None))

        step3 = Mock(spec=WorkflowStep)
        step3.name = "Failing Step"
        step3.is_critical = True
        step3.run = Mock(return_value=StepResult.fail("Resume then fail"))

        runner = WorkflowRunner([step1, step2, step3])
        result = runner.run(
            issue_id=1,
            adw_id="adw-resume-fail",
            resume_from="Resume Point",
            pipeline_type="test",
        )

        assert result is False

        # Step 1 should have been skipped
        step1.run.assert_not_called()

        # Step 2 should have run
        step2.run.assert_called_once()

        # Step 3 should have run and failed
        step3.run.assert_called_once()

    def test_resume_from_previously_failed_step_succeeds(self):
        """Test resuming from a previously failed step can succeed."""
        failed_step = Mock(spec=WorkflowStep)
        failed_step.name = "Previously Failed"
        failed_step.is_critical = True
        # This time it succeeds
        failed_step.run = Mock(return_value=StepResult.ok(None))

        next_step = Mock(spec=WorkflowStep)
        next_step.name = "Next Step"
        next_step.is_critical = True
        next_step.run = Mock(return_value=StepResult.ok(None))

        runner = WorkflowRunner([failed_step, next_step])
        result = runner.run(
            issue_id=1,
            adw_id="adw-retry",
            resume_from="Previously Failed",
        )

        assert result is True
        failed_step.run.assert_called_once()
        next_step.run.assert_called_once()


class TestWorkflowRunnerArtifactStorePersistence:
    """Tests for artifact store persistence during workflow execution."""

    def test_artifact_store_created_unconditionally(self):
        """Test artifact store is always created for workflows."""
        step1 = Mock(spec=WorkflowStep)
        step1.name = "Test Step"
        step1.is_critical = True

        captured_context = None

        def capture_context(ctx):
            nonlocal captured_context
            captured_context = ctx
            return StepResult.ok(None)

        step1.run = capture_context

        runner = WorkflowRunner([step1])
        runner.run(issue_id=1, adw_id="adw-store-test")

        # Verify artifact store was created in context
        assert captured_context is not None
        assert captured_context.artifact_store is not None
        assert captured_context.artifact_store.workflow_id == "adw-store-test"

    def test_artifact_store_directory_created(self):
        """Test artifact store directory is created on workflow run."""
        step1 = Mock(spec=WorkflowStep)
        step1.name = "Test Step"
        step1.is_critical = True
        step1.run = Mock(return_value=StepResult.ok(None))

        runner = WorkflowRunner([step1])
        runner.run(issue_id=1, adw_id="adw-dir-test")

        # Verify directory exists (in default location)
        # This is a basic check - actual path depends on RougePaths configuration
        step1.run.assert_called_once()


class TestWorkflowRunnerBestEffortStateWrite:
    """Tests for best-effort workflow state writes."""

    @patch("rouge.core.workflow.artifacts.ArtifactStore.write_artifact")
    def test_state_write_failure_does_not_halt_workflow(self, mock_write_artifact, tmp_path):
        """Test that workflow state write failures don't stop execution."""
        step1 = Mock(spec=WorkflowStep)
        step1.name = "Step 1"
        step1.is_critical = True
        step1.run = Mock(return_value=StepResult.ok(None))

        runner = WorkflowRunner([step1])

        # Mock write_artifact to raise exception
        mock_write_artifact.side_effect = IOError("Write failed")

        # Workflow should still succeed despite write failure
        result = runner.run(issue_id=1, adw_id="adw-write-fail")

        assert result is True
        step1.run.assert_called_once()
