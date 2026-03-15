"""Tests for database resilience and error handling in the worker daemon.

This module tests the database connection recovery mechanisms implemented across
the worker stack, including:
- Client reset functionality
- Transient error detection and handling
- Worker retry/backoff logic
- State management during database failures
"""

from unittest.mock import Mock, patch

import httpx
import pytest

from rouge.core.database import get_client, reset_client
from rouge.worker.config import WorkerConfig
from rouge.worker.database import get_next_issue
from rouge.worker.exceptions import TransientDatabaseError
from rouge.worker.worker import IssueWorker


@pytest.fixture
def mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock environment variables for Supabase."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test_key")


@pytest.fixture
def worker_config() -> WorkerConfig:
    """Create a worker configuration for testing with retry settings."""
    return WorkerConfig(
        worker_id="test-worker",
        poll_interval=5,
        log_level="DEBUG",
        db_retries=3,
        db_backoff_ms=100,
    )


@pytest.fixture
def worker(mock_env: None, worker_config: WorkerConfig) -> IssueWorker:
    """Create a worker instance for testing."""
    with patch("rouge.worker.database.get_client"):
        with patch("rouge.worker.worker_artifact.read_worker_artifact"):
            with patch("rouge.worker.worker_artifact.write_worker_artifact"):
                worker = IssueWorker(worker_config)
                return worker


class TestResetClient:
    """Tests for the reset_client() function in core.database."""

    def test_reset_client_clears_singleton(self, mock_env: None) -> None:
        """Verify reset_client() clears _client and get_client() recreates it."""
        # Import the module to access the singleton
        from rouge.core import database

        # Ensure we start with a clean state
        database._client = None

        # Get a client (creates singleton)
        client1 = get_client()
        assert client1 is not None
        assert database._client is client1

        # Reset the client
        reset_client()
        assert database._client is None

        # Get client again (should create new instance)
        client2 = get_client()
        assert client2 is not None
        assert database._client is client2

        # The two clients should be different instances
        assert client1 is not client2

    def test_reset_client_idempotent(self, mock_env: None) -> None:
        """Test that calling reset_client() multiple times is safe."""
        from rouge.core import database

        # Reset multiple times should not raise errors
        reset_client()
        reset_client()
        reset_client()

        assert database._client is None


