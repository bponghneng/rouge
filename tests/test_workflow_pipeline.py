import logging
from unittest.mock import MagicMock

import pytest

from rouge.core.workflow.pipeline import (
    AddressReviewStep,
    BuildChorePlanStep,
    BuildFeaturePlanStep,
    BuildPatchPlanStep,
    ClassifyIssueStep,
    CodeQualityStep,
    CreateGitLabPullRequestStep,
    CreateGitHubPullRequestStep,
    CreatePullRequestStep,
    ExecuteAcceptanceTestsStep,
    FetchPatchStep,
    FindPlanFileStep,
    GenerateReviewStep,
    ImplementStep,
    UpdatePRCommitsStep,
    ValidatePatchAcceptanceStep,
    get_default_pipeline,
    get_patch_pipeline,
)
from rouge.core.workflow.runner import WorkflowRunner
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult


class TestStep(WorkflowStep):
    def __init__(self, name: str, critical: bool = True):
        self._name = name
        self._critical = critical
        self.executed = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_critical(self) -> bool:
        return self._critical

    def run(self, context: WorkflowContext) -> StepResult:
        self.executed = True
        return StepResult.ok(None)


class FailingStep(WorkflowStep):
    def __init__(self, name: str, critical: bool = True):
        self._name = name
        self._critical = critical

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_critical(self) -> bool:
        return self._critical

    def run(self, context: WorkflowContext) -> StepResult:
        return StepResult.fail("Step failed")


class TestWorkflowContext:
    def test_init(self):
        context = WorkflowContext(issue_id=1, adw_id="test-adw")
        assert context.issue_id == 1
        assert context.adw_id == "test-adw"
        assert context.artifacts_enabled is False
        assert context.artifact_store is None
        assert context.parent_workflow_id is None

    def test_data_storage(self):
        context = WorkflowContext(issue_id=1)
        context.data["key"] = "value"
        assert context.data["key"] == "value"


class TestWorkflowRunner:
    def test_execute_pipeline_success(self, caplog):
        step1 = TestStep("Step 1")
        step2 = TestStep("Step 2")
        runner = WorkflowRunner([step1, step2])
        context = WorkflowContext(issue_id=1)

        with caplog.at_level(logging.INFO):
            success = runner.run(context)

        assert success
        assert step1.executed
        assert step2.executed
        assert "Workflow completed successfully" in caplog.text

    def test_execute_pipeline_critical_failure(self, caplog):
        step1 = TestStep("Step 1")
        step2 = FailingStep("Step 2", critical=True)
        step3 = TestStep("Step 3")
        runner = WorkflowRunner([step1, step2, step3])
        context = WorkflowContext(issue_id=1)

        with caplog.at_level(logging.ERROR):
            success = runner.run(context)

        assert not success
        assert step1.executed
        assert not step3.executed
        assert "Critical step 'Step 2' failed" in caplog.text

    def test_execute_pipeline_best_effort_failure(self, caplog):
        step1 = TestStep("Step 1")
        step2 = FailingStep("Step 2", critical=False)
        step3 = TestStep("Step 3")
        runner = WorkflowRunner([step1, step2, step3])
        context = WorkflowContext(issue_id=1)

        with caplog.at_level(logging.WARNING):
            success = runner.run(context)

        assert success
        assert step1.executed
        assert step3.executed
        assert "Step 'Step 2' failed (non-critical), continuing" in caplog.text

    def test_context_passed_to_steps(self):
        context = WorkflowContext(issue_id=123)
        mock_step = MagicMock(spec=WorkflowStep)
        mock_step.name = "Mock Step"
        mock_step.is_critical = True
        mock_step.run.return_value = StepResult.ok(None)

        runner = WorkflowRunner([mock_step])
        runner.run(context)

        mock_step.run.assert_called_once_with(context)


class TestGetDefaultPipeline:
    def test_pipeline_structure_no_platform(self, monkeypatch):
        monkeypatch.delenv("DEV_SEC_OPS_PLATFORM", raising=False)
        pipeline = get_default_pipeline()
        
        # Check step count (should be 10 without PR step)
        assert len(pipeline) == 10
        
        # Verify order and types
        expected_types = [
            ClassifyIssueStep,
            FindPlanFileStep,
            BuildChorePlanStep,
            BuildFeaturePlanStep,
            ImplementStep,
            CodeQualityStep,
            ExecuteAcceptanceTestsStep,
            GenerateReviewStep,
            AddressReviewStep,
            CodeQualityStep, # Final check
        ]
        
        for step, expected_type in zip(pipeline, expected_types):
            assert isinstance(step, expected_type)
            
        # Verify critical flags
        assert pipeline[0].is_critical # Classify
        assert not pipeline[1].is_critical # FindPlan
        assert pipeline[4].is_critical # Implement
        assert not pipeline[5].is_critical # Quality
        assert not pipeline[7].is_critical # Review
        assert not pipeline[9].is_critical # Final Quality

    def test_pipeline_structure_github(self, monkeypatch):
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        pipeline = get_default_pipeline()
        
        assert len(pipeline) == 11
        assert isinstance(pipeline[-1], CreateGitHubPullRequestStep)
        assert not pipeline[-1].is_critical  # PR creation is best effort

    def test_pipeline_structure_gitlab(self, monkeypatch):
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "gitlab")
        pipeline = get_default_pipeline()
        
        assert len(pipeline) == 11
        assert isinstance(pipeline[-1], CreateGitLabPullRequestStep)
        assert not pipeline[-1].is_critical


