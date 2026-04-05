"""Tests for ImplementPlanStep and ImplementDirectStep workflow steps."""

from unittest.mock import Mock, patch

import pytest

from rouge.core.workflow.step_base import StepInputError, WorkflowContext
from rouge.core.workflow.steps.implement_direct_step import ImplementDirectStep
from rouge.core.workflow.steps.implement_step import ImplementPlanStep
from rouge.core.workflow.types import (
    ImplementData,
    PlanData,
    StepResult,
)


@pytest.fixture
def mock_context() -> WorkflowContext:
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
def sample_plan_data() -> PlanData:
    """Create a sample PlanData."""
    return PlanData(
        plan="## Plan\n\n### Step 1\nImplement feature X",
        summary="Implement feature X",
        session_id="session-123",
    )


@pytest.fixture
def sample_implement_data() -> ImplementData:
    """Create a sample ImplementData."""
    return ImplementData(
        output="Implementation completed successfully. Files modified: README.md",
        session_id="impl-session-456",
    )


class TestImplementPlanStepRun:
    """Tests for ImplementPlanStep.run method."""

    @patch("rouge.core.workflow.steps.implement_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.implement_step.emit_comment_from_payload")
    @patch.object(ImplementPlanStep, "_implement_plan")
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

        step = ImplementPlanStep()
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

        step = ImplementPlanStep()
        result = step.run(mock_context)

        assert result.success is False
        assert "no plan available" in result.error

    @patch("rouge.core.workflow.steps.implement_step.emit_comment_from_payload")
    @patch.object(ImplementPlanStep, "_implement_plan")
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

        step = ImplementPlanStep()
        result = step.run(mock_context)

        assert result.success is False
        assert "Implementation failed" in result.error
        _mock_emit.assert_not_called()

    @patch("rouge.core.workflow.steps.implement_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.implement_step.emit_comment_from_payload")
    @patch.object(ImplementPlanStep, "_implement_plan")
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

        step = ImplementPlanStep()
        result = step.run(mock_context)

        assert result.success is True
        mock_context.artifact_store.write_artifact.assert_called_once()

        # Check the artifact type
        saved_artifact = mock_context.artifact_store.write_artifact.call_args[0][0]
        assert saved_artifact.artifact_type == "implement"
        assert saved_artifact.implement_data == sample_implement_data


class TestImplementPlanStepRerunBehavior:
    """Tests for ImplementPlanStep rerun behavior when plan is missing."""

    def test_rerun_from_building_implementation_plan_when_no_plan(
        self, mock_load_required_artifact
    ) -> None:
        """Test ImplementPlanStep requests rerun from default plan step when plan is missing."""
        mock_context = mock_load_required_artifact
        mock_context.data = {}

        step = ImplementPlanStep()
        result = step.run(mock_context)

        assert result.success is False
        assert "no plan available" in result.error
        assert result.rerun_from == "Building implementation plan"

    def test_rerun_from_custom_plan_step_when_no_plan(self, mock_load_required_artifact) -> None:
        """Test ImplementPlanStep requests rerun from custom plan step name when plan is missing."""
        mock_context = mock_load_required_artifact
        mock_context.data = {}

        step = ImplementPlanStep(plan_step_name="Building patch plan")
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
        """Test that ImplementPlanStep does not set rerun_from when plan is available."""
        mock_context = mock_load_required_artifact
        mock_context.data = {"plan_data": sample_plan_data}
        mock_context.artifact_store.artifact_exists.return_value = False

        with patch.object(ImplementPlanStep, "_implement_plan") as mock_impl:
            with patch(
                "rouge.core.workflow.steps.implement_step.emit_comment_from_payload"
            ) as mock_e:
                with patch(
                    "rouge.core.workflow.steps.implement_step.emit_artifact_comment"
                ) as mock_emit_artifact:
                    mock_impl.return_value = StepResult.ok(sample_implement_data)
                    mock_e.return_value = ("success", "ok")
                    mock_emit_artifact.return_value = ("success", "ok")

                    step = ImplementPlanStep()
                    result = step.run(mock_context)

                    assert result.success is True
                    assert result.rerun_from is None


class TestImplementPlanStepProperties:
    """Tests for ImplementPlanStep properties."""

    def test_step_name(self) -> None:
        """Test that ImplementPlanStep has correct name."""
        step = ImplementPlanStep()
        assert step.name == "Implementing plan-based solution"

    def test_step_is_critical(self) -> None:
        """Test that ImplementPlanStep is critical by default."""
        step = ImplementPlanStep()
        assert step.is_critical is True


