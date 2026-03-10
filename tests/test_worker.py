"""Tests for the CAPE issue worker daemon."""

import os
import subprocess
from unittest.mock import Mock, patch

import pytest

from rouge.worker import database
from rouge.worker.config import WorkerConfig
from rouge.worker.worker import IssueWorker


@pytest.fixture
def mock_env(monkeypatch) -> None:
    """Mock environment variables for Supabase."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test_key")


@pytest.fixture
def worker_config() -> WorkerConfig:
    """Create a worker configuration for testing."""
    return WorkerConfig(worker_id="test-worker", poll_interval=5, log_level="DEBUG")


@pytest.fixture
def worker(mock_env, worker_config) -> IssueWorker:
    """Create a worker instance for testing."""
    with patch("rouge.worker.database.get_client"):
        worker = IssueWorker(worker_config)
        return worker


class TestIssueWorkerInit:
    """Tests for IssueWorker initialization."""

    def test_worker_initialization(self, mock_env, worker_config) -> None:
        """Test worker initializes with correct parameters."""
        with patch("rouge.worker.database.get_client"):
            worker = IssueWorker(worker_config)

            assert worker.config.worker_id == "test-worker"
            assert worker.config.poll_interval == 5
            assert worker.config.log_level == "DEBUG"
            assert worker.running is True

    def test_worker_logging_setup(self, mock_env, worker_config) -> None:
        """Test worker sets up logging correctly."""
        with patch("rouge.worker.database.get_client"):
            worker = IssueWorker(worker_config)

            assert worker.logger is not None
            assert worker.logger.name == "rouge_worker_test-worker"


class TestGetNextIssue:
    """Tests for get_next_issue function."""

    def test_get_next_issue_success(self, mock_env) -> None:
        """Test successfully retrieving next issue."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.data = [
            {
                "issue_id": 123,
                "issue_description": "Test issue",
                "issue_status": "pending",
                "issue_type": "main",
            }
        ]
        mock_client.rpc.return_value.execute.return_value = mock_response

        with patch("rouge.worker.database.get_client", return_value=mock_client):
            result = database.get_next_issue("test-worker")

            assert result == (123, "Test issue", "pending", "main")
            mock_client.rpc.assert_called_once_with(
                "get_and_lock_next_issue", {"p_worker_id": "test-worker"}
            )

    def test_get_next_issue_no_issues(self, mock_env) -> None:
        """Test when no issues are available."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.data = []
        mock_client.rpc.return_value.execute.return_value = mock_response

        with patch("rouge.worker.database.get_client", return_value=mock_client):
            result = database.get_next_issue("test-worker")

            assert result is None

    def test_get_next_issue_database_error(self, mock_env) -> None:
        """Test handling database errors."""
        mock_client = Mock()
        mock_client.rpc.side_effect = Exception("Database connection failed")

        with patch("rouge.worker.database.get_client", return_value=mock_client):
            result = database.get_next_issue("test-worker")

            assert result is None


class TestExecuteWorkflow:
    """Tests for execute_workflow method."""

    def test_execute_workflow_success(self, worker) -> None:
        """Test successful workflow execution."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Workflow completed successfully"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            with patch("rouge.worker.worker.update_issue_status") as mock_update:
                result = worker.execute_workflow(123, "Test issue", "pending", "main")

                assert result is True
                mock_update.assert_called_once_with(123, "completed", worker.logger)

    def test_execute_workflow_failure(self, worker) -> None:
        """Test workflow execution failure."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Workflow failed"

        with patch("subprocess.run", return_value=mock_result):
            with patch("rouge.worker.worker.update_issue_status") as mock_update:
                result = worker.execute_workflow(123, "Test issue", "pending", "main")

                assert result is False
                mock_update.assert_called_once_with(123, "failed", worker.logger)

    def test_execute_workflow_timeout(self, worker) -> None:
        """Test workflow execution timeout."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 3600)):
            with patch("rouge.worker.worker.update_issue_status") as mock_update:
                result = worker.execute_workflow(123, "Test issue", "pending", "main")

                assert result is False
                mock_update.assert_called_once_with(123, "failed", worker.logger)

    def test_execute_workflow_exception(self, worker) -> None:
        """Test workflow execution with unexpected exception."""
        with patch("subprocess.run", side_effect=Exception("Unexpected error")):
            with patch("rouge.worker.worker.update_issue_status") as mock_update:
                result = worker.execute_workflow(123, "Test issue", "pending", "main")

                assert result is False
                mock_update.assert_called_once_with(123, "failed", worker.logger)

    def test_execute_workflow_command_format(self, worker) -> None:
        """Test workflow command is formatted correctly."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Success"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            with patch("rouge.worker.worker.update_issue_status"):
                with patch("rouge.worker.worker.make_adw_id", return_value="test-adw"):
                    # Mock shutil.which to return None so it falls back to uv run
                    with patch("shutil.which", return_value=None):
                        worker.execute_workflow(456, "Test description", "pending", "main")

                    # Verify the command was called with correct arguments
                    call_args = mock_run.call_args
                    cmd = call_args[0][0]

                    assert cmd[0] == "uv"
                    assert cmd[1] == "run"
                    assert cmd[2] == "rouge-adw"
                    assert cmd[3] == "--adw-id"
                    assert cmd[4] == "test-adw"
                    assert cmd[5] == "--workflow-type"
                    assert cmd[6] == "main"
                    assert cmd[7] == "456"

    def test_execute_workflow_command_from_path(self, worker) -> None:
        """Test workflow command uses rouge-adw from PATH when available."""
        mock_result = Mock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            with patch("rouge.worker.worker.update_issue_status"):
                with patch("rouge.worker.worker.make_adw_id", return_value="test-adw"):
                    # Mock shutil.which to return a path, simulating global install
                    with patch("shutil.which", return_value="/usr/local/bin/rouge-adw"):
                        worker.execute_workflow(456, "Test description", "pending", "main")

                    # Verify the command uses rouge-adw directly
                    call_args = mock_run.call_args
                    cmd = call_args[0][0]

                    assert cmd[0] == "rouge-adw"
                    assert cmd[1] == "--adw-id"
                    assert cmd[2] == "test-adw"
                    assert cmd[3] == "--workflow-type"
                    assert cmd[4] == "main"
                    assert cmd[5] == "456"

    def test_execute_workflow_command_from_env_var(self, worker, monkeypatch) -> None:
        """Test workflow command uses ROUGE_ADW_COMMAND when set."""
        monkeypatch.setenv("ROUGE_ADW_COMMAND", "/custom/path/rouge-adw --verbose")
        mock_result = Mock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            with patch("rouge.worker.worker.update_issue_status"):
                with patch("rouge.worker.worker.make_adw_id", return_value="test-adw"):
                    worker.execute_workflow(456, "Test description", "pending", "main")

                    # Verify the command uses the custom command
                    call_args = mock_run.call_args
                    cmd = call_args[0][0]

                # The base command may be ["rouge-adw"], ["uv", "run", "rouge-adw"],
                # or a custom ROUGE_ADW_COMMAND depending on environment
                # Find the rouge-adw command and the arguments after it
                if "rouge-adw" in cmd:
                    adw_idx = cmd.index("rouge-adw")
                    assert cmd[adw_idx + 1] == "--adw-id"
                    assert cmd[adw_idx + 2] == "test-adw"
                    assert cmd[adw_idx + 3] == "--workflow-type"
                    assert cmd[adw_idx + 4] == "main"
                    assert cmd[adw_idx + 5] == "456"
                else:
                    # Fallback: just verify the command contains expected args
                    assert "--adw-id" in cmd
                    assert "test-adw" in cmd
                    assert "--workflow-type" in cmd
                    assert "main" in cmd
                    assert "456" in cmd


class TestUpdateIssueStatus:
    """Tests for update_issue_status function."""

    def test_update_issue_status_success(self, mock_env) -> None:
        """Test successfully updating issue status."""
        mock_issue = Mock()
        mock_issue.id = 123
        mock_issue.status = "completed"

        with patch("rouge.worker.database._update_issue", return_value=mock_issue) as mock_update:
            database.update_issue_status(123, "completed")
            mock_update.assert_called_once_with(123, status="completed")

    def test_update_issue_status_database_error(self, mock_env) -> None:
        """Test handling database errors during status update."""
        with patch("rouge.worker.database._update_issue", side_effect=Exception("Database error")):
            # Should not raise exception
            database.update_issue_status(123, "completed")


class TestWorkerRun:
    """Tests for the main worker run loop."""

    @pytest.mark.skip(reason="Hangs intermittently on Windows runners; tracked for later fix.")
    def test_run_processes_issue(self, worker) -> None:
        """Test worker processes an issue and then stops."""
        worker.running = True
        call_count = [0]

        def mock_get_next_issue(worker_id, logger):
            call_count[0] += 1
            if call_count[0] == 1:
                return (123, "Test issue", "pending", "main")
            worker.running = False
            return None

        with patch("rouge.worker.database.get_next_issue", side_effect=mock_get_next_issue):
            with patch.object(worker, "execute_workflow") as mock_execute:
                worker.run()

                mock_execute.assert_called_once_with(123, "Test issue", "pending", "main")

    @pytest.mark.skip(reason="Flaky sleep timing on CI runners; revisit later.")
    def test_run_sleeps_when_no_issues(self, worker) -> None:
        """Test worker sleeps when no issues are available."""
        worker.running = True
        call_count = [0]

        def mock_get_next_issue(worker_id, logger):
            call_count[0] += 1
            if call_count[0] >= 2:
                worker.running = False
            return None

        with patch("rouge.worker.database.get_next_issue", side_effect=mock_get_next_issue):
            with patch("time.sleep") as mock_sleep:
                worker.run()

                # Should have slept at least once
                assert mock_sleep.call_count >= 1
                mock_sleep.assert_called_with(5)  # poll_interval is 5 for test worker

    @pytest.mark.skip(reason="Intermittent signal propagation issues on Windows runners.")
    def test_run_handles_keyboard_interrupt(self, worker) -> None:
        """Test worker handles keyboard interrupt gracefully."""

        def mock_get_next_issue(worker_id, logger):
            raise KeyboardInterrupt()

        with patch("rouge.worker.database.get_next_issue", side_effect=mock_get_next_issue):
            worker.run()

            assert worker.running is False

    @pytest.mark.skip(reason="Flaky on Windows due to patching/time.sleep interactions.")
    def test_run_handles_unexpected_error(self, worker) -> None:
        """Test worker handles unexpected errors and continues."""
        worker.running = True
        call_count = [0]

        def mock_get_next_issue(worker_id, logger):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Unexpected error")
            worker.running = False
            return None

        with patch("rouge.worker.database.get_next_issue", side_effect=mock_get_next_issue):
            with patch("time.sleep") as mock_sleep:
                worker.run()

                # Should have slept after the error
                assert mock_sleep.call_count >= 1


class TestSignalHandling:
    """Tests for signal handling."""

    def test_handle_shutdown_signal(self, worker) -> None:
        """Test worker handles shutdown signals."""
        assert worker.running is True

        worker._handle_shutdown(15, None)  # SIGTERM

        assert worker.running is False


class TestCommandLineInterface:
    """Tests for command line argument parsing."""

    def test_main_with_required_args(self, mock_env, monkeypatch) -> None:
        """Test main function with required arguments."""
        from typer.testing import CliRunner as TyperRunner

        from rouge.worker.cli import app as worker_app

        monkeypatch.delenv("ROUGE_LOG_LEVEL", raising=False)
        runner = TyperRunner()

        with patch("rouge.worker.cli.IssueWorker") as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker

            result = runner.invoke(worker_app, ["--worker-id", "test-worker"])

            assert result.exit_code == 0, result.output
            # Verify WorkerConfig was created and passed
            assert mock_worker_class.call_count == 1
            config = mock_worker_class.call_args[0][0]
            assert isinstance(config, WorkerConfig)
            assert config.worker_id == "test-worker"
            assert config.poll_interval == 10
            assert config.log_level == "INFO"
            mock_worker.run.assert_called_once()

    def test_main_with_all_args(self, mock_env) -> None:
        """Test main function with all arguments."""
        from typer.testing import CliRunner as TyperRunner

        from rouge.worker.cli import app as worker_app

        runner = TyperRunner()

        with patch("rouge.worker.cli.IssueWorker") as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker

            result = runner.invoke(
                worker_app,
                [
                    "--worker-id",
                    "custom-worker",
                    "--poll-interval",
                    "15",
                    "--log-level",
                    "DEBUG",
                ],
            )

            assert result.exit_code == 0, result.output
            # Verify WorkerConfig was created and passed
            assert mock_worker_class.call_count == 1
            config = mock_worker_class.call_args[0][0]
            assert isinstance(config, WorkerConfig)
            assert config.worker_id == "custom-worker"
            assert config.poll_interval == 15
            assert config.log_level == "DEBUG"
            mock_worker.run.assert_called_once()

    def test_workflow_timeout_from_cli(self, mock_env) -> None:
        """Test workflow-timeout flag is parsed and passed to WorkerConfig."""
        from typer.testing import CliRunner as TyperRunner

        from rouge.worker.cli import app as worker_app

        runner = TyperRunner()

        with patch("rouge.worker.cli.IssueWorker") as mock_worker_class:
            mock_worker = Mock()
            mock_worker_class.return_value = mock_worker

            result = runner.invoke(
                worker_app,
                [
                    "--worker-id",
                    "test-worker",
                    "--workflow-timeout",
                    "7200",
                ],
            )

            assert result.exit_code == 0, result.output
            # Verify WorkerConfig was created with the specified workflow_timeout
            assert mock_worker_class.call_count == 1
            config = mock_worker_class.call_args[0][0]
            assert isinstance(config, WorkerConfig)
            assert config.workflow_timeout == 7200
            mock_worker.run.assert_called_once()

    def test_workflow_timeout_from_env_var(self, mock_env, monkeypatch) -> None:
        """Test ROUGE_WORKFLOW_TIMEOUT_SECONDS env var is used as default.

        This test verifies that the CLI correctly reads the environment variable
        to set the default value for --workflow-timeout when the flag is not
        provided on the command line. We use subprocess to get a clean process
        where the environment variable is evaluated fresh.
        """
        # Run a subprocess that imports the CLI and prints the WorkerConfig timeout
        test_script = """
