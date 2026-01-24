"""Tests for workflow pipeline components."""

from unittest.mock import Mock

from rouge.core.workflow.pipeline import WorkflowRunner, get_default_pipeline
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult


class TestWorkflowContext:
    """Tests for WorkflowContext dataclass."""

    def test_context_initialization(self):
        """Test WorkflowContext initializes with required fields."""
        context = WorkflowContext(
            issue_id=123,
            adw_id="adw-456",
        )

        assert context.issue_id == 123
        assert context.adw_id == "adw-456"
        assert context.issue is None
        assert context.data == {}

    def test_context_data_storage(self):
        """Test WorkflowContext stores data between steps."""
        context = WorkflowContext(
            issue_id=1,
            adw_id="test",
        )

        # Simulate step storing data
        context.data["plan_file"] = "specs/plan.md"
        context.data["classify_data"] = {"type": "feature"}

        assert context.data["plan_file"] == "specs/plan.md"
        assert context.data["classify_data"]["type"] == "feature"


class TestWorkflowRunner:
    """Tests for WorkflowRunner orchestrator."""

    def test_runner_executes_all_steps(self):
        """Test runner executes all steps in order."""
        # Create mock steps
        step1 = Mock(spec=WorkflowStep)
        step1.name = "Step 1"
        step1.is_critical = True
        step1.run.return_value = StepResult.ok(None)

        step2 = Mock(spec=WorkflowStep)
        step2.name = "Step 2"
        step2.is_critical = True
        step2.run.return_value = StepResult.ok(None)

        runner = WorkflowRunner([step1, step2])
        result = runner.run(1, "adw123")

        assert result is True
        step1.run.assert_called_once()
        step2.run.assert_called_once()

    def test_runner_stops_on_critical_failure(self):
        """Test runner stops when critical step fails."""
        step1 = Mock(spec=WorkflowStep)
        step1.name = "Step 1"
        step1.is_critical = True
        step1.run.return_value = StepResult.fail("Step 1 failed")

        step2 = Mock(spec=WorkflowStep)
        step2.name = "Step 2"
        step2.is_critical = True
        step2.run.return_value = StepResult.ok(None)

        runner = WorkflowRunner([step1, step2])
        result = runner.run(1, "adw123")

        assert result is False
        step1.run.assert_called_once()
        step2.run.assert_not_called()  # Not reached

    def test_runner_continues_on_best_effort_failure(self):
        """Test runner continues when best-effort step fails."""
        step1 = Mock(spec=WorkflowStep)
        step1.name = "Critical Step"
        step1.is_critical = True
        step1.run.return_value = StepResult.ok(None)

        step2 = Mock(spec=WorkflowStep)
        step2.name = "Best Effort Step"
        step2.is_critical = False  # Best-effort
        step2.run.return_value = StepResult.fail("Best Effort Step failed")

        step3 = Mock(spec=WorkflowStep)
        step3.name = "Another Critical"
        step3.is_critical = True
        step3.run.return_value = StepResult.ok(None)

        runner = WorkflowRunner([step1, step2, step3])
        result = runner.run(1, "adw123")

        assert result is True  # Overall success
        step1.run.assert_called_once()
        step2.run.assert_called_once()
        step3.run.assert_called_once()  # Still executed

    def test_runner_passes_context_to_steps(self):
        """Test runner passes correct context to each step."""
        captured_context = None

        def capture_context(context):
            nonlocal captured_context
            captured_context = context
            return StepResult.ok(None)

        step = Mock(spec=WorkflowStep)
        step.name = "Test Step"
        step.is_critical = True
        step.run.side_effect = capture_context

        runner = WorkflowRunner([step])
        runner.run(42, "adw-test-123")

        assert captured_context is not None
        assert captured_context.issue_id == 42
        assert captured_context.adw_id == "adw-test-123"


