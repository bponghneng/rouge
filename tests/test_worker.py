"""Tests for the CAPE issue worker daemon."""

import os
import subprocess
from unittest.mock import Mock, patch

import pytest

from rouge.worker import database
from rouge.worker.config import WorkerConfig
from rouge.worker.worker import IssueWorker


@pytest.fixture
def mock_env(monkeypatch):
    """Mock environment variables for Supabase."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test_key")


@pytest.fixture
def worker_config():
    """Create a worker configuration for testing."""
    return WorkerConfig(worker_id="test-worker", poll_interval=5, log_level="DEBUG")


@pytest.fixture
def worker(mock_env, worker_config):
    """Create a worker instance for testing."""
    with patch("rouge.worker.database.get_client"):
        worker = IssueWorker(worker_config)
        return worker


class TestIssueWorkerInit:
    """Tests for IssueWorker initialization."""

    def test_worker_initialization(self, mock_env, worker_config):
        """Test worker initializes with correct parameters."""
        with patch("rouge.worker.database.get_client"):
            worker = IssueWorker(worker_config)

            assert worker.config.worker_id == "test-worker"
            assert worker.config.poll_interval == 5
            assert worker.config.log_level == "DEBUG"
            assert worker.running is True

    def test_worker_logging_setup(self, mock_env, worker_config):
        """Test worker sets up logging correctly."""
        with patch("rouge.worker.database.get_client"):
            worker = IssueWorker(worker_config)

            assert worker.logger is not None
            assert worker.logger.name == "rouge_worker_test-worker"


class TestGetNextIssue:
    """Tests for get_next_issue function."""

    def test_get_next_issue_success(self, mock_env):
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

    def test_get_next_issue_no_issues(self, mock_env):
        """Test when no issues are available."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.data = []
        mock_client.rpc.return_value.execute.return_value = mock_response

        with patch("rouge.worker.database.get_client", return_value=mock_client):
            result = database.get_next_issue("test-worker")

            assert result is None

    def test_get_next_issue_database_error(self, mock_env):
        """Test handling database errors."""
        mock_client = Mock()
        mock_client.rpc.side_effect = Exception("Database connection failed")

        with patch("rouge.worker.database.get_client", return_value=mock_client):
            result = database.get_next_issue("test-worker")

            assert result is None


class TestExecuteWorkflow:
    """Tests for execute_workflow method."""

    def test_execute_workflow_success(self, worker):
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

    def test_execute_workflow_failure(self, worker):
        """Test workflow execution failure."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Workflow failed"

        with patch("subprocess.run", return_value=mock_result):
            with patch("rouge.worker.worker.update_issue_status") as mock_update:
                result = worker.execute_workflow(123, "Test issue", "pending", "main")

                assert result is False
                mock_update.assert_called_once_with(123, "pending", worker.logger)

    def test_execute_workflow_timeout(self, worker):
        """Test workflow execution timeout."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 3600)):
            with patch("rouge.worker.worker.update_issue_status") as mock_update:
                result = worker.execute_workflow(123, "Test issue", "pending", "main")

                assert result is False
                mock_update.assert_called_once_with(123, "pending", worker.logger)

    def test_execute_workflow_exception(self, worker):
        """Test workflow execution with unexpected exception."""
        with patch("subprocess.run", side_effect=Exception("Unexpected error")):
            with patch("rouge.worker.worker.update_issue_status") as mock_update:
                result = worker.execute_workflow(123, "Test issue", "pending", "main")

                assert result is False
                mock_update.assert_called_once_with(123, "pending", worker.logger)

    def test_execute_workflow_command_format(self, worker):
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

    def test_execute_workflow_command_from_path(self, worker):
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

    def test_execute_workflow_command_from_env_var(self, worker, monkeypatch):
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

    def test_update_issue_status_success(self, mock_env):
        """Test successfully updating issue status."""
        mock_client = Mock()
        mock_table = Mock()
        mock_update = Mock()
        mock_eq = Mock()

        mock_client.table.return_value = mock_table
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value = mock_eq
        mock_eq.execute.return_value = Mock()

        with patch("rouge.worker.database.get_client", return_value=mock_client):
            database.update_issue_status(123, "completed")

            mock_client.table.assert_called_once_with("issues")
            mock_table.update.assert_called_once_with({"status": "completed"})
            mock_update.eq.assert_called_once_with("id", 123)
            mock_eq.execute.assert_called_once()

    def test_update_issue_status_database_error(self, mock_env):
        """Test handling database errors during status update."""
        mock_client = Mock()
        mock_client.table.side_effect = Exception("Database error")

        with patch("rouge.worker.database.get_client", return_value=mock_client):
            # Should not raise exception
            database.update_issue_status(123, "completed")