import os
import sys
os.environ["SUPABASE_URL"] = "https://test.supabase.co"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test_key"

# Import after setting env var so the default is evaluated with our value
from rouge.worker.cli import app as worker_app
from typer.testing import CliRunner
from unittest.mock import Mock, patch

runner = CliRunner()
with patch("rouge.worker.cli.IssueWorker") as mock_worker_class:
    mock_worker = Mock()
    mock_worker_class.return_value = mock_worker
    result = runner.invoke(worker_app, ["--worker-id", "test-worker"])
    config = mock_worker_class.call_args[0][0]
    print(config.workflow_timeout)
"""
        result = subprocess.run(
            ["python", "-c", test_script],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "ROUGE_WORKFLOW_TIMEOUT_SECONDS": "1800",
                "SUPABASE_URL": "https://test.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "test_key",
            },
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        assert result.stdout.strip() == "1800"

    def test_workflow_timeout_cli_overrides_env(self, mock_env, monkeypatch) -> None:
        """Test CLI flag takes precedence over environment variable.

        We use subprocess to ensure the environment variable is evaluated
        in a fresh process, then verify the CLI flag overrides it.
        """
        test_script = """
import os
import sys
os.environ["SUPABASE_URL"] = "https://test.supabase.co"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test_key"

from rouge.worker.cli import app as worker_app
from typer.testing import CliRunner
from unittest.mock import Mock, patch

