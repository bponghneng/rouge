"""Tests for CodeReviewStep workflow step."""

import subprocess
from unittest.mock import Mock, patch

import pytest

from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.code_review_step import CodeReviewStep
from rouge.core.workflow.types import PlanData, ReviewData, StepResult


@pytest.fixture
def mock_context():
    """Create a mock workflow context."""
    context = Mock(spec=WorkflowContext)
    context.issue_id = 10
    context.require_issue_id = 10
    context.adw_id = "test-adw-review"
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
def sample_review_data():
    """Create sample review data."""
    return ReviewData(
        review_text="File: src/app.py\nLine 10: Consider using list comprehension for better performance.\n\nFile: tests/test_app.py\nLine 5: Add test coverage for edge cases."
    )


class TestCodeReviewStepRun:
    """Tests for CodeReviewStep.run method."""

    @patch("rouge.core.workflow.steps.code_review_step.emit_comment_from_payload")
    @patch.object(CodeReviewStep, "_generate_review")
    def test_run_success_emits_artifact_comment_during_generation(
        self,
        mock__generate_review,
        mock_emit_comment,
        mock_context,
        sample_plan_data,
        sample_review_data,
    ):
        """Test successful review generation emits artifact comment with full review data."""
        # Setup: plan loaded, review generation succeeds
        mock_context.data = {"plan_data": sample_plan_data}

        def load_artifact_if_missing(context_key, _artifact_type, _artifact_class, _extract_fn):
            return mock_context.data.get(context_key)

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        mock__generate_review.return_value = StepResult.ok(sample_review_data)
        # Mock for progress comment from run
        mock_emit_comment.return_value = ("success", "Comment inserted")

        step = CodeReviewStep()
        result = step.run(mock_context)

        # Verify step succeeded
        assert result.success is True

        # Verify _generate_review was called
        mock__generate_review.assert_called_once()

        # Since we mocked _generate_review, only the run method's progress comment is emitted
        # The artifact comment would be emitted inside _generate_review (tested separately)
        assert mock_emit_comment.call_count == 1

        # Verify the progress comment
        call_payload = mock_emit_comment.call_args[0][0]
        assert call_payload.kind == "workflow"
        assert "CodeRabbit review complete" in call_payload.text

    @patch("rouge.core.workflow.steps.code_review_step.emit_comment_from_payload")
    @patch.object(CodeReviewStep, "_generate_review")
    def test_run_succeeds_even_if_progress_comment_fails(
        self,
        mock__generate_review,
        mock_emit_comment,
        mock_context,
        sample_plan_data,
        sample_review_data,
    ):
        """Test that step succeeds even if progress comment fails (non-blocking)."""
        # Setup: plan loaded, review generation succeeds
        mock_context.data = {"plan_data": sample_plan_data}

        def load_artifact_if_missing(context_key, _artifact_type, _artifact_class, _extract_fn):
            return mock_context.data.get(context_key)

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        mock__generate_review.return_value = StepResult.ok(sample_review_data)

        # Mock progress comment emission to fail (e.g., DB unavailable)
        mock_emit_comment.return_value = ("error", "DB unavailable")

        step = CodeReviewStep()
        result = step.run(mock_context)

        # Verify step still succeeds (progress comment failure is non-blocking)
        assert result.success is True

        # Verify emit_comment_from_payload was called once (for progress comment)
        assert mock_emit_comment.call_count == 1

    def test_run_fails_when_no_plan_available_for_issue_workflow(self, mock_context):
        """Test that run fails when no plan is available for issue-based workflow."""
        mock_context.data = {}

        def load_artifact_if_missing(_context_key, _artifact_type, _artifact_class, _extract_fn):
            return None

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        step = CodeReviewStep()
        result = step.run(mock_context)

        assert result.success is False
        assert "No plan data available" in result.error

    @patch("rouge.core.workflow.steps.code_review_step.emit_comment_from_payload")
    @patch.object(CodeReviewStep, "_generate_review")
    def test_run_fails_when__generate_review_fails(
        self,
        mock__generate_review,
        _mock_emit_comment,
        mock_context,
        sample_plan_data,
    ):
        """Test that run fails when _generate_review fails."""
        mock_context.data = {"plan_data": sample_plan_data}

        def load_artifact_if_missing(context_key, _artifact_type, _artifact_class, _extract_fn):
            return mock_context.data.get(context_key)

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        mock__generate_review.return_value = StepResult.fail("CodeRabbit review failed")

        step = CodeReviewStep()
        result = step.run(mock_context)

        assert result.success is False
        assert "Failed to generate CodeRabbit review" in result.error
        assert "CodeRabbit review failed" in result.error

    @patch("rouge.core.workflow.steps.code_review_step.emit_comment_from_payload")
    @patch.object(CodeReviewStep, "_generate_review")
    def test_run_saves_artifact(
        self,
        mock__generate_review,
        mock_emit_comment,
        mock_context,
        sample_plan_data,
        sample_review_data,
    ):
        """Test that review artifact is saved."""
        mock_context.data = {"plan_data": sample_plan_data}

        def load_artifact_if_missing(context_key, _artifact_type, _artifact_class, _extract_fn):
            return mock_context.data.get(context_key)

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        mock__generate_review.return_value = StepResult.ok(sample_review_data)
        mock_emit_comment.return_value = ("success", "Comment inserted")

        step = CodeReviewStep()
        result = step.run(mock_context)

        assert result.success is True
        mock_context.artifact_store.write_artifact.assert_called_once()

        # Check the artifact type
        saved_artifact = mock_context.artifact_store.write_artifact.call_args[0][0]
        assert saved_artifact.artifact_type == "code-review"
        assert saved_artifact.review_data == sample_review_data

    @patch("rouge.core.workflow.steps.code_review_step.emit_comment_from_payload")
    @patch.object(CodeReviewStep, "_generate_review")
    def test_run_standalone_workflow_without_issue_id(
        self,
        mock__generate_review,
        mock_emit_comment,
        mock_context,
        sample_review_data,
    ):
        """Test that standalone codereview workflow works without issue_id."""
        # Standalone workflow: no issue_id
        mock_context.issue_id = None
        mock_context.data = {}

        def load_artifact_if_missing(_context_key, _artifact_type, _artifact_class, _extract_fn):
            return None

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        mock__generate_review.return_value = StepResult.ok(sample_review_data)

        step = CodeReviewStep()
        result = step.run(mock_context)

        # Verify step succeeded
        assert result.success is True

        # Verify _generate_review was called (without plan_data)
        mock__generate_review.assert_called_once()

        # For standalone workflow (issue_id=None), no progress comment is emitted from run
        # The artifact comment would be emitted inside _generate_review (tested separately)
        mock_emit_comment.assert_not_called()