class TestImplementDirectStepProperties:
    """Tests for ImplementDirectStep properties."""

    def test_step_name(self) -> None:
        """Test that ImplementDirectStep has correct name."""
        step = ImplementDirectStep()
        assert step.name == "Implementing direct solution"

    def test_step_is_critical(self) -> None:
        """Test that ImplementDirectStep is critical."""
        step = ImplementDirectStep()
        assert step.is_critical is True


class TestImplementDirectStepRun:
    """Tests for ImplementDirectStep.run method."""

    @pytest.fixture
    def direct_mock_context(self) -> WorkflowContext:
        """Create a mock workflow context for direct implementation tests."""
        context = Mock(spec=WorkflowContext)
        context.issue_id = 10
        context.require_issue_id = 10
        context.adw_id = "test-adw-direct"
        context.data = {}
        context.artifact_store = Mock()
        return context

    @patch("rouge.core.workflow.steps.implement_direct_step.update_status")
    @patch("rouge.core.workflow.steps.implement_direct_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.implement_direct_step.emit_comment_from_payload")
    @patch.object(ImplementDirectStep, "_implement_direct")
    def test_run_success(
        self,
        mock_implement_direct,
        mock_emit,
        mock_emit_artifact,
        mock_update_status,
        direct_mock_context,
    ) -> None:
        """Test successful direct implementation."""
        issue_mock = Mock()
        issue_mock.description = "Implement feature X directly"
        direct_mock_context.issue = issue_mock

        sample_data = ImplementData(
            output="Implementation completed successfully.",
            session_id="direct-session-789",
        )

        def _load(context_key, _artifact_type, _artifact_class, extract_fn):
            return issue_mock

        direct_mock_context.load_required_artifact = _load

        mock_implement_direct.return_value = StepResult.ok(sample_data)
        mock_emit_artifact.return_value = ("success", "ok")
        mock_emit.return_value = ("success", "Comment inserted")

        step = ImplementDirectStep()
        result = step.run(direct_mock_context)

        assert result.success is True
        mock_implement_direct.assert_called_once_with(
            issue_mock.description,
            direct_mock_context.require_issue_id,
            direct_mock_context.adw_id,
        )
        mock_update_status.assert_called_once_with(
            direct_mock_context.require_issue_id,
            "completed",
            adw_id=direct_mock_context.adw_id,
        )

    @patch("rouge.core.workflow.steps.implement_direct_step.update_status")
    @patch("rouge.core.workflow.steps.implement_direct_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.implement_direct_step.emit_comment_from_payload")
    @patch.object(ImplementDirectStep, "_implement_direct")
    def test_run_emits_finalization_comment(
        self,
        mock_implement_direct,
        mock_emit,
        mock_emit_artifact,
        mock_update_status,
        direct_mock_context,
    ) -> None:
        """Test that finalization emits 'Solution implemented successfully' comment."""
        issue_mock = Mock()
        issue_mock.description = "Implement feature X directly"

        def _load(context_key, _artifact_type, _artifact_class, extract_fn):
            return issue_mock

        direct_mock_context.load_required_artifact = _load

        sample_data = ImplementData(
            output="Implementation completed successfully.",
            session_id="direct-session-789",
        )
        mock_implement_direct.return_value = StepResult.ok(sample_data)
        mock_emit_artifact.return_value = ("success", "ok")
        mock_emit.return_value = ("success", "Comment inserted")

        step = ImplementDirectStep()
        result = step.run(direct_mock_context)

        assert result.success is True
        # Verify the finalization comment text
        mock_emit.assert_called_once()
        payload = mock_emit.call_args[0][0]
        assert payload.text == "Solution implemented successfully"


    @patch("rouge.core.workflow.steps.implement_direct_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.implement_direct_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.implement_direct_step.update_status")
    @patch.object(ImplementDirectStep, "_implement_direct")
    def test_run_succeeds_when_status_persistence_fails(
        self,
        mock_implement_direct,
        mock_update_status,
        mock_emit,
        mock_emit_artifact,
        direct_mock_context,
    ) -> None:
        """Test that finalization status persistence is best-effort."""
        issue_mock = Mock()
        issue_mock.description = "Implement feature X directly"

        def _load(_context_key, _artifact_type, _artifact_class, _extract_fn):
            return issue_mock

        direct_mock_context.load_required_artifact = _load

        sample_data = ImplementData(
            output="Implementation completed successfully.",
            session_id="direct-session-789",
        )
        mock_implement_direct.return_value = StepResult.ok(sample_data)
        mock_update_status.side_effect = RuntimeError("transient status failure")
        mock_emit_artifact.return_value = ("success", "ok")
        mock_emit.return_value = ("success", "Comment inserted")

        step = ImplementDirectStep()
        result = step.run(direct_mock_context)

        assert result.success is True
        mock_emit.assert_called_once()

    def test_run_fails_when_no_fetch_issue_artifact(self, direct_mock_context) -> None:
        """Test that run fails when fetch-issue artifact is missing."""

        def _load(_context_key, _artifact_type, _artifact_class, _extract_fn):
            raise StepInputError("Required artifact 'fetch-issue' not found")

        direct_mock_context.load_required_artifact = _load

        step = ImplementDirectStep()
        result = step.run(direct_mock_context)

        assert result.success is False
        assert "no issue available" in result.error


    def test_run_fails_when_issue_description_is_whitespace_only(
        self, direct_mock_context
    ) -> None:
        """Test that whitespace-only issue descriptions are rejected."""
        issue_mock = Mock()
        issue_mock.description = "   \n\t  "

        def _load(_context_key, _artifact_type, _artifact_class, _extract_fn):
            return issue_mock

        direct_mock_context.load_required_artifact = _load

        step = ImplementDirectStep()
        result = step.run(direct_mock_context)

        assert result.success is False
        assert result.error == "Cannot implement: issue has no description"
        assert result.rerun_from == "Fetching issue"

    @patch("rouge.core.workflow.steps.implement_direct_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.implement_direct_step.emit_comment_from_payload")
    @patch.object(ImplementDirectStep, "_implement_direct")
    def test_run_fails_when_implement_direct_fails(
        self,
        mock_implement_direct,
        _mock_emit,
        _mock_emit_artifact,
        direct_mock_context,
    ) -> None:
        """Test that run fails when _implement_direct fails."""
        issue_mock = Mock()
        issue_mock.description = "Implement feature X"

        def _load(_context_key, _artifact_type, _artifact_class, _extract_fn):
            return issue_mock

        direct_mock_context.load_required_artifact = _load

        mock_implement_direct.return_value = StepResult.fail("Direct implementation failed")

        step = ImplementDirectStep()
        result = step.run(direct_mock_context)

        assert result.success is False
        assert (
            "implementing solution" in result.error.lower()
            or "Direct implementation failed" in result.error
        )

    @patch("rouge.core.workflow.steps.implement_direct_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.implement_direct_step.emit_comment_from_payload")
    @patch.object(ImplementDirectStep, "_implement_direct")
    def test_run_fails_when_empty_output(
        self,
        mock_implement_direct,
        _mock_emit,
        _mock_emit_artifact,
        direct_mock_context,
    ) -> None:
        """Test that run fails when _implement_direct returns None data."""
        issue_mock = Mock()
        issue_mock.description = "Implement feature X"

        def _load(_context_key, _artifact_type, _artifact_class, _extract_fn):
            return issue_mock

        direct_mock_context.load_required_artifact = _load

        # success=True but data=None
        mock_implement_direct.return_value = StepResult.ok(None)

        step = ImplementDirectStep()
        result = step.run(direct_mock_context)

        assert result.success is False
        assert "missing" in result.error.lower() or "Implementation data" in result.error

    @patch("rouge.core.workflow.steps.implement_direct_step.update_status")
    @patch("rouge.core.workflow.steps.implement_direct_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.implement_direct_step.emit_comment_from_payload")
    @patch.object(ImplementDirectStep, "_implement_direct")
    def test_run_saves_artifact(
        self,
        mock_implement_direct,
        mock_emit,
        mock_emit_artifact,
        _mock_update_status,
        direct_mock_context,
    ) -> None:
        """Test that implementation artifact is saved on success."""
        issue_mock = Mock()
        issue_mock.description = "Implement feature X directly"

        def _load(_context_key, _artifact_type, _artifact_class, _extract_fn):
            return issue_mock

        direct_mock_context.load_required_artifact = _load

        sample_data = ImplementData(
            output="Implementation completed successfully.",
            session_id="direct-session-789",
        )
        mock_implement_direct.return_value = StepResult.ok(sample_data)
        mock_emit_artifact.return_value = ("success", "ok")
        mock_emit.return_value = ("success", "Comment inserted")

        step = ImplementDirectStep()
        result = step.run(direct_mock_context)

        assert result.success is True
        direct_mock_context.artifact_store.write_artifact.assert_called_once()

        saved_artifact = direct_mock_context.artifact_store.write_artifact.call_args[0][0]
        assert saved_artifact.artifact_type == "implement:direct"
        assert saved_artifact.implement_data == sample_data
