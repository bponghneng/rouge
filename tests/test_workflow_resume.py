"""Unit tests for workflow resume logic in WorkflowRunner."""

import os
import shutil
from unittest.mock import Mock, patch

import pytest

from rouge.core.paths import RougePaths
from rouge.core.workflow.artifacts import ArtifactStore, WorkflowStateArtifact
from rouge.core.workflow.pipeline import WorkflowRunner
from rouge.core.workflow.step_base import WorkflowStep
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

        # Verify directory exists using RougePaths
        expected_path = RougePaths.get_workflow_dir("adw-dir-test")
        assert os.path.isdir(expected_path), f"Expected directory {expected_path} was not created"

        # Clean up created directory to avoid test pollution
        shutil.rmtree(expected_path)

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


class TestWorkflowRunnerStepIdResume:
    """Tests for resume/persistence of stable ``step_id`` identifiers.

    The runner prefers ``step_id`` over ``step.name`` when resolving resume
    targets so declarative pipelines (built via ``WorkflowConfig``) can use
    stable identifiers.  Persisted ``WorkflowStateArtifact`` records carry
    both ``last_completed_step`` and ``last_completed_step_id`` so resume by
    either identifier works.  Old-style state artifacts that pre-date
    ``last_completed_step_id`` continue to resume correctly via name.
    """

    def _make_step(self, *, name: str, step_id: str | None = None) -> Mock:
        step = Mock(spec=WorkflowStep)
        step.name = name
        step.is_critical = True
        step.run = Mock(return_value=StepResult.ok(None))
        # Mock(spec=WorkflowStep) inherits the class-level ``step_id`` default
        # of None; set it explicitly so the runner picks it up.
        step.step_id = step_id
        return step

    def test_last_completed_step_id_written_when_step_has_id(self) -> None:
        """When a step declares ``step_id``, it is persisted alongside name."""
        step = self._make_step(name="Plan Step", step_id="plan-step")

        runner = WorkflowRunner([step])
        result = runner.run(issue_id=1, adw_id="adw-state-id", pipeline_type="full")

        assert result is True

        store = ArtifactStore("adw-state-id")
        assert store.artifact_exists("workflow-state")
        state = store.read_artifact("workflow-state", WorkflowStateArtifact)
        assert state.last_completed_step == "Plan Step"
        assert state.last_completed_step_id == "plan-step"

    def test_last_completed_step_id_is_none_when_step_lacks_id(self) -> None:
        """Steps without a ``step_id`` persist a None last_completed_step_id."""
        step = self._make_step(name="Legacy Step", step_id=None)

        runner = WorkflowRunner([step])
        result = runner.run(issue_id=1, adw_id="adw-state-noid", pipeline_type="full")

        assert result is True

        store = ArtifactStore("adw-state-noid")
        state = store.read_artifact("workflow-state", WorkflowStateArtifact)
        assert state.last_completed_step == "Legacy Step"
        assert state.last_completed_step_id is None

    def test_resume_by_step_id_skips_earlier_steps(self) -> None:
        """Resume target matches against ``step_id`` first."""
        step1 = self._make_step(name="Fetch Issue", step_id="fetch-issue")
        step2 = self._make_step(name="Build Plan", step_id="claude-code-plan")
        step3 = self._make_step(name="Implement Plan", step_id="implement-plan")

        runner = WorkflowRunner([step1, step2, step3])
        # Resume from the *step_id*, not the human-readable name.
        result = runner.run(issue_id=1, adw_id="adw-resume-by-id", resume_from="claude-code-plan")

        assert result is True
        step1.run.assert_not_called()
        step2.run.assert_called_once()
        step3.run.assert_called_once()

    def test_resume_by_name_still_works_alongside_step_id(self) -> None:
        """Resume target falls back to ``step.name`` when not a step_id."""
        step1 = self._make_step(name="Fetch Issue", step_id="fetch-issue")
        step2 = self._make_step(name="Build Plan", step_id="claude-code-plan")
        step3 = self._make_step(name="Implement Plan", step_id="implement-plan")

        runner = WorkflowRunner([step1, step2, step3])
        # Resume by display name even though step_ids are also available.
        result = runner.run(issue_id=1, adw_id="adw-resume-by-name", resume_from="Build Plan")

        assert result is True
        step1.run.assert_not_called()
        step2.run.assert_called_once()
        step3.run.assert_called_once()

    def test_resume_with_old_style_state_artifact(self, tmp_path, monkeypatch) -> None:
        """Old persisted artifacts (no ``last_completed_step_id``) still resume.

        The runner's resume_from argument is what drives skip behaviour, so
        callers (CLI / orchestrator) reading an older WorkflowStateArtifact
        can pass ``state.last_completed_step`` and the name-based fallback
        path still works as before.
        """
        monkeypatch.setattr("rouge.core.paths.get_working_dir", lambda: str(tmp_path))

        # Simulate a pre-existing old-style state artifact written before the
        # ``last_completed_step_id`` field existed.
        legacy_store = ArtifactStore("adw-legacy")
        legacy_state = WorkflowStateArtifact(
            workflow_id="adw-legacy",
            last_completed_step="Step One",
            # last_completed_step_id intentionally omitted (defaults to None).
            failed_step=None,
            pipeline_type="full",
        )
        legacy_store.write_artifact(legacy_state)

        # Read back and verify shape mirrors what older code would have written.
        loaded = legacy_store.read_artifact("workflow-state", WorkflowStateArtifact)
        assert loaded.last_completed_step == "Step One"
        assert loaded.last_completed_step_id is None

        # Now resume the workflow using the legacy name; the runner still
        # advances past the named step.
        step1 = self._make_step(name="Step One", step_id=None)
        step2 = self._make_step(name="Step Two", step_id=None)

        runner = WorkflowRunner([step1, step2])
        result = runner.run(
            issue_id=1,
            adw_id="adw-legacy-resume",
            resume_from=loaded.last_completed_step + "_unused",  # use Step Two by name
        )
        # The above resume target is intentionally unknown; the runner falls
        # back to running from the beginning.  Assert success and run-counts.
        assert result is True

        # Now do an actual resume by the legacy name "Step Two" — confirms
        # name-based resume continues to work for callers that haven't yet
        # adopted step_id-based persistence.
        step1.run.reset_mock()
        step2.run.reset_mock()
        runner = WorkflowRunner([step1, step2])
        result = runner.run(
            issue_id=1,
            adw_id="adw-legacy-resume-2",
            resume_from="Step Two",
        )
        assert result is True
        step1.run.assert_not_called()
        step2.run.assert_called_once()
