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


def test_execute_adw_workflow_code_review_routes_to_loop(monkeypatch):
    """workflow_type='codereview' should delegate to execute_code_review_loop."""
    calls = {}

    def fake_loop(workflow_id, config=None):
        calls["args"] = (workflow_id, config)
        return True, workflow_id

    monkeypatch.setattr("rouge.adw.adw.execute_code_review_loop", fake_loop)

    success, workflow_id = execute_adw_workflow(
        issue_id=None,
        adw_id="cr-route-001",
        workflow_type="codereview",
        config={"base_commit": "abc123"},
    )

    assert success is True, "expected success to be True for code review workflow"
    assert (
        workflow_id == "cr-route-001"
    ), f"unexpected workflow_id: expected 'cr-route-001', got '{workflow_id}'"
    assert calls["args"] == (
        "cr-route-001",
        {"base_commit": "abc123"},
    ), f"unexpected call arguments: {calls['args']}"


def test_execute_adw_workflow_main_without_issue_id_raises(monkeypatch):
    """workflow_type='main' with issue_id=None should raise ValueError."""
    with pytest.raises(ValueError, match="issue_id is required"):
        execute_adw_workflow(issue_id=None, workflow_type="main")


def test_execute_adw_workflow_unknown_type_raises(monkeypatch):
    """Unknown workflow type should raise ValueError with available types."""

    def fake_get_pipeline(wf_type):
        raise ValueError(f"Unknown workflow type '{wf_type}'. Available types: main, patch")

    monkeypatch.setattr("rouge.adw.adw.get_pipeline_for_type", fake_get_pipeline)

    with pytest.raises(ValueError, match="Unknown workflow type 'bogus'"):
        execute_adw_workflow(999, workflow_type="bogus")