class TestGetDefaultPipeline:
    """Tests for get_default_pipeline factory."""

    def test_returns_correct_step_count_without_platform(self, monkeypatch):
        """Test default pipeline has 10 steps when DEV_SEC_OPS_PLATFORM is unset."""
        monkeypatch.delenv("DEV_SEC_OPS_PLATFORM", raising=False)
        pipeline = get_default_pipeline()
        assert len(pipeline) == 10

    def test_returns_correct_step_count_with_github(self, monkeypatch):
        """Test default pipeline has 11 steps when DEV_SEC_OPS_PLATFORM=github."""
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        pipeline = get_default_pipeline()
        assert len(pipeline) == 11

    def test_returns_correct_step_count_with_gitlab(self, monkeypatch):
        """Test default pipeline has 11 steps when DEV_SEC_OPS_PLATFORM=gitlab."""
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "gitlab")
        pipeline = get_default_pipeline()
        assert len(pipeline) == 11

    def test_returns_workflow_step_instances(self, monkeypatch):
        """Test all items are WorkflowStep subclasses."""
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        pipeline = get_default_pipeline()
        for step in pipeline:
            assert isinstance(step, WorkflowStep)

    def test_step_order_without_platform(self, monkeypatch):
        """Test steps are in correct order when no platform is set."""
        monkeypatch.delenv("DEV_SEC_OPS_PLATFORM", raising=False)
        pipeline = get_default_pipeline()
        step_names = [step.name for step in pipeline]

        # Verify key steps are in expected order
        assert "git environment" in step_names[0].lower()
        assert "Fetching" in step_names[1]
        assert "Classifying" in step_names[2]
        assert "Building" in step_names[3]
        assert "Implementing" in step_names[4]
        assert "review" in step_names[5].lower()
        assert "review" in step_names[6].lower()
        assert "quality" in step_names[7].lower()
        assert "acceptance" in step_names[8].lower()
        assert "pull request" in step_names[9].lower()

    def test_step_order_with_github(self, monkeypatch):
        """Test steps are in correct order when DEV_SEC_OPS_PLATFORM=github."""
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        pipeline = get_default_pipeline()
        step_names = [step.name for step in pipeline]

        # Verify key steps are in expected order
        assert "git environment" in step_names[0].lower()
        assert "Fetching" in step_names[1]
        assert "Classifying" in step_names[2]
        assert "Building" in step_names[3]
        assert "Implementing" in step_names[4]
        assert "review" in step_names[5].lower()
        assert "review" in step_names[6].lower()
        assert "quality" in step_names[7].lower()
        assert "acceptance" in step_names[8].lower()
        assert "pull request" in step_names[9].lower()
        assert "github" in step_names[10].lower()

    def test_step_order_with_gitlab(self, monkeypatch):
        """Test steps are in correct order when DEV_SEC_OPS_PLATFORM=gitlab."""
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "gitlab")
        pipeline = get_default_pipeline()
        step_names = [step.name for step in pipeline]

        # Verify key steps are in expected order
        assert "git environment" in step_names[0].lower()
        assert "Fetching" in step_names[1]
        assert "Classifying" in step_names[2]
        assert "Building" in step_names[3]
        assert "Implementing" in step_names[4]
        assert "review" in step_names[5].lower()
        assert "review" in step_names[6].lower()
        assert "quality" in step_names[7].lower()
        assert "acceptance" in step_names[8].lower()
        assert "pull request" in step_names[9].lower()
        assert "gitlab" in step_names[10].lower()

    def test_critical_flags_without_platform(self, monkeypatch):
        """Test critical/best-effort flags are set correctly when no platform is set."""
        monkeypatch.delenv("DEV_SEC_OPS_PLATFORM", raising=False)
        pipeline = get_default_pipeline()

        # First 5 steps should be critical (setup, fetch, classify, plan, implement)
        for step in pipeline[:5]:
            assert step.is_critical is True, f"{step.name} should be critical"

        # Review steps are not critical
        assert pipeline[5].is_critical is False  # GenerateReviewStep
        assert pipeline[6].is_critical is False  # AddressReviewStep

        # Quality is best-effort
        assert pipeline[7].is_critical is False  # CodeQualityStep

        # Acceptance is best-effort
        assert pipeline[8].is_critical is False  # ValidateAcceptanceStep

        # PR step is best-effort
        assert pipeline[9].is_critical is False  # PreparePullRequestStep

    def test_critical_flags_with_github(self, monkeypatch):
        """Test critical/best-effort flags with GitHub platform."""
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        pipeline = get_default_pipeline()

        # First 5 steps should be critical (setup, fetch, classify, plan, implement)
        for step in pipeline[:5]:
            assert step.is_critical is True, f"{step.name} should be critical"

        # Review steps are not critical
        assert pipeline[5].is_critical is False  # GenerateReviewStep
        assert pipeline[6].is_critical is False  # AddressReviewStep

        # Quality is best-effort
        assert pipeline[7].is_critical is False  # CodeQualityStep

        # Acceptance is best-effort
        assert pipeline[8].is_critical is False  # ValidateAcceptanceStep

        # PR steps are best-effort
        assert pipeline[9].is_critical is False  # PreparePullRequestStep
        assert pipeline[10].is_critical is False  # CreateGitHubPullRequestStep

    def test_critical_flags_with_gitlab(self, monkeypatch):
        """Test critical/best-effort flags with GitLab platform."""
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "gitlab")
        pipeline = get_default_pipeline()

        # First 5 steps should be critical (setup, fetch, classify, plan, implement)
        for step in pipeline[:5]:
            assert step.is_critical is True, f"{step.name} should be critical"

        # Review steps are not critical
        assert pipeline[5].is_critical is False  # GenerateReviewStep
        assert pipeline[6].is_critical is False  # AddressReviewStep

        # Quality is best-effort
        assert pipeline[7].is_critical is False  # CodeQualityStep

        # Acceptance is best-effort
        assert pipeline[8].is_critical is False  # ValidateAcceptanceStep

        # PR steps are best-effort
        assert pipeline[9].is_critical is False  # PreparePullRequestStep
        assert pipeline[10].is_critical is False  # CreateGitLabPullRequestStep

    def test_includes_github_step_when_platform_is_github(self, monkeypatch):
        """Test pipeline includes CreateGitHubPullRequestStep when DEV_SEC_OPS_PLATFORM=github."""
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        pipeline = get_default_pipeline()

        from rouge.core.workflow.steps.create_github_pr import (
            CreateGitHubPullRequestStep,
        )

        assert isinstance(pipeline[-1], CreateGitHubPullRequestStep)

    def test_includes_gitlab_step_when_platform_is_gitlab(self, monkeypatch):
        """Test pipeline includes CreateGitLabPullRequestStep when DEV_SEC_OPS_PLATFORM=gitlab."""
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "gitlab")
        pipeline = get_default_pipeline()

        from rouge.core.workflow.steps.create_gitlab_pr import (
            CreateGitLabPullRequestStep,
        )

        assert isinstance(pipeline[-1], CreateGitLabPullRequestStep)

    def test_excludes_pr_step_when_platform_unset(self, monkeypatch):
        """Test pipeline excludes PR/MR step when DEV_SEC_OPS_PLATFORM is unset."""
        monkeypatch.delenv("DEV_SEC_OPS_PLATFORM", raising=False)
        pipeline = get_default_pipeline()

        from rouge.core.workflow.steps.create_github_pr import (
            CreateGitHubPullRequestStep,
        )
        from rouge.core.workflow.steps.create_gitlab_pr import (
            CreateGitLabPullRequestStep,
        )

        # Verify no PR/MR creation step is in the pipeline
        for step in pipeline:
            assert not isinstance(step, CreateGitHubPullRequestStep)
            assert not isinstance(step, CreateGitLabPullRequestStep)

    def test_platform_env_var_case_insensitive(self, monkeypatch):
        """Test DEV_SEC_OPS_PLATFORM is handled case-insensitively."""
        from rouge.core.workflow.steps.create_github_pr import (
            CreateGitHubPullRequestStep,
        )
        from rouge.core.workflow.steps.create_gitlab_pr import (
            CreateGitLabPullRequestStep,
        )

        # Test uppercase GITHUB
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "GITHUB")
        pipeline = get_default_pipeline()
        assert isinstance(pipeline[-1], CreateGitHubPullRequestStep)

        # Test mixed case GitLab
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "GitLab")
        pipeline = get_default_pipeline()
        assert isinstance(pipeline[-1], CreateGitLabPullRequestStep)


