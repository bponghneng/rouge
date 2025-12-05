"""Tests for CAPE ADW functionality."""

from unittest.mock import MagicMock

from cape.adw.adw import execute_adw_workflow


def test_execute_adw_workflow_generates_id(monkeypatch):
    """Workflow should generate an ADW ID and return execution status."""
    mock_logger = MagicMock()
    calls = {}

    monkeypatch.setattr("cape.adw.adw.make_adw_id", lambda: "generated-id")
    monkeypatch.setattr("cape.adw.adw.setup_logger", lambda *args, **kwargs: mock_logger)

    def fake_execute(issue_id, adw_id, logger):
        calls["args"] = (issue_id, adw_id, logger)
        return True

    monkeypatch.setattr("cape.adw.adw.execute_workflow", fake_execute)

    success, workflow_id = execute_adw_workflow(123)

    assert success is True
    assert workflow_id == "generated-id"
    assert calls["args"] == (123, "generated-id", mock_logger)


def test_execute_adw_workflow_uses_provided_values(monkeypatch):
    """Workflow should respect caller-provided workflow ID and logger."""
    provided_logger = MagicMock()

    monkeypatch.setattr("cape.adw.adw.execute_workflow", lambda issue_id, adw_id, logger: False)

    success, workflow_id = execute_adw_workflow(456, adw_id="custom-id", logger=provided_logger)

    assert success is False
    assert workflow_id == "custom-id"
