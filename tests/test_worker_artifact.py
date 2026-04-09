"""Unit tests for WorkerArtifact and worker artifact persistence."""

import json
import logging
from datetime import datetime
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from rouge.worker.worker_artifact import (
    WorkerArtifact,
    read_worker_artifact,
    transition_worker_artifact,
    write_worker_artifact,
)


class TestWorkerArtifactModel:
    """Tests for WorkerArtifact model definition."""

    def test_artifact_creation_ready_state(self):
        """Test WorkerArtifact creation with ready state."""
        artifact = WorkerArtifact(
            worker_id="worker-1",
            state="ready",
        )

        assert artifact.worker_id == "worker-1"
        assert artifact.state == "ready"
        assert artifact.current_issue_id is None
        assert artifact.current_adw_id is None
        assert isinstance(artifact.updated_at, datetime)

    def test_artifact_creation_working_state(self):
        """Test WorkerArtifact creation with working state and issue ID."""
        artifact = WorkerArtifact(
            worker_id="worker-2",
            state="working",
            current_issue_id=123,
            current_adw_id="adw-abc123",
        )

        assert artifact.worker_id == "worker-2"
        assert artifact.state == "working"
        assert artifact.current_issue_id == 123
        assert artifact.current_adw_id == "adw-abc123"

    def test_artifact_creation_failed_state(self):
        """Test WorkerArtifact creation with failed state."""
        artifact = WorkerArtifact(
            worker_id="worker-3",
            state="failed",
            current_issue_id=456,
            current_adw_id="adw-def456",
        )

        assert artifact.worker_id == "worker-3"
        assert artifact.state == "failed"
        assert artifact.current_issue_id == 456
        assert artifact.current_adw_id == "adw-def456"

    def test_worker_id_validation(self):
        """Test worker_id field validation."""
        # Valid worker ID
        artifact = WorkerArtifact(worker_id="valid-worker-id", state="ready")
        assert artifact.worker_id == "valid-worker-id"

    def test_empty_worker_id_fails_pydantic(self):
        """Test that empty worker_id fails Pydantic validation."""
        with pytest.raises(ValueError, match="at least 1 character"):
            WorkerArtifact(worker_id="", state="ready")

    @pytest.mark.parametrize(
        "invalid_id",
        [
            " ",  # single space
            "\t",  # tab character
            "\n",  # newline character
        ],
        ids=["space", "tab", "newline"],
    )
    def test_whitespace_worker_id_fails_path_validation(self, invalid_id):
        """Test that whitespace-only worker_id fails path validation."""
        from rouge.worker.worker_artifact import _get_worker_artifact_path

        with pytest.raises(ValueError, match="empty or whitespace-only"):
            _get_worker_artifact_path(invalid_id)

    @pytest.mark.parametrize(
        "invalid_id,expected_match",
        [
            ("/", "disallowed characters"),  # forward slash
            ("\\", "disallowed characters"),  # backslash
            ("a/b", "disallowed characters"),  # path separator in middle
            ("../etc", "disallowed characters"),  # path traversal attempt
        ],
        ids=["forward_slash", "backslash", "path_in_middle", "path_traversal"],
    )
    def test_path_separator_worker_id_fails(self, invalid_id, expected_match):
        """Test that worker_id with path separators fails validation."""
        from rouge.worker.worker_artifact import _get_worker_artifact_path

        with pytest.raises(ValueError, match=expected_match):
            _get_worker_artifact_path(invalid_id)

    def test_none_worker_id_fails(self):
        """Test that None worker_id fails with ValidationError."""
        with pytest.raises(ValidationError, match="Input should be a valid string"):
            WorkerArtifact(worker_id=None, state="ready")  # type: ignore

    def test_state_validation(self):
        """Test state field only accepts valid literals."""
        # Valid states
        artifact1 = WorkerArtifact(worker_id="w1", state="ready")
        assert artifact1.state == "ready"

        artifact2 = WorkerArtifact(worker_id="w2", state="working")
        assert artifact2.state == "working"

        artifact3 = WorkerArtifact(worker_id="w3", state="failed")
        assert artifact3.state == "failed"

    def test_invalid_state_fails(self):
        """Test that invalid state value fails validation."""
        with pytest.raises(ValueError):
            WorkerArtifact(worker_id="w1", state="invalid")  # type: ignore


