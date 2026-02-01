"""Tests for workflow registry module."""

import logging
from typing import Generator

import pytest

from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult
from rouge.core.workflow.workflow_registry import (
    WORKFLOW_REGISTRY_FLAG,
    StepConfig,
    WorkflowDefinition,
    WorkflowRegistry,
    get_pipeline_for_type,
    get_workflow_registry,
    is_registry_enabled,
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
# TestStepConfig
# ---------------------------------------------------------------------------


class TestStepConfig:
    def test_create_step_instantiates_correctly(self):
        """StepConfig.create_step() returns an instance of the configured step class."""
        config = StepConfig(step_class=DummyStep)
        step = config.create_step()

        assert isinstance(step, DummyStep)
        assert isinstance(step, WorkflowStep)

    def test_create_step_logs_warning_when_is_critical_set(self, caplog):
        """StepConfig.create_step() logs a warning when is_critical is overridden."""
        config = StepConfig(step_class=DummyStep, is_critical=True)

        with caplog.at_level(logging.WARNING):
            step = config.create_step()

        assert isinstance(step, DummyStep)
        assert "is_critical override requested for DummyStep" in caplog.text
        assert "not yet implemented" in caplog.text


# ---------------------------------------------------------------------------
# TestWorkflowDefinition
# ---------------------------------------------------------------------------


class TestWorkflowDefinition:
    def test_get_pipeline_with_callable(self):
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

    def test_get_pipeline_with_step_config_list(self):
        """WorkflowDefinition.get_pipeline() instantiates from StepConfig list."""
        defn = WorkflowDefinition(
            type_id="test",
            pipeline=[StepConfig(step_class=DummyStep)],
            description="test workflow",
        )
        pipeline = defn.get_pipeline()

        assert isinstance(pipeline, list)
        assert len(pipeline) == 1
        assert isinstance(pipeline[0], DummyStep)


# ---------------------------------------------------------------------------
# TestWorkflowRegistry
# ---------------------------------------------------------------------------


class TestWorkflowRegistry:
    def test_register_and_get_pipeline(self):
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

    def test_get_pipeline_unknown_type_raises_value_error(self):
        """get_pipeline() raises ValueError for an unregistered type."""
        registry = WorkflowRegistry()

        with pytest.raises(ValueError, match="Unknown workflow type: unknown"):
            registry.get_pipeline("unknown")

    def test_list_types(self):
        """list_types() returns a sorted list of registered type IDs."""
        registry = WorkflowRegistry()
        registry.register(WorkflowDefinition(type_id="beta", pipeline=lambda: [], description=""))
        registry.register(WorkflowDefinition(type_id="alpha", pipeline=lambda: [], description=""))
        registry.register(WorkflowDefinition(type_id="gamma", pipeline=lambda: [], description=""))

        types = registry.list_types()

        assert types == ["alpha", "beta", "gamma"]

    def test_is_registered(self):
        """is_registered() returns True for registered types and False otherwise."""
        registry = WorkflowRegistry()
        registry.register(WorkflowDefinition(type_id="exists", pipeline=lambda: [], description=""))

        assert registry.is_registered("exists") is True
        assert registry.is_registered("missing") is False


# ---------------------------------------------------------------------------
# TestSingleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_workflow_registry_returns_same_instance(self):
        """get_workflow_registry() returns the same object on repeated calls."""
        first = get_workflow_registry()
        second = get_workflow_registry()

        assert first is second

    def test_register_default_workflows_registers_main_and_patch(self):
        """The default singleton has 'main' and 'patch' workflow types registered."""
        registry = get_workflow_registry()

        assert registry.is_registered("main")
        assert registry.is_registered("patch")

    def test_reset_workflow_registry_clears_singleton(self):
        """reset_workflow_registry() causes get_workflow_registry() to create a new instance."""
        first = get_workflow_registry()
        reset_workflow_registry()
        second = get_workflow_registry()

        assert first is not second


# ---------------------------------------------------------------------------
# TestIsRegistryEnabled
# ---------------------------------------------------------------------------


class TestIsRegistryEnabled:
    @pytest.mark.parametrize(
        "env_value, expected",
        [
            ("true", True),
            ("TRUE", True),
            ("1", True),
            ("yes", True),
            ("YES", True),
            ("false", False),
            ("0", False),
            ("no", False),
            ("", False),
        ],
    )
    def test_is_registry_enabled_with_env_values(self, monkeypatch, env_value, expected):
        """is_registry_enabled() interprets various env var values correctly."""
        monkeypatch.setenv(WORKFLOW_REGISTRY_FLAG, env_value)

        assert is_registry_enabled() is expected

    def test_is_registry_enabled_when_unset(self, monkeypatch):
        """is_registry_enabled() returns False when the env var is not set."""
        monkeypatch.delenv(WORKFLOW_REGISTRY_FLAG, raising=False)

        assert is_registry_enabled() is False


# ---------------------------------------------------------------------------
# TestGetPipelineForType
# ---------------------------------------------------------------------------


class TestGetPipelineForType:
    def test_flag_disabled_main_returns_default_pipeline(self, monkeypatch):
        """With the flag disabled, get_pipeline_for_type('main') returns the default pipeline."""
        monkeypatch.delenv(WORKFLOW_REGISTRY_FLAG, raising=False)

        pipeline = get_pipeline_for_type("main")

        assert isinstance(pipeline, list)
        assert len(pipeline) > 0
        assert all(isinstance(step, WorkflowStep) for step in pipeline)

    def test_flag_disabled_patch_returns_patch_pipeline(self, monkeypatch):
        """With the flag disabled, get_pipeline_for_type('patch') returns the patch pipeline."""
        monkeypatch.delenv(WORKFLOW_REGISTRY_FLAG, raising=False)

        pipeline = get_pipeline_for_type("patch")

        assert isinstance(pipeline, list)
        assert len(pipeline) > 0
        assert all(isinstance(step, WorkflowStep) for step in pipeline)

    def test_flag_disabled_unknown_raises_value_error(self, monkeypatch):
        """With the flag disabled, unknown types raise ValueError mentioning the registry."""
        monkeypatch.delenv(WORKFLOW_REGISTRY_FLAG, raising=False)

        with pytest.raises(ValueError, match="Registry is disabled"):
            get_pipeline_for_type("custom")

    def test_flag_enabled_main_resolves_via_registry(self, monkeypatch):
        """With the flag enabled, get_pipeline_for_type('main') resolves via the registry."""
        monkeypatch.setenv(WORKFLOW_REGISTRY_FLAG, "true")

        pipeline = get_pipeline_for_type("main")

        assert isinstance(pipeline, list)
        assert len(pipeline) > 0
        assert all(isinstance(step, WorkflowStep) for step in pipeline)

    def test_flag_enabled_patch_resolves_via_registry(self, monkeypatch):
        """With the flag enabled, get_pipeline_for_type('patch') resolves via the registry."""
        monkeypatch.setenv(WORKFLOW_REGISTRY_FLAG, "true")

        pipeline = get_pipeline_for_type("patch")

        assert isinstance(pipeline, list)
        assert len(pipeline) > 0
        assert all(isinstance(step, WorkflowStep) for step in pipeline)

    def test_flag_enabled_unknown_raises_value_error(self, monkeypatch):
        """With the flag enabled, unknown types raise ValueError from the registry."""
        monkeypatch.setenv(WORKFLOW_REGISTRY_FLAG, "true")

        with pytest.raises(ValueError, match="Unknown workflow type: unknown"):
            get_pipeline_for_type("unknown")
