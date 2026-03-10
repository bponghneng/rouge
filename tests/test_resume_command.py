"""Unit tests for resume CLI command."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from rouge.cli.cli import app
from rouge.core.models import Issue
from rouge.core.workflow.artifacts import ArtifactStore, WorkflowStateArtifact
from rouge.worker.worker_artifact import WorkerArtifact

runner = CliRunner()


class TestResumeCommandValidation:
    """Tests for resume command input validation."""

    @patch("rouge.cli.resume.fetch_issue")
    def test_resume_command_with_valid_issue_id(self, mock_fetch_issue):
        """Test resume command accepts valid issue ID."""
        mock_issue = Issue(
            id=123,
            description="Test issue",
            status="failed",
            adw_id="adw-123",
        )
        mock_fetch_issue.return_value = mock_issue

        # Will fail later but should pass initial validation
        result = runner.invoke(app, ["resume", "123"])

        mock_fetch_issue.assert_called_once_with(123)
        # Exit code will be non-zero due to missing artifact, but that's expected

    def test_resume_command_with_zero_issue_id(self):
        """Test resume command rejects issue_id of 0."""
        result = runner.invoke(app, ["resume", "0"])

        assert result.exit_code == 1
        assert "Error: issue_id must be greater than 0" in result.output

    def test_resume_command_with_negative_issue_id(self):
        """Test resume command rejects negative issue_id."""
        result = runner.invoke(app, ["resume", "-1"])

        # Typer will reject negative numbers as invalid
        assert result.exit_code != 0

    def test_resume_command_requires_issue_id(self):
        """Test resume command requires issue_id argument."""
        result = runner.invoke(app, ["resume"])

        assert result.exit_code != 0
        assert "Missing argument" in result.output or "required" in result.output.lower()


class TestResumeCommandIssueValidation:
    """Tests for issue state validation in resume command."""

    @patch("rouge.cli.resume.fetch_issue")
    def test_resume_with_non_failed_issue(self, mock_fetch_issue):
        """Test resume rejects issues that are not in failed status."""
        mock_issue = Issue(
            id=456,
            description="Test issue",
            status="completed",
            adw_id="adw-456",
        )
        mock_fetch_issue.return_value = mock_issue

        result = runner.invoke(app, ["resume", "456"])

        assert result.exit_code == 1
        assert "Error: Issue 456 has status 'completed'" in result.output
        assert "can only resume 'failed' issues" in result.output

    @patch("rouge.cli.resume.fetch_issue")
    def test_resume_with_pending_issue(self, mock_fetch_issue):
        """Test resume rejects pending issues."""
        mock_issue = Issue(
            id=789,
            description="Test issue",
            status="pending",
            adw_id="adw-789",
        )
        mock_fetch_issue.return_value = mock_issue

        result = runner.invoke(app, ["resume", "789"])

        assert result.exit_code == 1
        assert "has status 'pending'" in result.output
        assert "can only resume 'failed' issues" in result.output

    @patch("rouge.cli.resume.fetch_issue")
    def test_resume_with_started_issue(self, mock_fetch_issue):
        """Test resume rejects started issues."""
        mock_issue = Issue(
            id=111,
            description="Test issue",
            status="started",
            adw_id="adw-111",
        )
        mock_fetch_issue.return_value = mock_issue

        result = runner.invoke(app, ["resume", "111"])

        assert result.exit_code == 1
        assert "has status 'started'" in result.output

    @patch("rouge.cli.resume.fetch_issue")
    def test_resume_with_missing_adw_id(self, mock_fetch_issue):
        """Test resume rejects issues without adw_id."""
        mock_issue = Issue(
            id=222,
            description="Test issue",
            status="failed",
            adw_id=None,
        )
        mock_fetch_issue.return_value = mock_issue

        result = runner.invoke(app, ["resume", "222"])

        assert result.exit_code == 1
        assert "Error: Issue 222 has no adw_id set" in result.output
        assert "cannot resume without workflow ID" in result.output

    @patch("rouge.cli.resume.fetch_issue")
    def test_resume_with_nonexistent_issue(self, mock_fetch_issue):
        """Test resume handles nonexistent issue."""
        mock_fetch_issue.side_effect = ValueError("Issue with id 999 not found")

        result = runner.invoke(app, ["resume", "999"])

        assert result.exit_code == 1
        assert "Error: Issue with id 999 not found" in result.output


class TestResumeCommandArtifactLoading:
    """Tests for workflow state artifact loading in resume command."""

    @patch("rouge.cli.resume.execute_adw_workflow")
    @patch("rouge.cli.resume.update_issue")
    @patch("rouge.cli.resume.fetch_issue")
    def test_resume_loads_workflow_state_artifact(
        self, mock_fetch_issue, mock_update_issue, mock_execute_adw, tmp_path
    ):
        """Test resume command loads workflow state artifact."""
        mock_issue = Issue(
            id=333,
            description="Test issue",
            status="failed",
            adw_id="adw-333",
        )
        mock_fetch_issue.return_value = mock_issue
        mock_execute_adw.return_value = (True, "adw-333")

        # Create workflow state artifact
        with patch("rouge.cli.resume.ArtifactStore") as mock_store_class:
            mock_store = Mock()
            mock_store_class.return_value = mock_store
            mock_store.artifact_exists.return_value = True
            mock_store.workflow_dir = tmp_path / "adw-333"

            state_artifact = WorkflowStateArtifact(
                workflow_id="adw-333",
                pipeline_type="adw",
                failed_step="implement",
            )
            mock_store.read_artifact.return_value = state_artifact

            result = runner.invoke(app, ["resume", "333"])

            assert result.exit_code == 0
            mock_store.read_artifact.assert_called_once_with(
                "workflow-state", WorkflowStateArtifact
            )

    @patch("rouge.cli.resume.fetch_issue")
    def test_resume_fails_when_state_artifact_missing(self, mock_fetch_issue, tmp_path):
        """Test resume fails when workflow state artifact is missing."""
        mock_issue = Issue(
            id=444,
            description="Test issue",
            status="failed",
            adw_id="adw-444",
        )
        mock_fetch_issue.return_value = mock_issue

        # Use real ArtifactStore that won't find the artifact
        with patch("rouge.cli.resume.ArtifactStore") as mock_store_class:
            store = ArtifactStore("adw-444", base_path=tmp_path)
            mock_store_class.return_value = store

            result = runner.invoke(app, ["resume", "444"])

            assert result.exit_code == 1
            assert "Error: Workflow state artifact not found" in result.output
            assert "adw-444" in result.output

    @patch("rouge.cli.resume.fetch_issue")
    def test_resume_fails_when_failed_step_not_set(self, mock_fetch_issue, tmp_path):
        """Test resume fails when workflow state has no failed_step."""
        mock_issue = Issue(
            id=555,
            description="Test issue",
            status="failed",
            adw_id="adw-555",
        )
        mock_fetch_issue.return_value = mock_issue

        with patch("rouge.cli.resume.ArtifactStore") as mock_store_class:
            mock_store = Mock()
            mock_store_class.return_value = mock_store
            mock_store.artifact_exists.return_value = True
            mock_store.workflow_dir = tmp_path / "adw-555"

            # State artifact with no failed_step
            state_artifact = WorkflowStateArtifact(
                workflow_id="adw-555",
                pipeline_type="adw",
                failed_step=None,
            )
            mock_store.read_artifact.return_value = state_artifact

            result = runner.invoke(app, ["resume", "555"])

            assert result.exit_code == 1
            assert "Error: Workflow state artifact has no failed_step set" in result.output
            assert "cannot determine resume point" in result.output

    @patch("rouge.cli.resume.fetch_issue")
    def test_resume_fails_when_artifact_corrupted(self, mock_fetch_issue, tmp_path):
        """Test resume fails when workflow state artifact is corrupted."""
        mock_issue = Issue(
            id=666,
            description="Test issue",
            status="failed",
            adw_id="adw-666",
        )
        mock_fetch_issue.return_value = mock_issue

        with patch("rouge.cli.resume.ArtifactStore") as mock_store_class:
            mock_store = Mock()
            mock_store_class.return_value = mock_store
            mock_store.artifact_exists.return_value = True
            mock_store.workflow_dir = tmp_path / "adw-666"
            mock_store.read_artifact.side_effect = ValueError("Corrupted artifact")

            result = runner.invoke(app, ["resume", "666"])

            assert result.exit_code == 1
            assert "Error: Failed to load workflow state artifact" in result.output


class TestResumeCommandWorkflowInvocation:
    """Tests for workflow execution during resume."""

    @patch("rouge.cli.resume.execute_adw_workflow")
    @patch("rouge.cli.resume.update_issue")
    @patch("rouge.cli.resume.fetch_issue")
    def test_resume_invokes_execute_adw_workflow(
        self, mock_fetch_issue, mock_update_issue, mock_execute_adw, tmp_path
    ):
        """Test resume command invokes execute_adw_workflow with correct params."""
        mock_issue = Issue(
            id=777,
            description="Test issue",
            status="failed",
            adw_id="adw-777",
        )
        mock_fetch_issue.return_value = mock_issue
        mock_execute_adw.return_value = (True, "adw-777")

        with patch("rouge.cli.resume.ArtifactStore") as mock_store_class:
            mock_store = Mock()
            mock_store_class.return_value = mock_store
            mock_store.artifact_exists.return_value = True
            mock_store.workflow_dir = tmp_path / "adw-777"

            state_artifact = WorkflowStateArtifact(
                workflow_id="adw-777",
                pipeline_type="adw",
                failed_step="code-review",
            )
            mock_store.read_artifact.return_value = state_artifact

            result = runner.invoke(app, ["resume", "777"])

            assert result.exit_code == 0
            mock_execute_adw.assert_called_once_with(
                777,
                adw_id="adw-777",
                resume_from="code-review",
                workflow_type="adw",
            )

    @patch("rouge.cli.resume.execute_adw_workflow")
    @patch("rouge.cli.resume.update_issue")
    @patch("rouge.cli.resume.fetch_issue")
    def test_resume_resets_issue_status_to_started(
        self, mock_fetch_issue, mock_update_issue, mock_execute_adw, tmp_path
    ):
        """Test resume command resets issue status from failed to started."""
        mock_issue = Issue(
            id=888,
            description="Test issue",
            status="failed",
            adw_id="adw-888",
        )
        mock_fetch_issue.return_value = mock_issue
        mock_execute_adw.return_value = (True, "adw-888")

        with patch("rouge.cli.resume.ArtifactStore") as mock_store_class:
            mock_store = Mock()
            mock_store_class.return_value = mock_store
            mock_store.artifact_exists.return_value = True
            mock_store.workflow_dir = tmp_path / "adw-888"

            state_artifact = WorkflowStateArtifact(
                workflow_id="adw-888",
                pipeline_type="patch",
                failed_step="acceptance",
            )
            mock_store.read_artifact.return_value = state_artifact

            result = runner.invoke(app, ["resume", "888"])

            assert result.exit_code == 0
            mock_update_issue.assert_called_once_with(888, status="started")

    @patch("rouge.cli.resume.execute_adw_workflow")
    @patch("rouge.cli.resume.update_issue")
    @patch("rouge.cli.resume.fetch_issue")
    def test_resume_fails_when_workflow_execution_fails(
        self, mock_fetch_issue, mock_update_issue, mock_execute_adw, tmp_path
    ):
        """Test resume command handles workflow execution failure."""
        mock_issue = Issue(
            id=999,
            description="Test issue",
            status="failed",
            adw_id="adw-999",
        )
        mock_fetch_issue.return_value = mock_issue
        mock_execute_adw.return_value = (False, "adw-999")

        with patch("rouge.cli.resume.ArtifactStore") as mock_store_class:
            mock_store = Mock()
            mock_store_class.return_value = mock_store
            mock_store.artifact_exists.return_value = True
            mock_store.workflow_dir = tmp_path / "adw-999"

            state_artifact = WorkflowStateArtifact(
                workflow_id="adw-999",
                pipeline_type="adw",
                failed_step="implement",
            )
            mock_store.read_artifact.return_value = state_artifact

            result = runner.invoke(app, ["resume", "999"])

            assert result.exit_code == 1
            assert "Error: Workflow execution failed during resume" in result.output

    @patch("rouge.cli.resume.execute_adw_workflow")
    @patch("rouge.cli.resume.update_issue")
    @patch("rouge.cli.resume.fetch_issue")
    def test_resume_outputs_workflow_id_on_success(
        self, mock_fetch_issue, mock_update_issue, mock_execute_adw, tmp_path
    ):
        """Test resume command outputs workflow ID on success."""
        mock_issue = Issue(
            id=1000,
            description="Test issue",
            status="failed",
            adw_id="adw-1000",
        )
        mock_fetch_issue.return_value = mock_issue
        mock_execute_adw.return_value = (True, "adw-1000")

        with patch("rouge.cli.resume.ArtifactStore") as mock_store_class:
            mock_store = Mock()
            mock_store_class.return_value = mock_store
            mock_store.artifact_exists.return_value = True
            mock_store.workflow_dir = tmp_path / "adw-1000"

            state_artifact = WorkflowStateArtifact(
                workflow_id="adw-1000",
                pipeline_type="adw",
                failed_step="plan",
            )
            mock_store.read_artifact.return_value = state_artifact

            result = runner.invoke(app, ["resume", "1000"])

            assert result.exit_code == 0
            assert "adw-1000" in result.output


class TestResumeCommandWorkerArtifactUpdate:
    """Tests for worker artifact updates during resume."""

    @patch("rouge.cli.resume.transition_worker_artifact")
    @patch("rouge.cli.resume.read_worker_artifact")
    @patch("rouge.cli.resume.execute_adw_workflow")
    @patch("rouge.cli.resume.update_issue")
    @patch("rouge.cli.resume.fetch_issue")
    @patch("rouge.cli.resume.RougePaths.get_base_dir")
    def test_resume_updates_worker_with_matching_issue_id(
        self,
        mock_get_base_dir,
        mock_fetch_issue,
        mock_update_issue,
        mock_execute_adw,
        mock_read_worker,
        mock_transition_worker,
        tmp_path,
    ):
        """Test resume updates worker artifact with matching current_issue_id."""
        # Setup base directory with workers
        workers_dir = tmp_path / "workers"
        workers_dir.mkdir()
        (workers_dir / "worker-1").mkdir()
        (workers_dir / "worker-2").mkdir()

        mock_get_base_dir.return_value = tmp_path

        mock_issue = Issue(
            id=1234,
            description="Test issue",
            status="failed",
            adw_id="adw-1234",
        )
        mock_fetch_issue.return_value = mock_issue
        mock_execute_adw.return_value = (True, "adw-1234")

        # Worker 1 is working on this issue
        worker1 = WorkerArtifact(
            worker_id="worker-1",
            state="working",
            current_issue_id=1234,
            current_adw_id="adw-1234",
        )

        # Worker 2 is working on different issue
        worker2 = WorkerArtifact(
            worker_id="worker-2",
            state="working",
            current_issue_id=9999,
            current_adw_id="adw-9999",
        )

        mock_read_worker.side_effect = [worker1, worker2]

        with patch("rouge.cli.resume.ArtifactStore") as mock_store_class:
            mock_store = Mock()
            mock_store_class.return_value = mock_store
            mock_store.artifact_exists.return_value = True
            mock_store.workflow_dir = tmp_path / "adw-1234"

            state_artifact = WorkflowStateArtifact(
                workflow_id="adw-1234",
                pipeline_type="adw",
                failed_step="implement",
            )
            mock_store.read_artifact.return_value = state_artifact

            result = runner.invoke(app, ["resume", "1234"])

            assert result.exit_code == 0

            # Verify worker 1 was transitioned to ready state
            transition_calls = mock_transition_worker.call_args_list
            assert len(transition_calls) == 1

            call_args = transition_calls[0]
            assert call_args[0][0].worker_id == "worker-1"
            assert call_args[0][1] == "ready"
            assert call_args[1].get("clear_issue") is True

    @patch("rouge.cli.resume.transition_worker_artifact")
    @patch("rouge.cli.resume.read_worker_artifact")
    @patch("rouge.cli.resume.execute_adw_workflow")
    @patch("rouge.cli.resume.update_issue")
    @patch("rouge.cli.resume.fetch_issue")
    @patch("rouge.cli.resume.RougePaths.get_base_dir")
    def test_resume_skips_workers_without_matching_issue_id(
        self,
        mock_get_base_dir,
        mock_fetch_issue,
        mock_update_issue,
        mock_execute_adw,
        mock_read_worker,
        mock_transition_worker,
        tmp_path,
    ):
        """Test resume doesn't update workers not working on the issue."""
        workers_dir = tmp_path / "workers"
        workers_dir.mkdir()
        (workers_dir / "worker-1").mkdir()

        mock_get_base_dir.return_value = tmp_path

        mock_issue = Issue(
            id=5555,
            description="Test issue",
            status="failed",
            adw_id="adw-5555",
        )
        mock_fetch_issue.return_value = mock_issue
        mock_execute_adw.return_value = (True, "adw-5555")

        # Worker is working on different issue
        worker = WorkerArtifact(
            worker_id="worker-1",
            state="working",
            current_issue_id=9999,
            current_adw_id="adw-9999",
        )
        mock_read_worker.return_value = worker

        with patch("rouge.cli.resume.ArtifactStore") as mock_store_class:
            mock_store = Mock()
            mock_store_class.return_value = mock_store
            mock_store.artifact_exists.return_value = True
            mock_store.workflow_dir = tmp_path / "adw-5555"

            state_artifact = WorkflowStateArtifact(
                workflow_id="adw-5555",
                pipeline_type="adw",
                failed_step="classify",
            )
            mock_store.read_artifact.return_value = state_artifact

            result = runner.invoke(app, ["resume", "5555"])

            assert result.exit_code == 0

            # Verify no workers were updated
            mock_transition_worker.assert_not_called()

    @patch("rouge.cli.resume.execute_adw_workflow")
    @patch("rouge.cli.resume.update_issue")
    @patch("rouge.cli.resume.fetch_issue")
    @patch("rouge.cli.resume.RougePaths.get_base_dir")
    def test_resume_handles_missing_workers_directory(
        self, mock_get_base_dir, mock_fetch_issue, mock_update_issue, mock_execute_adw, tmp_path
    ):
        """Test resume handles case when workers directory doesn't exist."""
        # No workers directory created
        mock_get_base_dir.return_value = tmp_path

        mock_issue = Issue(
            id=6666,
            description="Test issue",
            status="failed",
            adw_id="adw-6666",
        )
        mock_fetch_issue.return_value = mock_issue
        mock_execute_adw.return_value = (True, "adw-6666")

        with patch("rouge.cli.resume.ArtifactStore") as mock_store_class:
            mock_store = Mock()
            mock_store_class.return_value = mock_store
            mock_store.artifact_exists.return_value = True
            mock_store.workflow_dir = tmp_path / "adw-6666"

            state_artifact = WorkflowStateArtifact(
                workflow_id="adw-6666",
                pipeline_type="adw",
                failed_step="plan",
            )
            mock_store.read_artifact.return_value = state_artifact

            result = runner.invoke(app, ["resume", "6666"])

            # Should succeed even without workers directory
            assert result.exit_code == 0


