"""Tests for CAPE ADW functionality."""

import pytest

from rouge.adw.adw import execute_adw_workflow


def test_execute_adw_workflow_generates_id(monkeypatch):
    """Workflow should accept an ADW ID and return execution status."""
    calls = {}

    monkeypatch.setattr("rouge.adw.adw.get_pipeline_for_type", lambda wf_type: "main-pipeline")

    def fake_execute(issue_id, adw_id, *, pipeline=None, resume_from=None, pipeline_type=None):
        calls["args"] = (issue_id, adw_id)
        calls["pipeline"] = pipeline
        calls["resume_from"] = resume_from
        calls["pipeline_type"] = pipeline_type
        return True

    monkeypatch.setattr("rouge.adw.adw.execute_workflow", fake_execute)

    success, workflow_id = execute_adw_workflow("generated-id", 123)

    assert success is True
    assert workflow_id == "generated-id"
    assert calls["args"] == (123, "generated-id")
    assert calls["pipeline"] == "main-pipeline"
    assert calls["resume_from"] is None
    assert calls["pipeline_type"] == "main"


def test_execute_adw_workflow_uses_provided_values(monkeypatch):
    """Workflow should respect caller-provided workflow ID."""
    calls = {}

    monkeypatch.setattr("rouge.adw.adw.get_pipeline_for_type", lambda wf_type: "main-pipeline")

    def fake_execute(issue_id, adw_id, *, pipeline=None, resume_from=None, pipeline_type=None):
        calls["resume_from"] = resume_from
        calls["pipeline_type"] = pipeline_type
        return False

    monkeypatch.setattr("rouge.adw.adw.execute_workflow", fake_execute)

    success, workflow_id = execute_adw_workflow("custom-id", 456)

    assert success is False
    assert workflow_id == "custom-id"
    assert calls["resume_from"] is None
    assert calls["pipeline_type"] == "main"


def test_execute_adw_workflow_patch_type(monkeypatch):
    """Patch workflow should use patch pipeline via workflow registry."""
    calls = {}
    registry_calls = {}

    def fake_get_pipeline(wf_type):
        registry_calls["workflow_type"] = wf_type
        return "patch-pipeline"

    def fake_execute(issue_id, adw_id, *, pipeline=None, resume_from=None, pipeline_type=None):
        calls["args"] = (issue_id, adw_id)
        calls["pipeline"] = pipeline
        calls["resume_from"] = resume_from
        calls["pipeline_type"] = pipeline_type
        return True

    monkeypatch.setattr("rouge.adw.adw.execute_workflow", fake_execute)
    monkeypatch.setattr("rouge.adw.adw.get_pipeline_for_type", fake_get_pipeline)

    success, workflow_id = execute_adw_workflow(
        "any-workflow-id", 789, workflow_type="patch"
    )

    assert success is True
    assert workflow_id == "any-workflow-id"
    assert registry_calls["workflow_type"] == "patch"
    assert calls["args"] == (789, "any-workflow-id")
    assert calls["pipeline"] == "patch-pipeline"
    assert calls["resume_from"] is None
    assert calls["pipeline_type"] == "patch"


def test_execute_adw_workflow_codereview_type(monkeypatch) -> None:
    """Codereview workflow should use codereview pipeline via workflow registry."""
    calls = {}
    registry_calls = {}

    def fake_get_pipeline(wf_type):
        registry_calls["workflow_type"] = wf_type
        return "codereview-pipeline"

    def fake_execute(issue_id, adw_id, *, pipeline=None, resume_from=None, pipeline_type=None):
        calls["args"] = (issue_id, adw_id)
        calls["pipeline"] = pipeline
        calls["resume_from"] = resume_from
        calls["pipeline_type"] = pipeline_type
        return True

    monkeypatch.setattr("rouge.adw.adw.execute_workflow", fake_execute)
    monkeypatch.setattr("rouge.adw.adw.get_pipeline_for_type", fake_get_pipeline)

    success, workflow_id = execute_adw_workflow(
        "codereview-workflow-id", 123, workflow_type="codereview"
    )

    assert success is True, "expected success to be True"
    assert workflow_id == "codereview-workflow-id", "unexpected workflow_id"
    assert registry_calls["workflow_type"] == "codereview", "registry workflow_type mismatch"
    assert calls["args"] == (123, "codereview-workflow-id"), "pipeline call args mismatch"
    assert calls["pipeline"] == "codereview-pipeline", "pipeline name mismatch"
    assert calls["resume_from"] is None
    assert calls["pipeline_type"] == "codereview"


def test_execute_adw_workflow_main_without_issue_id_raises(monkeypatch):
    """workflow_type='main' with issue_id=None should raise ValueError."""
    with pytest.raises(ValueError, match="issue_id is required"):
        execute_adw_workflow("test-adw-id", issue_id=None, workflow_type="main")


def test_execute_adw_workflow_unknown_type_raises(monkeypatch):
    """Unknown workflow type should raise ValueError with available types."""

    def fake_get_pipeline(wf_type):
        raise ValueError(f"Unknown workflow type '{wf_type}'. Available types: main, patch")

    monkeypatch.setattr("rouge.adw.adw.get_pipeline_for_type", fake_get_pipeline)

    with pytest.raises(ValueError, match="Unknown workflow type 'bogus'"):
        execute_adw_workflow("test-adw-id", 999, workflow_type="bogus")