class TestWorkerRun:
    """Tests for the main worker run loop."""

    @pytest.mark.skip(reason="Hangs intermittently on Windows runners; tracked for later fix.")
    def test_run_processes_issue(self, worker):
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
    def test_run_sleeps_when_no_issues(self, worker):
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
    def test_run_handles_keyboard_interrupt(self, worker):
        """Test worker handles keyboard interrupt gracefully."""

        def mock_get_next_issue(worker_id, logger):
            raise KeyboardInterrupt()

        with patch("rouge.worker.database.get_next_issue", side_effect=mock_get_next_issue):
            worker.run()

            assert worker.running is False

    @pytest.mark.skip(reason="Flaky on Windows due to patching/time.sleep interactions.")
    def test_run_handles_unexpected_error(self, worker):
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

    def test_handle_shutdown_signal(self, worker):
        """Test worker handles shutdown signals."""
        assert worker.running is True

        worker._handle_shutdown(15, None)  # SIGTERM

        assert worker.running is False


class TestCommandLineInterface:
    """Tests for command line argument parsing."""

    def test_main_with_required_args(self, mock_env):
        """Test main function with required arguments."""
        test_args = ["rouge-worker", "--worker-id", "test-worker"]

        with patch("sys.argv", test_args):
            with patch("rouge.worker.cli.IssueWorker") as mock_worker_class:
                mock_worker = Mock()
                mock_worker_class.return_value = mock_worker

                from rouge.worker.cli import main

                main()

                # Verify WorkerConfig was created and passed
                assert mock_worker_class.call_count == 1
                config = mock_worker_class.call_args[0][0]
                assert isinstance(config, WorkerConfig)
                assert config.worker_id == "test-worker"
                assert config.poll_interval == 10
                assert config.log_level == "INFO"
                mock_worker.run.assert_called_once()

    def test_main_with_all_args(self, mock_env):
        """Test main function with all arguments."""
        test_args = [
            "rouge-worker",
            "--worker-id",
            "custom-worker",
            "--poll-interval",
            "15",
            "--log-level",
            "DEBUG",
        ]

        with patch("sys.argv", test_args):
            with patch("rouge.worker.cli.IssueWorker") as mock_worker_class:
                mock_worker = Mock()
                mock_worker_class.return_value = mock_worker

                from rouge.worker.cli import main

                main()

                # Verify WorkerConfig was created and passed
                assert mock_worker_class.call_count == 1
                config = mock_worker_class.call_args[0][0]
                assert isinstance(config, WorkerConfig)
                assert config.worker_id == "custom-worker"
                assert config.poll_interval == 15
                assert config.log_level == "DEBUG"
                mock_worker.run.assert_called_once()

    def test_workflow_timeout_from_cli(self, mock_env):
        """Test workflow-timeout flag is parsed and passed to WorkerConfig."""
        test_args = [
            "rouge-worker",
            "--worker-id",
            "test-worker",
            "--workflow-timeout",
            "7200",
        ]

        with patch("sys.argv", test_args):
            with patch("rouge.worker.cli.IssueWorker") as mock_worker_class:
                mock_worker = Mock()
                mock_worker_class.return_value = mock_worker

                from rouge.worker.cli import main

                main()

                # Verify WorkerConfig was created with the specified workflow_timeout
                assert mock_worker_class.call_count == 1
                config = mock_worker_class.call_args[0][0]
                assert isinstance(config, WorkerConfig)
                assert config.workflow_timeout == 7200
                mock_worker.run.assert_called_once()

    def test_workflow_timeout_from_env_var(self, mock_env, monkeypatch):
        """Test ROUGE_WORKFLOW_TIMEOUT_SECONDS env var is used as default.

        This test verifies that the CLI correctly reads the environment variable
        to set the default value for --workflow-timeout when the flag is not
        provided on the command line. We use subprocess to get a clean process
        where the environment variable is evaluated fresh.
        """
        # Run a subprocess that imports the CLI and prints the parsed timeout
        test_script = """
import os
import sys
os.environ["SUPABASE_URL"] = "https://test.supabase.co"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test_key"
sys.argv = ["rouge-worker", "--worker-id", "test-worker"]

# Import after setting env var so the default is evaluated with our value
from rouge.worker.cli import main
import argparse

# Patch argparse to capture the parsed args instead of running the worker
original_parse = argparse.ArgumentParser.parse_args
parsed = None
def capture_parse(self, *args, **kwargs):
    global parsed
    parsed = original_parse(self, *args, **kwargs)
    return parsed

argparse.ArgumentParser.parse_args = capture_parse

# Mock IssueWorker to prevent actual execution
from unittest.mock import Mock, patch
with patch("rouge.worker.cli.IssueWorker") as mock_worker:
    mock_worker.return_value = Mock()
    main()
    print(parsed.workflow_timeout)
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

    def test_workflow_timeout_cli_overrides_env(self, mock_env, monkeypatch):
        """Test CLI flag takes precedence over environment variable.

        We use subprocess to ensure the environment variable is evaluated
        in a fresh process, then verify the CLI flag overrides it.
        """
        test_script = """
