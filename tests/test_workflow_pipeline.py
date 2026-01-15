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
