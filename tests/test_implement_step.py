"""Tests for ImplementStep workflow step."""

from unittest.mock import Mock, patch

import pytest

from rouge.core.workflow.artifacts import AcceptanceArtifact
from rouge.core.workflow.step_base import StepInputError, WorkflowContext
from rouge.core.workflow.steps.implement_step import ImplementStep
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
    context.artifact_store = Mock()
    return context


@pytest.fixture
def mock_load_required_artifact(mock_context) -> WorkflowContext:
    """Configure mock_context.load_required_artifact with shared _load helper logic.

    The helper reads from context.data and raises StepInputError when the key is absent.
    Returns the configured mock_context.
    """

    def _load(context_key, _artifact_type, _artifact_class, _extract_fn) -> object:
        value = mock_context.data.get(context_key)
        if value is None:
            raise StepInputError(f"Required artifact '{_artifact_type}' not found")
        return value

    mock_context.load_required_artifact = _load
    return mock_context


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

    @patch("rouge.core.workflow.steps.implement_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.implement_step.emit_comment_from_payload")
    @patch.object(ImplementStep, "_implement_plan")
    def test_run_success_with_plan(
        self,
        mock__implement_plan,
        mock_emit_artifact,
        mock_emit,
        mock_load_required_artifact,
        sample_plan_data,
        sample_implement_data,
    ) -> None:
        """Test successful implementation using plan."""
        mock_context = mock_load_required_artifact
        mock_context.data = {"plan_data": sample_plan_data}
        mock_context.artifact_store.artifact_exists.return_value = False

        mock__implement_plan.return_value = StepResult.ok(sample_implement_data)
        mock_emit_artifact.return_value = ("success", "ok")
        mock_emit.return_value = ("success", "Comment inserted")

        step = ImplementStep()
        result = step.run(mock_context)

        assert result.success is True
        mock__implement_plan.assert_called_once_with(
            sample_plan_data.plan,
            mock_context.issue_id,
            mock_context.adw_id,
        )

    def test_run_fails_when_no_plan_available(self, mock_load_required_artifact) -> None:
        """Test that run fails when no plan is available."""
        mock_context = mock_load_required_artifact
        mock_context.data = {}

        step = ImplementStep()
        result = step.run(mock_context)

        assert result.success is False
        assert "no plan available" in result.error

    @patch("rouge.core.workflow.steps.implement_step.emit_comment_from_payload")
    @patch.object(ImplementStep, "_implement_plan")
    def test_run_fails_when__implement_plan_fails(
        self,
        mock__implement_plan,
        _mock_emit,
        mock_load_required_artifact,
        sample_plan_data,
    ) -> None:
        """Test that run fails when _implement_plan fails."""
        mock_context = mock_load_required_artifact
        mock_context.data = {"plan_data": sample_plan_data}
        mock_context.artifact_store.artifact_exists.return_value = False

        mock__implement_plan.return_value = StepResult.fail("Implementation failed")

        step = ImplementStep()
        result = step.run(mock_context)

        assert result.success is False
        assert "Implementation failed" in result.error
        _mock_emit.assert_not_called()

    @patch("rouge.core.workflow.steps.implement_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.implement_step.emit_comment_from_payload")
    @patch.object(ImplementStep, "_implement_plan")
    def test_run_saves_artifact(
        self,
        mock__implement_plan,
        mock_emit_artifact,
        mock_emit,
        mock_load_required_artifact,
        sample_plan_data,
        sample_implement_data,
    ) -> None:
        """Test that implementation artifact is saved."""
        mock_context = mock_load_required_artifact
        mock_context.data = {"plan_data": sample_plan_data}
        mock_context.artifact_store.artifact_exists.return_value = False

        mock__implement_plan.return_value = StepResult.ok(sample_implement_data)
        mock_emit_artifact.return_value = ("success", "ok")
        mock_emit.return_value = ("success", "Comment inserted")

        step = ImplementStep()
        result = step.run(mock_context)

        assert result.success is True
        mock_context.artifact_store.write_artifact.assert_called_once()

        # Check the artifact type
        saved_artifact = mock_context.artifact_store.write_artifact.call_args[0][0]
        assert saved_artifact.artifact_type == "implement"
        assert saved_artifact.implement_data == sample_implement_data

    @patch("rouge.core.workflow.steps.implement_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.implement_step.emit_comment_from_payload")
    @patch.object(ImplementStep, "_implement_plan")
    def test_run_appends_acceptance_feedback_when_unmet_requirements_exist(
        self,
        mock__implement_plan,
        mock_emit,
        mock_emit_artifact,
        mock_load_required_artifact,
        sample_plan_data,
        sample_implement_data,
    ) -> None:
        """Test that acceptance feedback is appended when unmet requirements exist."""
        mock_context = mock_load_required_artifact
        mock_context.data = {"plan_data": sample_plan_data}

        # Mock acceptance artifact exists with unmet requirements
        mock_context.artifact_store.artifact_exists.return_value = True
        acceptance_artifact = AcceptanceArtifact(
            workflow_id="test-adw-impl",
            success=False,
            acceptance_status="fail",
            unmet_requirements=["req1", "req2"],
        )
        mock_context.artifact_store.read_artifact.return_value = acceptance_artifact

        mock__implement_plan.return_value = StepResult.ok(sample_implement_data)
        mock_emit_artifact.return_value = ("success", "ok")
        mock_emit.return_value = ("success", "Comment inserted")

        step = ImplementStep()
        result = step.run(mock_context)

        assert result.success is True

        # Verify _implement_plan was called
        mock__implement_plan.assert_called_once()
        call_args = mock__implement_plan.call_args[0]
        plan_text_arg = call_args[0]

        # Assert the plan text contains acceptance feedback
        assert "Previous Acceptance Feedback" in plan_text_arg
        assert "req1" in plan_text_arg
        assert "req2" in plan_text_arg
        assert "The following requirements were unmet:" in plan_text_arg

    @patch("rouge.core.workflow.steps.implement_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.implement_step.emit_comment_from_payload")
    @patch.object(ImplementStep, "_implement_plan")
    def test_run_does_not_append_feedback_when_unmet_requirements_empty(
        self,
        mock__implement_plan,
        mock_emit,
        mock_emit_artifact,
        mock_load_required_artifact,
        sample_plan_data,
        sample_implement_data,
    ) -> None:
        """Test that acceptance feedback is not appended when unmet requirements are empty."""
        mock_context = mock_load_required_artifact
        mock_context.data = {"plan_data": sample_plan_data}

        # Mock acceptance artifact exists but with no unmet requirements
        mock_context.artifact_store.artifact_exists.return_value = True
        acceptance_artifact = AcceptanceArtifact(
            workflow_id="test-adw-impl",
            success=True,
            acceptance_status="pass",
            unmet_requirements=[],
        )
        mock_context.artifact_store.read_artifact.return_value = acceptance_artifact

        mock__implement_plan.return_value = StepResult.ok(sample_implement_data)
        mock_emit_artifact.return_value = ("success", "ok")
        mock_emit.return_value = ("success", "Comment inserted")

        step = ImplementStep()
        result = step.run(mock_context)

        assert result.success is True

        # Verify _implement_plan was called with original plan text (no feedback appended)
        mock__implement_plan.assert_called_once_with(
            sample_plan_data.plan,
            mock_context.issue_id,
            mock_context.adw_id,
        )

    @patch("rouge.core.workflow.steps.implement_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.implement_step.emit_comment_from_payload")
    @patch.object(ImplementStep, "_implement_plan")
    def test_run_continues_when_acceptance_artifact_not_found(
        self,
        mock__implement_plan,
        mock_emit,
        mock_emit_artifact,
        mock_load_required_artifact,
        sample_plan_data,
        sample_implement_data,
    ) -> None:
        """Test that run continues successfully when acceptance artifact cannot be read."""
        mock_context = mock_load_required_artifact
        mock_context.data = {"plan_data": sample_plan_data}

        # Mock acceptance artifact exists but read raises FileNotFoundError
        mock_context.artifact_store.artifact_exists.return_value = True
        mock_context.artifact_store.read_artifact.side_effect = FileNotFoundError(
            "Acceptance artifact not found"
        )

        mock__implement_plan.return_value = StepResult.ok(sample_implement_data)
        mock_emit_artifact.return_value = ("success", "ok")
        mock_emit.return_value = ("success", "Comment inserted")

        step = ImplementStep()
        result = step.run(mock_context)

        # Assert run completes successfully despite the error
        assert result.success is True

        # Verify _implement_plan was called with original plan text (no feedback)
        mock__implement_plan.assert_called_once_with(
            sample_plan_data.plan,
            mock_context.issue_id,
            mock_context.adw_id,
        )


