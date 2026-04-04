"""Tests for workflow registry module."""

from typing import Generator

import pytest

from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult
from rouge.core.workflow.workflow_registry import (
    WorkflowDefinition,
    WorkflowRegistry,
    get_pipeline_for_type,
    get_workflow_registry,
    reset_workflow_registry,
)


class DummyStep(WorkflowStep):
    """Concrete WorkflowStep for testing."""

    def __init__(self, name: str = "dummy") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def run(self, _context: WorkflowContext) -> StepResult:
        return StepResult.ok(None)


@pytest.fixture(autouse=True)
def _reset_workflow_registry_fixture() -> Generator[None, None, None]:
    """Reset the global registry singleton before and after each test."""
    reset_workflow_registry()
    yield
    reset_workflow_registry()


# ---------------------------------------------------------------------------
# TestWorkflowDefinition
# ---------------------------------------------------------------------------


class TestWorkflowDefinition:
    def test_get_pipeline_with_callable(self) -> None:
        """WorkflowDefinition.get_pipeline() delegates to a callable pipeline."""

        def make_pipeline():
            return [DummyStep("from_callable")]

        defn = WorkflowDefinition(
            type_id="test",
            pipeline=make_pipeline,
            description="test workflow",
        )
        pipeline = defn.get_pipeline()

        assert isinstance(pipeline, list)
        assert len(pipeline) == 1
        assert isinstance(pipeline[0], DummyStep)
        assert pipeline[0].name == "from_callable"


# ---------------------------------------------------------------------------
# TestWorkflowRegistry
# ---------------------------------------------------------------------------


class TestWorkflowRegistry:
    def test_register_and_get_pipeline(self) -> None:
        """Registering a definition and retrieving its pipeline returns the expected steps."""
        registry = WorkflowRegistry()
        defn = WorkflowDefinition(
            type_id="custom",
            pipeline=lambda: [DummyStep("custom_step")],
            description="custom workflow",
        )
        registry.register(defn)

        pipeline = registry.get_pipeline("custom")

        assert isinstance(pipeline, list)
        assert len(pipeline) == 1
        assert isinstance(pipeline[0], DummyStep)
        assert pipeline[0].name == "custom_step"

    def test_get_pipeline_unknown_type_raises_value_error(self) -> None:
        """get_pipeline() raises ValueError for an unregistered type."""
        registry = WorkflowRegistry()

        with pytest.raises(ValueError, match="Unknown workflow type: unknown"):
            registry.get_pipeline("unknown")

    def test_list_types(self) -> None:
        """list_types() returns a sorted list of registered type IDs."""
        registry = WorkflowRegistry()
        registry.register(WorkflowDefinition(type_id="beta", pipeline=lambda: [], description=""))
        registry.register(WorkflowDefinition(type_id="alpha", pipeline=lambda: [], description=""))
        registry.register(WorkflowDefinition(type_id="gamma", pipeline=lambda: [], description=""))

        types = registry.list_types()

        assert types == ["alpha", "beta", "gamma"]

    def test_is_registered(self) -> None:
        """is_registered() returns True for registered types and False otherwise."""
        registry = WorkflowRegistry()
        registry.register(WorkflowDefinition(type_id="exists", pipeline=lambda: [], description=""))

        assert registry.is_registered("exists") is True
        assert registry.is_registered("missing") is False


# ---------------------------------------------------------------------------
# TestSingleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_workflow_registry_returns_same_instance(self) -> None:
        """get_workflow_registry() returns the same object on repeated calls."""
        first = get_workflow_registry()
        second = get_workflow_registry()

        assert first is second

    def test_register_default_workflows_registers_full_and_patch(self) -> None:
        """
        The default singleton has 'full' and 'patch'
        workflow types registered.
        """
        registry = get_workflow_registry()

        assert registry.is_registered("full")
        assert registry.is_registered("patch")

    def test_main_is_not_registered(self) -> None:
        """The 'main' workflow type should NOT be registered."""
        registry = get_workflow_registry()

        assert not registry.is_registered("main")

    def test_register_default_workflows_registers_full(self):
        """
        The default singleton has 'full' workflow type registered.
        """
        registry = get_workflow_registry()

        assert registry.is_registered("full")
        assert "full" in registry.list_types()

    def test_reset_workflow_registry_clears_singleton(self):
        """reset_workflow_registry() causes get_workflow_registry() to create a new instance."""
        first = get_workflow_registry()
        reset_workflow_registry()
        second = get_workflow_registry()

        assert first is not second