class TestGetNextIssueTimeoutHandling:
    """Tests for get_next_issue() timeout and connection error handling."""

    def test_get_next_issue_catches_read_timeout(self, mock_env: None) -> None:
        """Test that get_next_issue catches httpx.ReadTimeout and raises TransientDatabaseError."""
        mock_client = Mock()
        mock_client.rpc.side_effect = httpx.ReadTimeout("Read timeout")

        with patch("rouge.worker.database.get_client", return_value=mock_client):
            with patch("rouge.worker.database.reset_client") as mock_reset:
                with pytest.raises(TransientDatabaseError) as exc_info:
                    get_next_issue("test-worker")

                # Verify the error message includes the error type
                assert "ReadTimeout" in str(exc_info.value)
                assert exc_info.value.original_error is not None
                assert isinstance(exc_info.value.original_error, httpx.ReadTimeout)

                # Verify reset_client was called
                mock_reset.assert_called_once()

    def test_get_next_issue_catches_connect_timeout(self, mock_env: None) -> None:
        """Test get_next_issue catches httpx.ConnectTimeout, raises TransientDatabaseError."""
        mock_client = Mock()
        mock_client.rpc.side_effect = httpx.ConnectTimeout("Connection timeout")

        with patch("rouge.worker.database.get_client", return_value=mock_client):
            with patch("rouge.worker.database.reset_client") as mock_reset:
                with pytest.raises(TransientDatabaseError) as exc_info:
                    get_next_issue("test-worker")

                # Verify the error message includes the error type
                assert "ConnectTimeout" in str(exc_info.value)
                assert exc_info.value.original_error is not None
                assert isinstance(exc_info.value.original_error, httpx.ConnectTimeout)

                # Verify reset_client was called
                mock_reset.assert_called_once()

    def test_get_next_issue_catches_connect_error(self, mock_env: None) -> None:
        """Test that get_next_issue catches httpx.ConnectError and raises TransientDatabaseError."""
        mock_client = Mock()
        mock_client.rpc.side_effect = httpx.ConnectError("Connection failed")

        with patch("rouge.worker.database.get_client", return_value=mock_client):
            with patch("rouge.worker.database.reset_client") as mock_reset:
                with pytest.raises(TransientDatabaseError) as exc_info:
                    get_next_issue("test-worker")

                # Verify the error message includes the error type
                assert "ConnectError" in str(exc_info.value)
                assert exc_info.value.original_error is not None
                assert isinstance(exc_info.value.original_error, httpx.ConnectError)

                # Verify reset_client was called
                mock_reset.assert_called_once()

    def test_reset_client_called_before_raising_transient_error(self, mock_env: None) -> None:
        """Test that reset_client() is called before re-raising TransientDatabaseError."""
        mock_client = Mock()
        mock_client.rpc.side_effect = httpx.ReadTimeout("Read timeout")

        call_order = []

        def track_reset():
            call_order.append("reset")

        def track_raise(*args, **kwargs):
            call_order.append("raise")
            raise httpx.ReadTimeout("Read timeout")

        mock_client.rpc.side_effect = track_raise

        with patch("rouge.worker.database.get_client", return_value=mock_client):
            with patch("rouge.worker.database.reset_client", side_effect=track_reset):
                with pytest.raises(TransientDatabaseError):
                    get_next_issue("test-worker")

                # Verify reset was called before raise
                assert call_order == ["raise", "reset"]

    def test_get_next_issue_logs_warning_on_timeout(self, mock_env: None) -> None:
        """Test that timeout errors are logged with appropriate warning level."""
        mock_client = Mock()
        mock_client.rpc.side_effect = httpx.ReadTimeout("Read timeout")
        mock_logger = Mock()

        with patch("rouge.worker.database.get_client", return_value=mock_client):
            with patch("rouge.worker.database.reset_client"):
                with pytest.raises(TransientDatabaseError):
                    get_next_issue("test-worker", logger=mock_logger)

                # Verify warning was logged
                mock_logger.warning.assert_called_once()
                warning_msg = mock_logger.warning.call_args[0][0]
                assert "Transient database error" in warning_msg
                assert "ReadTimeout" in mock_logger.warning.call_args[0][1]

    def test_transient_database_error_preserves_original_exception(self, mock_env: None) -> None:
        """Test that TransientDatabaseError preserves the original exception details."""
        original_error = httpx.ReadTimeout("Original timeout message")
        mock_client = Mock()
        mock_client.rpc.side_effect = original_error

        with patch("rouge.worker.database.get_client", return_value=mock_client):
            with patch("rouge.worker.database.reset_client"):
                with pytest.raises(TransientDatabaseError) as exc_info:
                    get_next_issue("test-worker")

                # Verify original error is preserved
                assert exc_info.value.original_error is original_error
                assert "Original timeout message" in str(exc_info.value.original_error)

    def test_get_next_issue_non_transient_errors_not_reset_client(self, mock_env: None) -> None:
        """Test that non-transient errors do not trigger client reset."""
        mock_client = Mock()
        # Simulate a non-transient error
        mock_client.rpc.side_effect = ValueError("Some other error")

        with patch("rouge.worker.database.get_client", return_value=mock_client):
            with patch("rouge.worker.database.reset_client") as mock_reset:
                # Should return None for unexpected errors
                result = get_next_issue("test-worker")

                assert result is None
                # reset_client should NOT be called for non-transient errors
                mock_reset.assert_not_called()