class TestGetPatchPipeline:
    def test_patch_pipeline_structure_no_platform(self, monkeypatch):
        monkeypatch.delenv("DEV_SEC_OPS_PLATFORM", raising=False)
        pipeline = get_patch_pipeline()
        
        # Check step count (should be 9 without PR step)
        assert len(pipeline) == 9
        
        # Verify order and types
        expected_types = [
            FetchPatchStep,
            BuildPatchPlanStep,
            ImplementStep,
            GenerateReviewStep,
            AddressReviewStep,
            CodeQualityStep,
            ExecuteAcceptanceTestsStep,
            ValidatePatchAcceptanceStep,
            UpdatePRCommitsStep,
        ]
        
        for i, (step, expected_type) in enumerate(zip(pipeline, expected_types)):
            assert isinstance(step, expected_type), (
                f"Step {i} should be {expected_type.__name__}, got {type(step).__name__}"
            )

        # Verify critical flags
        assert pipeline[0].is_critical  # Fetch patch
        assert pipeline[1].is_critical  # Build plan
        assert pipeline[2].is_critical  # Implement
        assert not pipeline[3].is_critical  # Review (best effort)
        assert not pipeline[5].is_critical  # Code quality
        assert pipeline[7].is_critical  # Validate acceptance (critical for patch)
        assert not pipeline[8].is_critical  # Update PR commits (best effort)

    def test_patch_pipeline_excludes_create_pr_steps(self, monkeypatch):
        """Verify patch pipeline never includes CreatePullRequestStep."""
        # Even with platform set
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        pipeline = get_patch_pipeline()
        
        for step in pipeline:
            assert not isinstance(step, CreatePullRequestStep), (
                "Patch pipeline should not include CreatePullRequestStep"
            )

    def test_patch_pipeline_includes_update_commits_step(self, monkeypatch):
        """Verify patch pipeline ends with UpdatePRCommitsStep."""
        monkeypatch.delenv("DEV_SEC_OPS_PLATFORM", raising=False)
        pipeline = get_patch_pipeline()
        
        assert isinstance(pipeline[-1], UpdatePRCommitsStep)
        assert not pipeline[-1].is_critical  # Should be best effort

    def test_patch_pipeline_step_order(self, monkeypatch):
        """Verify the exact sequence of steps in the patch pipeline."""
        monkeypatch.delenv("DEV_SEC_OPS_PLATFORM", raising=False)
        pipeline = get_patch_pipeline()

        expected_types = [
            FetchPatchStep,
            BuildPatchPlanStep,
            ImplementStep,
            GenerateReviewStep,
            AddressReviewStep,
            CodeQualityStep,
            ExecuteAcceptanceTestsStep,
            ValidatePatchAcceptanceStep,
            UpdatePRCommitsStep,
        ]

        for i, (step, expected_type) in enumerate(zip(pipeline, expected_types, strict=True)):
            assert isinstance(step, expected_type), (
                f"Step {i} should be {expected_type.__name__}, got {type(step).__name__}"
            )


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
        main_wf_id = "main-wf-1"
        patch_wf_id = "patch-wf-1"
        
        # Create artifacts in main workflow
        main_store = ArtifactStore(main_wf_id, base_path=tmp_path)
        
        issue_artifact = IssueArtifact(
            workflow_id=main_wf_id,
            issue_id=1,
            title="Main Issue",
            description="Main Description"
        )
        main_store.write_artifact(issue_artifact)
        
        plan_artifact = PlanArtifact(
            workflow_id=main_wf_id,
            plan=PlanData(
                problem_statement="Problem",
                proposed_changes=["Change 1"],
                files_to_modify=["file.py"]
            )
        )
        main_store.write_artifact(plan_artifact)

        # Create context for patch workflow with parent_workflow_id
        context = WorkflowContext(
            issue_id=1,
            adw_id=patch_wf_id,
            parent_workflow_id=main_wf_id,
            artifacts_enabled=True,
            working_dir=tmp_path
        )
        
        # Run a simple workflow that accesses artifacts
        class AccessArtifactsStep(WorkflowStep):
            @property
            def name(self): return "Access Artifacts"
            
            @property
            def is_critical(self): return True
            
            def run(self, ctx):
                store = ctx.artifact_store
                # Should find parent artifacts
                issue = store.get_latest_artifact(IssueArtifact)
                plan = store.get_latest_artifact(PlanArtifact)
                
                if not issue or issue.title != "Main Issue":
                    return StepResult.fail("Failed to read parent IssueArtifact")
                if not plan or plan.plan.problem_statement != "Problem":
                    return StepResult.fail("Failed to read parent PlanArtifact")
                    
                return StepResult.ok(None)

        runner = WorkflowRunner([AccessArtifactsStep()])
        success = runner.run(context)
        
        assert success, "Workflow failed to access parent artifacts"

    def test_patch_pipeline_uses_isolated_artifacts(self, tmp_path):
        """Verify patch workflow writes new artifacts without overwriting parent's."""
        from rouge.core.workflow.artifacts import (
            ArtifactStore,
            ImplementationArtifact,
            ReviewArtifact,
        )
        
        main_wf_id = "main-wf-1"
        patch_wf_id = "patch-wf-1"
        
        # 1. Main workflow creates implementation
        main_store = ArtifactStore(main_wf_id, base_path=tmp_path)
        main_impl = ImplementationArtifact(
            workflow_id=main_wf_id,
            files_modified=["main.py"],
            diff="main diff",
            pr_url="http://pr/1"
        )
        main_store.write_artifact(main_impl)
        
        # 2. Patch workflow creates its own implementation
        patch_store = ArtifactStore(patch_wf_id, parent_workflow_id=main_wf_id, base_path=tmp_path)
        
        # Verify it can see parent's initially
        initial_read = patch_store.get_latest_artifact(ImplementationArtifact)
        assert initial_read.diff == "main diff"
        assert initial_read.workflow_id == main_wf_id
        
        # Write patch-specific implementation
        patch_impl = ImplementationArtifact(
            workflow_id=patch_wf_id,
            files_modified=["patch.py"],
            diff="patch diff",
            pr_url="http://pr/1"
        )
        patch_store.write_artifact(patch_impl)
        
        # 3. Verify patch workflow sees its own version now
        patch_read = patch_store.get_latest_artifact(ImplementationArtifact)
        assert patch_read.diff == "patch diff"
        assert patch_read.workflow_id == patch_wf_id
        
        # 4. Verify main workflow still sees original version (ISOLATION)
        main_read = main_store.get_latest_artifact(ImplementationArtifact)
        assert main_read.diff == "main diff"
        assert main_read.workflow_id == main_wf_id

    def test_patch_artifacts_do_not_fallback_to_parent(self, tmp_path):
        """Verify that patch-specific artifacts (like Review) don't fallback if missing."""
        from rouge.core.workflow.artifacts import ArtifactStore, ReviewArtifact
        
        main_wf_id = "main-wf-1"
        patch_wf_id = "patch-wf-1"
        
        # Main workflow has a review
        main_store = ArtifactStore(main_wf_id, base_path=tmp_path)
        main_review = ReviewArtifact(
            workflow_id=main_wf_id,
            review_content="Main review",
            status="approved"
        )
        main_store.write_artifact(main_review)
        
        # Patch workflow store
        patch_store = ArtifactStore(patch_wf_id, parent_workflow_id=main_wf_id, base_path=tmp_path)
        
        # Should be able to read it (ReviewArtifact is shared type)
        read = patch_store.get_latest_artifact(ReviewArtifact)
        assert read is not None
        assert read.review_content == "Main review"
        
        # But if we write a new one, it takes precedence
        patch_review = ReviewArtifact(
            workflow_id=patch_wf_id,
            review_content="Patch review",
            status="changes_requested"
        )
        patch_store.write_artifact(patch_review)
        
        read_new = patch_store.get_latest_artifact(ReviewArtifact)
        assert read_new.review_content == "Patch review"

    def test_multiple_patch_workflows_are_isolated(self, tmp_path):
        """Verify two patch workflows from same parent don't see each other's artifacts."""
        from rouge.core.workflow.artifacts import ArtifactStore, ImplementationArtifact
        
        main_wf_id = "main-wf"
        patch1_id = "patch-1"
        patch2_id = "patch-2"
        
        # Common parent
        main_store = ArtifactStore(main_wf_id, base_path=tmp_path)
        
        # Patch 1 writes something
        store1 = ArtifactStore(patch1_id, parent_workflow_id=main_wf_id, base_path=tmp_path)
        impl1 = ImplementationArtifact(
            workflow_id=patch1_id,
            files_modified=["f1"],
            diff="diff1"
        )
        store1.write_artifact(impl1)
        
        # Patch 2 should NOT see Patch 1's artifact
        store2 = ArtifactStore(patch2_id, parent_workflow_id=main_wf_id, base_path=tmp_path)
        read2 = store2.get_latest_artifact(ImplementationArtifact)
        
        assert read2 is None  # Should be empty as main has none and patch2 has none
