"""Step registry for workflow step metadata.

This module provides a registry for declaring workflow step metadata,
enabling step lookup by name or slug.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Type, TypeVar

from rouge.core.workflow.step_base import WorkflowStep

# Module-level logger is appropriate here: step registration occurs at initialization
# time before workflows exist, so workflow-scoped logging is not applicable.
logger = logging.getLogger(__name__)

# Type variable for step classes
S = TypeVar("S", bound=WorkflowStep)


@dataclass
class StepMetadata:
    """Metadata for a registered workflow step.

    Attributes:
        step_class: The WorkflowStep subclass
        slug: Unique slug identifier for the step (kebab-case)
        is_critical: Whether the step is critical (workflow aborts on failure)
        description: Optional description of what the step does
    """

    step_class: Type[WorkflowStep]
    slug: str = ""
    is_critical: bool = True
    description: Optional[str] = None


class StepRegistry:
    """Registry for workflow step metadata.

    Provides step registration and metadata lookup by name or slug.
    """

    def __init__(self) -> None:
        """Initialize an empty step registry."""
        self._steps: Dict[str, StepMetadata] = {}
        self._slug_to_name: Dict[str, str] = {}

    def register(
        self,
        step_class: Type[WorkflowStep],
        is_critical: Optional[bool] = None,
        description: Optional[str] = None,
        slug: Optional[str] = None,
        **kwargs: object,  # noqa: ARG002
    ) -> None:
        """Register a workflow step with its metadata.

        Args:
            step_class: The WorkflowStep subclass to register
            is_critical: Whether the step is critical (uses step's default if not specified)
            description: Optional description of what the step does
            slug: Optional unique slug identifier (kebab-case)
            **kwargs: Ignored (accepts legacy keyword arguments for backward compatibility)

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
            List of dicts with slug, name, is_critical, description
        """
        result = []
        for step_name, metadata in self._steps.items():
            result.append(
                {
                    "slug": metadata.slug,
                    "name": step_name,
                    "is_critical": metadata.is_critical,
                    "description": metadata.description,
                }
            )
        return result


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
    from rouge.core.workflow.steps.claude_code_plan_step import ClaudeCodePlanStep
    from rouge.core.workflow.steps.code_quality_step import CodeQualityStep
    from rouge.core.workflow.steps.compose_commits_step import ComposeCommitsStep
    from rouge.core.workflow.steps.compose_request_step import ComposeRequestStep
    from rouge.core.workflow.steps.fetch_issue_step import FetchIssueStep
    from rouge.core.workflow.steps.fetch_patch_step import FetchPatchStep
    from rouge.core.workflow.steps.gh_pull_request_step import (
        GhPullRequestStep,
    )
    from rouge.core.workflow.steps.git_branch_step import GitBranchStep
    from rouge.core.workflow.steps.git_checkout_step import GitCheckoutStep
    from rouge.core.workflow.steps.git_prepare_step import GitPrepareStep
    from rouge.core.workflow.steps.glab_pull_request_step import (
        GlabPullRequestStep,
    )
    from rouge.core.workflow.steps.implement_direct_step import ImplementDirectStep
    from rouge.core.workflow.steps.implement_step import ImplementPlanStep
    from rouge.core.workflow.steps.patch_plan_step import PatchPlanStep
    from rouge.core.workflow.steps.thin_plan_step import ThinPlanStep

    registry.register(
        GitBranchStep,
        slug="git-branch",
        description="Set up git environment for workflow execution",
    )

    registry.register(
        GitCheckoutStep,
        slug="git-checkout",
        description="Check out existing git branch and pull latest changes",
    )

    registry.register(
        FetchIssueStep,
        slug="fetch-issue",
        description="Fetch issue from Supabase database",
    )

    registry.register(
        FetchPatchStep,
        slug="fetch-patch",
        description="Fetch pending patch from Supabase database",
    )

    registry.register(
        ImplementPlanStep,
        slug="implement-plan",
        description="Execute the plan-based implementation",
    )

    registry.register(
        CodeQualityStep,
        slug="code-quality",
        description="Run code quality checks",
    )

    registry.register(
        ComposeRequestStep,
        slug="compose-request",
        description="Prepare pull request metadata",
    )

    registry.register(
        GhPullRequestStep,
        slug="gh-pull-request",
        description="Create GitHub pull request via gh CLI",
    )

    registry.register(
        GlabPullRequestStep,
        slug="glab-pull-request",
        description="Create GitLab merge request via glab CLI",
    )

    registry.register(
        PatchPlanStep,
        slug="patch-plan",
        is_critical=True,
        description="Build standalone implementation plan for patch issue",
    )

    registry.register(
        ComposeCommitsStep,
        slug="compose-commits",
        is_critical=False,
        description="Push patch commits to existing PR/MR (detects PR via gh/glab CLI)",
    )

    registry.register(
        ClaudeCodePlanStep,
        slug="claude-code-plan",
        is_critical=True,
        description="Build task-oriented implementation plan without classification",
    )

    registry.register(
        ThinPlanStep,
        slug="thin-plan",
        is_critical=True,
        description="Build a lightweight implementation plan with minimal agent interaction",
    )

    registry.register(
        ImplementDirectStep,
        slug="implement-direct",
        is_critical=True,
        description="Implement directly from the issue description without a plan",
    )

    registry.register(
        GitPrepareStep,
        slug="git-prepare",
        is_critical=True,
        description="Branch-aware git workspace preparation (creates or checks out branch)",
    )


def reset_step_registry() -> None:
    """Reset the global step registry (primarily for testing).

    This clears the global registry so it will be re-initialized on next access.
    """
    global _global_registry
    _global_registry = None