# ---------------------------------------------------------------------------
# TestGetPipelineForType
# ---------------------------------------------------------------------------


class TestGetPipelineForType:
    def test_patch_returns_patch_pipeline(self) -> None:
        """get_pipeline_for_type('patch') returns the patch pipeline."""
        pipeline = get_pipeline_for_type("patch")

        assert isinstance(pipeline, list)
        assert len(pipeline) > 0
        assert all(isinstance(step, WorkflowStep) for step in pipeline)

    def test_unknown_raises_value_error(self) -> None:
        """Unknown types raise ValueError from the registry."""
        with pytest.raises(ValueError, match="Unknown workflow type: unknown"):
            get_pipeline_for_type("unknown")

    def test_full_returns_full_pipeline(self):
        """get_pipeline_for_type('full') returns the full pipeline."""
        pipeline = get_pipeline_for_type("full")

        assert isinstance(pipeline, list)
        assert len(pipeline) > 0
        assert all(isinstance(step, WorkflowStep) for step in pipeline)

    def test_thin_returns_thin_pipeline(self) -> None:
        """get_pipeline_for_type('thin') returns the thin pipeline."""
        pipeline = get_pipeline_for_type("thin")

        assert isinstance(pipeline, list)
        assert len(pipeline) > 0
        assert all(isinstance(step, WorkflowStep) for step in pipeline)


# ---------------------------------------------------------------------------
# TestCLIToRegistryFlow — integration tests for execute_adw_workflow routing
# ---------------------------------------------------------------------------


class TestCLIToRegistryFlow:
    """Integration tests verifying that execute_adw_workflow routes through
    get_pipeline_for_type and passes a valid pipeline to execute_workflow.
    """

    def test_adw_workflow_uses_registry_for_full(self, monkeypatch) -> None:
        """Calling execute_adw_workflow with workflow_type='full' uses the real
        get_pipeline_for_type('full') and passes a non-empty WorkflowStep pipeline
        to execute_workflow.
        """
        from rouge.adw.adw import execute_adw_workflow

        captured: dict = {}

        def fake_execute_workflow(
            issue_id, adw_id, pipeline=None, resume_from=None, pipeline_type=None
        ):
            captured["issue_id"] = issue_id
            captured["adw_id"] = adw_id
            captured["pipeline"] = pipeline
            return True

        monkeypatch.setattr("rouge.adw.adw.execute_workflow", fake_execute_workflow)

        success, wf_id = execute_adw_workflow("fixed-adw-id", 42, workflow_type="full")

        assert success is True
        assert wf_id == "fixed-adw-id"
        assert captured["issue_id"] == 42
        assert captured["adw_id"] == "fixed-adw-id"

        pipeline = captured["pipeline"]
        assert isinstance(pipeline, list)
        assert len(pipeline) > 0
        assert all(isinstance(step, WorkflowStep) for step in pipeline)

    def test_adw_workflow_uses_registry_for_patch(self, monkeypatch) -> None:
        """Calling execute_adw_workflow with workflow_type='patch' uses the real
        get_pipeline_for_type('patch') and passes a valid WorkflowStep pipeline
        to execute_workflow.
        """
        from rouge.adw.adw import execute_adw_workflow

        captured: dict = {}

        def fake_execute_workflow(
            issue_id, adw_id, pipeline=None, resume_from=None, pipeline_type=None
        ):
            captured["issue_id"] = issue_id
            captured["adw_id"] = adw_id
            captured["pipeline"] = pipeline
            return True

        monkeypatch.setattr("rouge.adw.adw.execute_workflow", fake_execute_workflow)

        success, wf_id = execute_adw_workflow("fixed-adw-id", 99, workflow_type="patch")

        assert success is True
        assert wf_id == "fixed-adw-id"

        pipeline = captured["pipeline"]
        assert isinstance(pipeline, list)
        assert len(pipeline) > 0
        assert all(isinstance(step, WorkflowStep) for step in pipeline)

    def test_adw_workflow_unknown_type_raises(self, monkeypatch) -> None:
        """execute_adw_workflow with an unknown workflow_type raises ValueError
        containing 'Unknown workflow type'.
        """
        from rouge.adw.adw import execute_adw_workflow

        monkeypatch.setattr("rouge.adw.adw.execute_workflow", lambda *a, **kw: True)

        with pytest.raises(ValueError, match="Unknown workflow type"):
            execute_adw_workflow("fixed-adw-id", 1, workflow_type="custom")
