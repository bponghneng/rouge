"""Tests for GitPrepareStep workflow step."""

from unittest.mock import Mock, patch

from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.git_prepare_step import GitPrepareStep
from rouge.core.workflow.types import StepResult


class TestGitPrepareStepProperties:
    """Tests for GitPrepareStep properties."""

    def test_step_name(self) -> None:
        """Test that GitPrepareStep has correct name."""
        step = GitPrepareStep()
        assert step.name == "Preparing git workspace"

    def test_step_is_critical(self) -> None:
        """Test that GitPrepareStep is critical."""
        step = GitPrepareStep()
        assert step.is_critical is True


class TestGitPrepareStepRun:
    """Tests for GitPrepareStep.run method."""

    @patch("rouge.core.workflow.steps.git_prepare_step.GitBranchStep")
    def test_run_with_no_branch_delegates_to_git_branch(self, mock_git_branch_cls) -> None:
        """Test that when issue.branch is None, GitBranchStep.run is called."""
        context = Mock(spec=WorkflowContext)
        issue_mock = Mock()
        issue_mock.branch = None
        context.issue = issue_mock

        mock_instance = mock_git_branch_cls.return_value
        mock_instance.run.return_value = StepResult.ok(None)

        step = GitPrepareStep()
        result = step.run(context)

        assert result.success is True
        mock_instance.run.assert_called_once_with(context)

    @patch("rouge.core.workflow.steps.git_prepare_step.GitCheckoutStep")
    def test_run_with_branch_delegates_to_git_checkout(self, mock_git_checkout_cls) -> None:
        """Test that when issue.branch is set, GitCheckoutStep.run is called."""
        context = Mock(spec=WorkflowContext)
        issue_mock = Mock()
        issue_mock.branch = "my-branch"
        context.issue = issue_mock

        mock_instance = mock_git_checkout_cls.return_value
        mock_instance.run.return_value = StepResult.ok(None)

        step = GitPrepareStep()
        result = step.run(context)

        assert result.success is True
        mock_instance.run.assert_called_once_with(context)

    @patch("rouge.core.workflow.steps.git_prepare_step.GitBranchStep")
    def test_run_with_no_issue_delegates_to_git_branch(self, mock_git_branch_cls) -> None:
        """Test that when context.issue is None, GitBranchStep.run is called (fallback)."""
        context = Mock(spec=WorkflowContext)
        context.issue = None

        mock_instance = mock_git_branch_cls.return_value
        mock_instance.run.return_value = StepResult.ok(None)

        step = GitPrepareStep()
        result = step.run(context)

        assert result.success is True
        mock_instance.run.assert_called_once_with(context)

    @patch("rouge.core.workflow.steps.git_prepare_step.GitBranchStep")
    def test_run_with_whitespace_only_branch_delegates_to_git_branch(
        self, mock_git_branch_cls
    ) -> None:
        """Test that whitespace-only branch is treated as unset."""
        context = Mock(spec=WorkflowContext)
        issue_mock = Mock()
        issue_mock.branch = "   "
        context.issue = issue_mock

        mock_instance = mock_git_branch_cls.return_value
        mock_instance.run.return_value = StepResult.ok(None)

        step = GitPrepareStep()
        result = step.run(context)

        assert result.success is True
        mock_instance.run.assert_called_once_with(context)