class TestImplementStepRerunBehavior:
    """Tests for ImplementStep rerun behavior when plan is missing."""

    def test_rerun_from_building_implementation_plan_when_no_plan(
        self, mock_load_required_artifact
    ) -> None:
        """Test ImplementStep requests rerun from default plan step when plan is missing."""
        mock_context = mock_load_required_artifact
        mock_context.data = {}

        step = ImplementStep()
        result = step.run(mock_context)

        assert result.success is False
        assert "no plan available" in result.error
        assert result.rerun_from == "Building implementation plan"

    def test_rerun_from_custom_plan_step_when_no_plan(self, mock_load_required_artifact) -> None:
        """Test ImplementStep requests rerun from custom plan step name when plan is missing."""
        mock_context = mock_load_required_artifact
        mock_context.data = {}

        step = ImplementStep(plan_step_name="Building patch plan")
        result = step.run(mock_context)

        assert result.success is False
        assert "no plan available" in result.error
        assert result.rerun_from == "Building patch plan"

    def test_no_rerun_from_when_plan_available(
        self,
        mock_load_required_artifact,
        sample_plan_data,
        sample_implement_data,
    ) -> None:
        """Test that ImplementStep does not set rerun_from when plan is available."""
        mock_context = mock_load_required_artifact
        mock_context.data = {"plan_data": sample_plan_data}
        mock_context.artifact_store.artifact_exists.return_value = False

        with patch.object(ImplementStep, "_implement_plan") as mock_impl:
            with patch(
                "rouge.core.workflow.steps.implement_step.emit_comment_from_payload"
            ) as mock_e:
                with patch(
                    "rouge.core.workflow.steps.implement_step.emit_artifact_comment"
                ) as mock_emit_artifact:
                    mock_impl.return_value = StepResult.ok(sample_implement_data)
                    mock_e.return_value = ("success", "ok")
                    mock_emit_artifact.return_value = ("success", "ok")

                    step = ImplementStep()
                    result = step.run(mock_context)

                    assert result.success is True
                    assert result.rerun_from is None


class TestImplementStepProperties:
    """Tests for ImplementStep properties."""

    def test_step_name(self) -> None:
        """Test that ImplementStep has correct name."""
        step = ImplementStep()
        assert step.name == "Implementing solution"

    def test_step_is_critical(self) -> None:
        """Test that ImplementStep is critical by default."""
        step = ImplementStep()
        assert step.is_critical is True
