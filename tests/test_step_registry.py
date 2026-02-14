"""Unit tests for step registry and dependency resolution."""

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
            dependencies=["issue"],
            outputs=["classification"],
            is_critical=True,
            description="Test step",
        )

        assert metadata.step_class == MockStep
        assert metadata.dependencies == ["issue"]
        assert metadata.outputs == ["classification"]
        assert metadata.is_critical is True
        assert metadata.description == "Test step"

    def test_metadata_defaults(self):
        """Test StepMetadata has correct defaults."""
        metadata = StepMetadata(step_class=MockStep)

        assert metadata.dependencies == []
        assert metadata.outputs == []
        assert metadata.is_critical is True
        assert metadata.description is None


class TestStepRegistry:
    """Tests for StepRegistry class."""

    def test_register_step(self):
        """Test registering a step with metadata."""
        registry = StepRegistry()
        registry.register(
            MockStep,
            dependencies=["issue"],
            outputs=["classification"],
            description="Mock classification",
        )

        metadata = registry.get_step_metadata("Mock Step")
        assert metadata is not None
        assert metadata.step_class == MockStep
        assert metadata.dependencies == ["issue"]
        assert metadata.outputs == ["classification"]

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
            dependencies=["issue"],
            outputs=["classification"],
            description="Mock step",
        )

        details = registry.list_step_details()
        assert len(details) == 1
        assert details[0]["name"] == "Mock Step"
        assert details[0]["dependencies"] == ["issue"]
        assert details[0]["outputs"] == ["classification"]
        assert details[0]["is_critical"] is True
        assert details[0]["description"] == "Mock step"


class TestDependencyResolution:
    """Tests for dependency resolution functionality."""

    def test_resolve_no_dependencies(self):
        """Test resolving step with no dependencies."""
        registry = StepRegistry()
        registry.register(MockStep, dependencies=[], outputs=["issue"])

        deps = registry.resolve_dependencies("Mock Step")
        assert deps == []

    def test_resolve_single_dependency(self):
        """Test resolving step with single dependency."""
        registry = StepRegistry()
        registry.register(MockStep, dependencies=[], outputs=["issue"])
        registry.register(AnotherMockStep, dependencies=["issue"], outputs=["classification"])

        deps = registry.resolve_dependencies("Another Mock Step")
        assert deps == ["Mock Step"]

    def test_resolve_chain_dependencies(self):
        """Test resolving chain of dependencies."""

        class Step1(WorkflowStep):
            @property
            def name(self) -> str:
                return "Step 1"

            def run(self, context: WorkflowContext) -> StepResult:
                return StepResult.ok(None)

        class Step2(WorkflowStep):
            @property
            def name(self) -> str:
                return "Step 2"

            def run(self, context: WorkflowContext) -> StepResult:
                return StepResult.ok(None)

        class Step3(WorkflowStep):
            @property
            def name(self) -> str:
                return "Step 3"

            def run(self, context: WorkflowContext) -> StepResult:
                return StepResult.ok(None)

        registry = StepRegistry()
        registry.register(Step1, dependencies=[], outputs=["issue"])
        registry.register(Step2, dependencies=["issue"], outputs=["classification"])
        registry.register(Step3, dependencies=["classification"], outputs=["plan"])

        deps = registry.resolve_dependencies("Step 3")
        # Step 1 must come before Step 2
        assert "Step 1" in deps
        assert "Step 2" in deps
        assert deps.index("Step 1") < deps.index("Step 2")

    def test_resolve_unknown_step(self):
        """Test resolving unknown step raises ValueError."""
        registry = StepRegistry()

        with pytest.raises(ValueError, match="Unknown step"):
            registry.resolve_dependencies("Unknown Step")

    def test_resolve_circular_dependency(self):
        """Test resolving circular dependency raises ValueError."""

        class CircularStep1(WorkflowStep):
            @property
            def name(self) -> str:
                return "Circular 1"

            def run(self, context: WorkflowContext) -> StepResult:
                return StepResult.ok(None)

        class CircularStep2(WorkflowStep):
            @property
            def name(self) -> str:
                return "Circular 2"

            def run(self, context: WorkflowContext) -> StepResult:
                return StepResult.ok(None)

        registry = StepRegistry()
        registry.register(CircularStep1, dependencies=["artifact_b"], outputs=["artifact_a"])
        registry.register(CircularStep2, dependencies=["artifact_a"], outputs=["artifact_b"])

        with pytest.raises(ValueError, match="Circular dependency"):
            registry.resolve_dependencies("Circular 1")