class TestResumeCommandResumeFromOverride:
    """Tests for --resume-from CLI option override behavior."""

    @patch("rouge.cli.resume.execute_adw_workflow")
    @patch("rouge.cli.resume.update_issue")
    @patch("rouge.cli.resume.fetch_issue")
    def test_resume_from_with_no_failed_step_succeeds(
        self, mock_fetch_issue, mock_update_issue, mock_execute_adw, tmp_path
    ):
        """Test --resume-from provided with failed_step=None succeeds and uses supplied step."""
        mock_issue = Issue(
            id=2001,
            description="Test issue",
            status="failed",
            adw_id="adw-2001",
        )
        mock_fetch_issue.return_value = mock_issue
        mock_execute_adw.return_value = (True, "adw-2001")

        with patch("rouge.cli.resume.ArtifactStore") as mock_store_class:
            mock_store = Mock()
            mock_store_class.return_value = mock_store
            mock_store.artifact_exists.return_value = True
            mock_store.workflow_dir = tmp_path / "adw-2001"

            # State artifact with no failed_step
            state_artifact = WorkflowStateArtifact(
                workflow_id="adw-2001",
                pipeline_type="adw",
                failed_step=None,
            )
            mock_store.read_artifact.return_value = state_artifact

            result = runner.invoke(app, ["resume", "2001", "--resume-from", "implement"])

            assert result.exit_code == 0
            mock_execute_adw.assert_called_once_with(
                2001,
                adw_id="adw-2001",
                resume_from="implement",
                workflow_type="adw",
            )

    @patch("rouge.cli.resume.execute_adw_workflow")
    @patch("rouge.cli.resume.update_issue")
    @patch("rouge.cli.resume.fetch_issue")
    def test_resume_from_overrides_failed_step(
        self, mock_fetch_issue, mock_update_issue, mock_execute_adw, tmp_path
    ):
        """Test --resume-from wins over failed_step when both are set."""
        mock_issue = Issue(
            id=2002,
            description="Test issue",
            status="failed",
            adw_id="adw-2002",
        )
        mock_fetch_issue.return_value = mock_issue
        mock_execute_adw.return_value = (True, "adw-2002")

        with patch("rouge.cli.resume.ArtifactStore") as mock_store_class:
            mock_store = Mock()
            mock_store_class.return_value = mock_store
            mock_store.artifact_exists.return_value = True
            mock_store.workflow_dir = tmp_path / "adw-2002"

            # State artifact with a failed_step set
            state_artifact = WorkflowStateArtifact(
                workflow_id="adw-2002",
                pipeline_type="adw",
                failed_step="code-review",
            )
            mock_store.read_artifact.return_value = state_artifact

            result = runner.invoke(app, ["resume", "2002", "--resume-from", "plan"])

            assert result.exit_code == 0
            # "plan" (from --resume-from) must be used, not "code-review" (failed_step)
            mock_execute_adw.assert_called_once_with(
                2002,
                adw_id="adw-2002",
                resume_from="plan",
                workflow_type="adw",
            )

    @patch("rouge.cli.resume.fetch_issue")
    def test_no_resume_from_and_no_failed_step_errors(self, mock_fetch_issue, tmp_path):
        """Test --resume-from not provided with failed_step=None gives existing error."""
        mock_issue = Issue(
            id=2003,
            description="Test issue",
            status="failed",
            adw_id="adw-2003",
        )
        mock_fetch_issue.return_value = mock_issue

        with patch("rouge.cli.resume.ArtifactStore") as mock_store_class:
            mock_store = Mock()
            mock_store_class.return_value = mock_store
            mock_store.artifact_exists.return_value = True
            mock_store.workflow_dir = tmp_path / "adw-2003"

            state_artifact = WorkflowStateArtifact(
                workflow_id="adw-2003",
                pipeline_type="adw",
                failed_step=None,
            )
            mock_store.read_artifact.return_value = state_artifact

            result = runner.invoke(app, ["resume", "2003"])

            assert result.exit_code == 1
            assert "Error: Workflow state artifact has no failed_step set" in result.output
            assert "cannot determine resume point" in result.output


class TestResumeCommandErrorHandling:
    """Tests for error handling in resume command."""

    @patch("rouge.cli.resume.fetch_issue")
    def test_resume_handles_unexpected_exception(self, mock_fetch_issue):
        """Test resume command handles unexpected exceptions."""
        mock_fetch_issue.side_effect = Exception("Unexpected database error")

        result = runner.invoke(app, ["resume", "123"])

        assert result.exit_code == 1
        assert "Unexpected error: Unexpected database error" in result.output
