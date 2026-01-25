"""Tests for ImplementStep workflow step."""

from unittest.mock import Mock, patch

import pytest

from rouge.core.workflow.artifacts import (
    PatchPlanArtifact,
    PlanArtifact,
)
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.implement import ImplementStep
from rouge.core.workflow.types import (
    ImplementData,
    PatchPlanData,
    PlanData,
    StepResult,
)


@pytest.fixture
def mock_context():
    """Create a mock workflow context."""
    context = Mock(spec=WorkflowContext)
    context.issue_id = 10
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
def sample_patch_plan_data():
    """Create a sample PatchPlanData."""
    return PatchPlanData(
        patch_description="Fix typo in documentation",
        original_plan_reference="adw-original-123",
        patch_plan_content="## Patch Plan\n\n### Changes\nFix typo in README.md",
    )


@pytest.fixture
def sample_implement_data():
    """Create a sample ImplementData."""
    return ImplementData(
        output="Implementation completed successfully. Files modified: README.md",
        session_id="impl-session-456",
    )


class TestLoadPlanText:
    """Tests for _load_plan_text method."""

    def test_uses_patch_plan_when_available(
        self, mock_context, sample_patch_plan_data, sample_plan_data
    ):
        """Test that patch_plan is preferred when available."""
        # Setup: patch_plan_data is in context
        mock_context.data = {"patch_plan_data": sample_patch_plan_data}

        # Setup load_artifact_if_missing to return from context
        def load_artifact_if_missing(context_key, _artifact_type, _artifact_class, _extract_fn):
            return mock_context.data.get(context_key)

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        step = ImplementStep()
        result = step._load_plan_text(mock_context)

        assert result == sample_patch_plan_data.patch_plan_content

    def test_falls_back_to_plan_when_patch_plan_not_available(self, mock_context, sample_plan_data):
        """Test that plan is used when patch_plan is not available."""
        # Setup: only plan_data is in context
        mock_context.data = {"plan_data": sample_plan_data}

        def load_artifact_if_missing(context_key, _artifact_type, _artifact_class, _extract_fn):
            return mock_context.data.get(context_key)

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        step = ImplementStep()
        result = step._load_plan_text(mock_context)

        assert result == sample_plan_data.plan

    def test_returns_none_when_no_plan_available(self, mock_context):
        """Test that None is returned when neither plan is available."""
        mock_context.data = {}

        def load_artifact_if_missing(_context_key, _artifact_type, _artifact_class, _extract_fn):
            return None

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        step = ImplementStep()
        result = step._load_plan_text(mock_context)

        assert result is None

    def test_loads_patch_plan_from_artifact(self, mock_context, sample_patch_plan_data):
        """Test loading patch_plan from artifact store."""
        mock_context.data = {}
        patch_plan_artifact = PatchPlanArtifact(
            workflow_id="test-adw",
            patch_plan_data=sample_patch_plan_data,
        )

        call_count = {"count": 0}

        def load_artifact_if_missing(context_key, artifact_type, _artifact_class, extract_fn):
            call_count["count"] += 1
            if artifact_type == "patch_plan":
                value = extract_fn(patch_plan_artifact)
                mock_context.data[context_key] = value
                return value
            return None

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        step = ImplementStep()
        result = step._load_plan_text(mock_context)

        assert result == sample_patch_plan_data.patch_plan_content
        # Should only call once since patch_plan was found
        assert call_count["count"] == 1

    def test_loads_plan_from_artifact_when_patch_plan_missing(self, mock_context, sample_plan_data):
        """Test loading plan from artifact when patch_plan is not available."""
        mock_context.data = {}
        plan_artifact = PlanArtifact(
            workflow_id="test-adw",
            plan_data=sample_plan_data,
        )

        def load_artifact_if_missing(context_key, artifact_type, _artifact_class, extract_fn):
            if artifact_type == "patch_plan":
                return None
            if artifact_type == "plan":
                value = extract_fn(plan_artifact)
                mock_context.data[context_key] = value
                return value
            return None

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        step = ImplementStep()
        result = step._load_plan_text(mock_context)

        assert result == sample_plan_data.plan


class TestImplementStepRun:
    """Tests for ImplementStep.run method."""

    @patch("rouge.core.workflow.steps.implement.emit_progress_comment")
    @patch("rouge.core.workflow.steps.implement.implement_plan")
    def test_run_success_with_patch_plan(
        self,
        mock_implement_plan,
        mock_emit,
        mock_context,
        sample_patch_plan_data,
        sample_implement_data,
    ):
        """Test successful implementation using patch_plan."""
        mock_context.data = {"patch_plan_data": sample_patch_plan_data}

        def load_artifact_if_missing(context_key, _artifact_type, _artifact_class, _extract_fn):
            return mock_context.data.get(context_key)

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        mock_implement_plan.return_value = StepResult.ok(sample_implement_data)

        step = ImplementStep()
        result = step.run(mock_context)

        assert result.success is True
        mock_implement_plan.assert_called_once_with(
            sample_patch_plan_data.patch_plan_content,
            mock_context.issue_id,
            mock_context.adw_id,
        )
        mock_emit.assert_called_once()

    @patch("rouge.core.workflow.steps.implement.emit_progress_comment")
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

        step = ImplementStep()
        result = step.run(mock_context)

        assert result.success is True
        mock_implement_plan.assert_called_once_with(
            sample_plan_data.plan,
            mock_context.issue_id,
            mock_context.adw_id,
        )

    def test_run_fails_when_no_plan_available(self, mock_context):
        """Test that run fails when no plan or patch_plan is available."""
        mock_context.data = {}

        def load_artifact_if_missing(_context_key, _artifact_type, _artifact_class, _extract_fn):
            return None

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        step = ImplementStep()
        result = step.run(mock_context)

        assert result.success is False
        assert "no plan or patch_plan available" in result.error

    @patch("rouge.core.workflow.steps.implement.emit_progress_comment")
    @patch("rouge.core.workflow.steps.implement.implement_plan")
    def test_run_fails_when_implement_plan_fails(
        self,
        mock_implement_plan,
        mock_emit,
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
        mock_emit.assert_not_called()

    @patch("rouge.core.workflow.steps.implement.emit_progress_comment")
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

        step = ImplementStep()
        result = step.run(mock_context)

        assert result.success is True
        mock_context.artifact_store.write_artifact.assert_called_once()

        # Check the artifact type
        saved_artifact = mock_context.artifact_store.write_artifact.call_args[0][0]
        assert saved_artifact.artifact_type == "implementation"
        assert saved_artifact.implement_data == sample_implement_data


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