class TestCodeReviewStepGenerateReview:
    """Tests for CodeReviewStep._generate_review method."""

    @patch("rouge.core.workflow.steps.code_review_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.code_review_step.subprocess.run")
    @patch("rouge.core.workflow.steps.code_review_step.os.path.exists")
    def test_generate_review_emits_artifact_comment_with_full_review(
        self,
        mock_exists,
        mock_subprocess,
        mock_emit_comment,
    ):
        """Test _generate_review emits artifact comment with type='artifact' and full review data in raw."""
        mock_exists.return_value = True

        # Mock successful CodeRabbit execution
        review_text = "File: src/app.py\nLine 10: Consider refactoring for clarity."
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=review_text,
            stderr="",
        )

        mock_emit_comment.return_value = ("success", "Artifact comment inserted")

        step = CodeReviewStep()
        result = step._generate_review(
            repo_path="/test/repo",
            issue_id=10,
            adw_id="test-adw",
        )

        # Verify review generation succeeded
        assert result.success is True
        assert result.data is not None
        assert result.data.review_text == review_text

        # Verify emit_comment_from_payload was called with artifact comment
        mock_emit_comment.assert_called_once()
        payload = mock_emit_comment.call_args[0][0]

        # Verify payload structure
        assert payload.issue_id == 10
        assert payload.adw_id == "test-adw"
        assert payload.kind == "artifact"
        assert payload.source == "system"
        assert payload.text == "CodeRabbit review generated"

        # Verify raw field contains full review text
        assert "review_text" in payload.raw
        assert payload.raw["review_text"] == review_text

    @patch("rouge.core.workflow.steps.code_review_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.code_review_step.subprocess.run")
    @patch("rouge.core.workflow.steps.code_review_step.os.path.exists")
    def test_generate_review_succeeds_even_if_emit_comment_fails(
        self,
        mock_exists,
        mock_subprocess,
        mock_emit_comment,
    ):
        """Test _generate_review succeeds even if emit_comment_from_payload fails."""
        mock_exists.return_value = True

        review_text = "Review completed."
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=review_text,
            stderr="",
        )

        # Mock emit_comment to fail
        mock_emit_comment.return_value = ("error", "DB unavailable")

        step = CodeReviewStep()
        result = step._generate_review(
            repo_path="/test/repo",
            issue_id=10,
            adw_id="test-adw",
        )

        # Verify review generation still succeeded (comment failure is non-blocking)
        assert result.success is True
        assert result.data is not None
        assert result.data.review_text == review_text

        # Verify emit_comment was called (and logged the error)
        mock_emit_comment.assert_called_once()

    @patch("rouge.core.workflow.steps.code_review_step.subprocess.run")
    @patch("rouge.core.workflow.steps.code_review_step.os.path.exists")
    def test_generate_review_fails_when_config_missing(
        self,
        mock_exists,
        _mock_subprocess,
    ):
        """Test _generate_review fails when .coderabbit.yaml config is missing."""
        mock_exists.return_value = False

        step = CodeReviewStep()
        result = step._generate_review(
            repo_path="/test/repo",
            issue_id=10,
            adw_id="test-adw",
        )

        # Verify review generation failed
        assert result.success is False
        assert "CodeRabbit config not found" in result.error

    @patch("rouge.core.workflow.steps.code_review_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.code_review_step.subprocess.run")
    @patch("rouge.core.workflow.steps.code_review_step.os.path.exists")
    def test_generate_review_fails_when_subprocess_fails(
        self,
        mock_exists,
        mock_subprocess,
        _mock_emit_comment,
    ):
        """Test _generate_review fails when CodeRabbit subprocess fails."""
        mock_exists.return_value = True

        # Mock subprocess failure
        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="CodeRabbit error: invalid config",
        )

        step = CodeReviewStep()
        result = step._generate_review(
            repo_path="/test/repo",
            issue_id=10,
            adw_id="test-adw",
        )

        # Verify review generation failed
        assert result.success is False
        assert "CodeRabbit review failed with code 1" in result.error

    @patch("rouge.core.workflow.steps.code_review_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.code_review_step.subprocess.run")
    @patch("rouge.core.workflow.steps.code_review_step.os.path.exists")
    def test_generate_review_handles_timeout(
        self,
        mock_exists,
        mock_subprocess,
        _mock_emit_comment,
    ):
        """Test _generate_review handles subprocess timeout."""
        mock_exists.return_value = True

        # Mock subprocess timeout
        mock_subprocess.side_effect = subprocess.TimeoutExpired(
            cmd=["coderabbit"], timeout=600
        )

        step = CodeReviewStep()
        result = step._generate_review(
            repo_path="/test/repo",
            issue_id=10,
            adw_id="test-adw",
        )

        # Verify review generation failed
        assert result.success is False
        assert "timed out" in result.error


class TestCodeReviewStepProperties:
    """Tests for CodeReviewStep properties."""

    def test_step_name(self):
        """Test that CodeReviewStep has correct name."""
        step = CodeReviewStep()
        assert step.name == "Generating CodeRabbit review"

    def test_step_is_not_critical(self):
        """Test that CodeReviewStep is not critical."""
        step = CodeReviewStep()
        assert step.is_critical is False
