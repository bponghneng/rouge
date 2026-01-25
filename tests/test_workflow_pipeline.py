import logging
import os
from unittest.mock import MagicMock, patch

import pytest

from rouge.core.models import Issue
from rouge.core.workflow.pipeline import (
    WorkflowRunner,
    get_default_pipeline,
    get_patch_pipeline,
)
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.steps import (
    AddressReviewStep,
    BuildPlanStep,
    ClassifyStep,
    CodeQualityStep,
    FetchIssueStep,
    FetchPatchStep,
    GenerateReviewStep,
    ImplementStep,
    PreparePullRequestStep,
    SetupStep,
    ValidateAcceptanceStep,
)
from rouge.core.workflow.steps.create_github_pr import CreateGitHubPullRequestStep
from rouge.core.workflow.steps.create_gitlab_pr import CreateGitLabPullRequestStep
from rouge.core.workflow.steps.patch_acceptance import ValidatePatchAcceptanceStep
from rouge.core.workflow.steps.patch_plan import BuildPatchPlanStep
from rouge.core.workflow.steps.update_pr_commits import UpdatePRCommitsStep
from rouge.core.workflow.types import ImplementData, PatchPlanData, PlanData, ReviewData, StepResult


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

    def test_data_storage(self):
        context = WorkflowContext(issue_id=1, adw_id="test-adw")
        context.data["key"] = "value"
        assert context.data["key"] == "value"


class TestWorkflowRunner:
    def test_execute_pipeline_success(self, caplog, tmp_path):
        step1 = TestStep("Step 1")
        step2 = TestStep("Step 2")
        runner = WorkflowRunner([step1, step2])

        with caplog.at_level(logging.INFO):
            with pytest.MonkeyPatch.context() as mp:
                mp.setenv("ROUGE_DATA_DIR", str(tmp_path))
                success = runner.run(issue_id=1, adw_id="test-adw-1")

        assert success
        assert step1.executed
        assert step2.executed
        assert "Workflow completed successfully" in caplog.text

    def test_execute_pipeline_critical_failure(self, caplog, tmp_path):
        step1 = TestStep("Step 1")
        step2 = FailingStep("Step 2", critical=True)
        step3 = TestStep("Step 3")
        runner = WorkflowRunner([step1, step2, step3])

        with caplog.at_level(logging.ERROR):
            with pytest.MonkeyPatch.context() as mp:
                mp.setenv("ROUGE_DATA_DIR", str(tmp_path))
                success = runner.run(issue_id=1, adw_id="test-adw-2")

        assert not success
        assert step1.executed
        assert not step3.executed
        assert "Critical step 'Step 2' failed" in caplog.text

    def test_execute_pipeline_best_effort_failure(self, caplog, tmp_path):
        step1 = TestStep("Step 1")
        step2 = FailingStep("Step 2", critical=False)
        step3 = TestStep("Step 3")
        runner = WorkflowRunner([step1, step2, step3])

        with caplog.at_level(logging.WARNING):
            with pytest.MonkeyPatch.context() as mp:
                mp.setenv("ROUGE_DATA_DIR", str(tmp_path))
                success = runner.run(issue_id=1, adw_id="test-adw-3")

        assert success
        assert step1.executed
        assert step3.executed
        assert "Best-effort step 'Step 2' failed" in caplog.text

    def test_context_passed_to_steps(self, tmp_path):
        mock_step = MagicMock(spec=WorkflowStep)
        mock_step.name = "Mock Step"
        mock_step.is_critical = True
        mock_step.run.return_value = StepResult.ok(None)

        runner = WorkflowRunner([mock_step])
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("ROUGE_DATA_DIR", str(tmp_path))
            runner.run(issue_id=123, adw_id="test-adw-4")

        mock_step.run.assert_called_once()
        call_args = mock_step.run.call_args[0][0]
        assert isinstance(call_args, WorkflowContext)
        assert call_args.issue_id == 123
        assert call_args.adw_id == "test-adw-4"


