"""Unit tests for step registry."""

import pytest

from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.step_registry import (
    StepMetadata,
    StepRegistry,
    get_step_registry,
    reset_step_registry,
)
from rouge.core.workflow.types import StepResult


class MockStep(WorkflowStep):
    """Mock step for testing."""

    @property
    def name(self) -> str:
        return "Mock Step"

    def run(self, context: WorkflowContext) -> StepResult:
        return StepResult.ok(None)


class AnotherMockStep(WorkflowStep):
    """Another mock step for testing."""

    @property
    def name(self) -> str:
        return "Another Mock Step"

    def run(self, context: WorkflowContext) -> StepResult:
        return StepResult.ok(None)


class BestEffortMockStep(WorkflowStep):
    """Non-critical mock step for testing."""

    @property
    def name(self) -> str:
        return "Best Effort Step"

    @property
    def is_critical(self) -> bool:
        return False

    def run(self, context: WorkflowContext) -> StepResult:
        return StepResult.ok(None)


class TestStepMetadata:
    """Tests for StepMetadata dataclass."""

    def test_metadata_creation(self):
        """Test StepMetadata can be created with all fields."""
        metadata = StepMetadata(
            step_class=MockStep,
            slug="mock-step",
            is_critical=True,
            description="Test step",
        )

        assert metadata.step_class == MockStep
        assert metadata.slug == "mock-step"
        assert metadata.is_critical is True
        assert metadata.description == "Test step"

    def test_metadata_defaults(self):
        """Test StepMetadata has correct defaults."""
        metadata = StepMetadata(step_class=MockStep)

        assert metadata.slug == ""
        assert metadata.is_critical is True
        assert metadata.description is None


class TestStepRegistry:
    """Tests for StepRegistry class."""

    def test_register_step(self):
        """Test registering a step with metadata."""
        registry = StepRegistry()
        registry.register(
            MockStep,
            slug="mock-step",
            description="Mock classification",
        )

        metadata = registry.get_step_metadata("Mock Step")
        assert metadata is not None
        assert metadata.step_class == MockStep
        assert metadata.slug == "mock-step"
        assert metadata.description == "Mock classification"

    def test_register_step_infers_is_critical(self):
        """Test register infers is_critical from step class."""
        registry = StepRegistry()

        registry.register(MockStep)
        registry.register(BestEffortMockStep)

        critical_metadata = registry.get_step_metadata("Mock Step")
        best_effort_metadata = registry.get_step_metadata("Best Effort Step")

        assert critical_metadata.is_critical is True
        assert best_effort_metadata.is_critical is False

    def test_register_step_override_is_critical(self):
        """Test is_critical can be overridden during registration."""
        registry = StepRegistry()
        registry.register(MockStep, is_critical=False)

        metadata = registry.get_step_metadata("Mock Step")
        assert metadata.is_critical is False

    def test_get_step_metadata_not_found(self):
        """Test get_step_metadata returns None for unknown step."""
        registry = StepRegistry()
        metadata = registry.get_step_metadata("Unknown Step")
        assert metadata is None

    def test_get_step_by_name(self):
        """Test get_step_by_name returns step class."""
        registry = StepRegistry()
        registry.register(MockStep)

        step_class = registry.get_step_by_name("Mock Step")
        assert step_class == MockStep

    def test_get_step_by_name_not_found(self):
        """Test get_step_by_name returns None for unknown step."""
        registry = StepRegistry()
        step_class = registry.get_step_by_name("Unknown Step")
        assert step_class is None

    def test_list_all_steps(self):
        """Test list_all_steps returns all registered step names."""
        registry = StepRegistry()
        registry.register(MockStep)
        registry.register(AnotherMockStep)

        steps = registry.list_all_steps()
        assert "Mock Step" in steps
        assert "Another Mock Step" in steps
        assert len(steps) == 2

    def test_list_all_steps_empty(self):
        """Test list_all_steps returns empty list for empty registry."""
        registry = StepRegistry()
        steps = registry.list_all_steps()
        assert steps == []

    def test_list_step_details(self):
        """Test list_step_details returns full metadata for all steps."""
        registry = StepRegistry()
        registry.register(
            MockStep,
            slug="mock-step",
            description="Mock step",
        )

        details = registry.list_step_details()
        assert len(details) == 1
        assert details[0]["name"] == "Mock Step"
        assert details[0]["slug"] == "mock-step"
        assert details[0]["is_critical"] is True
        assert details[0]["description"] == "Mock step"

    def test_register_accepts_legacy_kwargs(self):
        """Test register accepts and ignores legacy keyword arguments."""
        registry = StepRegistry()
        # Should not raise even with unknown kwargs
        registry.register(
            MockStep,
            dependencies=["issue"],
            outputs=["classification"],
        )

        metadata = registry.get_step_metadata("Mock Step")
        assert metadata is not None
        assert metadata.step_class == MockStep