class TestWorkerArtifactSerialization:
    """Tests for WorkerArtifact JSON serialization/deserialization."""

    def test_artifact_round_trip_ready(self):
        """Test artifact can be serialized and deserialized in ready state."""
        original = WorkerArtifact(
            worker_id="rt-worker-1",
            state="ready",
        )

        json_str = original.model_dump_json()
        restored = WorkerArtifact.model_validate_json(json_str)

        assert restored.worker_id == "rt-worker-1"
        assert restored.state == "ready"
        assert restored.current_issue_id is None
        assert restored.current_adw_id is None

    def test_artifact_round_trip_working(self):
        """Test artifact serialization in working state."""
        original = WorkerArtifact(
            worker_id="rt-worker-2",
            state="working",
            current_issue_id=789,
            current_adw_id="adw-xyz789",
        )

        json_str = original.model_dump_json()
        restored = WorkerArtifact.model_validate_json(json_str)

        assert restored.worker_id == "rt-worker-2"
        assert restored.state == "working"
        assert restored.current_issue_id == 789
        assert restored.current_adw_id == "adw-xyz789"

    def test_json_structure_is_valid(self):
        """Test artifact JSON has expected structure."""
        artifact = WorkerArtifact(
            worker_id="json-worker",
            state="working",
            current_issue_id=111,
            current_adw_id="adw-test",
        )

        json_str = artifact.model_dump_json(indent=2)
        parsed = json.loads(json_str)

        assert "worker_id" in parsed
        assert "state" in parsed
        assert "current_issue_id" in parsed
        assert "current_adw_id" in parsed
        assert "updated_at" in parsed
        assert parsed["worker_id"] == "json-worker"
        assert parsed["state"] == "working"
        assert parsed["current_issue_id"] == 111
        assert parsed["current_adw_id"] == "adw-test"

    def test_json_with_none_values(self):
        """Test artifact JSON correctly handles None values."""
        artifact = WorkerArtifact(
            worker_id="none-worker",
            state="ready",
        )

        json_str = artifact.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["current_issue_id"] is None
        assert parsed["current_adw_id"] is None


class TestWorkerArtifactStateTransitions:
    """Tests for WorkerArtifact state transitions."""

    def test_ready_to_working_transition(self):
        """Test transitioning from ready to working state."""
        artifact = WorkerArtifact(worker_id="w1", state="ready")

        # Simulate state transition
        artifact.state = "working"
        artifact.current_issue_id = 123
        artifact.current_adw_id = "adw-123"

        assert artifact.state == "working"
        assert artifact.current_issue_id == 123
        assert artifact.current_adw_id == "adw-123"

    def test_working_to_ready_transition(self):
        """Test transitioning from working back to ready state."""
        artifact = WorkerArtifact(
            worker_id="w2",
            state="working",
            current_issue_id=456,
            current_adw_id="adw-456",
        )

        # Simulate completion
        artifact.state = "ready"
        artifact.current_issue_id = None
        artifact.current_adw_id = None

        assert artifact.state == "ready"
        assert artifact.current_issue_id is None
        assert artifact.current_adw_id is None

    def test_working_to_failed_transition(self):
        """Test transitioning from working to failed state."""
        artifact = WorkerArtifact(
            worker_id="w3",
            state="working",
            current_issue_id=789,
            current_adw_id="adw-789",
        )

        # Simulate failure
        artifact.state = "failed"
        # Issue info typically retained on failure

        assert artifact.state == "failed"
        assert artifact.current_issue_id == 789
        assert artifact.current_adw_id == "adw-789"

    def test_failed_to_ready_transition(self):
        """Test transitioning from failed back to ready state."""
        artifact = WorkerArtifact(
            worker_id="w4",
            state="failed",
            current_issue_id=999,
            current_adw_id="adw-999",
        )

        # Simulate reset
        artifact.state = "ready"
        artifact.current_issue_id = None
        artifact.current_adw_id = None

        assert artifact.state == "ready"
        assert artifact.current_issue_id is None
        assert artifact.current_adw_id is None


