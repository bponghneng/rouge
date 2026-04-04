"""Workflow registry for managing and resolving workflow pipelines by type.

Provides a registry of workflow definitions that can be looked up by type ID.
"""

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from rouge.core.workflow.step_base import WorkflowStep


@dataclass
class WorkflowDefinition:
    """Definition of a named workflow pipeline.

    Attributes:
        type_id: Unique identifier for this workflow type (e.g., "full", "patch")
        pipeline: A callable that returns a list of WorkflowStep instances
        description: Human-readable description of the workflow
    """

    type_id: str
    pipeline: Callable[[], List[WorkflowStep]]
    description: str = ""

    def get_pipeline(self) -> List[WorkflowStep]:
        """Resolve the pipeline definition into a list of step instances.

        Returns:
            List of WorkflowStep instances in execution order
        """
        return self.pipeline()


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
        get_full_pipeline,
        get_patch_pipeline,
        get_thin_pipeline,
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
            type_id="full",
            pipeline=get_full_pipeline,
            description="Full workflow pipeline",
        )
    )
    registry.register(
        WorkflowDefinition(
            type_id="thin",
            pipeline=get_thin_pipeline,
            description="Thin workflow pipeline for straightforward issues",
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
# Public API
# ---------------------------------------------------------------------------


def get_pipeline_for_type(workflow_type: str) -> List[WorkflowStep]:
    """Resolve a workflow type to its pipeline of steps.

    Delegates to the global WorkflowRegistry for resolution.

    Args:
        workflow_type: The workflow type ID (e.g., "full", "patch")

    Returns:
        List of WorkflowStep instances for the requested workflow type

    Raises:
        ValueError: If the workflow type is unknown
    """
    return get_workflow_registry().get_pipeline(workflow_type)