class TestWorkerRetriesOnTransientError:
    """Tests for worker retry/backoff logic on transient database errors."""

    def test_worker_retries_on_transient_error(self, worker: IssueWorker) -> None:
        """Mock get_next_issue to fail with TransientDatabaseError twice, then succeed.

        Verify worker retries with backoff and does not flip to "failed".
        """
        from rouge.worker.worker_artifact import WorkerArtifact

        # Set up ready artifact
        ready_artifact = WorkerArtifact(
            worker_id="test-worker",
            state="ready",
            current_issue_id=None,
            current_adw_id=None,
        )

        call_count = [0]
        transient_error = TransientDatabaseError(
            "Database connection timeout", original_error=httpx.ReadTimeout("timeout")
        )

        def mock_get_next_issue(worker_id, logger):
            call_count[0] += 1
            if call_count[0] <= 2:
                # Fail first 2 attempts
                raise transient_error
            else:
                # Succeed on 3rd attempt
                worker.running = False
                return (123, "Test issue", "pending", "main", None)

        with patch("rouge.worker.worker.read_worker_artifact", return_value=ready_artifact):
            with patch("rouge.worker.worker.get_next_issue", side_effect=mock_get_next_issue):
                with patch("rouge.worker.worker.reset_client") as mock_reset:
                    with patch("rouge.worker.worker.time.sleep") as mock_sleep:
                        with patch.object(worker, "execute_workflow") as mock_execute:
                            worker.run()

                            # Should have retried and eventually called execute_workflow
                            assert call_count[0] == 3
                            mock_execute.assert_called_once_with(
                                123, "Test issue", "pending", "main", adw_id=None
                            )

                            # Should have called reset_client before each retry (2 times)
                            assert mock_reset.call_count >= 2

                            # Should have slept for backoff between retries (2 times)
                            assert mock_sleep.call_count >= 2

    def test_worker_skips_poll_after_exhausted_retries(self, worker: IssueWorker) -> None:
        """Mock get_next_issue to always fail with TransientDatabaseError.

        Verify worker skips cycle after max retries without halting.
        """
        from rouge.worker.worker_artifact import WorkerArtifact

        ready_artifact = WorkerArtifact(
            worker_id="test-worker",
            state="ready",
            current_issue_id=None,
            current_adw_id=None,
        )

        call_count = [0]
        poll_cycles = [0]
        transient_error = TransientDatabaseError(
            "Database connection timeout", original_error=httpx.ReadTimeout("timeout")
        )

        def mock_get_next_issue(worker_id, logger):
            call_count[0] += 1
            # Stop after two complete poll cycles (3 attempts each = 6 total)
            if call_count[0] >= worker.config.db_retries * 2:
                worker.running = False
            raise transient_error

        def mock_sleep(seconds):
            # Track poll cycles by counting sleep calls (happens after exhausted retries)
            if seconds == worker.config.poll_interval:
                poll_cycles[0] += 1

        with patch("rouge.worker.worker.read_worker_artifact", return_value=ready_artifact):
            with patch("rouge.worker.worker.get_next_issue", side_effect=mock_get_next_issue):
                with patch("rouge.worker.worker.reset_client"):
                    with patch("rouge.worker.worker.time.sleep", side_effect=mock_sleep):
                        with patch.object(worker, "execute_workflow") as mock_execute:
                            worker.run()

                            # Should have attempted db_retries attempts in two poll cycles
                            assert call_count[0] == worker.config.db_retries * 2

                            # Should complete two poll cycles (sleep twice after retries)
                            assert poll_cycles[0] == 2

                            # Should NOT have executed any workflow
                            mock_execute.assert_not_called()

                            # Worker should still be running=False (normal shutdown, not crashed)
                            assert worker.running is False

    def test_worker_applies_backoff_between_retries(self, worker: IssueWorker) -> None:
        """Verify worker applies exponential backoff with jitter between retries."""
        from rouge.worker.worker_artifact import WorkerArtifact

        ready_artifact = WorkerArtifact(
            worker_id="test-worker",
            state="ready",
            current_issue_id=None,
            current_adw_id=None,
        )

        call_count = [0]
        transient_error = TransientDatabaseError(
            "Database connection timeout", original_error=httpx.ReadTimeout("timeout")
        )

        def mock_get_next_issue(worker_id, logger):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise transient_error
            else:
                worker.running = False
                return None

        sleep_calls = []

        def mock_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("rouge.worker.worker.read_worker_artifact", return_value=ready_artifact):
            with patch("rouge.worker.worker.get_next_issue", side_effect=mock_get_next_issue):
                with patch("rouge.worker.worker.reset_client"):
                    with patch("rouge.worker.worker.time.sleep", side_effect=mock_sleep):
                        worker.run()

                        # Should have called sleep for backoff (at least 2 times for 2 retries)
                        assert len(sleep_calls) >= 2

                        # Each backoff sleep should be in the range of 0.5x to 1.5x the base backoff
                        base_backoff = worker.config.db_backoff_ms / 1000.0
                        for sleep_time in sleep_calls[:2]:  # Check first 2 backoff sleeps
                            assert 0.5 * base_backoff <= sleep_time <= 1.5 * base_backoff