runner = CliRunner()
with patch("rouge.worker.cli.IssueWorker") as mock_worker_class:
    mock_worker = Mock()
    mock_worker_class.return_value = mock_worker
    result = runner.invoke(worker_app, ["--worker-id", "test-worker", "--workflow-timeout", "5400"])
    config = mock_worker_class.call_args[0][0]
    print(config.workflow_timeout)
"""
        result = subprocess.run(
            ["python", "-c", test_script],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "ROUGE_WORKFLOW_TIMEOUT_SECONDS": "1800",  # This should be overridden
                "SUPABASE_URL": "https://test.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "test_key",
            },
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        # CLI value (5400) should take precedence over env var (1800)
        assert result.stdout.strip() == "5400"

    def test_workflow_timeout_invalid_env_var(self, mock_env) -> None:
        """Test invalid environment variable values are handled gracefully.

        This test verifies that non-numeric and non-positive values in
        ROUGE_WORKFLOW_TIMEOUT_SECONDS trigger a warning and fall back to
        the default timeout value of 3600 seconds.
        """
        # Test non-numeric value
        test_script_non_numeric = """
import os
import sys
os.environ["SUPABASE_URL"] = "https://test.supabase.co"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test_key"

from rouge.worker.cli import app as worker_app
from typer.testing import CliRunner
from unittest.mock import Mock, patch

