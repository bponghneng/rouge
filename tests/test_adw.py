"""Tests for CAPE ADW functionality."""

from rouge.adw.adw import execute_adw_workflow


def test_execute_adw_workflow_generates_id(monkeypatch):
    """Workflow should generate an ADW ID and return execution status."""
    calls = {}

    monkeypatch.setattr("rouge.adw.adw.make_adw_id", lambda: "generated-id")

    def fake_execute(issue_id, adw_id):
        calls["args"] = (issue_id, adw_id)
        return True

    monkeypatch.setattr("rouge.adw.adw.execute_workflow", fake_execute)

    success, workflow_id = execute_adw_workflow(123)

    assert success is True
    assert workflow_id == "generated-id"
    assert calls["args"] == (123, "generated-id")


def test_execute_adw_workflow_uses_provided_values(monkeypatch):
    """Workflow should respect caller-provided workflow ID."""
    monkeypatch.setattr("rouge.adw.adw.execute_workflow", lambda issue_id, adw_id: False)

    success, workflow_id = execute_adw_workflow(456, adw_id="custom-id")

    assert success is False
    assert workflow_id == "custom-id"


def test_execute_adw_workflow_patch_mode(monkeypatch):
    """Patch workflow should use patch pipeline."""
    calls = {}

    def fake_execute(issue_id, adw_id, pipeline=None):
        calls["args"] = (issue_id, adw_id, pipeline)
        return True

    monkeypatch.setattr("rouge.adw.adw.execute_workflow", fake_execute)
    monkeypatch.setattr("rouge.adw.adw.get_patch_pipeline", lambda: "patch-pipeline")

    success, workflow_id = execute_adw_workflow(789, adw_id="any-workflow-id", patch_mode=True)

    assert success is True
    assert workflow_id == "any-workflow-id"
    assert calls["args"] == (789, "any-workflow-id", "patch-pipeline")