class TestWorkerContinuesAfterTransientError:
    """Tests verifying worker artifact state management during database errors."""

    def test_worker_continues_after_transient_error(self, worker: IssueWorker) -> None:
        """Verify worker artifact remains in "ready" state after transient error.

        The worker should not transition to "failed" state for transient database
        errors, as these are expected to be temporary and resolved through retries.
        """
        from rouge.worker.worker_artifact import WorkerArtifact

        ready_artifact = WorkerArtifact(
            worker_id="test-worker",
            state="ready",
            current_issue_id=None,
            current_adw_id=None,
        )

        call_count = [0]
        transient_error = TransientDatabaseError(
            "Database connection timeout", original_error=httpx.ReadTimeout("timeout")
        )

        def mock_get_next_issue(worker_id, logger):
            call_count[0] += 1
            if call_count[0] == 1:
                raise transient_error
            else:
                worker.running = False
                return None

        artifact_writes = []

        def capture_write(artifact):
            artifact_writes.append(artifact.model_copy(deep=True))

        with patch("rouge.worker.worker.read_worker_artifact", return_value=ready_artifact):
            with patch("rouge.worker.worker.get_next_issue", side_effect=mock_get_next_issue):
                with patch("rouge.worker.worker.reset_client"):
                    with patch("rouge.worker.worker.time.sleep"):
                        with patch(
                            "rouge.worker.worker_artifact.write_worker_artifact",
                            side_effect=capture_write,
                        ):
                            worker.run()

                            # Worker artifact should not have transitioned to failed
                            # (no writes should have occurred for transient errors)
                            for artifact in artifact_writes:
                                assert artifact.state != "failed", (
                                    "Worker artifact should not transition to failed state "
                                    "for transient database errors"
                                )

    def test_worker_transitions_to_failed_on_workflow_failure(self, worker: IssueWorker) -> None:
        """Verify worker artifact transitions to "failed" on workflow failure, not DB errors.

        This test ensures we distinguish between database errors (which should not
        mark the worker as failed) and actual workflow execution failures (which should).
        """
        from rouge.worker.worker_artifact import WorkerArtifact

        ready_artifact = WorkerArtifact(
            worker_id="test-worker",
            state="ready",
            current_issue_id=None,
            current_adw_id=None,
        )

        call_count = [0]

        def mock_get_next_issue(worker_id, logger):
            call_count[0] += 1
            if call_count[0] == 1:
                return (123, "Test issue", "pending", "main", None)
            else:
                worker.running = False
                return None

        artifact_writes = []

        def capture_write(artifact):
            artifact_writes.append(artifact.model_copy(deep=True))
            if artifact.state == "failed":
                worker.running = False

        # Mock subprocess to fail
        mock_result = Mock()
        mock_result.returncode = 1

        with patch("rouge.worker.worker.read_worker_artifact", return_value=ready_artifact):
            with patch("rouge.worker.worker.get_next_issue", side_effect=mock_get_next_issue):
                with patch("rouge.worker.worker.time.sleep"):
                    with patch("subprocess.run", return_value=mock_result):
                        with patch("rouge.worker.worker.update_issue_status"):
                            with patch("rouge.worker.worker.make_adw_id", return_value="test-adw"):
                                with patch(
                                    "rouge.worker.worker_artifact.write_worker_artifact",
                                    side_effect=capture_write,
                                ):
                                    worker.run()

                                # Should have transitioned to failed state
                                assert any(
                                    a.state == "failed" for a in artifact_writes
                                ), "Worker should transition to failed on workflow failure"