class TestSlugFunctionality:
    """Tests for slug-based step lookup functionality."""

    def test_slug_uniqueness_validation(self):
        """Test registering duplicate slug raises ValueError."""
        registry = StepRegistry()
        registry.register(MockStep, slug="mock-slug")

        with pytest.raises(ValueError, match="Slug 'mock-slug' is already registered"):
            registry.register(AnotherMockStep, slug="mock-slug")

    def test_get_step_by_slug(self):
        """Test get_step_by_slug returns correct step class."""
        registry = StepRegistry()
        registry.register(MockStep, slug="mock-slug")
        registry.register(AnotherMockStep, slug="another-slug")

        step_class = registry.get_step_by_slug("mock-slug")
        assert step_class == MockStep

        another_class = registry.get_step_by_slug("another-slug")
        assert another_class == AnotherMockStep

    def test_get_step_by_slug_not_found(self):
        """Test get_step_by_slug returns None for unknown slug."""
        registry = StepRegistry()
        registry.register(MockStep, slug="mock-slug")

        step_class = registry.get_step_by_slug("unknown-slug")
        assert step_class is None

    def test_get_step_metadata_by_slug(self):
        """Test get_step_metadata_by_slug returns correct metadata."""
        registry = StepRegistry()
        registry.register(
            MockStep,
            slug="mock-slug",
            description="Test step",
        )

        metadata = registry.get_step_metadata_by_slug("mock-slug")
        assert metadata is not None
        assert metadata.step_class == MockStep
        assert metadata.slug == "mock-slug"
        assert metadata.description == "Test step"

    def test_get_step_metadata_by_slug_not_found(self):
        """Test get_step_metadata_by_slug returns None for unknown slug."""
        registry = StepRegistry()
        registry.register(MockStep, slug="mock-slug")

        metadata = registry.get_step_metadata_by_slug("unknown-slug")
        assert metadata is None


class TestGlobalRegistry:
    """Tests for global registry functions."""

    def setup_method(self):
        """Reset global registry before each test."""
        reset_step_registry()

    def teardown_method(self):
        """Reset global registry after each test."""
        reset_step_registry()

    def test_get_step_registry_initializes_once(self):
        """Test get_step_registry returns same instance."""
        registry1 = get_step_registry()
        registry2 = get_step_registry()

        assert registry1 is registry2

    def test_get_step_registry_has_default_steps(self):
        """Test global registry has default steps registered."""
        registry = get_step_registry()
        steps = registry.list_all_steps()

        # Check key steps are registered
        assert any("Fetching" in s for s in steps)
        assert any("Building" in s for s in steps)
        assert any("Implementing" in s for s in steps)

    def test_default_steps_all_have_unique_slugs(self):
        """Test that all default steps have unique slugs and can be resolved."""
        registry = get_step_registry()
        step_details = registry.list_step_details()

        # Collect all slugs
        slugs = [step["slug"] for step in step_details]

        # Check that all steps have slugs
        assert all(slug for slug in slugs), "All default steps should have slugs"

        # Check that all slugs are unique
        assert len(slugs) == len(set(slugs)), "All default step slugs should be unique"

        # Verify each slug can resolve back to a step
        for slug in slugs:
            step_class = registry.get_step_by_slug(slug)
            assert step_class is not None, f"Slug '{slug}' should resolve to a step class"

            metadata = registry.get_step_metadata_by_slug(slug)
            assert metadata is not None, f"Slug '{slug}' should resolve to metadata"
            assert metadata.slug == slug, "Metadata slug should match lookup slug"

    def test_reset_step_registry(self):
        """Test reset_step_registry clears the registry."""
        registry1 = get_step_registry()
        reset_step_registry()
        registry2 = get_step_registry()

        # After reset, should be a new instance
        assert registry1 is not registry2

    def test_implement_plan_step_registration(self) -> None:
        """Test ImplementPlanStep is registered with slug 'implement-plan'."""
        registry = get_step_registry()

        metadata = registry.get_step_metadata_by_slug("implement-plan")
        assert (
            metadata is not None
        ), "ImplementPlanStep should be registered with slug 'implement-plan'"
        assert metadata.is_critical is True

    def test_implement_direct_step_registration(self) -> None:
        """Test ImplementDirectStep is registered with correct metadata."""
        registry = get_step_registry()

        metadata = registry.get_step_metadata_by_slug("implement-direct")
        assert (
            metadata is not None
        ), "ImplementDirectStep should be registered with slug 'implement-direct'"
        assert metadata.is_critical is True

    def test_git_prepare_step_registration(self) -> None:
        """Test GitPrepareStep is registered with correct metadata."""
        registry = get_step_registry()

        metadata = registry.get_step_metadata_by_slug("git-prepare")
        assert metadata is not None, "GitPrepareStep should be registered with slug 'git-prepare'"
        assert metadata.is_critical is True

    def test_patch_plan_step_registration(self):
        """Test PatchPlanStep is registered with correct metadata."""
        registry = get_step_registry()

        metadata = registry.get_step_metadata_by_slug("patch-plan")
        assert metadata is not None, "PatchPlanStep should be registered"
        assert metadata.is_critical is True

    def test_compose_commits_step_registration(self):
        """Test ComposeCommitsStep is registered with correct metadata."""
        registry = get_step_registry()

        metadata = registry.get_step_metadata_by_slug("compose-commits")
        assert metadata is not None, "ComposeCommitsStep should be registered"
        assert metadata.is_critical is False

    def test_thin_plan_step_registration(self) -> None:
        """Test ThinPlanStep is registered with correct metadata."""
        registry = get_step_registry()

        metadata = registry.get_step_metadata_by_slug("thin-plan")
        assert metadata is not None, "ThinPlanStep should be registered with slug 'thin-plan'"
        assert metadata.is_critical is True