class TestArtifactQueries:
    """Tests for artifact-related query methods."""

    def test_get_steps_for_artifact(self):
        """Test finding steps that produce an artifact."""
        registry = StepRegistry()
        registry.register(MockStep, outputs=["issue"])
        registry.register(AnotherMockStep, outputs=["classification"])

        producers = registry.get_steps_for_artifact("issue")
        assert producers == ["Mock Step"]

    def test_get_steps_for_artifact_none(self):
        """Test finding producers for non-existent artifact."""
        registry = StepRegistry()
        registry.register(MockStep, outputs=["issue"])

        producers = registry.get_steps_for_artifact("unknown")
        assert producers == []

    def test_get_steps_requiring_artifact(self):
        """Test finding steps that require an artifact."""
        registry = StepRegistry()
        registry.register(MockStep, outputs=["issue"])
        registry.register(AnotherMockStep, dependencies=["issue"])

        consumers = registry.get_steps_requiring_artifact("issue")
        assert consumers == ["Another Mock Step"]

    def test_get_steps_requiring_artifact_none(self):
        """Test finding consumers for non-required artifact."""
        registry = StepRegistry()
        registry.register(MockStep, dependencies=["issue"])

        consumers = registry.get_steps_requiring_artifact("unknown")
        assert consumers == []