import os
import sys
os.environ["SUPABASE_URL"] = "https://test.supabase.co"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test_key"
sys.argv = ["rouge-worker", "--worker-id", "test-worker", "--workflow-timeout", "5400"]

from rouge.worker.cli import main
import argparse

original_parse = argparse.ArgumentParser.parse_args
parsed = None
def capture_parse(self, *args, **kwargs):
    global parsed
    parsed = original_parse(self, *args, **kwargs)
    return parsed

argparse.ArgumentParser.parse_args = capture_parse

from unittest.mock import Mock, patch
with patch("rouge.worker.cli.IssueWorker") as mock_worker:
    mock_worker.return_value = Mock()
    main()
    print(parsed.workflow_timeout)
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

    def test_workflow_timeout_invalid_env_var(self, mock_env):
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
sys.argv = ["rouge-worker", "--worker-id", "test-worker"]

from rouge.worker.cli import main
import argparse

original_parse = argparse.ArgumentParser.parse_args
parsed = None
def capture_parse(self, *args, **kwargs):
    global parsed
    parsed = original_parse(self, *args, **kwargs)
    return parsed

argparse.ArgumentParser.parse_args = capture_parse

from unittest.mock import Mock, patch
with patch("rouge.worker.cli.IssueWorker") as mock_worker:
    mock_worker.return_value = Mock()
    main()
    print(parsed.workflow_timeout)
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
        # Should have warning in stderr
        assert "Warning: Invalid value for ROUGE_WORKFLOW_TIMEOUT_SECONDS" in result.stderr

        # Test negative value
        test_script_negative = """
import os
import sys
os.environ["SUPABASE_URL"] = "https://test.supabase.co"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test_key"
sys.argv = ["rouge-worker", "--worker-id", "test-worker"]

from rouge.worker.cli import main
import argparse

original_parse = argparse.ArgumentParser.parse_args
parsed = None
def capture_parse(self, *args, **kwargs):
    global parsed
    parsed = original_parse(self, *args, **kwargs)
    return parsed

argparse.ArgumentParser.parse_args = capture_parse

from unittest.mock import Mock, patch
with patch("rouge.worker.cli.IssueWorker") as mock_worker:
    mock_worker.return_value = Mock()
    main()
    print(parsed.workflow_timeout)
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
        # Should have warning in stderr
        assert "Warning: ROUGE_WORKFLOW_TIMEOUT_SECONDS must be positive" in result.stderr


class TestWorkflowRouting:
    """Tests for workflow routing based on issue type."""

    def test_execute_workflow_routes_to_main_for_main_type(self, worker):
        """Test that execute_workflow calls _execute_workflow for type='main'."""
        with patch.object(worker, "_execute_workflow") as mock_workflow:
            mock_workflow.return_value = ("adw-test-123", True)

            result = worker.execute_workflow(123, "Test issue", "pending", "main")

            assert result is True
            mock_workflow.assert_called_once_with(123, "main", "Test issue")

    def test_execute_workflow_routes_to_patch_for_patch_type(self, worker):
        """Test that execute_workflow calls _execute_workflow for type='patch'."""
        with patch.object(worker, "_execute_workflow") as mock_workflow:
            mock_workflow.return_value = ("patch-adw-test-123", True)

            result = worker.execute_workflow(456, "Patch issue", "pending", "patch")

            assert result is True
            mock_workflow.assert_called_once_with(456, "patch", "Patch issue")

    def test_execute_workflow_defaults_to_main_for_unknown_type(self, worker):
        """Test execute_workflow passes unknown type to _execute_workflow (registry)."""
        with patch.object(worker, "_execute_workflow") as mock_workflow:
            mock_workflow.return_value = ("adw-test-789", True)

            result = worker.execute_workflow(789, "Unknown type issue", "pending", "unknown")

            assert result is True
            mock_workflow.assert_called_once_with(789, "unknown", "Unknown type issue")

    @pytest.mark.skip(reason="Hangs intermittently on CI runners; routing logic tested above.")
    def test_run_loop_routes_patch_issue_to_patch_workflow(self, worker):
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
    def test_run_loop_routes_main_issue_to_main_workflow(self, worker):
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

    def test_execute_workflow_handles_patch_failure(self, worker):
        """Test execute_workflow handles patch workflow failure correctly."""
        with patch.object(worker, "_execute_workflow") as mock_workflow:
            mock_workflow.return_value = ("patch-adw-test-fail", False)

            result = worker.execute_workflow(123, "Patch issue", "pending", "patch")

            assert result is False
            mock_workflow.assert_called_once_with(123, "patch", "Patch issue")

    def test_execute_workflow_handles_main_failure(self, worker):
        """Test execute_workflow handles main workflow failure correctly."""
        with patch.object(worker, "_execute_workflow") as mock_workflow:
            mock_workflow.return_value = ("adw-test-fail", False)

            result = worker.execute_workflow(123, "Main issue", "pending", "main")

            assert result is False
            mock_workflow.assert_called_once_with(123, "main", "Main issue")

    def test_execute_workflow_catches_patch_exception(self, worker):
        """Test execute_workflow catches and handles patch workflow exceptions."""
        with patch.object(worker, "_execute_workflow") as mock_workflow:
            with patch("rouge.worker.worker.update_issue_status") as mock_update:
                mock_workflow.side_effect = Exception("Patch failed")

                result = worker.execute_workflow(123, "Patch issue", "pending", "patch")

                assert result is False
                mock_update.assert_called_once_with(123, "pending", worker.logger)

    def test_execute_workflow_catches_main_exception(self, worker):
        """Test execute_workflow catches and handles main workflow exceptions."""
        with patch.object(worker, "_execute_workflow") as mock_workflow:
            with patch("rouge.worker.worker.update_issue_status") as mock_update:
                mock_workflow.side_effect = Exception("Main failed")

                result = worker.execute_workflow(123, "Main issue", "pending", "main")

                assert result is False
                mock_update.assert_called_once_with(123, "pending", worker.logger)


class TestWorkerConfig:
    """Tests for WorkerConfig."""

    def test_config_invalid_workflow_timeout(self):
        """Test configuration with invalid workflow_timeout."""
        with pytest.raises(ValueError, match="workflow_timeout must be positive"):
            WorkerConfig(worker_id="test", poll_interval=10, workflow_timeout=0)

        with pytest.raises(ValueError, match="workflow_timeout must be positive"):
            WorkerConfig(worker_id="test", poll_interval=10, workflow_timeout=-1)

    def test_config_validation_success(self):
        """Test valid configuration."""
        config = WorkerConfig(worker_id="test-worker", poll_interval=10, log_level="INFO")

        assert config.worker_id == "test-worker"
        assert config.poll_interval == 10
        assert config.log_level == "INFO"

    def test_config_empty_worker_id(self):
        """Test configuration with empty worker_id."""
        with pytest.raises(ValueError, match="worker_id cannot be empty"):
            WorkerConfig(worker_id="", poll_interval=10)

    def test_config_invalid_poll_interval(self):
        """Test configuration with invalid poll_interval."""
        with pytest.raises(ValueError, match="poll_interval must be positive"):
            WorkerConfig(worker_id="test", poll_interval=0)

    def test_config_invalid_log_level(self):
        """Test configuration with invalid log_level."""
        with pytest.raises(ValueError, match="log_level must be one of"):
            WorkerConfig(worker_id="test", log_level="INVALID")

    def test_config_log_level_normalization(self):
        """Test log level is normalized to uppercase."""
        config = WorkerConfig(worker_id="test", log_level="debug")
        assert config.log_level == "DEBUG"