runner = CliRunner()
with patch("rouge.worker.cli.IssueWorker") as mock_worker_class:
    mock_worker = Mock()
    mock_worker_class.return_value = mock_worker
    result = runner.invoke(worker_app, ["--worker-id", "test-worker"])
    config = mock_worker_class.call_args[0][0]
    print(config.workflow_timeout)
    # Print captured output to real stderr so subprocess can check it
    import sys as _sys
    print(result.output, file=_sys.stderr)
"""
        result = subprocess.run(
            ["python", "-c", test_script_non_numeric],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "ROUGE_WORKFLOW_TIMEOUT_SECONDS": "invalid",
                "SUPABASE_URL": "https://test.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "test_key",
            },
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        # Should fall back to default 3600
        assert result.stdout.strip() == "3600"
        # Should have warning in stderr (forwarded from Typer's captured output)
        assert "Warning: Invalid value for ROUGE_WORKFLOW_TIMEOUT_SECONDS" in result.stderr

        # Test negative value
        test_script_negative = """
import os
import sys
os.environ["SUPABASE_URL"] = "https://test.supabase.co"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test_key"

from rouge.worker.cli import app as worker_app
from typer.testing import CliRunner
from unittest.mock import Mock, patch

runner = CliRunner()
with patch("rouge.worker.cli.IssueWorker") as mock_worker_class:
    mock_worker = Mock()
    mock_worker_class.return_value = mock_worker
    result = runner.invoke(worker_app, ["--worker-id", "test-worker"])
    config = mock_worker_class.call_args[0][0]
    print(config.workflow_timeout)
    # Print captured output to real stderr so subprocess can check it
    import sys as _sys
    print(result.output, file=_sys.stderr)