class TestRegistryValidation:
    """Tests for registry validation functionality."""

    def test_validate_valid_registry(self):
        """Test validation of valid registry returns no issues."""
        registry = StepRegistry()
        registry.register(MockStep, dependencies=[], outputs=["issue"])
        registry.register(AnotherMockStep, dependencies=["issue"], outputs=["classification"])

        issues = registry.validate_registry()
        assert issues == []

    def test_validate_missing_producer(self):
        """Test validation catches missing artifact producer."""
        registry = StepRegistry()
        registry.register(MockStep, dependencies=["nonexistent"], outputs=["issue"])

        issues = registry.validate_registry()
        assert len(issues) == 1
        assert "nonexistent" in issues[0]
        assert "no step produces it" in issues[0]

    def test_validate_circular_dependency(self):
        """Test validation catches circular dependencies."""

        class CircularA(WorkflowStep):
            @property
            def name(self) -> str:
                return "Circular A"

            def run(self, context: WorkflowContext) -> StepResult:
                return StepResult.ok(None)

        class CircularB(WorkflowStep):
            @property
            def name(self) -> str:
                return "Circular B"

            def run(self, context: WorkflowContext) -> StepResult:
                return StepResult.ok(None)

        registry = StepRegistry()
        registry.register(CircularA, dependencies=["b_output"], outputs=["a_output"])
        registry.register(CircularB, dependencies=["a_output"], outputs=["b_output"])

        issues = registry.validate_registry()
        assert any("Circular dependency" in issue for issue in issues)


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
            dependencies=["issue"],
            outputs=["classification"],
            description="Test step",
        )

        metadata = registry.get_step_metadata_by_slug("mock-slug")
        assert metadata is not None
        assert metadata.step_class == MockStep
        assert metadata.slug == "mock-slug"
        assert metadata.dependencies == ["issue"]
        assert metadata.outputs == ["classification"]
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
        assert any("Classifying" in s for s in steps)
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
            assert metadata.slug == slug, f"Metadata slug should match lookup slug"

    def test_reset_step_registry(self):
        """Test reset_step_registry clears the registry."""
        registry1 = get_step_registry()
        reset_step_registry()
        registry2 = get_step_registry()

        # After reset, should be a new instance
        assert registry1 is not registry2

    def test_default_step_dependencies(self):
        """Test default steps have correct dependencies configured."""
        registry = get_step_registry()

        # ClassifyStep should depend on issue
        classify_meta = None
        for name in registry.list_all_steps():
            if "Classifying" in name:
                classify_meta = registry.get_step_metadata(name)
                break

        assert classify_meta is not None
        assert "issue" in classify_meta.dependencies

    def test_default_step_outputs(self):
        """Test default steps have correct outputs configured."""
        registry = get_step_registry()

        # FetchIssueStep should output issue
        fetch_meta = None
        for name in registry.list_all_steps():
            if "Fetching" in name:
                fetch_meta = registry.get_step_metadata(name)
                break

        assert fetch_meta is not None
        assert "issue" in fetch_meta.outputs

    def test_dependency_chain_resolution(self):
        """Test resolving full dependency chain for late step.

        ImplementStep depends on "plan", which can be produced by either
        PlanStep (main) or PatchPlanStep (patch). The resolver
        picks one valid chain.
        """
        registry = get_step_registry()

        # Find the implement step
        implement_step_name = None
        for name in registry.list_all_steps():
            if "Implementing" in name:
                implement_step_name = name
                break

        assert implement_step_name is not None

        deps = registry.resolve_dependencies(implement_step_name)

        # Should have at least a fetch step and a plan-building step
        assert len(deps) >= 2
        assert any("Building" in dep for dep in deps), "Should depend on a plan building step"

    def test_patch_plan_step_registration(self):
        """Test PatchPlanStep is registered with correct metadata.

        After decoupling, PatchPlanStep only depends on the patch artifact
        and produces a regular plan artifact (not a separate patch_plan).
        """
        registry = get_step_registry()

        # Find the patch plan step - exact name is "Building patch plan"
        patch_plan_step_name = None
        for name in registry.list_all_steps():
            if "Building patch plan" in name:
                patch_plan_step_name = name
                break

        assert patch_plan_step_name is not None, "PatchPlanStep should be registered"

        metadata = registry.get_step_metadata(patch_plan_step_name)
        assert metadata is not None
        assert metadata.dependencies == ["patch"]
        assert metadata.outputs == ["plan"]
        assert metadata.is_critical is True

    def test_update_pr_commits_step_registration(self):
        """Test ComposeCommitsStep is registered with correct metadata.

        After decoupling, ComposeCommitsStep detects PRs via gh/glab CLI
        rather than loading parent PullRequestArtifact, so it has no artifact
        dependencies.
        """
        registry = get_step_registry()

        # Find the update PR commits step - exact name is "Updating pull request with patch commits"
        update_pr_commits_step_name = None
        for name in registry.list_all_steps():
            if "Updating pull request with patch commits" in name:
                update_pr_commits_step_name = name
                break

        assert update_pr_commits_step_name is not None, "ComposeCommitsStep should be registered"

        metadata = registry.get_step_metadata(update_pr_commits_step_name)
        assert metadata is not None
        assert metadata.dependencies == []
        assert metadata.outputs == []
        assert metadata.is_critical is False

    def test_validate_registry_passes(self):
        """Test that validate_registry passes with no issues."""
        registry = get_step_registry()

        issues = registry.validate_registry()

        # Should have no issues -- all artifact dependencies are now resolvable.
        # Both 'plan' producers (PlanStep and BuildPatchPlanStep) and
        # 'patch' producer (FetchPatchStep) are registered.
        assert issues == [], f"Registry validation issues: {issues}"

    def test_patch_plan_dependency_resolution(self):
        """Test dependency resolution for PatchPlanStep.

        After decoupling, PatchPlanStep only depends on the patch artifact
        produced by FetchPatchStep. It no longer depends on FetchIssueStep or
        PlanStep from a parent workflow.
        """
        registry = get_step_registry()

        # Find the patch plan step - exact name is "Building patch plan"
        patch_plan_step_name = None
        for name in registry.list_all_steps():
            if "Building patch plan" in name:
                patch_plan_step_name = name
                break

        assert patch_plan_step_name is not None

        deps = registry.resolve_dependencies(patch_plan_step_name)

        # Should only include FetchPatchStep (produces patch artifact)
        assert any(
            "Fetching pending patch" in dep for dep in deps
        ), "Should depend on FetchPatchStep"
        # Should NOT depend on FetchIssueStep or PlanStep (decoupled)
        assert not any(
            "Fetching issue" in dep for dep in deps
        ), "Should not depend on FetchIssueStep"
        assert not any(
            "Building implementation plan" in dep for dep in deps
        ), "Should not depend on PlanStep"