class TestWriteWorkerArtifact:
    """Tests for write_worker_artifact function."""

    @patch("rouge.worker.worker_artifact._get_worker_artifact_path")
    def test_write_worker_artifact_creates_directory(self, mock_get_path, tmp_path):
        """Test write_worker_artifact creates worker directory."""
        worker_dir = tmp_path / "workers" / "test-worker"
        artifact_path = worker_dir / "state.json"
        mock_get_path.return_value = artifact_path

        artifact = WorkerArtifact(
            worker_id="test-worker",
            state="ready",
        )

        write_worker_artifact(artifact)

        assert worker_dir.exists()
        assert artifact_path.exists()

    @patch("rouge.worker.worker_artifact._get_worker_artifact_path")
    def test_write_worker_artifact_content(self, mock_get_path, tmp_path):
        """Test write_worker_artifact writes correct content."""
        artifact_path = tmp_path / "state.json"
        mock_get_path.return_value = artifact_path

        artifact = WorkerArtifact(
            worker_id="content-worker",
            state="working",
            current_issue_id=123,
            current_adw_id="adw-test",
        )

        write_worker_artifact(artifact)

        content = json.loads(artifact_path.read_text())
        assert content["worker_id"] == "content-worker"
        assert content["state"] == "working"
        assert content["current_issue_id"] == 123
        assert content["current_adw_id"] == "adw-test"

    @patch("rouge.worker.worker_artifact._get_worker_artifact_path")
    def test_write_worker_artifact_overwrites_existing(self, mock_get_path, tmp_path):
        """Test write_worker_artifact overwrites existing artifact."""
        artifact_path = tmp_path / "state.json"
        mock_get_path.return_value = artifact_path

        # Write first version
        artifact1 = WorkerArtifact(
            worker_id="overwrite-worker",
            state="ready",
        )
        write_worker_artifact(artifact1)

        # Write second version
        artifact2 = WorkerArtifact(
            worker_id="overwrite-worker",
            state="working",
            current_issue_id=999,
            current_adw_id="adw-999",
        )
        write_worker_artifact(artifact2)

        # Verify second version is persisted
        content = json.loads(artifact_path.read_text())
        assert content["state"] == "working"
        assert content["current_issue_id"] == 999

    @patch("rouge.worker.worker_artifact.tempfile.mkstemp")
    @patch("rouge.worker.worker_artifact._get_worker_artifact_path")
    @patch("rouge.worker.worker_artifact.logger")
    def test_write_worker_artifact_handles_failure_gracefully(
        self, mock_logger, mock_get_path, mock_mkstemp, tmp_path
    ):
        """Test write_worker_artifact logs but doesn't raise on failure."""
        artifact_path = tmp_path / "state.json"
        mock_get_path.return_value = artifact_path

        # Simulate write failure by making mkstemp raise OSError
        mock_mkstemp.side_effect = OSError("Permission denied")

        artifact = WorkerArtifact(
            worker_id="fail-worker",
            state="ready",
        )

        # Should not raise, but should log warning
        write_worker_artifact(artifact)

        # Verify warning was logged
        mock_logger.warning.assert_called()


