"""Tests for workflow pipeline components."""

import logging
from unittest.mock import Mock

import pytest

from cape.core.workflow.pipeline import WorkflowRunner, get_default_pipeline
from cape.core.workflow.step_base import WorkflowContext, WorkflowStep


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    return Mock(spec=logging.Logger)


class TestWorkflowContext:
    """Tests for WorkflowContext dataclass."""

    def test_context_initialization(self, mock_logger):
        """Test WorkflowContext initializes with required fields."""
        context = WorkflowContext(
            issue_id=123,
            adw_id="adw-456",
            logger=mock_logger,
        )

        assert context.issue_id == 123
        assert context.adw_id == "adw-456"
        assert context.logger is mock_logger
        assert context.issue is None
        assert context.data == {}

    def test_context_data_storage(self, mock_logger):
        """Test WorkflowContext stores data between steps."""
        context = WorkflowContext(
            issue_id=1,
            adw_id="test",
            logger=mock_logger,
        )

        # Simulate step storing data
        context.data["plan_file"] = "specs/plan.md"
        context.data["classify_data"] = {"type": "feature"}

        assert context.data["plan_file"] == "specs/plan.md"
        assert context.data["classify_data"]["type"] == "feature"


class TestWorkflowRunner:
    """Tests for WorkflowRunner orchestrator."""

    def test_runner_executes_all_steps(self, mock_logger):
        """Test runner executes all steps in order."""
        # Create mock steps
        step1 = Mock(spec=WorkflowStep)
        step1.name = "Step 1"
        step1.is_critical = True
        step1.run.return_value = True

        step2 = Mock(spec=WorkflowStep)
        step2.name = "Step 2"
        step2.is_critical = True
        step2.run.return_value = True

        runner = WorkflowRunner([step1, step2])
        result = runner.run(1, "adw123", mock_logger)

        assert result is True
        step1.run.assert_called_once()
        step2.run.assert_called_once()

    def test_runner_stops_on_critical_failure(self, mock_logger):
        """Test runner stops when critical step fails."""
        step1 = Mock(spec=WorkflowStep)
        step1.name = "Step 1"
        step1.is_critical = True
        step1.run.return_value = False  # Fails

        step2 = Mock(spec=WorkflowStep)
        step2.name = "Step 2"
        step2.is_critical = True
        step2.run.return_value = True

        runner = WorkflowRunner([step1, step2])
        result = runner.run(1, "adw123", mock_logger)

        assert result is False
        step1.run.assert_called_once()
        step2.run.assert_not_called()  # Not reached

    def test_runner_continues_on_best_effort_failure(self, mock_logger):
        """Test runner continues when best-effort step fails."""
        step1 = Mock(spec=WorkflowStep)
        step1.name = "Critical Step"
        step1.is_critical = True
        step1.run.return_value = True

        step2 = Mock(spec=WorkflowStep)
        step2.name = "Best Effort Step"
        step2.is_critical = False  # Best-effort
        step2.run.return_value = False  # Fails

        step3 = Mock(spec=WorkflowStep)
        step3.name = "Another Critical"
        step3.is_critical = True
        step3.run.return_value = True

        runner = WorkflowRunner([step1, step2, step3])
        result = runner.run(1, "adw123", mock_logger)

        assert result is True  # Overall success
        step1.run.assert_called_once()
        step2.run.assert_called_once()
        step3.run.assert_called_once()  # Still executed

    def test_runner_passes_context_to_steps(self, mock_logger):
        """Test runner passes correct context to each step."""
        captured_context = None

        def capture_context(context):
            nonlocal captured_context
            captured_context = context
            return True

        step = Mock(spec=WorkflowStep)
        step.name = "Test Step"
        step.is_critical = True
        step.run.side_effect = capture_context

        runner = WorkflowRunner([step])
        runner.run(42, "adw-test-123", mock_logger)

        assert captured_context is not None
        assert captured_context.issue_id == 42
        assert captured_context.adw_id == "adw-test-123"
        assert captured_context.logger is mock_logger


class TestGetDefaultPipeline:
    """Tests for get_default_pipeline factory."""

    def test_returns_correct_step_count(self):
        """Test default pipeline has 11 steps."""
        pipeline = get_default_pipeline()
        assert len(pipeline) == 11

    def test_returns_workflow_step_instances(self):
        """Test all items are WorkflowStep subclasses."""
        pipeline = get_default_pipeline()
        for step in pipeline:
            assert isinstance(step, WorkflowStep)

    def test_step_order(self):
        """Test steps are in correct order."""
        pipeline = get_default_pipeline()
        step_names = [step.name for step in pipeline]

        # Verify key steps are in expected order
        assert "Fetching" in step_names[0]
        assert "Classifying" in step_names[1]
        assert "Building" in step_names[2]
        assert "plan file" in step_names[3].lower()
        assert "Implementing" in step_names[4]
        assert "implemented plan" in step_names[5].lower()
        assert "review" in step_names[6].lower()
        assert "review" in step_names[7].lower()
        assert "quality" in step_names[8].lower()
        assert "acceptance" in step_names[9].lower()
        assert "pull request" in step_names[10].lower()

    def test_critical_flags(self):
        """Test critical/best-effort flags are set correctly."""
        pipeline = get_default_pipeline()

        # First 6 steps should be critical
        for step in pipeline[:6]:
            assert step.is_critical is True, f"{step.name} should be critical"

        # Review steps are not critical
        assert pipeline[6].is_critical is False  # GenerateReviewStep
        assert pipeline[7].is_critical is False  # AddressReviewStep

        # Quality is best-effort
        assert pipeline[8].is_critical is False  # CodeQualityStep

        # Acceptance is best-effort
        assert pipeline[9].is_critical is False  # ValidateAcceptanceStep

        # PR is best-effort
        assert pipeline[10].is_critical is False  # PreparePullRequestStep
