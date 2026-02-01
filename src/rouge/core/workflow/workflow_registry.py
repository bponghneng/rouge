"""Workflow registry for managing and resolving workflow pipelines by type.

Provides a registry of workflow definitions that can be looked up by type ID,
gated behind a feature flag for safe incremental rollout. When the feature flag
is disabled, the module falls back to direct pipeline function calls.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Type, Union

from rouge.core.workflow.step_base import WorkflowStep

WORKFLOW_REGISTRY_FLAG = "ROUGE_USE_WORKFLOW_REGISTRY"

logger = logging.getLogger(__name__)


@dataclass
class StepConfig:
    """Configuration for a single workflow step.

    Attributes:
        step_class: The WorkflowStep subclass to instantiate
        is_critical: Optional override for step criticality (deferred feature)
        config: Additional configuration passed to the step (reserved for future use)
    """

    step_class: Type[WorkflowStep]
    is_critical: Optional[bool] = None
    config: Dict[str, Any] = field(default_factory=dict)

    def create_step(self) -> WorkflowStep:
        """Instantiate the configured workflow step.

        Returns:
            A new instance of the configured WorkflowStep subclass
        """
        if self.is_critical is not None:
            logger.warning(
                "is_critical override requested for %s, not yet implemented",
                self.step_class.__name__,
            )
        return self.step_class()


@dataclass
class WorkflowDefinition:
    """Definition of a named workflow pipeline.

    The pipeline can be specified either as a list of StepConfig objects
    (for declarative pipelines) or as a callable that returns a list of
    WorkflowStep instances (for dynamic pipelines).

    Attributes:
        type_id: Unique identifier for this workflow type (e.g., "main", "patch")
        pipeline: Either a list of StepConfig or a callable returning List[WorkflowStep]
        description: Human-readable description of the workflow
    """

    type_id: str
    pipeline: Union[List[StepConfig], Callable[[], List[WorkflowStep]]]
    description: str = ""

    def get_pipeline(self) -> List[WorkflowStep]:
        """Resolve the pipeline definition into a list of step instances.

        Returns:
            List of WorkflowStep instances in execution order
        """
        if callable(self.pipeline):
            return self.pipeline()
        return [step_config.create_step() for step_config in self.pipeline]


class WorkflowRegistry:
    """Registry for workflow definitions, keyed by type ID.

    Provides lookup, registration, and enumeration of available workflow types.
    """

    def __init__(self) -> None:
        self._registry: Dict[str, WorkflowDefinition] = {}

    def register(self, definition: WorkflowDefinition) -> None:
        """Register a workflow definition.

        Args:
            definition: The workflow definition to register
        """
        self._registry[definition.type_id] = definition

    def get_pipeline(self, workflow_type: str) -> List[WorkflowStep]:
        """Resolve a workflow type to its pipeline of steps.

        Args:
            workflow_type: The type ID to look up

        Returns:
            List of WorkflowStep instances for the requested workflow type

        Raises:
            ValueError: If the workflow type is not registered
        """
        definition = self._registry.get(workflow_type)
        if definition is None:
            raise ValueError(
                f"Unknown workflow type: {workflow_type}. Available: {self.list_types()}"
            )
        return definition.get_pipeline()

    def list_types(self) -> List[str]:
        """List all registered workflow type IDs.

        Returns:
            Sorted list of registered type IDs
        """
        return sorted(self._registry.keys())

    def is_registered(self, workflow_type: str) -> bool:
        """Check whether a workflow type is registered.

        Args:
            workflow_type: The type ID to check

        Returns:
            True if the type is registered
        """
        return workflow_type in self._registry


# ---------------------------------------------------------------------------
# Singleton management
# ---------------------------------------------------------------------------

_REGISTRY_INSTANCE: Optional[WorkflowRegistry] = None


def _register_default_workflows(registry: WorkflowRegistry) -> None:
    """Populate *registry* with the built-in workflow types.

    Uses local imports to avoid circular dependencies with pipeline.py.
    """
    from rouge.core.workflow.pipeline import (
        get_code_review_pipeline,
        get_default_pipeline,
        get_patch_pipeline,
    )

    registry.register(
        WorkflowDefinition(
            type_id="main",
            pipeline=get_default_pipeline,
            description="Default workflow pipeline",
        )
    )
    registry.register(
        WorkflowDefinition(
            type_id="patch",
            pipeline=get_patch_pipeline,
            description="Patch workflow pipeline",
        )
    )
    registry.register(
        WorkflowDefinition(
            type_id="code-review",
            pipeline=get_code_review_pipeline,
            description="Automated code review loop for commits",
        )
    )


def get_workflow_registry() -> WorkflowRegistry:
    """Return the global WorkflowRegistry singleton, creating it on first call.

    Returns:
        The shared WorkflowRegistry instance with default workflows registered
    """
    global _REGISTRY_INSTANCE
    if _REGISTRY_INSTANCE is None:
        _REGISTRY_INSTANCE = WorkflowRegistry()
        _register_default_workflows(_REGISTRY_INSTANCE)
    return _REGISTRY_INSTANCE


def reset_workflow_registry() -> None:
    """Reset the global registry singleton (for test isolation)."""
    global _REGISTRY_INSTANCE
    _REGISTRY_INSTANCE = None


# ---------------------------------------------------------------------------
# Feature-flag helpers and public API
# ---------------------------------------------------------------------------


def is_registry_enabled() -> bool:
    """Check whether the workflow registry feature flag is enabled.

    Returns:
        True if the ROUGE_USE_WORKFLOW_REGISTRY env var is set to a truthy value
    """
    return os.environ.get(WORKFLOW_REGISTRY_FLAG, "").lower() in (
        "true",
        "1",
        "yes",
    )


def get_pipeline_for_type(workflow_type: str) -> List[WorkflowStep]:
    """Resolve a workflow type to its pipeline of steps.

    When the registry feature flag is disabled, this falls back to direct
    calls to the pipeline factory functions for the built-in types
    ("main", "patch", and "code-review"), ensuring zero behavior change.

    When the feature flag is enabled, resolution is delegated to the
    global WorkflowRegistry which supports additional registered types.

    Args:
        workflow_type: The workflow type ID (e.g., "main", "patch")

    Returns:
        List of WorkflowStep instances for the requested workflow type

    Raises:
        ValueError: If the workflow type is unknown
    """
    if not is_registry_enabled():
        if workflow_type == "main":
            from rouge.core.workflow.pipeline import get_default_pipeline

            return get_default_pipeline()
        if workflow_type == "patch":
            from rouge.core.workflow.pipeline import get_patch_pipeline

            return get_patch_pipeline()
        if workflow_type == "code-review":
            from rouge.core.workflow.pipeline import get_code_review_pipeline

            return get_code_review_pipeline()
        raise ValueError(
            f"Unknown workflow type: {workflow_type}. "
            "Registry is disabled; only 'main', 'patch', and 'code-review' are available."
        )

    return get_workflow_registry().get_pipeline(workflow_type)