class TestReadWorkerArtifact:
    """Tests for read_worker_artifact function."""

    @patch("rouge.worker.worker_artifact._get_worker_artifact_path")
    def test_read_worker_artifact_success(self, mock_get_path, tmp_path):
        """Test read_worker_artifact reads existing artifact."""
        artifact_path = tmp_path / "state.json"
        mock_get_path.return_value = artifact_path

        # Write artifact first
        original = WorkerArtifact(
            worker_id="read-worker",
            state="working",
            current_issue_id=555,
            current_adw_id="adw-555",
        )
        artifact_path.write_text(original.model_dump_json())

        # Read it back
        restored = read_worker_artifact("read-worker")

        assert restored is not None
        assert restored.worker_id == "read-worker"
        assert restored.state == "working"
        assert restored.current_issue_id == 555
        assert restored.current_adw_id == "adw-555"

    @patch("rouge.worker.worker_artifact._get_worker_artifact_path")
    def test_read_worker_artifact_not_found(self, mock_get_path, tmp_path):
        """Test read_worker_artifact returns None when file doesn't exist."""
        artifact_path = tmp_path / "nonexistent.json"
        mock_get_path.return_value = artifact_path

        result = read_worker_artifact("missing-worker")

        assert result is None

    @patch("rouge.worker.worker_artifact._get_worker_artifact_path")
    @patch("rouge.worker.worker_artifact.logger")
    def test_read_worker_artifact_corrupted_json(self, mock_logger, mock_get_path, tmp_path):
        """Test read_worker_artifact returns None for corrupted JSON."""
        artifact_path = tmp_path / "corrupted.json"
        mock_get_path.return_value = artifact_path

        # Write invalid JSON
        artifact_path.write_text("{ invalid json }")

        result = read_worker_artifact("corrupted-worker")

        assert result is None
        mock_logger.warning.assert_called()

    @patch("rouge.worker.worker_artifact._get_worker_artifact_path")
    @patch("rouge.worker.worker_artifact.logger")
    def test_read_worker_artifact_invalid_data(self, mock_logger, mock_get_path, tmp_path):
        """Test read_worker_artifact returns None for invalid artifact data."""
        artifact_path = tmp_path / "invalid.json"
        mock_get_path.return_value = artifact_path

        # Write valid JSON but missing required fields
        artifact_path.write_text('{"worker_id": "test"}')

        result = read_worker_artifact("invalid-worker")

        assert result is None
        mock_logger.warning.assert_called()


class TestWorkerArtifactPath:
    """Tests for worker artifact path generation."""

    @patch("rouge.core.paths.RougePaths.get_base_dir")
    def test_get_worker_artifact_path(self, mock_get_base_dir, tmp_path):
        """Test _get_worker_artifact_path generates correct path."""
        from rouge.worker.worker_artifact import _get_worker_artifact_path

        mock_get_base_dir.return_value = tmp_path

        path = _get_worker_artifact_path("test-worker-id")

        expected = tmp_path / "workers" / "test-worker-id" / "state.json"
        assert path == expected

    @patch("rouge.core.paths.RougePaths.get_base_dir")
    def test_worker_artifact_path_isolation(self, mock_get_base_dir, tmp_path):
        """Test each worker gets isolated directory."""
        from rouge.worker.worker_artifact import _get_worker_artifact_path

        mock_get_base_dir.return_value = tmp_path

        path1 = _get_worker_artifact_path("worker-1")
        path2 = _get_worker_artifact_path("worker-2")

        # Different workers get different directories
        assert path1.parent != path2.parent
        assert path1.parent.name == "worker-1"
        assert path2.parent.name == "worker-2"


class TestTransitionWorkerArtifactLogging:
    """Tests for transition_worker_artifact INFO logging."""

    @patch("rouge.worker.worker_artifact.write_worker_artifact")
    def test_transition_worker_artifact_logs_info(self, _mock_write, caplog):
        """Test that transition_worker_artifact emits an INFO log with expected format."""
        artifact = WorkerArtifact(worker_id="w1", state="working")
        with caplog.at_level(logging.INFO):
            transition_worker_artifact(artifact, "ready", clear_issue=True)
        assert "Worker w1 transitioned from 'working' to 'ready' (issue cleared)" in caplog.text

    @patch("rouge.worker.worker_artifact.write_worker_artifact")
    def test_transition_worker_artifact_logs_without_clear_issue(self, _mock_write, caplog):
        """Test log message omits '(issue cleared)' when clear_issue is False."""
        artifact = WorkerArtifact(worker_id="w2", state="ready")
        with caplog.at_level(logging.INFO):
            transition_worker_artifact(artifact, "working")
        assert "Worker w2 transitioned from 'ready' to 'working'" in caplog.text
        assert "(issue cleared)" not in caplog.text

    @patch("rouge.worker.worker_artifact.write_worker_artifact")
    def test_transition_worker_artifact_updates_state(self, _mock_write):
        """Test that transition_worker_artifact actually updates the artifact state."""
        artifact = WorkerArtifact(
            worker_id="w3",
            state="working",
            current_issue_id=42,
            current_adw_id="adw-42",
        )
        transition_worker_artifact(artifact, "ready", clear_issue=True)
        assert artifact.state == "ready"
        assert artifact.current_issue_id is None
        assert artifact.current_adw_id is None