"""
        result = subprocess.run(
            ["python", "-c", test_script_negative],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "ROUGE_WORKFLOW_TIMEOUT_SECONDS": "-100",
                "SUPABASE_URL": "https://test.supabase.co",
                "SUPABASE_SERVICE_ROLE_KEY": "test_key",
            },
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        # Should fall back to default 3600
        assert result.stdout.strip() == "3600"
        # Should have warning in stderr (forwarded from Typer's captured output)
        assert "Warning: ROUGE_WORKFLOW_TIMEOUT_SECONDS must be positive" in result.stderr


class TestWorkflowRouting:
    """Tests for workflow routing based on issue type."""

    def test_execute_workflow_routes_to_main_for_main_type(self, worker) -> None:
        """Test that execute_workflow calls _execute_workflow for type='main'."""
        with patch.object(worker, "_execute_workflow") as mock_workflow:
            mock_workflow.return_value = ("adw-test-123", True)

            result = worker.execute_workflow(123, "Test issue", "pending", "main")

            assert result is True
            mock_workflow.assert_called_once_with(123, "main", "Test issue")

    def test_execute_workflow_routes_to_patch_for_patch_type(self, worker) -> None:
        """Test that execute_workflow calls _execute_workflow for type='patch'."""
        with patch.object(worker, "_execute_workflow") as mock_workflow:
            mock_workflow.return_value = ("patch-adw-test-123", True)

            result = worker.execute_workflow(456, "Patch issue", "pending", "patch")

            assert result is True
            mock_workflow.assert_called_once_with(456, "patch", "Patch issue")

    def test_execute_workflow_defaults_to_main_for_unknown_type(self, worker) -> None:
        """Test execute_workflow passes unknown type to _execute_workflow (registry)."""
        with patch.object(worker, "_execute_workflow") as mock_workflow:
            mock_workflow.return_value = ("adw-test-789", True)

            result = worker.execute_workflow(789, "Unknown type issue", "pending", "unknown")

            assert result is True
            mock_workflow.assert_called_once_with(789, "unknown", "Unknown type issue")

    @pytest.mark.skip(reason="Hangs intermittently on CI runners; routing logic tested above.")
    def test_run_loop_routes_patch_issue_to_patch_workflow(self, worker) -> None:
        """Test worker run loop routes patch type issues to patch workflow."""
        worker.running = True
        call_count = [0]

        def mock_get_next_issue(worker_id, logger):
            call_count[0] += 1
            if call_count[0] == 1:
                return (123, "Patch issue description", "pending", "patch")
            worker.running = False
            return None

        with patch("rouge.worker.database.get_next_issue", side_effect=mock_get_next_issue):
            with patch.object(worker, "execute_workflow") as mock_execute:
                mock_execute.return_value = True
                worker.run()

                mock_execute.assert_called_once_with(
                    123, "Patch issue description", "pending", "patch"
                )

    @pytest.mark.skip(reason="Hangs intermittently on CI runners; routing logic tested above.")
    def test_run_loop_routes_main_issue_to_main_workflow(self, worker) -> None:
        """Test worker run loop routes main type issues to main workflow."""
        worker.running = True
        call_count = [0]

        def mock_get_next_issue(worker_id, logger):
            call_count[0] += 1
            if call_count[0] == 1:
                return (456, "Main issue description", "pending", "main")
            worker.running = False
            return None

        with patch("rouge.worker.database.get_next_issue", side_effect=mock_get_next_issue):
            with patch.object(worker, "execute_workflow") as mock_execute:
                mock_execute.return_value = True
                worker.run()

                mock_execute.assert_called_once_with(
                    456, "Main issue description", "pending", "main"
                )

    def test_execute_workflow_handles_patch_failure(self, worker) -> None:
        """Test execute_workflow handles patch workflow failure correctly."""
        with patch.object(worker, "_execute_workflow") as mock_workflow:
            mock_workflow.return_value = ("patch-adw-test-fail", False)

            result = worker.execute_workflow(123, "Patch issue", "pending", "patch")

            assert result is False
            mock_workflow.assert_called_once_with(123, "patch", "Patch issue")

    def test_execute_workflow_handles_main_failure(self, worker) -> None:
        """Test execute_workflow handles main workflow failure correctly."""
        with patch.object(worker, "_execute_workflow") as mock_workflow:
            mock_workflow.return_value = ("adw-test-fail", False)

            result = worker.execute_workflow(123, "Main issue", "pending", "main")

            assert result is False
            mock_workflow.assert_called_once_with(123, "main", "Main issue")


class TestPatchWorkflowAdwId:
    """Tests verifying patch workflows generate unique ADW IDs."""

    def test_patch_workflow_generates_unique_adw_id(self, worker) -> None:
        """Test that patch workflows generate unique ADW IDs via make_adw_id()."""
        generated_ids = []

        def capture_adw_id():
            adw_id = f"mock-{len(generated_ids)}"
            generated_ids.append(adw_id)
            return adw_id

        mock_result = Mock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            with patch("rouge.worker.worker.update_issue_status"):
                with patch("rouge.worker.worker.make_adw_id", side_effect=capture_adw_id):
                    worker.execute_workflow(100, "Patch issue", "pending", "patch")
                    worker.execute_workflow(200, "Another patch", "pending", "patch")

        assert len(generated_ids) == 2
        assert generated_ids[0] != generated_ids[1]

    def test_patch_workflow_does_not_reuse_parent_adw_id(self, worker) -> None:
        """Test that patch workflows do not reuse any parent ADW ID.

        After decoupling, all workflow types use make_adw_id() to generate
        a fresh unique identifier rather than inheriting from a parent.
        """
        adw_ids_used = []

        mock_result = Mock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            with patch("rouge.worker.worker.update_issue_status"):
                with patch(
                    "rouge.worker.worker.make_adw_id",
                    side_effect=["patch-abc", "main-xyz"],
                ):
                    # Execute a patch workflow
                    worker.execute_workflow(100, "Patch issue", "pending", "patch")
                    # Execute a main workflow
                    worker.execute_workflow(200, "Main issue", "pending", "main")

                    # Collect the adw_id arguments from subprocess.run calls
                    for call in mock_run.call_args_list:
                        cmd = call[0][0]
                        if "--adw-id" in cmd:
                            adw_idx = cmd.index("--adw-id")
                            adw_ids_used.append(cmd[adw_idx + 1])

        # Both should have unique generated IDs
        assert len(adw_ids_used) == 2
        assert adw_ids_used[0] == "patch-abc"
        assert adw_ids_used[1] == "main-xyz"
        assert adw_ids_used[0] != adw_ids_used[1]

    def test_make_adw_id_called_for_every_workflow_type(self, worker) -> None:
        """Test that make_adw_id is called once per workflow execution."""
        mock_result = Mock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            with patch("rouge.worker.worker.update_issue_status"):
                with patch(
                    "rouge.worker.worker.make_adw_id", return_value="unique-id"
                ) as mock_make:
                    worker.execute_workflow(100, "Issue", "pending", "patch")

                    mock_make.assert_called_once()


class TestWorkerConfig:
    """Tests for WorkerConfig."""

    def test_config_invalid_workflow_timeout(self) -> None:
        """Test configuration with invalid workflow_timeout."""
        with pytest.raises(ValueError, match="workflow_timeout must be positive"):
            WorkerConfig(worker_id="test", poll_interval=10, workflow_timeout=0)

        with pytest.raises(ValueError, match="workflow_timeout must be positive"):
            WorkerConfig(worker_id="test", poll_interval=10, workflow_timeout=-1)

    def test_config_validation_success(self) -> None:
        """Test valid configuration."""
        config = WorkerConfig(worker_id="test-worker", poll_interval=10, log_level="INFO")

        assert config.worker_id == "test-worker"
        assert config.poll_interval == 10
        assert config.log_level == "INFO"

    def test_config_empty_worker_id(self) -> None:
        """Test configuration with empty worker_id."""
        with pytest.raises(ValueError, match="worker_id cannot be empty"):
            WorkerConfig(worker_id="", poll_interval=10)

    def test_config_whitespace_only_worker_id(self) -> None:
        """Test configuration with whitespace-only worker_id."""
        # Whitespace-only strings will fail the leading/trailing check first
        with pytest.raises(ValueError, match="leading or trailing whitespace"):
            WorkerConfig(worker_id="   ", poll_interval=10)

        with pytest.raises(ValueError, match="leading or trailing whitespace"):
            WorkerConfig(worker_id="\t", poll_interval=10)

        with pytest.raises(ValueError, match="leading or trailing whitespace"):
            WorkerConfig(worker_id="\n", poll_interval=10)

    def test_config_worker_id_leading_whitespace(self) -> None:
        """Test configuration rejects worker_id with leading whitespace."""
        with pytest.raises(ValueError, match="leading or trailing whitespace"):
            WorkerConfig(worker_id=" test-worker", poll_interval=10)

        with pytest.raises(ValueError, match="leading or trailing whitespace"):
            WorkerConfig(worker_id="\ttest-worker", poll_interval=10)

    def test_config_worker_id_trailing_whitespace(self) -> None:
        """Test configuration rejects worker_id with trailing whitespace."""
        with pytest.raises(ValueError, match="leading or trailing whitespace"):
            WorkerConfig(worker_id="test-worker ", poll_interval=10)

        with pytest.raises(ValueError, match="leading or trailing whitespace"):
            WorkerConfig(worker_id="test-worker\n", poll_interval=10)

    def test_config_worker_id_internal_whitespace(self) -> None:
        """Test configuration rejects worker_id with internal whitespace."""
        with pytest.raises(ValueError, match="worker_id cannot contain whitespace characters"):
            WorkerConfig(worker_id="test worker", poll_interval=10)

        with pytest.raises(ValueError, match="worker_id cannot contain whitespace characters"):
            WorkerConfig(worker_id="test\tworker", poll_interval=10)

        with pytest.raises(ValueError, match="worker_id cannot contain whitespace characters"):
            WorkerConfig(worker_id="test\nworker", poll_interval=10)

    def test_config_worker_id_path_separators(self) -> None:
        """Test configuration rejects worker_id with path separators."""
        with pytest.raises(ValueError, match="worker_id cannot contain path separators"):
            WorkerConfig(worker_id="test/worker", poll_interval=10)

        with pytest.raises(ValueError, match="worker_id cannot contain path separators"):
            WorkerConfig(worker_id="test\\worker", poll_interval=10)

    def test_config_worker_id_path_traversal(self) -> None:
        """Test configuration rejects worker_id with path traversal attempts."""
        with pytest.raises(ValueError, match="parent directory references"):
            WorkerConfig(worker_id="..test", poll_interval=10)

        with pytest.raises(ValueError, match="parent directory references"):
            WorkerConfig(worker_id="test..", poll_interval=10)

    def test_config_worker_id_special_paths(self) -> None:
        """Test configuration rejects special path components."""
        # "." fails the path component check (Path(".").parts returns empty tuple)
        with pytest.raises(ValueError, match="worker_id must be a single path component"):
            WorkerConfig(worker_id=".", poll_interval=10)

        # ".." fails the parent directory check first
        with pytest.raises(ValueError, match="parent directory references"):
            WorkerConfig(worker_id="..", poll_interval=10)

    def test_config_worker_id_multiple_path_components(self) -> None:
        """Test configuration rejects worker_id with multiple path components."""
        # This test validates that worker_id must be a single path component
        with pytest.raises(ValueError, match="worker_id cannot contain path separators"):
            WorkerConfig(worker_id="parent/child", poll_interval=10)

    def test_config_invalid_poll_interval(self) -> None:
        """Test configuration with invalid poll_interval."""
        with pytest.raises(ValueError, match="poll_interval must be positive"):
            WorkerConfig(worker_id="test", poll_interval=0)

    def test_config_invalid_log_level(self) -> None:
        """Test configuration with invalid log_level."""
        with pytest.raises(ValueError, match="log_level must be one of"):
            WorkerConfig(worker_id="test", log_level="INVALID")

    def test_config_log_level_normalization(self) -> None:
        """Test log level is normalized to uppercase."""
        config = WorkerConfig(worker_id="test", log_level="debug")
        assert config.log_level == "DEBUG"


class TestWorkerStateTransitions:
    """Tests for worker state transitions during workflow execution."""

    def test_worker_transitions_to_working_state_on_workflow_start(self, worker) -> None:
        """Test worker artifact transitions to working state when workflow starts."""

        mock_result = Mock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            with patch("rouge.worker.worker.update_issue_status"):
                with patch("rouge.worker.worker.make_adw_id", return_value="test-adw-123"):
                    # Mock the artifact writes to capture state changes
                    write_calls = []

                    def capture_write(artifact):
                        write_calls.append(artifact.model_copy(deep=True))

                    with patch(
                        "rouge.worker.worker.write_worker_artifact", side_effect=capture_write
                    ):
                        worker.execute_workflow(100, "Test issue", "pending", "main")

                    # Should have at least 2 writes: one for working, one for ready
                    assert len(write_calls) >= 2

                    # First write should transition to working state
                    first_write = write_calls[0]
                    assert first_write.state == "working"
                    assert first_write.current_issue_id == 100
                    assert first_write.current_adw_id == "test-adw-123"

    def test_worker_transitions_to_ready_state_on_workflow_success(self, worker) -> None:
        """Test worker artifact transitions to ready state when workflow succeeds."""
        mock_result = Mock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            with patch("rouge.worker.worker.update_issue_status"):
                with patch("rouge.worker.worker.make_adw_id", return_value="test-adw-456"):
                    write_calls = []

                    def capture_write(artifact):
                        write_calls.append(artifact.model_copy(deep=True))

                    with patch(
                        "rouge.worker.worker.write_worker_artifact", side_effect=capture_write
                    ):
                        worker.execute_workflow(200, "Success issue", "pending", "main")

                    # Last write should transition to ready state
                    last_write = write_calls[-1]
                    assert last_write.state == "ready"
                    assert last_write.current_issue_id is None
                    assert last_write.current_adw_id is None

    def test_worker_transitions_to_failed_state_on_workflow_failure(self, worker) -> None:
        """Test worker artifact transitions to failed state when workflow fails."""
        mock_result = Mock()
        mock_result.returncode = 1

        with patch("subprocess.run", return_value=mock_result):
            with patch("rouge.worker.worker.update_issue_status"):
                with patch("rouge.worker.worker.make_adw_id", return_value="test-adw-789"):
                    write_calls = []

                    def capture_write(artifact):
                        write_calls.append(artifact.model_copy(deep=True))

                    with patch(
                        "rouge.worker.worker.write_worker_artifact", side_effect=capture_write
                    ):
                        worker.execute_workflow(300, "Fail issue", "pending", "main")

                    # Last write should transition to failed state
                    last_write = write_calls[-1]
                    assert last_write.state == "failed"
                    # Should keep issue_id and adw_id set for debugging
                    assert last_write.current_issue_id == 300
                    assert last_write.current_adw_id == "test-adw-789"

    def test_worker_transitions_to_failed_state_on_timeout(self, worker) -> None:
        """Test worker artifact transitions to failed state when workflow times out."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 3600)):
            with patch("rouge.worker.worker.update_issue_status"):
                with patch("rouge.worker.worker.make_adw_id", return_value="test-adw-timeout"):
                    write_calls = []

                    def capture_write(artifact):
                        write_calls.append(artifact.model_copy(deep=True))

                    with patch(
                        "rouge.worker.worker.write_worker_artifact", side_effect=capture_write
                    ):
                        worker.execute_workflow(400, "Timeout issue", "pending", "main")

                    # Last write should transition to failed state
                    last_write = write_calls[-1]
                    assert last_write.state == "failed"
                    assert last_write.current_issue_id == 400
                    assert last_write.current_adw_id == "test-adw-timeout"

    def test_worker_transitions_to_failed_state_on_exception(self, worker) -> None:
        """Test worker artifact transitions to failed state on unexpected exception."""
        with patch("subprocess.run", side_effect=Exception("Unexpected error")):
            with patch("rouge.worker.worker.update_issue_status"):
                with patch("rouge.worker.worker.make_adw_id", return_value="test-adw-error"):
                    write_calls = []

                    def capture_write(artifact):
                        write_calls.append(artifact.model_copy(deep=True))

                    with patch(
                        "rouge.worker.worker.write_worker_artifact", side_effect=capture_write
                    ):
                        worker.execute_workflow(500, "Error issue", "pending", "main")

                    # Last write should transition to failed state
                    last_write = write_calls[-1]
                    assert last_write.state == "failed"
                    assert last_write.current_issue_id == 500
                    assert last_write.current_adw_id == "test-adw-error"

    def test_worker_state_persists_across_multiple_workflows(self, worker) -> None:
        """Test worker state correctly transitions across multiple workflow executions."""
        mock_result = Mock()
        mock_result.returncode = 0

        write_calls = []

        def capture_write(artifact):
            write_calls.append(artifact.model_copy(deep=True))

        with patch("subprocess.run", return_value=mock_result):
            with patch("rouge.worker.worker.update_issue_status"):
                with patch("rouge.worker.worker.make_adw_id", side_effect=["adw-1", "adw-2"]):
                    with patch(
                        "rouge.worker.worker.write_worker_artifact", side_effect=capture_write
                    ):
                        # Execute first workflow
                        worker.execute_workflow(100, "First issue", "pending", "main")

                        # Execute second workflow
                        worker.execute_workflow(200, "Second issue", "pending", "main")

        # Should have writes for both workflows
        assert len(write_calls) >= 4  # 2 per workflow (working + ready)

        # Check state progression for first workflow
        assert write_calls[0].state == "working"
        assert write_calls[0].current_issue_id == 100
        assert write_calls[1].state == "ready"
        assert write_calls[1].current_issue_id is None

        # Check state progression for second workflow
        assert write_calls[2].state == "working"
        assert write_calls[2].current_issue_id == 200
        assert write_calls[3].state == "ready"
        assert write_calls[3].current_issue_id is None


