"""Tests for ImplementStep workflow step."""

from unittest.mock import Mock, patch

import pytest

from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.implement import ImplementStep
from rouge.core.workflow.types import (
    ImplementData,
    PlanData,
    StepResult,
)


@pytest.fixture
def mock_context():
    """Create a mock workflow context."""
    context = Mock(spec=WorkflowContext)
    context.issue_id = 10
    context.require_issue_id = 10
    context.adw_id = "test-adw-impl"
    context.data = {}
    context.artifacts_enabled = True
    context.artifact_store = Mock()
    return context


@pytest.fixture
def sample_plan_data():
    """Create a sample PlanData."""
    return PlanData(
        plan="## Plan\n\n### Step 1\nImplement feature X",
        summary="Implement feature X",
        session_id="session-123",
    )


@pytest.fixture
def sample_implement_data():
    """Create a sample ImplementData."""
    return ImplementData(
        output="Implementation completed successfully. Files modified: README.md",
        session_id="impl-session-456",
    )


class TestImplementStepRun:
    """Tests for ImplementStep.run method."""

    @patch("rouge.core.workflow.steps.implement.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.implement.implement_plan")
    def test_run_success_with_plan(
        self,
        mock_implement_plan,
        mock_emit,
        mock_context,
        sample_plan_data,
        sample_implement_data,
    ):
        """Test successful implementation using plan."""
        mock_context.data = {"plan_data": sample_plan_data}

        def load_artifact_if_missing(context_key, _artifact_type, _artifact_class, _extract_fn):
            return mock_context.data.get(context_key)

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        mock_implement_plan.return_value = StepResult.ok(sample_implement_data)
        mock_emit.return_value = ("success", "Comment inserted")

        step = ImplementStep()
        result = step.run(mock_context)

        assert result.success is True
        mock_implement_plan.assert_called_once_with(
            sample_plan_data.plan,
            mock_context.issue_id,
            mock_context.adw_id,
        )

    def test_run_fails_when_no_plan_available(self, mock_context):
        """Test that run fails when no plan is available."""
        mock_context.data = {}

        def load_artifact_if_missing(_context_key, _artifact_type, _artifact_class, _extract_fn):
            return None

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        step = ImplementStep()
        result = step.run(mock_context)

        assert result.success is False
        assert "no plan available" in result.error

    @patch("rouge.core.workflow.steps.implement.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.implement.implement_plan")
    def test_run_fails_when_implement_plan_fails(
        self,
        mock_implement_plan,
        _mock_emit,
        mock_context,
        sample_plan_data,
    ):
        """Test that run fails when implement_plan fails."""
        mock_context.data = {"plan_data": sample_plan_data}

        def load_artifact_if_missing(context_key, _artifact_type, _artifact_class, _extract_fn):
            return mock_context.data.get(context_key)

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        mock_implement_plan.return_value = StepResult.fail("Implementation failed")

        step = ImplementStep()
        result = step.run(mock_context)

        assert result.success is False
        assert "Implementation failed" in result.error
        _mock_emit.assert_not_called()

    @patch("rouge.core.workflow.steps.implement.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.implement.implement_plan")
    def test_run_saves_artifact(
        self,
        mock_implement_plan,
        mock_emit,
        mock_context,
        sample_plan_data,
        sample_implement_data,
    ):
        """Test that implementation artifact is saved."""
        mock_context.data = {"plan_data": sample_plan_data}

        def load_artifact_if_missing(context_key, _artifact_type, _artifact_class, _extract_fn):
            return mock_context.data.get(context_key)

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        mock_implement_plan.return_value = StepResult.ok(sample_implement_data)
        mock_emit.return_value = ("success", "Comment inserted")

        step = ImplementStep()
        result = step.run(mock_context)

        assert result.success is True
        mock_context.artifact_store.write_artifact.assert_called_once()

        # Check the artifact type
        saved_artifact = mock_context.artifact_store.write_artifact.call_args[0][0]
        assert saved_artifact.artifact_type == "implementation"
        assert saved_artifact.implement_data == sample_implement_data


class TestImplementStepRerunBehavior:
    """Tests for ImplementStep rerun behavior when plan is missing."""

    def test_rerun_from_building_implementation_plan_when_no_plan(self, mock_context):
        """Test ImplementStep requests rerun from default plan step when plan is missing."""
        mock_context.data = {}

        def load_artifact_if_missing(_context_key, _artifact_type, _artifact_class, _extract_fn):
            return None

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        step = ImplementStep()
        result = step.run(mock_context)

        assert result.success is False
        assert "no plan available" in result.error
        assert result.rerun_from == "Building implementation plan"

    def test_rerun_from_custom_plan_step_when_no_plan(self, mock_context):
        """Test ImplementStep requests rerun from custom plan step name when plan is missing."""
        mock_context.data = {}

        def load_artifact_if_missing(_context_key, _artifact_type, _artifact_class, _extract_fn):
            return None

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        step = ImplementStep(plan_step_name="Building patch plan")
        result = step.run(mock_context)

        assert result.success is False
        assert "no plan available" in result.error
        assert result.rerun_from == "Building patch plan"

    def test_no_rerun_from_when_plan_available(
        self,
        mock_context,
        sample_plan_data,
        sample_implement_data,
    ):
        """Test that ImplementStep does not set rerun_from when plan is available."""
        mock_context.data = {"plan_data": sample_plan_data}

        def load_artifact_if_missing(context_key, _artifact_type, _artifact_class, _extract_fn):
            return mock_context.data.get(context_key)

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        with patch("rouge.core.workflow.steps.implement.implement_plan") as mock_impl:
            with patch("rouge.core.workflow.steps.implement.emit_comment_from_payload") as mock_e:
                mock_impl.return_value = StepResult.ok(sample_implement_data)
                mock_e.return_value = ("success", "ok")

                step = ImplementStep()
                result = step.run(mock_context)

                assert result.success is True
                assert result.rerun_from is None


class TestImplementStepProperties:
    """Tests for ImplementStep properties."""

    def test_step_name(self):
        """Test that ImplementStep has correct name."""
        step = ImplementStep()
        assert step.name == "Implementing solution"

    def test_step_is_critical(self):
        """Test that ImplementStep is critical by default."""
        step = ImplementStep()
        assert step.is_critical is True