class TestJitteredBackoff:
    """Tests for jittered backoff delay to prevent thundering herd."""

    def test_jittered_backoff_within_bounds(self, worker: IssueWorker) -> None:
        """Verify backoff delay includes ±20% random jitter."""
        from rouge.worker.worker_artifact import WorkerArtifact

        ready_artifact = WorkerArtifact(
            worker_id="test-worker",
            state="ready",
            current_issue_id=None,
            current_adw_id=None,
        )

        call_count = [0]
        transient_error = TransientDatabaseError(
            "Database connection timeout", original_error=httpx.ReadTimeout("timeout")
        )

        def mock_get_next_issue(worker_id, logger):
            call_count[0] += 1
            if call_count[0] <= worker.config.db_retries - 1:
                raise transient_error
            else:
                worker.running = False
                return None

        sleep_calls = []

        def mock_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("rouge.worker.worker.read_worker_artifact", return_value=ready_artifact):
            with patch("rouge.worker.worker.get_next_issue", side_effect=mock_get_next_issue):
                with patch("rouge.worker.worker.reset_client"):
                    with patch("rouge.worker.worker.time.sleep", side_effect=mock_sleep):
                        worker.run()

                        # Extract only backoff sleeps (not poll interval sleeps)
                        base_backoff_s = worker.config.db_backoff_ms / 1000.0
                        poll_interval = worker.config.poll_interval
                        backoff_sleeps = [s for s in sleep_calls if s < poll_interval]

                        # Should have at least 2 backoff sleeps for db_retries=3 (2 retries)
                        assert len(backoff_sleeps) >= 2

                        # Each backoff sleep should be within ±20% of base backoff
                        for sleep_time in backoff_sleeps:
                            assert 0.8 * base_backoff_s <= sleep_time <= 1.2 * base_backoff_s, (
                                f"Backoff sleep {sleep_time}s not within ±20% jitter "
                                f"of base {base_backoff_s}s"
                            )

    def test_jittered_backoff_prevents_thundering_herd(self, worker: IssueWorker) -> None:
        """Verify that multiple retry attempts use different jittered delays.

        This test ensures the random jitter is actually being applied, not just
        using a constant backoff delay every time.
        """
        from rouge.worker.worker_artifact import WorkerArtifact

        ready_artifact = WorkerArtifact(
            worker_id="test-worker",
            state="ready",
            current_issue_id=None,
            current_adw_id=None,
        )

        # Set up to fail multiple times to get multiple backoff samples
        call_count = [0]
        transient_error = TransientDatabaseError(
            "Database connection timeout", original_error=httpx.ReadTimeout("timeout")
        )

        def mock_get_next_issue(worker_id, logger):
            call_count[0] += 1
            # Fail enough times to get 5+ backoff samples across 2 poll cycles
            if call_count[0] < 6:
                raise transient_error
            else:
                worker.running = False
                return None

        sleep_calls = []

        def mock_sleep(seconds):
            sleep_calls.append(seconds)

        with patch("rouge.worker.worker.read_worker_artifact", return_value=ready_artifact):
            with patch("rouge.worker.worker.get_next_issue", side_effect=mock_get_next_issue):
                with patch("rouge.worker.worker.reset_client"):
                    with patch("rouge.worker.worker.time.sleep", side_effect=mock_sleep):
                        # Fix random seed to ensure test is deterministic
                        with patch("random.uniform") as mock_random:
                            # Return different jitter values for each call
                            mock_random.side_effect = [-0.15, 0.12, -0.08, 0.18, -0.05]
                            worker.run()

                            # Verify random.uniform was called with correct jitter bounds (±20%)
                            for call in mock_random.call_args_list:
                                args = call[0]
                                assert args == (
                                    -0.2,
                                    0.2,
                                ), f"Expected jitter bounds (-0.2, 0.2), got {args}"

                            # Verify we got different jittered values
                            poll_interval = worker.config.poll_interval
                            backoff_sleeps = [s for s in sleep_calls if s < poll_interval]

                            # Should have multiple backoff sleeps
                            assert len(backoff_sleeps) >= 4

                            # With different jitter values, the sleep times should differ
                            unique_sleep_times = set(backoff_sleeps)
                            assert len(unique_sleep_times) > 1, (
                                "Expected different jittered backoff delays, "
                                f"got all {backoff_sleeps[0]}s"
                            )


class TestTransientDatabaseError:
    """Tests for the TransientDatabaseError exception class."""

    def test_transient_error_preserves_original_error(self) -> None:
        """Verify TransientDatabaseError preserves the original exception."""
        original = httpx.ReadTimeout("Connection timeout")
        error = TransientDatabaseError("Database error", original_error=original)

        assert error.message == "Database error"
        assert error.original_error is original
        assert isinstance(error.original_error, httpx.ReadTimeout)

    def test_transient_error_string_representation(self) -> None:
        """Verify TransientDatabaseError has a useful string representation."""
        original = httpx.ConnectTimeout("Connect timeout")
        error = TransientDatabaseError("Database connection failed", original_error=original)

        error_str = str(error)
        assert "Database connection failed" in error_str
        assert "ConnectTimeout" in error_str
        assert "Connect timeout" in error_str