class TestGetDefaultPipeline:
    def test_pipeline_structure_no_platform(self, monkeypatch):
        monkeypatch.delenv("DEV_SEC_OPS_PLATFORM", raising=False)
        pipeline = get_default_pipeline()

        # Check step count (should be 10 without PR step)
        assert len(pipeline) == 10

        # Verify order and types
        expected_types = [
            SetupStep,
            FetchIssueStep,
            ClassifyStep,
            BuildPlanStep,
            ImplementStep,
            GenerateReviewStep,
            AddressReviewStep,
            CodeQualityStep,
            ValidateAcceptanceStep,
            PreparePullRequestStep,
        ]

        for i, (step, expected_type) in enumerate(zip(pipeline, expected_types, strict=True)):
            assert isinstance(step, expected_type), (
                f"Step {i} should be {expected_type.__name__}, got {type(step).__name__}"
            )

        # Verify critical flags
        assert pipeline[0].is_critical  # Setup
        assert pipeline[1].is_critical  # Fetch
        assert pipeline[2].is_critical  # Classify
        assert pipeline[3].is_critical  # Plan
        assert pipeline[4].is_critical  # Implement
        assert not pipeline[7].is_critical  # Quality

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

        # Check step count (should be 8 steps)
        assert len(pipeline) == 8

        # Verify order and types
        expected_types = [
            FetchPatchStep,
            BuildPatchPlanStep,
            ImplementStep,
            GenerateReviewStep,
            AddressReviewStep,
            CodeQualityStep,
            ValidatePatchAcceptanceStep,
            UpdatePRCommitsStep,
        ]

        for i, (step, expected_type) in enumerate(zip(pipeline, expected_types, strict=True)):
            assert isinstance(step, expected_type), (
                f"Step {i} should be {expected_type.__name__}, got {type(step).__name__}"
            )

        # Verify critical flags
        assert pipeline[0].is_critical  # Fetch patch
        assert pipeline[1].is_critical  # Build patch plan
        assert pipeline[2].is_critical  # Implement
        assert not pipeline[3].is_critical  # Review (best effort)
        assert not pipeline[4].is_critical  # Address review (best effort)
        assert not pipeline[5].is_critical  # Code quality
        assert not pipeline[6].is_critical  # Validate patch acceptance (best effort)
        assert not pipeline[7].is_critical  # Update PR commits (best effort)

    def test_patch_pipeline_excludes_create_pr_steps(self, monkeypatch):
        """Verify patch pipeline never includes PR creation steps."""
        # Even with platform set
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        pipeline = get_patch_pipeline()

        pr_step_types = (CreateGitHubPullRequestStep, CreateGitLabPullRequestStep)
        for step in pipeline:
            assert not isinstance(step, pr_step_types), (
                "Patch pipeline should not include PR creation steps"
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

    def test_patch_workflow_reads_shared_artifacts_from_parent(self, tmp_path):
        """Test that patch workflows can read shared artifacts (issue, plan) from parent."""
        from rouge.core.models import Issue
        from rouge.core.workflow.artifacts import (
            ArtifactStore,
            IssueArtifact,
            PlanArtifact,
        )

        # Setup main workflow with shared artifacts
        main_wf_id = "main-wf-1"
        patch_wf_id = "patch-wf-1-patch"

        # Create artifacts in main workflow using the same base as WorkflowRunner.
        workflows_dir = tmp_path / ".rouge" / "workflows"
        main_store = ArtifactStore(main_wf_id, base_path=workflows_dir)

        issue_artifact = IssueArtifact(
            workflow_id=main_wf_id,
            issue=Issue(id=1, description="Main Issue"),
        )
        main_store.write_artifact(issue_artifact)

        plan_artifact = PlanArtifact(
            workflow_id=main_wf_id,
            plan_data=PlanData(plan="Problem statement and changes", summary="Main summary"),
        )
        main_store.write_artifact(plan_artifact)

        # Run a simple workflow that accesses artifacts via parent_workflow_id.
        class AccessArtifactsStep(WorkflowStep):
            @property
            def name(self) -> str:
                return "Access Artifacts"

            @property
            def is_critical(self) -> bool:
                return True

            def run(self, ctx: WorkflowContext) -> StepResult:
                store = ctx.artifact_store
                issue = store.read_artifact("issue", IssueArtifact)
                plan = store.read_artifact("plan", PlanArtifact)

                if not issue or issue.issue.description != "Main Issue":
                    return StepResult.fail("Failed to read parent IssueArtifact")
                if not plan or plan.plan_data.summary != "Main summary":
                    return StepResult.fail("Failed to read parent PlanArtifact")

                return StepResult.ok(None)

        with patch.dict(os.environ, {"ROUGE_DATA_DIR": str(tmp_path / ".rouge")}):
            runner = WorkflowRunner([AccessArtifactsStep()])
            success = runner.run(issue_id=1, adw_id=patch_wf_id, parent_workflow_id=main_wf_id)

        assert success, "Workflow failed to access parent artifacts"

    def test_patch_workflow_uses_patch_plan_for_implementation(self, tmp_path):
        """Test that patch workflows use patch_plan (not plan) for implementation."""
        from rouge.core.workflow.artifacts import (
            ArtifactStore,
            PatchPlanArtifact,
            PlanArtifact,
        )
        from rouge.core.workflow.types import PatchPlanData, PlanData

        main_wf_id = "main-wf-1"
        patch_wf_id = "patch-wf-1-patch"

        # Main workflow has a plan
        main_store = ArtifactStore(main_wf_id, base_path=tmp_path)
        main_store.write_artifact(
            PlanArtifact(
                workflow_id=main_wf_id,
                plan_data=PlanData(
                    plan="Original plan for main workflow",
                    summary="Original summary",
                ),
            )
        )

        # Patch workflow has its own patch_plan
        patch_store = ArtifactStore(
            patch_wf_id,
            base_path=tmp_path,
            parent_workflow_id=main_wf_id,
        )
        patch_plan_data = PatchPlanData(
            patch_description="Fix review feedback",
            original_plan_reference=main_wf_id,
            patch_plan_content="Patch-specific plan content",
        )
        patch_store.write_artifact(
            PatchPlanArtifact(
                workflow_id=patch_wf_id,
                patch_plan_data=patch_plan_data,
            )
        )

        # Verify patch_plan exists in patch workflow
        assert patch_store.artifact_exists("patch_plan")

        # Verify patch workflow can read its own patch_plan
        patch_plan = patch_store.read_artifact("patch_plan", PatchPlanArtifact)
        assert patch_plan.patch_plan_data.patch_plan_content == "Patch-specific plan content"

        # Verify plan falls back to parent (but patch_plan does NOT fall back)
        plan = patch_store.read_artifact("plan", PlanArtifact)
        assert plan.plan_data.plan == "Original plan for main workflow"

    def test_patch_workflow_fails_without_pull_request_artifact(self, tmp_path):
        """Test that patch workflow UpdatePRCommitsStep fails when no PR artifact exists."""
        from rouge.core.workflow.artifacts import ArtifactStore

        main_wf_id = "main-wf-1"
        patch_wf_id = "patch-wf-1-patch"

        # Main workflow exists but has no pull_request artifact
        ArtifactStore(main_wf_id, base_path=tmp_path)

        # Patch workflow store
        patch_store = ArtifactStore(
            patch_wf_id,
            base_path=tmp_path,
            parent_workflow_id=main_wf_id,
        )

        # pull_request is a shared artifact type, so it would fall back to parent
        # But since parent doesn't have it either, this should raise FileNotFoundError
        import pytest

        with pytest.raises(FileNotFoundError, match="Artifact not found: pull_request"):
            patch_store.read_artifact("pull_request")

    def test_patch_specific_artifacts_do_not_fallback_to_parent(self, tmp_path):
        """Verify that patch-specific artifacts (implementation, review) don't fallback."""
        from rouge.core.workflow.artifacts import (
            ArtifactStore,
            ImplementationArtifact,
            ReviewArtifact,
        )
        from rouge.core.workflow.types import ImplementData, ReviewData

        main_wf_id = "main-wf-1"
        patch_wf_id = "patch-wf-1-patch"

        # Main workflow has implementation and review
        main_store = ArtifactStore(main_wf_id, base_path=tmp_path)
        main_store.write_artifact(
            ImplementationArtifact(
                workflow_id=main_wf_id,
                implement_data=ImplementData(output="Main implementation output"),
            )
        )
        main_store.write_artifact(
            ReviewArtifact(
                workflow_id=main_wf_id,
                review_data=ReviewData(review_text="Main review content"),
            )
        )

        # Patch workflow store
        patch_store = ArtifactStore(
            patch_wf_id,
            base_path=tmp_path,
            parent_workflow_id=main_wf_id,
        )

        # implementation is patch-specific, should NOT fall back to parent
        import pytest

        with pytest.raises(FileNotFoundError, match="Artifact not found: implementation"):
            patch_store.read_artifact("implementation", ImplementationArtifact)

        # review is patch-specific, should NOT fall back to parent
        with pytest.raises(FileNotFoundError, match="Artifact not found: review"):
            patch_store.read_artifact("review", ReviewArtifact)

    def test_patch_workflow_writes_isolated_artifacts(self, tmp_path):
        """Verify patch workflow writes new artifacts without overwriting parent's."""
        from rouge.core.workflow.artifacts import (
            ArtifactStore,
            ImplementationArtifact,
        )
        from rouge.core.workflow.types import ImplementData

        main_wf_id = "main-wf-1"
        patch_wf_id = "patch-wf-1-patch"

        # 1. Main workflow creates implementation
        main_store = ArtifactStore(main_wf_id, base_path=tmp_path)
        main_impl = ImplementationArtifact(
            workflow_id=main_wf_id,
            implement_data=ImplementData(output="main implementation output"),
        )
        main_store.write_artifact(main_impl)

        # 2. Patch workflow creates its own implementation
        patch_store = ArtifactStore(
            patch_wf_id,
            base_path=tmp_path,
            parent_workflow_id=main_wf_id,
        )

        # Patch-specific artifact should NOT fall back
        import pytest
        with pytest.raises(FileNotFoundError):
            patch_store.read_artifact("implementation", ImplementationArtifact)

        # Write patch-specific implementation
        patch_impl = ImplementationArtifact(
            workflow_id=patch_wf_id,
            implement_data=ImplementData(output="patch implementation output"),
        )
        patch_store.write_artifact(patch_impl)

        # 3. Verify patch workflow sees its own version now
        patch_read = patch_store.read_artifact("implementation", ImplementationArtifact)
        assert patch_read.implement_data.output == "patch implementation output"
        assert patch_read.workflow_id == patch_wf_id

        # 4. Verify main workflow still sees original version (ISOLATION)
        main_read = main_store.read_artifact("implementation", ImplementationArtifact)
        assert main_read.implement_data.output == "main implementation output"
        assert main_read.workflow_id == main_wf_id

    def test_multiple_patch_workflows_are_isolated(self, tmp_path):
        """Verify two patch workflows from same parent don't see each other's artifacts."""
        from rouge.core.workflow.artifacts import (
            ArtifactStore,
            ImplementationArtifact,
        )
        from rouge.core.workflow.types import ImplementData

        main_wf_id = "main-wf"
        patch1_id = "patch-1-patch"
        patch2_id = "patch-2-patch"

        # Common parent (no implementation)
        ArtifactStore(main_wf_id, base_path=tmp_path)

        # Patch 1 writes an implementation
        store1 = ArtifactStore(patch1_id, parent_workflow_id=main_wf_id, base_path=tmp_path)
        impl1 = ImplementationArtifact(
            workflow_id=patch1_id,
            implement_data=ImplementData(output="patch 1 output"),
        )
        store1.write_artifact(impl1)

        # Patch 2 should NOT see Patch 1's artifact (implementation is patch-specific)
        store2 = ArtifactStore(patch2_id, parent_workflow_id=main_wf_id, base_path=tmp_path)

        import pytest

        # Should raise FileNotFoundError since:
        # - patch2 doesn't have implementation locally
        # - main doesn't have implementation
        # - implementation is patch-specific, so no fallback to parent
        with pytest.raises(FileNotFoundError, match="Artifact not found: implementation"):
            store2.read_artifact("implementation", ImplementationArtifact)

    def test_child_artifact_takes_precedence_over_parent_for_shared_types(self, tmp_path):
        """Test that child's artifact takes precedence when both exist (shared types)."""
        from rouge.core.models import Issue
        from rouge.core.workflow.artifacts import ArtifactStore, IssueArtifact

        main_wf_id = "main-wf"
        patch_wf_id = "patch-wf-patch"

        # Parent has an issue
        main_store = ArtifactStore(main_wf_id, base_path=tmp_path)
        main_store.write_artifact(
            IssueArtifact(
                workflow_id=main_wf_id,
                issue=Issue(id=1, description="Parent issue"),
            )
        )

        # Patch workflow creates its own issue (unusual but possible)
        patch_store = ArtifactStore(
            patch_wf_id,
            base_path=tmp_path,
            parent_workflow_id=main_wf_id,
        )
        patch_store.write_artifact(
            IssueArtifact(
                workflow_id=patch_wf_id,
                issue=Issue(id=2, description="Child issue"),
            )
        )

        # Read should return child's artifact (takes precedence)
        read = patch_store.read_artifact("issue", IssueArtifact)
        assert read.issue.id == 2
        assert read.issue.description == "Child issue"

    @patch("rouge.core.workflow.steps.implement.implement_plan")
    def test_implement_step_uses_patch_plan_when_both_artifacts_exist(
        self, mock_implement_plan, tmp_path
    ):
        """Test that ImplementStep uses patch_plan content when both plan and patch_plan exist.

        When a patch workflow has both the original plan artifact (from parent) and
        a patch_plan artifact, the ImplementStep should call implement_plan() with
        the patch_plan_content, not the original plan content.
        """
        from rouge.core.workflow.artifacts import (
            ArtifactStore,
            PatchPlanArtifact,
            PlanArtifact,
        )

        main_wf_id = "main-wf-1"
        patch_wf_id = "patch-wf-1"

        # 1. Create the parent workflow's plan artifact
        main_store = ArtifactStore(main_wf_id, base_path=tmp_path)
        original_plan = PlanArtifact(
            workflow_id=main_wf_id,
            plan_data=PlanData(
                plan="# Original Plan\n\nThis is the original implementation plan.",
                summary="Original plan summary",
            ),
        )
        main_store.write_artifact(original_plan)

        # 2. Create the patch workflow's patch_plan artifact
        patch_store = ArtifactStore(patch_wf_id, parent_workflow_id=main_wf_id, base_path=tmp_path)
        patch_plan = PatchPlanArtifact(
            workflow_id=patch_wf_id,
            patch_plan_data=PatchPlanData(
                patch_description="Fix the bug in the original plan",
                original_plan_reference=main_wf_id,
                patch_plan_content="# Patch Plan\n\nThis is the PATCH implementation plan.",
            ),
        )
        patch_store.write_artifact(patch_plan)

        # 3. Configure mock to return a successful implementation response
        mock_implement_plan.return_value = StepResult.ok(
            ImplementData(output="mock implementation output")
        )

        # 4. Create a WorkflowContext for the patch workflow
        # Note: artifact_store is created with parent_workflow_id for shared artifact access
        context = WorkflowContext(
            issue_id=1,
            adw_id=patch_wf_id,
            artifact_store=patch_store,
        )

        # 5. Run the ImplementStep
        step = ImplementStep()
        result = step.run(context)

        # 6. Verify step succeeded
        assert result.success, f"ImplementStep failed: {result.error}"

        # 7. Verify implement_plan was called with PATCH plan content, not original
        mock_implement_plan.assert_called_once()
        call_args = mock_implement_plan.call_args
        plan_content_arg = call_args[0][0]  # First positional argument

        # The patch plan content should be used
        assert "PATCH implementation plan" in plan_content_arg, (
            f"Expected patch plan content but got: {plan_content_arg}"
        )
        assert "Original Plan" not in plan_content_arg, "Should NOT contain original plan content"

    @patch("rouge.core.workflow.steps.implement.implement_plan")
    def test_implement_step_uses_original_plan_when_no_patch_plan(
        self, mock_implement_plan, tmp_path
    ):
        """Test that ImplementStep uses original plan when no patch_plan exists.

        In a regular (non-patch) workflow, only the plan artifact exists.
        ImplementStep should use the original plan content.
        """
        from rouge.core.workflow.artifacts import ArtifactStore, PlanArtifact

        wf_id = "regular-wf-1"

        # 1. Create only the plan artifact (no patch_plan)
        store = ArtifactStore(wf_id, base_path=tmp_path)
        plan = PlanArtifact(
            workflow_id=wf_id,
            plan_data=PlanData(
                plan="# Original Plan\n\nThis is the standard implementation plan.",
                summary="Standard plan summary",
            ),
        )
        store.write_artifact(plan)

        # 2. Configure mock to return a successful implementation response
        mock_implement_plan.return_value = StepResult.ok(
            ImplementData(output="mock implementation output")
        )

        # 3. Create a WorkflowContext (no parent workflow)
        context = WorkflowContext(
            issue_id=1,
            adw_id=wf_id,
            artifact_store=store,
        )

        # 4. Run the ImplementStep
        step = ImplementStep()
        result = step.run(context)

        # 5. Verify step succeeded
        assert result.success, f"ImplementStep failed: {result.error}"

        # 6. Verify implement_plan was called with the original plan content
        mock_implement_plan.assert_called_once()
        call_args = mock_implement_plan.call_args
        plan_content_arg = call_args[0][0]  # First positional argument

        # The original plan content should be used
        assert "standard implementation plan" in plan_content_arg, (
            f"Expected original plan content but got: {plan_content_arg}"
        )
