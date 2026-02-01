"""Tests for CAPE ADW functionality."""

import pytest

from rouge.adw.adw import execute_adw_workflow


def test_execute_adw_workflow_generates_id(monkeypatch):
    """Workflow should generate an ADW ID and return execution status."""
    calls = {}

    monkeypatch.setattr("rouge.adw.adw.make_adw_id", lambda: "generated-id")
    monkeypatch.setattr("rouge.adw.adw.get_pipeline_for_type", lambda wf_type: "main-pipeline")

    def fake_execute(issue_id, adw_id, *, pipeline=None):
        calls["args"] = (issue_id, adw_id)
        calls["pipeline"] = pipeline
        return True

    monkeypatch.setattr("rouge.adw.adw.execute_workflow", fake_execute)

    success, workflow_id = execute_adw_workflow(123)

    assert success is True
    assert workflow_id == "generated-id"
    assert calls["args"] == (123, "generated-id")
    assert calls["pipeline"] == "main-pipeline"


def test_execute_adw_workflow_uses_provided_values(monkeypatch):
    """Workflow should respect caller-provided workflow ID."""
    monkeypatch.setattr("rouge.adw.adw.get_pipeline_for_type", lambda wf_type: "main-pipeline")

    def fake_execute(issue_id, adw_id, *, pipeline=None):
        return False

    monkeypatch.setattr("rouge.adw.adw.execute_workflow", fake_execute)

    success, workflow_id = execute_adw_workflow(456, adw_id="custom-id")

    assert success is False
    assert workflow_id == "custom-id"


def test_execute_adw_workflow_patch_type(monkeypatch):
    """Patch workflow should use patch pipeline via workflow registry."""
    calls = {}
    registry_calls = {}

    def fake_get_pipeline(wf_type):
        registry_calls["workflow_type"] = wf_type
        return "patch-pipeline"

    def fake_execute(issue_id, adw_id, *, pipeline=None):
        calls["args"] = (issue_id, adw_id)
        calls["pipeline"] = pipeline
        return True

    monkeypatch.setattr("rouge.adw.adw.execute_workflow", fake_execute)
    monkeypatch.setattr("rouge.adw.adw.get_pipeline_for_type", fake_get_pipeline)

    success, workflow_id = execute_adw_workflow(
        789, adw_id="any-workflow-id", workflow_type="patch"
    )

    assert success is True
    assert workflow_id == "any-workflow-id"
    assert registry_calls["workflow_type"] == "patch"
    assert calls["args"] == (789, "any-workflow-id")
    assert calls["pipeline"] == "patch-pipeline"


def test_execute_adw_workflow_unknown_type_raises(monkeypatch):
    """Unknown workflow type should raise ValueError with available types."""

    def fake_get_pipeline(wf_type):
        raise ValueError(f"Unknown workflow type '{wf_type}'. Available types: main, patch")

    monkeypatch.setattr("rouge.adw.adw.get_pipeline_for_type", fake_get_pipeline)

    with pytest.raises(ValueError, match="Unknown workflow type 'bogus'"):
        execute_adw_workflow(999, workflow_type="bogus")