# Patch workflow pipeline tests


def test_get_patch_pipeline():
    """Test get_patch_pipeline returns correct steps."""
    from rouge.core.workflow.pipeline import get_patch_pipeline

    pipeline = get_patch_pipeline()

    # Verify pipeline contains expected steps
    step_names = [step.name for step in pipeline]

    # Check for patch-specific steps
    assert "Fetching pending patch" in step_names

    # Check for implementation and review steps
    assert "Implementing solution" in step_names
    assert "Generating CodeRabbit review" in step_names

    # Verify setup and classify steps are NOT in patch pipeline
    assert "Fetching issue" not in step_names
    assert "Classifying issue" not in step_names
    assert "Building plan" not in step_names


class TestPatchWorkflowArtifactIsolation:
    """Integration tests for patch workflow artifact isolation.

    Verifies that patch workflows can read shared artifacts from parent
    workflows while maintaining isolation for patch-specific artifacts.
    """

    def test_patch_workflow_runner_passes_parent_id_to_artifact_store(self, tmp_path):
        """Test WorkflowRunner.run creates ArtifactStore with parent_workflow_id."""
        from rouge.core.workflow.artifacts import (
            ArtifactStore,
            IssueArtifact,
            PlanArtifact,
        )
        from rouge.core.workflow.types import PlanData

        # Setup main workflow with shared artifacts
        main_store = ArtifactStore("main-workflow-001", base_path=tmp_path)
        from rouge.core.models import Issue

        main_issue = Issue(id=100, description="Main issue for testing")
        main_store.write_artifact(IssueArtifact(workflow_id="main-workflow-001", issue=main_issue))

        plan_data = PlanData(
            plan="# Implementation Plan\n\nSteps to implement feature...",
            summary="Feature implementation plan",
            session_id="session-main",
        )
        main_store.write_artifact(
            PlanArtifact(workflow_id="main-workflow-001", plan_data=plan_data)
        )

        # Create patch workflow store with parent_workflow_id
        patch_store = ArtifactStore(
            "patch-workflow-001",
            base_path=tmp_path,
            parent_workflow_id="main-workflow-001",
        )

        # Verify patch workflow can read shared artifacts from parent
        issue_artifact = patch_store.read_artifact("issue", IssueArtifact)
        assert issue_artifact.issue.id == 100
        assert issue_artifact.issue.description == "Main issue for testing"

        plan_artifact = patch_store.read_artifact("plan", PlanArtifact)
        assert plan_artifact.plan_data.summary == "Feature implementation plan"

    def test_patch_workflow_writes_to_own_directory(self, tmp_path):
        """Test patch workflow writes implementation/review to its own directory."""
        from rouge.core.workflow.artifacts import (
            ArtifactStore,
            ImplementationArtifact,
            IssueArtifact,
            PlanArtifact,
            ReviewArtifact,
        )
        from rouge.core.workflow.types import ImplementData, PlanData, ReviewData

        # Setup main workflow with shared artifacts
        main_store = ArtifactStore("main-workflow-002", base_path=tmp_path)
        from rouge.core.models import Issue

        main_store.write_artifact(
            IssueArtifact(
                workflow_id="main-workflow-002",
                issue=Issue(id=200, description="Main issue"),
            )
        )
        main_store.write_artifact(
            PlanArtifact(
                workflow_id="main-workflow-002",
                plan_data=PlanData(plan="Main plan", summary="Summary"),
            )
        )
        # Main workflow also has implementation
        main_store.write_artifact(
            ImplementationArtifact(
                workflow_id="main-workflow-002",
                implement_data=ImplementData(output="Main implementation output"),
            )
        )

        # Create patch workflow with parent reference
        patch_store = ArtifactStore(
            "patch-workflow-002",
            base_path=tmp_path,
            parent_workflow_id="main-workflow-002",
        )

        # Write patch-specific artifacts
        patch_store.write_artifact(
            ImplementationArtifact(
                workflow_id="patch-workflow-002",
                implement_data=ImplementData(output="Patch implementation output"),
            )
        )
        patch_store.write_artifact(
            ReviewArtifact(
                workflow_id="patch-workflow-002",
                review_data=ReviewData(review_text="Patch review content"),
            )
        )

        # Verify artifacts were written to patch directory
        patch_impl_path = tmp_path / "patch-workflow-002" / "implementation.json"
        patch_review_path = tmp_path / "patch-workflow-002" / "review.json"
        assert patch_impl_path.exists()
        assert patch_review_path.exists()

        # Verify patch store reads its own implementation (not parent's)
        patch_impl = patch_store.read_artifact("implementation", ImplementationArtifact)
        assert patch_impl.implement_data.output == "Patch implementation output"

    def test_main_workflow_unchanged_after_patch_operations(self, tmp_path):
        """Test main workflow artifacts remain unchanged after patch workflow operations."""
        from rouge.core.workflow.artifacts import (
            ArtifactStore,
            ImplementationArtifact,
            IssueArtifact,
            PlanArtifact,
            ReviewArtifact,
        )
        from rouge.core.workflow.types import ImplementData, PlanData, ReviewData

        # Setup main workflow with artifacts
        main_store = ArtifactStore("main-workflow-003", base_path=tmp_path)
        from rouge.core.models import Issue

        original_issue = Issue(id=300, description="Original main issue")
        original_plan_data = PlanData(plan="Original plan content", summary="Original summary")
        original_impl_data = ImplementData(output="Original implementation")
        original_review_data = ReviewData(review_text="Original review")

        main_store.write_artifact(
            IssueArtifact(workflow_id="main-workflow-003", issue=original_issue)
        )
        main_store.write_artifact(
            PlanArtifact(workflow_id="main-workflow-003", plan_data=original_plan_data)
        )
        main_store.write_artifact(
            ImplementationArtifact(
                workflow_id="main-workflow-003", implement_data=original_impl_data
            )
        )
        main_store.write_artifact(
            ReviewArtifact(workflow_id="main-workflow-003", review_data=original_review_data)
        )

        # Create patch workflow and write new artifacts
        patch_store = ArtifactStore(
            "patch-workflow-003",
            base_path=tmp_path,
            parent_workflow_id="main-workflow-003",
        )

        # Patch workflow writes its own implementation and review
        patch_store.write_artifact(
            ImplementationArtifact(
                workflow_id="patch-workflow-003",
                implement_data=ImplementData(output="Patch implementation - different"),
            )
        )
        patch_store.write_artifact(
            ReviewArtifact(
                workflow_id="patch-workflow-003",
                review_data=ReviewData(review_text="Patch review - different"),
            )
        )

        # Verify main workflow artifacts are unchanged
        main_issue = main_store.read_artifact("issue", IssueArtifact)
        main_plan = main_store.read_artifact("plan", PlanArtifact)
        main_impl = main_store.read_artifact("implementation", ImplementationArtifact)
        main_review = main_store.read_artifact("review", ReviewArtifact)

        assert main_issue.issue.id == 300
        assert main_issue.issue.description == "Original main issue"
        assert main_plan.plan_data.plan == "Original plan content"
        assert main_plan.plan_data.summary == "Original summary"
        assert main_impl.implement_data.output == "Original implementation"
        assert main_review.review_data.review_text == "Original review"

    def test_patch_specific_artifacts_do_not_fallback_to_parent(self, tmp_path):
        """Test patch-specific artifacts (implementation, review) don't fall back to parent."""
        import pytest

        from rouge.core.workflow.artifacts import (
            ArtifactStore,
            ImplementationArtifact,
            IssueArtifact,
            ReviewArtifact,
        )
        from rouge.core.workflow.types import ImplementData, ReviewData

        # Setup main workflow with all artifacts
        main_store = ArtifactStore("main-workflow-004", base_path=tmp_path)
        from rouge.core.models import Issue

        main_store.write_artifact(
            IssueArtifact(
                workflow_id="main-workflow-004",
                issue=Issue(id=400, description="Main issue"),
            )
        )
        main_store.write_artifact(
            ImplementationArtifact(
                workflow_id="main-workflow-004",
                implement_data=ImplementData(output="Main implementation"),
            )
        )
        main_store.write_artifact(
            ReviewArtifact(
                workflow_id="main-workflow-004",
                review_data=ReviewData(review_text="Main review"),
            )
        )

        # Create patch workflow with parent reference (no artifacts yet)
        patch_store = ArtifactStore(
            "patch-workflow-004",
            base_path=tmp_path,
            parent_workflow_id="main-workflow-004",
        )

        # Shared artifacts (issue) should fall back to parent
        issue = patch_store.read_artifact("issue", IssueArtifact)
        assert issue.issue.id == 400

        # Patch-specific artifacts should NOT fall back
        with pytest.raises(FileNotFoundError, match="Artifact not found: implementation"):
            patch_store.read_artifact("implementation", ImplementationArtifact)

        with pytest.raises(FileNotFoundError, match="Artifact not found: review"):
            patch_store.read_artifact("review", ReviewArtifact)

    def test_workflow_runner_with_parent_workflow_id(self, tmp_path, monkeypatch):
        """Test WorkflowRunner.run passes parent_workflow_id to ArtifactStore."""
        from rouge.core.workflow.artifacts import (
            ArtifactStore,
            IssueArtifact,
            PlanArtifact,
        )
        from rouge.core.workflow.pipeline import WorkflowRunner
        from rouge.core.workflow.step_base import WorkflowStep
        from rouge.core.workflow.types import PlanData, StepResult

        # Set ROUGE_DATA_DIR to tmp_path for this test
        monkeypatch.setenv("ROUGE_DATA_DIR", str(tmp_path / "data"))

        # Create base workflows dir
        workflows_dir = tmp_path / "data" / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)

        # Setup main workflow with shared artifacts using explicit base_path
        main_store = ArtifactStore("main-adw-005", base_path=workflows_dir)
        from rouge.core.models import Issue

        main_store.write_artifact(
            IssueArtifact(
                workflow_id="main-adw-005",
                issue=Issue(id=500, description="Main workflow issue"),
            )
        )
        main_store.write_artifact(
            PlanArtifact(
                workflow_id="main-adw-005",
                plan_data=PlanData(plan="Main plan", summary="Main summary"),
            )
        )

        # Create a mock step that captures the context
        captured_context = None

        class CapturingStep(WorkflowStep):
            name = "Capturing step"
            is_critical = True

            def run(self, context):
                nonlocal captured_context
                captured_context = context
                return StepResult.ok(None)

        # Run workflow with parent_workflow_id
        runner = WorkflowRunner([CapturingStep()])
        result = runner.run(
            issue_id=500,
            adw_id="patch-adw-005",
            parent_workflow_id="main-adw-005",
        )

        assert result is True
        assert captured_context is not None
        assert captured_context.artifact_store is not None

        # Verify the artifact store can read from parent
        issue = captured_context.artifact_store.read_artifact("issue", IssueArtifact)
        assert issue.issue.id == 500

        plan = captured_context.artifact_store.read_artifact("plan", PlanArtifact)
        assert plan.plan_data.summary == "Main summary"

    def test_multiple_patch_workflows_isolated_from_each_other(self, tmp_path):
        """Test multiple patch workflows are isolated from each other."""
        from rouge.core.workflow.artifacts import (
            ArtifactStore,
            ImplementationArtifact,
            IssueArtifact,
            PlanArtifact,
        )
        from rouge.core.workflow.types import ImplementData, PlanData

        # Setup main workflow
        main_store = ArtifactStore("main-workflow-006", base_path=tmp_path)
        from rouge.core.models import Issue

        main_store.write_artifact(
            IssueArtifact(
                workflow_id="main-workflow-006",
                issue=Issue(id=600, description="Shared issue"),
            )
        )
        main_store.write_artifact(
            PlanArtifact(
                workflow_id="main-workflow-006",
                plan_data=PlanData(plan="Shared plan", summary="Shared summary"),
            )
        )

        # Create two patch workflows
        patch_store_1 = ArtifactStore(
            "patch-workflow-006-a",
            base_path=tmp_path,
            parent_workflow_id="main-workflow-006",
        )
        patch_store_2 = ArtifactStore(
            "patch-workflow-006-b",
            base_path=tmp_path,
            parent_workflow_id="main-workflow-006",
        )

        # Both can read shared artifacts from parent
        issue_1 = patch_store_1.read_artifact("issue", IssueArtifact)
        issue_2 = patch_store_2.read_artifact("issue", IssueArtifact)
        assert issue_1.issue.id == 600
        assert issue_2.issue.id == 600

        # Write different implementations to each patch workflow
        patch_store_1.write_artifact(
            ImplementationArtifact(
                workflow_id="patch-workflow-006-a",
                implement_data=ImplementData(output="Patch A implementation"),
            )
        )
        patch_store_2.write_artifact(
            ImplementationArtifact(
                workflow_id="patch-workflow-006-b",
                implement_data=ImplementData(output="Patch B implementation"),
            )
        )

        # Verify each patch workflow reads its own implementation
        impl_1 = patch_store_1.read_artifact("implementation", ImplementationArtifact)
        impl_2 = patch_store_2.read_artifact("implementation", ImplementationArtifact)
        assert impl_1.implement_data.output == "Patch A implementation"
        assert impl_2.implement_data.output == "Patch B implementation"

        # Verify isolation - artifacts are in separate directories
        assert (tmp_path / "patch-workflow-006-a" / "implementation.json").exists()
        assert (tmp_path / "patch-workflow-006-b" / "implementation.json").exists()
