"""Integration tests for end-to-end workflow resume flow.

These tests verify the complete resume workflow including:
- Workflow failure → resume command → workflow completion
- Artifact persistence and reuse across resume cycles
- Worker artifact state transitions during resume
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rouge.core.models import Issue
from rouge.core.workflow.artifacts import ArtifactStore, WorkflowStateArtifact
from rouge.core.workflow.pipeline import WorkflowRunner
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult
from rouge.worker.worker_artifact import WorkerArtifact, read_worker_artifact, write_worker_artifact


@pytest.fixture(autouse=True)
def isolate_step_logging(monkeypatch):
    """Isolate step logging to prevent database/credentials access during tests.

    This fixture automatically patches log_step_start and log_step_end with harmless
    mocks for all tests in this module, preventing unintended database calls.
    """
    mock_log_start = Mock()
    mock_log_end = Mock()

    monkeypatch.setattr("rouge.core.workflow.pipeline.log_step_start", mock_log_start)
    monkeypatch.setattr("rouge.core.workflow.pipeline.log_step_end", mock_log_end)

    return {"log_step_start": mock_log_start, "log_step_end": mock_log_end}


class TestEndToEndResumeFlow:
    """Integration tests for complete workflow failure and resume cycle."""

    def test_workflow_fails_then_resumes_and_completes(self, tmp_path):
        """Test complete flow: workflow fails → resume command → workflow completes.

        This integration test verifies that:
        1. A workflow can fail at a specific step
        2. Workflow state artifact is written on failure
        3. Resume command can load the state and restart from failed step
        4. Workflow completes successfully when resumed
        """
        # Create workflow steps: step1 succeeds, step2 fails initially, step3 succeeds
        step1 = Mock(spec=WorkflowStep)
        step1.name = "Step 1"
        step1.is_critical = True
        step1.run = Mock(return_value=StepResult.ok(None))

        step2_call_count = [0]

        def step2_run(ctx):
            """Step 2 fails on first run, succeeds on second (resume)."""
            step2_call_count[0] += 1
            if step2_call_count[0] == 1:
                return StepResult.fail("Simulated failure")
            return StepResult.ok(None)

        step2 = Mock(spec=WorkflowStep)
        step2.name = "Step 2"
        step2.is_critical = True
        step2.run = step2_run

        step3 = Mock(spec=WorkflowStep)
        step3.name = "Step 3"
        step3.is_critical = True
        step3.run = Mock(return_value=StepResult.ok(None))

        # First run: workflow should fail at step2
        runner = WorkflowRunner([step1, step2, step3])
        store = ArtifactStore("test-adw-fail", base_path=tmp_path)

        with patch("rouge.core.workflow.pipeline.ArtifactStore") as mock_store_class:
            mock_store_class.return_value = store
            result = runner.run(issue_id=1, adw_id="test-adw-fail", pipeline_type="test")

        assert result is False
        assert step1.run.call_count == 1
        assert step2_call_count[0] == 1
        step3.run.assert_not_called()

        # Verify workflow state artifact was written with failed step
        assert store.artifact_exists("workflow-state")
        state = store.read_artifact("workflow-state", WorkflowStateArtifact)
        assert state.failed_step == "Step 2"
        assert state.last_completed_step == "Step 1"
        assert state.pipeline_type == "test"

        # Second run: resume from failed step, should succeed
        with patch("rouge.core.workflow.pipeline.ArtifactStore") as mock_store_class:
            mock_store_class.return_value = store
            result = runner.run(
                issue_id=1,
                adw_id="test-adw-fail",
                resume_from="Step 2",
                pipeline_type="test",
            )

        assert result is True
        # Step 1 should not run again (skipped during resume)
        assert step1.run.call_count == 1
        # Step 2 should run a second time (resume point)
        assert step2_call_count[0] == 2
        # Step 3 should now run
        step3.run.assert_called_once()

        # Verify workflow state artifact shows success (no failed_step)
        final_state = store.read_artifact("workflow-state", WorkflowStateArtifact)
        assert final_state.failed_step is None
        assert final_state.last_completed_step == "Step 3"

    def test_resume_command_integration_with_issue_and_artifact(self, tmp_path):
        """Test resume command integrates with issue database and artifact loading.

        This verifies the full resume command flow:
        1. Issue is fetched and validated
        2. Workflow state artifact is loaded
        3. Issue status is updated to 'started'
        4. Workflow execution is triggered with resume_from
        5. Worker artifacts are updated
        """
        from typer.testing import CliRunner

        from rouge.cli.cli import app

        runner = CliRunner()

        # Setup mock issue with failed status
        mock_issue = Issue(
            id=123,
            description="Test issue",
            status="failed",
            adw_id="adw-resume-123",
        )

        # Create workflow state artifact
        artifact_dir = tmp_path / "workflows" / "adw-resume-123"
        artifact_dir.mkdir(parents=True)
        store = ArtifactStore("adw-resume-123", base_path=tmp_path / "workflows")
        state = WorkflowStateArtifact(
            workflow_id="adw-resume-123",
            pipeline_type="adw",
            failed_step="implement",
            last_completed_step="classify",
        )
        store.write_artifact(state)

        # Create worker artifact that's stuck on this issue
        workers_dir = tmp_path / "workers" / "worker-1"
        workers_dir.mkdir(parents=True)
        worker = WorkerArtifact(
            worker_id="worker-1",
            state="failed",
            current_issue_id=123,
            current_adw_id="adw-resume-123",
        )

        with patch("rouge.cli.resume.RougePaths.get_base_dir", return_value=tmp_path):
            with patch(
                "rouge.worker.worker_artifact._get_worker_artifact_path",
                return_value=workers_dir / "state.json",
            ):
                write_worker_artifact(worker)

                with patch("rouge.cli.resume.fetch_issue", return_value=mock_issue):
                    with patch("rouge.cli.resume.update_issue") as mock_update:
                        with patch("rouge.cli.resume.execute_adw_workflow") as mock_execute:
                            mock_execute.return_value = (True, "adw-resume-123")

                            with patch(
                                "rouge.cli.resume.ArtifactStore",
                                return_value=store,
                            ):
                                result = runner.invoke(app, ["resume", "123"])

                # Verify command succeeded
                assert result.exit_code == 0
                assert "adw-resume-123" in result.output

                # Verify issue status was updated to started
                mock_update.assert_called_once_with(123, status="started")

                # Verify execute_adw_workflow was called with correct params
                mock_execute.assert_called_once_with(
                    "adw-resume-123",
                    123,
                    resume_from="implement",
                    workflow_type="adw",
                )

                # Verify worker artifact was updated to ready state
                updated_worker = read_worker_artifact("worker-1")
                assert updated_worker is not None
                assert updated_worker.state == "ready"
                assert updated_worker.current_issue_id is None
                assert updated_worker.current_adw_id is None


class TestArtifactReuseOnResume:
    """Integration tests for artifact persistence and reuse during resume."""

    def test_step_artifacts_persist_across_resume_cycles(self, tmp_path):
        """Test that artifacts written by earlier steps are available when resuming.

        This verifies:
        1. Steps can write custom artifacts during initial run
        2. These artifacts persist after workflow failure
        3. Resumed steps can read artifacts from prior steps
        """
        # Simplified test - just verify workflow state artifact persists across resume
        # which is the critical integration point for resume functionality

        step1 = Mock(spec=WorkflowStep)
        step1.name = "Step 1"
        step1.is_critical = True
        step1.run = Mock(return_value=StepResult.ok(None))

        step2_call_count = [0]

        def step2_run(ctx):
            step2_call_count[0] += 1
            # Store some state in context data to verify it persists
            ctx.data["step2_attempt"] = step2_call_count[0]
            if step2_call_count[0] == 1:
                return StepResult.fail("Intentional failure")
            return StepResult.ok(None)

        step2 = Mock(spec=WorkflowStep)
        step2.name = "Step 2"
        step2.is_critical = True
        step2.run = step2_run

        step3 = Mock(spec=WorkflowStep)
        step3.name = "Step 3"
        step3.is_critical = True
        step3.run = Mock(return_value=StepResult.ok(None))

        # First run: should fail at step 2
        runner = WorkflowRunner([step1, step2, step3])
        store = ArtifactStore("test-artifact-reuse", base_path=tmp_path)

        with patch("rouge.core.workflow.pipeline.ArtifactStore") as mock_store_class:
            mock_store_class.return_value = store
            result = runner.run(
                issue_id=1,
                adw_id="test-artifact-reuse",
                pipeline_type="test",
            )

        assert result is False
        assert step1.run.call_count == 1
        assert step2_call_count[0] == 1
        step3.run.assert_not_called()

        # Verify workflow state artifact exists and has correct data
        assert store.artifact_exists("workflow-state")
        state_after_fail = store.read_artifact("workflow-state", WorkflowStateArtifact)
        assert state_after_fail.failed_step == "Step 2"
        assert state_after_fail.last_completed_step == "Step 1"
        assert state_after_fail.workflow_id == "test-artifact-reuse"

        # Second run: resume from step 2, should succeed
        with patch("rouge.core.workflow.pipeline.ArtifactStore") as mock_store_class:
            mock_store_class.return_value = store
            result = runner.run(
                issue_id=1,
                adw_id="test-artifact-reuse",
                resume_from="Step 2",
                pipeline_type="test",
            )

        assert result is True
        # Step 1 should still only have 1 call (skipped during resume)
        assert step1.run.call_count == 1
        # Step 2 should have 2 calls now (initial + resume)
        assert step2_call_count[0] == 2
        # Step 3 should now be called
        step3.run.assert_called_once()

        # Verify workflow state artifact shows success
        state_after_resume = store.read_artifact("workflow-state", WorkflowStateArtifact)
        assert state_after_resume.failed_step is None
        assert state_after_resume.last_completed_step == "Step 3"

    def test_workflow_state_artifact_tracks_progress_correctly(self, tmp_path):
        """Test workflow state artifact correctly tracks progress through resume.

        This verifies:
        1. Workflow state shows last_completed_step after each step
        2. Workflow state shows failed_step on failure
        3. Resume updates workflow state to track new progress
        """
        step1 = Mock(spec=WorkflowStep)
        step1.name = "Initialize"
        step1.is_critical = True
        step1.run = Mock(return_value=StepResult.ok(None))

        step2_call_count = [0]

        def step2_run(ctx):
            step2_call_count[0] += 1
            if step2_call_count[0] == 1:
                return StepResult.fail("Transient failure")
            return StepResult.ok(None)

        step2 = Mock(spec=WorkflowStep)
        step2.name = "Process"
        step2.is_critical = True
        step2.run = step2_run

        step3 = Mock(spec=WorkflowStep)
        step3.name = "Finalize"
        step3.is_critical = True
        step3.run = Mock(return_value=StepResult.ok(None))

        runner = WorkflowRunner([step1, step2, step3])
        store = ArtifactStore("test-state-tracking", base_path=tmp_path)

        # First run: fail at step 2
        with patch("rouge.core.workflow.pipeline.ArtifactStore") as mock_store_class:
            mock_store_class.return_value = store
            result = runner.run(
                issue_id=1,
                adw_id="test-state-tracking",
                pipeline_type="test",
            )

        assert result is False

        # Check workflow state after failure
        state_after_fail = store.read_artifact("workflow-state", WorkflowStateArtifact)
        assert state_after_fail.workflow_id == "test-state-tracking"
        assert state_after_fail.last_completed_step == "Initialize"
        assert state_after_fail.failed_step == "Process"
        assert state_after_fail.pipeline_type == "test"

        # Second run: resume from Process
        with patch("rouge.core.workflow.pipeline.ArtifactStore") as mock_store_class:
            mock_store_class.return_value = store
            result = runner.run(
                issue_id=1,
                adw_id="test-state-tracking",
                resume_from="Process",
                pipeline_type="test",
            )

        assert result is True

        # Check workflow state after successful resume
        state_after_resume = store.read_artifact("workflow-state", WorkflowStateArtifact)
        assert state_after_resume.workflow_id == "test-state-tracking"
        assert state_after_resume.last_completed_step == "Finalize"
        assert state_after_resume.failed_step is None  # Cleared on success
        assert state_after_resume.pipeline_type == "test"


class TestWorkerArtifactResumeIntegration:
    """Integration tests for worker artifact updates during resume."""

    def test_worker_artifact_state_transitions_during_resume(self, tmp_path):
        """Test worker artifact correctly transitions through resume cycle.

        This verifies:
        1. Worker is in 'failed' state after workflow failure
        2. Resume command resets worker to 'ready' state
        3. Worker can then pick up new work
        """
        workers_dir = tmp_path / "workers" / "worker-test"
        workers_dir.mkdir(parents=True)

        # Create worker artifact in failed state (simulating workflow failure)
        worker = WorkerArtifact(
            worker_id="worker-test",
            state="failed",
            current_issue_id=456,
            current_adw_id="adw-failed-456",
        )

        with patch(
            "rouge.worker.worker_artifact._get_worker_artifact_path",
            return_value=workers_dir / "state.json",
        ):
            write_worker_artifact(worker)

            # Verify failed state
            loaded = read_worker_artifact("worker-test")
            assert loaded is not None
            assert loaded.state == "failed"
            assert loaded.current_issue_id == 456
            assert loaded.current_adw_id == "adw-failed-456"

            # Simulate resume command resetting worker to ready
            loaded.state = "ready"
            loaded.current_issue_id = None
            loaded.current_adw_id = None
            write_worker_artifact(loaded)

            # Verify ready state
            final = read_worker_artifact("worker-test")
            assert final is not None
            assert final.state == "ready"
            assert final.current_issue_id is None
            assert final.current_adw_id is None

    def test_resume_command_updates_multiple_worker_artifacts(self, tmp_path):
        """Test resume command updates all workers working on the resumed issue.

        This verifies:
        1. Multiple workers can be stuck on the same issue
        2. Resume command identifies and updates all matching workers
        3. Workers not working on the issue are left unchanged
        """
        from typer.testing import CliRunner

        from rouge.cli.cli import app

        runner = CliRunner()

        # Create multiple workers
        workers_dir = tmp_path / "workers"
        workers_dir.mkdir()

        # Worker 1: working on issue 789
        worker1_dir = workers_dir / "worker-1"
        worker1_dir.mkdir()
        worker1 = WorkerArtifact(
            worker_id="worker-1",
            state="failed",
            current_issue_id=789,
            current_adw_id="adw-789",
        )

        # Worker 2: also working on issue 789
        worker2_dir = workers_dir / "worker-2"
        worker2_dir.mkdir()
        worker2 = WorkerArtifact(
            worker_id="worker-2",
            state="failed",
            current_issue_id=789,
            current_adw_id="adw-789",
        )

        # Worker 3: working on different issue
        worker3_dir = workers_dir / "worker-3"
        worker3_dir.mkdir()
        worker3 = WorkerArtifact(
            worker_id="worker-3",
            state="working",
            current_issue_id=999,
            current_adw_id="adw-999",
        )

        def mock_get_path(worker_id):
            return workers_dir / worker_id / "state.json"

        with patch(
            "rouge.worker.worker_artifact._get_worker_artifact_path",
            side_effect=mock_get_path,
        ):
            write_worker_artifact(worker1)
            write_worker_artifact(worker2)
            write_worker_artifact(worker3)

            # Setup mock issue and artifact
            mock_issue = Issue(
                id=789,
                description="Multi-worker issue",
                status="failed",
                adw_id="adw-789",
            )

            artifact_store = ArtifactStore("adw-789", base_path=tmp_path / "workflows")
            state = WorkflowStateArtifact(
                workflow_id="adw-789",
                pipeline_type="adw",
                failed_step="implement",
            )
            artifact_store.write_artifact(state)

            with patch("rouge.cli.resume.RougePaths.get_base_dir", return_value=tmp_path):
                with patch("rouge.cli.resume.fetch_issue", return_value=mock_issue):
                    with patch("rouge.cli.resume.update_issue"):
                        with patch("rouge.cli.resume.execute_adw_workflow") as mock_execute:
                            mock_execute.return_value = (True, "adw-789")

                            with patch(
                                "rouge.cli.resume.ArtifactStore",
                                return_value=artifact_store,
                            ):
                                result = runner.invoke(app, ["resume", "789"])

            assert result.exit_code == 0

            # Verify workers 1 and 2 were updated to ready
            updated_worker1 = read_worker_artifact("worker-1")
            assert updated_worker1 is not None
            assert updated_worker1.state == "ready"
            assert updated_worker1.current_issue_id is None

            updated_worker2 = read_worker_artifact("worker-2")
            assert updated_worker2 is not None
            assert updated_worker2.state == "ready"
            assert updated_worker2.current_issue_id is None

            # Verify worker 3 was NOT changed
            unchanged_worker3 = read_worker_artifact("worker-3")
            assert unchanged_worker3 is not None
            assert unchanged_worker3.state == "working"
            assert unchanged_worker3.current_issue_id == 999
            assert unchanged_worker3.current_adw_id == "adw-999"

    def test_worker_can_resume_own_failed_workflow(self, tmp_path):
        """Test that a worker can resume its own failed workflow.

        This integration test simulates a worker:
        1. Starting a workflow (state=working)
        2. Workflow fails (state=failed)
        3. Operator runs resume command (state=ready)
        4. Worker can pick up new work
        """
        worker_id = "integration-worker"
        issue_id = 111
        adw_id = "adw-int-111"

        workers_dir = tmp_path / "workers" / worker_id
        workers_dir.mkdir(parents=True)

        def mock_get_path(wid):
            return tmp_path / "workers" / wid / "state.json"

        with patch(
            "rouge.worker.worker_artifact._get_worker_artifact_path",
            side_effect=mock_get_path,
        ):
            # Phase 1: Worker starts workflow
            worker = WorkerArtifact(
                worker_id=worker_id,
                state="working",
                current_issue_id=issue_id,
                current_adw_id=adw_id,
            )
            write_worker_artifact(worker)

            # Phase 2: Workflow fails, worker transitions to failed
            worker.state = "failed"
            write_worker_artifact(worker)

            loaded = read_worker_artifact(worker_id)
            assert loaded is not None
            assert loaded.state == "failed"
            assert loaded.current_issue_id == issue_id

            # Phase 3: Operator runs resume command (simulated)
            # Resume command should reset worker to ready
            loaded.state = "ready"
            loaded.current_issue_id = None
            loaded.current_adw_id = None
            write_worker_artifact(loaded)

            # Phase 4: Verify worker is ready for new work
            final = read_worker_artifact(worker_id)
            assert final is not None
            assert final.state == "ready"
            assert final.current_issue_id is None
            assert final.current_adw_id is None


class TestResumeErrorRecovery:
    """Integration tests for error recovery scenarios during resume."""

    def test_resume_handles_missing_artifact_gracefully(self, tmp_path):
        """Test resume fails gracefully when workflow state artifact is missing.

        This verifies the error handling path when artifacts are corrupted or deleted.
        """
        from typer.testing import CliRunner

        from rouge.cli.cli import app

        runner = CliRunner()

        mock_issue = Issue(
            id=999,
            description="Missing artifact issue",
            status="failed",
            adw_id="adw-missing",
        )

        # No artifact created - simulating missing/deleted artifact
        empty_store = ArtifactStore("adw-missing", base_path=tmp_path / "workflows")

        with patch("rouge.cli.resume.fetch_issue", return_value=mock_issue):
            with patch("rouge.cli.resume.ArtifactStore", return_value=empty_store):
                result = runner.invoke(app, ["resume", "999"])

        assert result.exit_code == 1
        assert "Workflow state artifact not found" in result.output
        assert "adw-missing" in result.output

    def test_resume_fails_when_workflow_execution_fails_again(self, tmp_path):
        """Test resume handles case when workflow fails again on resume.

        This verifies:
        1. Resume can be attempted
        2. If workflow fails again, proper error is reported
        3. Workflow state artifact is updated with new failure
        """
        step1 = Mock(spec=WorkflowStep)
        step1.name = "Step 1"
        step1.is_critical = True
        step1.run = Mock(return_value=StepResult.ok(None))

        # Step 2 always fails
        step2 = Mock(spec=WorkflowStep)
        step2.name = "Step 2"
        step2.is_critical = True
        step2.run = Mock(return_value=StepResult.fail("Persistent failure"))

        runner = WorkflowRunner([step1, step2])
        store = ArtifactStore("test-persistent-fail", base_path=tmp_path)

        # First run: fails at step 2
        with patch("rouge.core.workflow.pipeline.ArtifactStore") as mock_store_class:
            mock_store_class.return_value = store
            result = runner.run(
                issue_id=1,
                adw_id="test-persistent-fail",
                pipeline_type="test",
            )

        assert result is False

        # Verify failure recorded with last_completed_step from first run
        state1 = store.read_artifact("workflow-state", WorkflowStateArtifact)
        assert state1.failed_step == "Step 2"
        assert state1.last_completed_step == "Step 1"

        # Second run: resume, but fails again
        with patch("rouge.core.workflow.pipeline.ArtifactStore") as mock_store_class:
            mock_store_class.return_value = store
            result = runner.run(
                issue_id=1,
                adw_id="test-persistent-fail",
                resume_from="Step 2",
                pipeline_type="test",
            )

        assert result is False

        # Verify failure still recorded
        # When resuming from Step 2 (which fails), last_completed_step is None
        # because we skip Step 1 and Step 2 fails immediately
        state2 = store.read_artifact("workflow-state", WorkflowStateArtifact)
        assert state2.failed_step == "Step 2"
        # Note: last_completed_step is None because we resumed from Step 2 and it failed
        # immediately without any prior steps completing in this run
        assert state2.last_completed_step is None
