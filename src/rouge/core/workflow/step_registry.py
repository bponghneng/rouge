"""Step registry for workflow step metadata and dependency resolution.

This module provides a registry for declaring workflow step dependencies
and outputs, enabling independent step execution and dependency resolution.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Type, TypeVar

from rouge.core.workflow.artifacts import ArtifactType
from rouge.core.workflow.step_base import WorkflowStep

logger = logging.getLogger(__name__)

# Type variable for step classes
S = TypeVar("S", bound=WorkflowStep)


@dataclass
class StepMetadata:
    """Metadata for a registered workflow step.

    Attributes:
        step_class: The WorkflowStep subclass
        dependencies: List of artifact types required as input
        outputs: List of artifact types produced as output
        is_critical: Whether the step is critical (workflow aborts on failure)
        description: Optional description of what the step does
    """

    step_class: Type[WorkflowStep]
    dependencies: List[ArtifactType] = field(default_factory=list)
    outputs: List[ArtifactType] = field(default_factory=list)
    is_critical: bool = True
    description: Optional[str] = None


class StepRegistry:
    """Registry for workflow step metadata and dependency management.

    Provides step registration, metadata lookup, and dependency resolution
    for enabling independent step execution.
    """

    def __init__(self) -> None:
        """Initialize an empty step registry."""
        self._steps: Dict[str, StepMetadata] = {}

    def register(
        self,
        step_class: Type[WorkflowStep],
        dependencies: Optional[List[ArtifactType]] = None,
        outputs: Optional[List[ArtifactType]] = None,
        is_critical: Optional[bool] = None,
        description: Optional[str] = None,
    ) -> None:
        """Register a workflow step with its metadata.

        Args:
            step_class: The WorkflowStep subclass to register
            dependencies: List of artifact types required as input
            outputs: List of artifact types produced as output
            is_critical: Whether the step is critical (uses step's default if not specified)
            description: Optional description of what the step does
        """
        # Create a temporary instance to get the step name and is_critical flag
        temp_instance = step_class()
        step_name = temp_instance.name

        metadata = StepMetadata(
            step_class=step_class,
            dependencies=dependencies or [],
            outputs=outputs or [],
            is_critical=is_critical if is_critical is not None else temp_instance.is_critical,
            description=description,
        )

        self._steps[step_name] = metadata
        logger.debug("Registered step: %s", step_name)

    def get_step_metadata(self, step_name: str) -> Optional[StepMetadata]:
        """Get metadata for a registered step.

        Args:
            step_name: The step name to look up

        Returns:
            StepMetadata if found, None otherwise
        """
        return self._steps.get(step_name)

    def get_step_by_name(self, step_name: str) -> Optional[Type[WorkflowStep]]:
        """Get step class by its name.

        Args:
            step_name: The step name to look up

        Returns:
            WorkflowStep subclass if found, None otherwise
        """
        metadata = self._steps.get(step_name)
        return metadata.step_class if metadata else None

    def list_all_steps(self) -> List[str]:
        """List all registered step names.

        Returns:
            List of step names in registration order
        """
        return list(self._steps.keys())

    def list_step_details(self) -> List[Dict]:
        """List all steps with their full metadata.

        Returns:
            List of dicts with step name, dependencies, outputs, is_critical
        """
        result = []
        for step_name, metadata in self._steps.items():
            result.append(
                {
                    "name": step_name,
                    "dependencies": list(metadata.dependencies),
                    "outputs": list(metadata.outputs),
                    "is_critical": metadata.is_critical,
                    "description": metadata.description,
                }
            )
        return result

    def resolve_dependencies(self, step_name: str) -> List[str]:
        """Resolve the dependency order for executing a step.

        Returns the ordered list of step names that must be executed before
        the target step, using topological sort on the dependency graph.

        Args:
            step_name: The step to resolve dependencies for

        Returns:
            List of step names in execution order (not including target step)

        Raises:
            ValueError: If step not found or circular dependency detected
        """
        if step_name not in self._steps:
            raise ValueError(f"Unknown step: {step_name}")

        # Build a map of artifact -> producing step
        artifact_producers: Dict[str, str] = {}
        for name, metadata in self._steps.items():
            for output in metadata.outputs:
                artifact_producers[output] = name

        # Perform topological sort
        visited: Set[str] = set()
        result: List[str] = []
        in_progress: Set[str] = set()

        def visit(name: str) -> None:
            if name in visited:
                return
            if name in in_progress:
                raise ValueError(f"Circular dependency detected involving step: {name}")

            in_progress.add(name)
            metadata = self._steps.get(name)
            if metadata:
                for dep in metadata.dependencies:
                    producer = artifact_producers.get(dep)
                    if producer and producer != name:
                        visit(producer)

            in_progress.remove(name)
            visited.add(name)
            result.append(name)

        visit(step_name)

        # Remove the target step from the result (we only want dependencies)
        if step_name in result:
            result.remove(step_name)

        return result

    def get_steps_for_artifact(self, artifact_type: ArtifactType) -> List[str]:
        """Get all steps that produce a given artifact type.

        Args:
            artifact_type: The artifact type to find producers for

        Returns:
            List of step names that produce this artifact
        """
        producers = []
        for step_name, metadata in self._steps.items():
            if artifact_type in metadata.outputs:
                producers.append(step_name)
        return producers

    def get_steps_requiring_artifact(self, artifact_type: ArtifactType) -> List[str]:
        """Get all steps that require a given artifact type.

        Args:
            artifact_type: The artifact type to find consumers for

        Returns:
            List of step names that require this artifact
        """
        consumers = []
        for step_name, metadata in self._steps.items():
            if artifact_type in metadata.dependencies:
                consumers.append(step_name)
        return consumers

    def validate_registry(self) -> List[str]:
        """Validate the registry for consistency issues.

        Checks for:
        - Steps with unresolvable dependencies (no producer registered)
        - Circular dependencies

        Returns:
            List of warning/error messages (empty if valid)
        """
        issues = []

        # Build artifact producer map
        artifact_producers: Dict[str, str] = {}
        for step_name, metadata in self._steps.items():
            for output in metadata.outputs:
                artifact_producers[output] = step_name

        # Check for missing producers
        for step_name, metadata in self._steps.items():
            for dep in metadata.dependencies:
                if dep not in artifact_producers:
                    issues.append(
                        f"Step '{step_name}' requires artifact '{dep}' but no step produces it"
                    )

        # Check for circular dependencies
        detected_circular_deps = set()
        for step_name in self._steps:
            try:
                self.resolve_dependencies(step_name)
            except ValueError as e:
                if "Circular dependency" in str(e):
                    # Extract the cycle to avoid duplicate reporting
                    error_msg = str(e)
                    if error_msg not in detected_circular_deps:
                        detected_circular_deps.add(error_msg)
                        issues.append(error_msg)

        return issues


# Global registry instance
_global_registry: Optional[StepRegistry] = None


def get_step_registry() -> StepRegistry:
    """Get the global step registry, initializing it if needed.

    Returns:
        The global StepRegistry instance
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = StepRegistry()
        _register_default_steps(_global_registry)
    return _global_registry


def _register_default_steps(registry: StepRegistry) -> None:
    """Register all default workflow steps with their metadata.

    Args:
        registry: The registry to populate
    """
    # Import here to avoid circular imports
    from rouge.core.workflow.steps.acceptance import ValidateAcceptanceStep
    from rouge.core.workflow.steps.classify import ClassifyStep
    from rouge.core.workflow.steps.create_github_pr import CreateGitHubPullRequestStep
    from rouge.core.workflow.steps.create_gitlab_pr import CreateGitLabPullRequestStep
    from rouge.core.workflow.steps.fetch import FetchIssueStep
    from rouge.core.workflow.steps.fetch_patch import FetchPatchStep
    from rouge.core.workflow.steps.implement import ImplementStep
    from rouge.core.workflow.steps.patch_plan import BuildPatchPlanStep
    from rouge.core.workflow.steps.plan import BuildPlanStep
    from rouge.core.workflow.steps.pr import PreparePullRequestStep
    from rouge.core.workflow.steps.quality import CodeQualityStep
    from rouge.core.workflow.steps.review import AddressReviewStep, GenerateReviewStep
    from rouge.core.workflow.steps.setup import SetupStep
    from rouge.core.workflow.steps.update_pr_commits import UpdatePRCommitsStep

    # 0. SetupStep: no dependencies, no outputs (prerequisite step, critical)
    registry.register(
        SetupStep,
        dependencies=[],
        outputs=[],
        description="Set up git environment for workflow execution",
    )

    # 1. FetchIssueStep: no dependencies, produces issue artifact
    registry.register(
        FetchIssueStep,
        dependencies=[],
        outputs=["issue"],
        description="Fetch issue from Supabase database",
    )

    # 1b. FetchPatchStep: no dependencies, produces patch artifact (for patch workflow)
    registry.register(
        FetchPatchStep,
        dependencies=[],
        outputs=["patch"],
        description="Fetch pending patch from Supabase database",
    )

    # 2. ClassifyStep: requires issue, produces classification
    registry.register(
        ClassifyStep,
        dependencies=["issue"],
        outputs=["classification"],
        description="Classify issue type and complexity",
    )

    # 3. BuildPlanStep: requires issue and classification, produces plan
    registry.register(
        BuildPlanStep,
        dependencies=["issue", "classification"],
        outputs=["plan"],
        description="Build implementation plan for the issue",
    )

    # 4. ImplementStep: requires plan, produces implementation
    registry.register(
        ImplementStep,
        dependencies=["plan"],
        outputs=["implementation"],
        description="Execute the implementation plan",
    )

    # 5. GenerateReviewStep: requires plan, produces review
    registry.register(
        GenerateReviewStep,
        dependencies=["plan"],
        outputs=["review"],
        description="Generate code review for implementation",
    )

    # 7. AddressReviewStep: requires review, produces review_addressed
    registry.register(
        AddressReviewStep,
        dependencies=["review"],
        outputs=["review_addressed"],
        description="Address review issues and suggestions",
    )

    # 8. CodeQualityStep: requires implementation, produces quality_check
    registry.register(
        CodeQualityStep,
        dependencies=["implementation"],
        outputs=["quality_check"],
        description="Run code quality checks (linting, type checking)",
    )

    # 9. ValidateAcceptanceStep: requires plan (or patch_plan), produces acceptance
    registry.register(
        ValidateAcceptanceStep,
        dependencies=["plan", "patch_plan"],
        outputs=["acceptance"],
        description="Validate implementation against acceptance criteria",
    )

    # 10. PreparePullRequestStep: requires acceptance, produces pr_metadata
    registry.register(
        PreparePullRequestStep,
        dependencies=["acceptance"],
        outputs=["pr_metadata"],
        description="Prepare pull request metadata and commits",
    )

    # 11. CreateGitHubPullRequestStep: requires pr_metadata, produces pull_request
    registry.register(
        CreateGitHubPullRequestStep,
        dependencies=["pr_metadata"],
        outputs=["pull_request"],
        description="Create GitHub pull request via gh CLI",
    )

    # 12. CreateGitLabPullRequestStep: requires pr_metadata, produces pull_request
    registry.register(
        CreateGitLabPullRequestStep,
        dependencies=["pr_metadata"],
        outputs=["pull_request"],
        description="Create GitLab merge request via glab CLI",
    )

    # 13. BuildPatchPlanStep: requires issue, patch, plan; produces patch_plan
    registry.register(
        BuildPatchPlanStep,
        dependencies=["issue", "patch", "plan"],
        outputs=["patch_plan"],
        is_critical=True,
        description="Build patch-specific plan contextualized against original plan",
    )

    # 14. UpdatePRCommitsStep: requires pull_request, pushes commits
    registry.register(
        UpdatePRCommitsStep,
        dependencies=["pull_request"],
        outputs=[],
        is_critical=False,
        description="Push patch commits to existing PR/MR",
    )


def reset_step_registry() -> None:
    """Reset the global step registry (primarily for testing).

    This clears the global registry so it will be re-initialized on next access.
    """
    global _global_registry
    _global_registry = None
