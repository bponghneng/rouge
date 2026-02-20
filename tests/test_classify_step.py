"""Tests for ClassifyStep workflow step."""

from unittest.mock import Mock, patch

import pytest

from rouge.core.models import Issue
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.classify_step import ClassifyStep
from rouge.core.workflow.types import ClassifyData, StepResult


@pytest.fixture
def mock_context():
    """Create a mock workflow context."""
    context = Mock(spec=WorkflowContext)
    context.issue_id = 10
    context.require_issue_id = 10
    context.adw_id = "test-adw-classify"
    context.data = {}
    context.artifact_store = Mock()
    return context


@pytest.fixture
def sample_issue():
    """Create a sample Issue."""
    return Issue(
        id=10,
        description="Add dark mode toggle to settings page",
        type="main",
    )


@pytest.fixture
def sample_classify_data():
    """Create sample classification data."""
    return ClassifyData(
        command="/adw-feature-plan",
        classification={"type": "feature", "level": "average"},
    )


class TestClassifyStepRun:
    """Tests for ClassifyStep.run method."""

    @patch("rouge.core.workflow.steps.classify_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.classify_step.emit_artifact_comment")
    @patch.object(ClassifyStep, "_classify_issue")
    def test_run_success_emits_artifact_comment(
        self,
        mock__classify_issue,
        mock_emit_artifact,
        mock_emit_comment,
        mock_context,
        sample_issue,
        sample_classify_data,
    ):
        """Test successful classification emits artifact comment."""
        # Setup: issue loaded via load_required_artifact, classification succeeds
        def load_required_artifact(context_key, _artifact_type, _artifact_class, _extract_fn):
            if context_key == "issue":
                return sample_issue
            raise Exception(f"Required artifact '{_artifact_type}' not found")

        mock_context.load_required_artifact = load_required_artifact

        mock__classify_issue.return_value = StepResult.ok(sample_classify_data)
        mock_emit_artifact.return_value = ("success", "Artifact comment inserted ID=42")
        mock_emit_comment.return_value = ("success", "Progress comment inserted")

        step = ClassifyStep()
        result = step.run(mock_context)

        # Verify step succeeded
        assert result.success is True

        # Verify _classify_issue was called
        mock__classify_issue.assert_called_once_with(sample_issue, mock_context.adw_id)

        # Verify emit_artifact_comment was called after successful classification
        mock_emit_artifact.assert_called_once()
        call_args = mock_emit_artifact.call_args
        assert call_args[0][0] == mock_context.issue_id  # issue_id
        assert call_args[0][1] == mock_context.adw_id  # adw_id
        # Verify the artifact has the correct type
        artifact = call_args[0][2]
        assert artifact.artifact_type == "classify"
        assert artifact.classify_data == sample_classify_data

        # Verify progress comment was also emitted
        mock_emit_comment.assert_called_once()

    @patch("rouge.core.workflow.steps.classify_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.classify_step.emit_artifact_comment")
    @patch.object(ClassifyStep, "_classify_issue")
    def test_run_succeeds_even_if_artifact_comment_fails(
        self,
        mock__classify_issue,
        mock_emit_artifact,
        mock_emit_comment,
        mock_context,
        sample_issue,
        sample_classify_data,
    ):
        """Test that step succeeds even if emit_artifact_comment returns error (non-blocking)."""
        # Setup: issue loaded, classification succeeds
        def load_required_artifact(context_key, _artifact_type, _artifact_class, _extract_fn):
            if context_key == "issue":
                return sample_issue
            raise Exception(f"Required artifact '{_artifact_type}' not found")

        mock_context.load_required_artifact = load_required_artifact

        mock__classify_issue.return_value = StepResult.ok(sample_classify_data)
        # Mock artifact comment emission to fail (e.g., DB unavailable)
        mock_emit_artifact.return_value = ("error", "DB unavailable")
        mock_emit_comment.return_value = ("success", "Progress comment inserted")

        step = ClassifyStep()
        result = step.run(mock_context)

        # Verify step still succeeds (artifact comment failure is non-blocking)
        assert result.success is True

        # Verify emit_artifact_comment was called
        mock_emit_artifact.assert_called_once()

        # Verify the workflow continues and emits progress comment
        mock_emit_comment.assert_called_once()

    def test_run_fails_when_no_issue_available(self, mock_context):
        """Test that run fails when no issue is available (load_required_artifact raises)."""
        mock_context.data = {}

        from rouge.core.workflow.step_base import StepInputError

        def load_required_artifact(_context_key, _artifact_type, _artifact_class, _extract_fn):
            raise StepInputError(f"Required artifact '{_artifact_type}' not found")

        mock_context.load_required_artifact = load_required_artifact

        step = ClassifyStep()
        result = step.run(mock_context)

        assert result.success is False
        assert "Cannot classify: issue not fetched" in result.error

    @patch("rouge.core.workflow.steps.classify_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.classify_step.emit_artifact_comment")
    @patch.object(ClassifyStep, "_classify_issue")
    def test_run_fails_when__classify_issue_fails(
        self,
        mock__classify_issue,
        mock_emit_artifact,
        _mock_emit_comment,
        mock_context,
        sample_issue,
    ):
        """Test that run fails when _classify_issue fails."""

        def load_required_artifact(context_key, _artifact_type, _artifact_class, _extract_fn):
            if context_key == "issue":
                return sample_issue
            raise Exception(f"Required artifact '{_artifact_type}' not found")

        mock_context.load_required_artifact = load_required_artifact

        mock__classify_issue.return_value = StepResult.fail("Classification agent failed")

        step = ClassifyStep()
        result = step.run(mock_context)

        assert result.success is False
        assert "Error classifying issue" in result.error
        assert "Classification agent failed" in result.error

        # Verify artifact comment was not emitted (step failed before artifact creation)
        mock_emit_artifact.assert_not_called()
        _mock_emit_comment.assert_not_called()

    @patch("rouge.core.workflow.steps.classify_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.classify_step.emit_artifact_comment")
    @patch.object(ClassifyStep, "_classify_issue")
    def test_run_saves_artifact(
        self,
        mock__classify_issue,
        mock_emit_artifact,
        mock_emit_comment,
        mock_context,
        sample_issue,
        sample_classify_data,
    ):
        """Test that classification artifact is saved."""

        def load_required_artifact(context_key, _artifact_type, _artifact_class, _extract_fn):
            if context_key == "issue":
                return sample_issue
            raise Exception(f"Required artifact '{_artifact_type}' not found")

        mock_context.load_required_artifact = load_required_artifact

        mock__classify_issue.return_value = StepResult.ok(sample_classify_data)
        mock_emit_artifact.return_value = ("success", "Artifact comment inserted")
        mock_emit_comment.return_value = ("success", "Progress comment inserted")

        step = ClassifyStep()
        result = step.run(mock_context)

        assert result.success is True
        mock_context.artifact_store.write_artifact.assert_called_once()

        # Check the artifact type
        saved_artifact = mock_context.artifact_store.write_artifact.call_args[0][0]
        assert saved_artifact.artifact_type == "classify"
        assert saved_artifact.classify_data == sample_classify_data

    @patch("rouge.core.workflow.steps.classify_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.classify_step.emit_artifact_comment")
    @patch.object(ClassifyStep, "_classify_issue")
    def test_run_always_emits_artifact_comment_when_store_available(
        self,
        mock__classify_issue,
        mock_emit_artifact,
        mock_emit_comment,
        mock_context,
        sample_issue,
        sample_classify_data,
    ):
        """Test that artifact comment is always emitted when classification succeeds.

        Previously there was a guard for artifacts_enabled. Now artifact_store is always
        required, so the artifact comment is always emitted on success.
        """

        def load_required_artifact(context_key, _artifact_type, _artifact_class, _extract_fn):
            if context_key == "issue":
                return sample_issue
            raise Exception(f"Required artifact '{_artifact_type}' not found")

        mock_context.load_required_artifact = load_required_artifact

        mock__classify_issue.return_value = StepResult.ok(sample_classify_data)
        mock_emit_artifact.return_value = ("success", "Artifact comment inserted")
        mock_emit_comment.return_value = ("success", "Progress comment inserted")

        step = ClassifyStep()
        result = step.run(mock_context)

        assert result.success is True

        # Verify artifact comment IS always emitted (no artifacts_enabled guard)
        mock_emit_artifact.assert_called_once()

        # Verify progress comment was also emitted
        mock_emit_comment.assert_called_once()


class TestClassifyStepProperties:
    """Tests for ClassifyStep properties."""

    def test_step_name(self):
        """Test that ClassifyStep has correct name."""
        step = ClassifyStep()
        assert step.name == "Classifying issue"

    def test_step_is_critical(self):
        """Test that ClassifyStep is critical by default."""
        step = ClassifyStep()
        assert step.is_critical is True