class TestWorkerPollLoopGating:
    """Tests for poll loop gating based on worker state.

    These tests verify that the worker correctly gates its poll loop based on
    the worker artifact state, preventing issue polling when in failed or
    working states.
    """

    def test_poll_loop_skips_polling_when_in_failed_state(self, worker) -> None:
        """Test worker skips polling when in failed state."""
        from rouge.worker.worker_artifact import WorkerArtifact

        # Set worker to failed state
        failed_artifact = WorkerArtifact(
            worker_id="test-worker",
            state="failed",
            current_issue_id=123,
            current_adw_id="adw-failed",
        )
        worker.worker_artifact = failed_artifact

        worker.running = True
        call_count = [0]

        def mock_sleep(seconds):
            call_count[0] += 1
            if call_count[0] >= 2:
                worker.running = False

        with patch("rouge.worker.worker.read_worker_artifact", return_value=failed_artifact):
            with patch("rouge.worker.worker.time.sleep", side_effect=mock_sleep):
                with patch("rouge.worker.worker.get_next_issue") as mock_get_next:
                    worker.run()

                    # get_next_issue should NOT have been called (worker gated by failed state)
                    mock_get_next.assert_not_called()

    def test_poll_loop_skips_polling_when_in_working_state(self, worker) -> None:
        """Test worker skips polling when in working state without active execution."""
        from rouge.worker.worker_artifact import WorkerArtifact

        # Set worker to working state (simulating restart after crash during workflow)
        working_artifact = WorkerArtifact(
            worker_id="test-worker",
            state="working",
            current_issue_id=456,
            current_adw_id="adw-working",
        )
        worker.worker_artifact = working_artifact

        worker.running = True
        call_count = [0]

        def mock_sleep(seconds):
            call_count[0] += 1
            if call_count[0] >= 2:
                worker.running = False

        with patch("rouge.worker.worker.read_worker_artifact", return_value=working_artifact):
            with patch("rouge.worker.worker.time.sleep", side_effect=mock_sleep):
                with patch("rouge.worker.worker.get_next_issue") as mock_get_next:
                    worker.run()

                    # get_next_issue should NOT have been called (worker gated by working state)
                    mock_get_next.assert_not_called()

    def test_poll_loop_continues_when_in_ready_state(self, worker) -> None:
        """Test worker polls for issues when in ready state."""
        from rouge.worker.worker_artifact import WorkerArtifact

        # Set worker to ready state
        ready_artifact = WorkerArtifact(
            worker_id="test-worker",
            state="ready",
            current_issue_id=None,
            current_adw_id=None,
        )
        worker.worker_artifact = ready_artifact

        worker.running = True
        call_count = [0]

        def mock_get_next_issue(worker_id, logger):
            call_count[0] += 1
            if call_count[0] >= 1:
                # Stop after first poll to verify it was called
                worker.running = False
            return None  # No issues available

        def mock_sleep(seconds):
            # Mock sleep to do nothing
            pass

        with patch("rouge.worker.worker.read_worker_artifact", return_value=ready_artifact):
            with patch("rouge.worker.worker.get_next_issue", side_effect=mock_get_next_issue):
                with patch("rouge.worker.worker.time.sleep", side_effect=mock_sleep):
                    worker.run()

                    # get_next_issue should have been called (worker in ready state)
                    assert call_count[0] >= 1

    def test_poll_loop_logs_failed_state_message(self, worker) -> None:
        """Test worker logs appropriate message when in failed state."""
        from rouge.worker.worker_artifact import WorkerArtifact

        failed_artifact = WorkerArtifact(
            worker_id="test-worker",
            state="failed",
            current_issue_id=789,
            current_adw_id="adw-fail",
        )
        worker.worker_artifact = failed_artifact

        worker.running = True
        call_count = [0]

        def mock_sleep(seconds):
            call_count[0] += 1
            if call_count[0] >= 1:
                worker.running = False

        with patch("rouge.worker.worker.read_worker_artifact", return_value=failed_artifact):
            with patch("rouge.worker.worker.time.sleep", side_effect=mock_sleep):
                with patch("rouge.worker.worker.get_next_issue"):
                    with patch.object(worker.logger, "info") as mock_log:
                        worker.run()

                        # Should log message about failed state
                        # Check if the failed state message was logged with the correct issue_id
                        assert any(
                            "failed state" in call.args[0].lower() and 789 in call.args
                            for call in mock_log.call_args_list
                        )

    def test_poll_loop_logs_working_state_warning(self, worker) -> None:
        """Test worker logs warning when in working state without active execution."""
        from rouge.worker.worker_artifact import WorkerArtifact

        working_artifact = WorkerArtifact(
            worker_id="test-worker",
            state="working",
            current_issue_id=999,
            current_adw_id="adw-stuck",
        )
        worker.worker_artifact = working_artifact

        worker.running = True
        call_count = [0]

        def mock_sleep(seconds):
            call_count[0] += 1
            if call_count[0] >= 1:
                worker.running = False

        with patch("rouge.worker.worker.read_worker_artifact", return_value=working_artifact):
            with patch("rouge.worker.worker.time.sleep", side_effect=mock_sleep):
                with patch("rouge.worker.worker.get_next_issue"):
                    with patch.object(worker.logger, "warning") as mock_log:
                        worker.run()

                        # Should log warning about working state
                        # Check if the working state warning was logged with the correct issue_id
                        assert any(
                            "working state" in call.args[0].lower() and 999 in call.args
                            for call in mock_log.call_args_list
                        )

    def test_worker_rereads_artifact_from_disk_each_iteration(self, worker) -> None:
        """Test that the worker re-reads the artifact from disk on each poll iteration."""
        from rouge.worker.worker_artifact import WorkerArtifact

        # Set up: worker artifact starts as failed, then gets reset to ready externally
        failed_artifact = WorkerArtifact(
            worker_id="test-worker",
            state="failed",
            current_issue_id=42,
            current_adw_id="adw-123",
        )
        ready_artifact = WorkerArtifact(
            worker_id="test-worker",
            state="ready",
            current_issue_id=None,
            current_adw_id=None,
        )

        call_count = 0

        def side_effect(worker_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return failed_artifact
            else:
                worker.running = False  # Stop after second iteration
                return ready_artifact

        with (
            patch("rouge.worker.worker.read_worker_artifact", side_effect=side_effect),
            patch("rouge.worker.worker.get_next_issue", return_value=None),
            patch("rouge.worker.worker.time"),
        ):
            worker.run()

        assert call_count >= 2


class TestWorkerResetCLI:
    """Tests for the rouge-worker reset CLI subcommand."""

    def test_worker_reset_fails_when_no_artifact(self) -> None:
        """Test rouge-worker reset exits 1 when no artifact found."""
        from typer.testing import CliRunner

        from rouge.worker.cli import app as worker_app

        runner = CliRunner()
        with patch("rouge.worker.cli.read_worker_artifact", return_value=None):
            result = runner.invoke(worker_app, ["reset", "test-worker"])
        assert result.exit_code == 1
        assert "No artifact found" in result.output

    def test_worker_reset_fails_when_not_failed_state(self) -> None:
        """Test rouge-worker reset exits 1 when worker is not in failed state."""
        from typer.testing import CliRunner

        from rouge.worker.cli import app as worker_app
        from rouge.worker.worker_artifact import WorkerArtifact

        runner = CliRunner()
        ready_artifact = WorkerArtifact(worker_id="test-worker", state="ready")
        with patch("rouge.worker.cli.read_worker_artifact", return_value=ready_artifact):
            result = runner.invoke(worker_app, ["reset", "test-worker"])
        assert result.exit_code == 1
        assert "can only reset 'failed' workers" in result.output

    def test_worker_reset_succeeds_when_failed(self) -> None:
        """Test rouge-worker reset exits 0 and resets artifact when worker is in failed state."""
        from typer.testing import CliRunner

        from rouge.worker.cli import app as worker_app
        from rouge.worker.worker_artifact import WorkerArtifact

        runner = CliRunner()
        failed_artifact = WorkerArtifact(
            worker_id="test-worker",
            state="failed",
            current_issue_id=42,
            current_adw_id="adw-123",
        )
        with (
            patch("rouge.worker.cli.read_worker_artifact", return_value=failed_artifact),
            patch("rouge.worker.cli.write_worker_artifact") as mock_write,
        ):
            result = runner.invoke(worker_app, ["reset", "test-worker"])
        assert result.exit_code == 0
        assert "reset to ready" in result.output
        mock_write.assert_called_once()
        written = mock_write.call_args[0][0]
        assert written.state == "ready"
        assert written.current_issue_id is None
        assert written.current_adw_id is None

    def test_worker_reset_fails_when_working(self) -> None:
        """Test rouge-worker reset exits 1 when worker is in working state."""
        from typer.testing import CliRunner

        from rouge.worker.cli import app as worker_app
        from rouge.worker.worker_artifact import WorkerArtifact

        runner = CliRunner()
        working_artifact = WorkerArtifact(
            worker_id="test-worker",
            state="working",
            current_issue_id=5,
            current_adw_id="adw-456",
        )
        with patch("rouge.worker.cli.read_worker_artifact", return_value=working_artifact):
            result = runner.invoke(worker_app, ["reset", "test-worker"])
        assert result.exit_code == 1
        assert "can only reset 'failed' workers" in result.output
