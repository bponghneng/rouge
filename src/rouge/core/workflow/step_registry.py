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
        slug: Unique slug identifier for the step (kebab-case)
        dependencies: List of artifact types required as input
        outputs: List of artifact types produced as output
        is_critical: Whether the step is critical (workflow aborts on failure)
        description: Optional description of what the step does
    """

    step_class: Type[WorkflowStep]
    slug: str = ""
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
        self._slug_to_name: Dict[str, str] = {}

    def register(
        self,
        step_class: Type[WorkflowStep],
        dependencies: Optional[List[ArtifactType]] = None,
        outputs: Optional[List[ArtifactType]] = None,
        is_critical: Optional[bool] = None,
        description: Optional[str] = None,
        slug: Optional[str] = None,
    ) -> None:
        """Register a workflow step with its metadata.

        Args:
            step_class: The WorkflowStep subclass to register
            dependencies: List of artifact types required as input
            outputs: List of artifact types produced as output
            is_critical: Whether the step is critical (uses step's default if not specified)
            description: Optional description of what the step does
            slug: Optional unique slug identifier (kebab-case)

        Raises:
            ValueError: If the slug is already registered to a different step
        """
        # Create a temporary instance to get the step name and is_critical flag
        temp_instance = step_class()
        step_name = temp_instance.name

        # Validate slug uniqueness if provided
        if slug:
            if slug in self._slug_to_name:
                existing_step = self._slug_to_name[slug]
                if existing_step != step_name:
                    raise ValueError(
                        f"Slug '{slug}' is already registered for step '{existing_step}'"
                    )
            self._slug_to_name[slug] = step_name

        metadata = StepMetadata(
            step_class=step_class,
            slug=slug or "",
            dependencies=dependencies or [],
            outputs=outputs or [],
            is_critical=is_critical if is_critical is not None else temp_instance.is_critical,
            description=description,
        )

        self._steps[step_name] = metadata
        logger.debug("Registered step: %s (slug: %s)", step_name, slug or "none")

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

    def get_step_by_slug(self, slug: str) -> Optional[Type[WorkflowStep]]:
        """Get step class by its slug.

        Args:
            slug: The step slug to look up

        Returns:
            WorkflowStep subclass if found, None otherwise
        """
        step_name = self._slug_to_name.get(slug)
        if step_name:
            return self.get_step_by_name(step_name)
        return None

    def get_step_metadata_by_slug(self, slug: str) -> Optional[StepMetadata]:
        """Get metadata for a registered step by its slug.

        Args:
            slug: The step slug to look up

        Returns:
            StepMetadata if found, None otherwise
        """
        step_name = self._slug_to_name.get(slug)
        if step_name:
            return self.get_step_metadata(step_name)
        return None

    def list_all_steps(self) -> List[str]:
        """List all registered step names.

        Returns:
            List of step names in registration order
        """
        return list(self._steps.keys())

    def list_step_details(self) -> List[Dict]:
        """List all steps with their full metadata.

        Returns:
            List of dicts with slug, name, dependencies, outputs, is_critical, description
        """
        result = []
        for step_name, metadata in self._steps.items():
            result.append(
                {
                    "slug": metadata.slug,
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
    from rouge.core.workflow.steps.acceptance_step import AcceptanceStep
    from rouge.core.workflow.steps.classify_step import ClassifyStep
    from rouge.core.workflow.steps.code_quality_step import CodeQualityStep
    from rouge.core.workflow.steps.code_review_step import CodeReviewStep
    from rouge.core.workflow.steps.compose_commits_step import ComposeCommitsStep
    from rouge.core.workflow.steps.compose_request_step import ComposeRequestStep
    from rouge.core.workflow.steps.fetch_issue_step import FetchIssueStep
    from rouge.core.workflow.steps.fetch_patch_step import FetchPatchStep
    from rouge.core.workflow.steps.gh_pull_request_step import (
        GhPullRequestStep,
    )
    from rouge.core.workflow.steps.git_setup_step import GitSetupStep
    from rouge.core.workflow.steps.glab_pull_request_step import (
        GlabPullRequestStep,
    )
    from rouge.core.workflow.steps.implement_step import ImplementStep
    from rouge.core.workflow.steps.patch_plan_step import PatchPlanStep
    from rouge.core.workflow.steps.plan_step import PlanStep
    from rouge.core.workflow.steps.review_fix_step import ReviewFixStep
    from rouge.core.workflow.steps.review_plan_step import ReviewPlanStep

    # 0. GitSetupStep: no dependencies, produces git-setup artifact
    registry.register(
        GitSetupStep,
        slug="git-setup",
        dependencies=[],
        outputs=["git-setup"],
        description="Set up git environment for workflow execution",
    )

    # 1. FetchIssueStep: no dependencies, produces fetch-issue artifact
    registry.register(
        FetchIssueStep,
        slug="fetch-issue",
        dependencies=[],
        outputs=["fetch-issue"],
        description="Fetch issue from Supabase database",
    )

    # 1b. FetchPatchStep: no dependencies, produces fetch-patch artifact (for patch workflow)
    registry.register(
        FetchPatchStep,
        slug="fetch-patch",
        dependencies=[],
        outputs=["fetch-patch"],
        description="Fetch pending patch from Supabase database",
    )

    # 2. ClassifyStep: requires fetch-issue, produces classify artifact
    registry.register(
        ClassifyStep,
        slug="classify",
        dependencies=["fetch-issue"],
        outputs=["classify"],
        description="Classify issue type and complexity",
    )

    # 3. PlanStep: requires fetch-issue and classify, produces plan
    registry.register(
        PlanStep,
        slug="plan",
        dependencies=["fetch-issue", "classify"],
        outputs=["plan"],
        description="Build implementation plan for the issue",
    )

    # 3b. ReviewPlanStep: requires fetch-issue, produces plan (alternative to classify+plan)
    registry.register(
        ReviewPlanStep,
        slug="review-plan",
        dependencies=["fetch-issue"],
        outputs=["plan"],
        is_critical=True,
        description="Review and regenerate plan based on feedback",
    )

    # 4. ImplementStep: requires plan, produces implement artifact
    registry.register(
        ImplementStep,
        slug="implement",
        dependencies=["plan"],
        outputs=["implement"],
        description="Execute the implementation plan",
    )

    # 5. CodeReviewStep: requires plan, produces code-review artifact
    registry.register(
        CodeReviewStep,
        slug="code-review",
        dependencies=["plan"],
        outputs=["code-review"],
        description="Generate code review for implementation",
    )

    # 7. ReviewFixStep: requires code-review, produces review-fix artifact
    registry.register(
        ReviewFixStep,
        slug="review-fix",
        dependencies=["code-review"],
        outputs=["review-fix"],
        description="Address review issues and suggestions",
    )

    # 8. CodeQualityStep: requires implement, produces code-quality artifact
    registry.register(
        CodeQualityStep,
        slug="code-quality",
        dependencies=["implement"],
        outputs=["code-quality"],
        description="Run code quality checks (linting, type checking)",
    )

    # 9. AcceptanceStep: requires plan, produces acceptance
    registry.register(
        AcceptanceStep,
        slug="acceptance",
        dependencies=["plan"],
        outputs=["acceptance"],
        description="Validate implementation against acceptance criteria",
    )

    # 10. ComposeRequestStep: requires acceptance, produces compose-request artifact
    registry.register(
        ComposeRequestStep,
        slug="compose-request",
        dependencies=["acceptance"],
        outputs=["compose-request"],
        description="Prepare pull request metadata and commits",
    )

    # 11. GhPullRequestStep: requires compose-request, produces gh-pull-request artifact
    registry.register(
        GhPullRequestStep,
        slug="gh-pull-request",
        dependencies=["compose-request"],
        outputs=["gh-pull-request"],
        description="Create GitHub pull request via gh CLI",
    )

    # 12. GlabPullRequestStep: requires compose-request, produces glab-pull-request artifact
    registry.register(
        GlabPullRequestStep,
        slug="glab-pull-request",
        dependencies=["compose-request"],
        outputs=["glab-pull-request"],
        description="Create GitLab merge request via glab CLI",
    )

    # 13. PatchPlanStep: requires fetch-patch, produces plan
    registry.register(
        PatchPlanStep,
        slug="patch-plan",
        dependencies=["fetch-patch"],
        outputs=["plan"],
        is_critical=True,
        description="Build standalone implementation plan for patch issue",
    )

    # 14. ComposeCommitsStep: detects PR via CLI, pushes commits, produces compose-commits artifact
    registry.register(
        ComposeCommitsStep,
        slug="compose-commits",
        dependencies=[],
        outputs=["compose-commits"],
        is_critical=False,
        description="Push patch commits to existing PR/MR (detects PR via gh/glab CLI)",
    )


def reset_step_registry() -> None:
    """Reset the global step registry (primarily for testing).

    This clears the global registry so it will be re-initialized on next access.
    """
    global _global_registry
    _global_registry = None
