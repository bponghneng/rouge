"""Tests for CodeReviewStep workflow step."""

import os
import subprocess
from unittest.mock import ANY, Mock, patch

import pytest

from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.code_review_step import CodeReviewStep, is_clean_review
from rouge.core.workflow.types import PlanData, ReviewData, StepResult


@pytest.fixture
def mock_context() -> Mock:
    """Create a mock workflow context."""
    context = Mock(spec=WorkflowContext)
    context.issue_id = 10
    context.require_issue_id = 10
    context.adw_id = "test-adw-review"
    context.data = {}
    context.artifact_store = Mock()
    context.repo_paths = ["/path/to/repo"]
    context.load_optional_artifact.return_value = None
    return context


@pytest.fixture
def sample_plan_data() -> PlanData:
    """Create a sample PlanData."""
    return PlanData(
        plan="## Plan\n\n### Step 1\nImplement feature X",
        summary="Implement feature X",
        session_id="session-123",
    )


@pytest.fixture
def sample_review_data() -> ReviewData:
    """Create sample review data."""
    return ReviewData(
        review_text="File: src/app.py\nLine 10: Consider using list comprehension for better performance.\n\nFile: tests/test_app.py\nLine 5: Add test coverage for edge cases."
    )


class TestCodeReviewStepRun:
    """Tests for CodeReviewStep.run method."""

    @patch("rouge.core.workflow.steps.code_review_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.code_review_step.emit_comment_from_payload")
    @patch.object(CodeReviewStep, "_generate_review")
    def test_run_success_emits_artifact_comment_during_generation(
        self,
        mock__generate_review,
        mock_emit_comment_from_payload,
        mock_emit_artifact_comment,
        mock_context,
        sample_plan_data,
        sample_review_data,
    ) -> None:
        """Test successful review generation emits artifact comment with full review data."""
        # Setup: plan loaded, review generation succeeds
        mock_context.data = {"plan_data": sample_plan_data}

        def load_required_artifact(context_key, _artifact_type, _artifact_class, _extract_fn):
            value = mock_context.data.get(context_key)
            if value is None:
                raise Exception(f"Required artifact '{_artifact_type}' not found")
            return value

        mock_context.load_required_artifact = load_required_artifact

        mock__generate_review.return_value = StepResult.ok(sample_review_data)
        # Mock for artifact comment
        mock_emit_artifact_comment.return_value = ("success", "Artifact comment inserted")
        # Mock for progress comment from run
        mock_emit_comment_from_payload.return_value = ("success", "Progress comment inserted")

        step = CodeReviewStep()
        result = step.run(mock_context)

        # Verify step succeeded
        assert result.success is True

        # Verify _generate_review was called
        mock__generate_review.assert_called_once()

        # Verify artifact was written with correct fields
        mock_context.artifact_store.write_artifact.assert_called_once()
        saved_artifact = mock_context.artifact_store.write_artifact.call_args[0][0]
        assert saved_artifact.artifact_type == "code-review"
        assert saved_artifact.review_data == sample_review_data
        # Verify is_clean field is False because review contains "File: src/app.py" indicating issues
        assert saved_artifact.is_clean is False

        # Verify emit_artifact_comment was called with correct arguments
        mock_emit_artifact_comment.assert_called_once_with(
            mock_context.issue_id, mock_context.adw_id, saved_artifact
        )

        # Verify the progress comment from run() was emitted
        assert mock_emit_comment_from_payload.call_count == 1
        call_payload = mock_emit_comment_from_payload.call_args[0][0]
        assert call_payload.kind == "workflow"
        assert "CodeRabbit review complete" in call_payload.text

    @patch("rouge.core.workflow.steps.code_review_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.code_review_step.emit_comment_from_payload")
    @patch.object(CodeReviewStep, "_generate_review")
    def test_run_succeeds_even_if_progress_comment_fails(
        self,
        mock__generate_review,
        mock_emit_comment,
        mock_emit_artifact_comment,
        mock_context,
        sample_plan_data,
        sample_review_data,
    ) -> None:
        """Test that step succeeds even if progress comment fails (non-blocking)."""
        # Setup: plan loaded, review generation succeeds
        mock_context.data = {"plan_data": sample_plan_data}

        def load_required_artifact(context_key, _artifact_type, _artifact_class, _extract_fn):
            value = mock_context.data.get(context_key)
            if value is None:
                raise Exception(f"Required artifact '{_artifact_type}' not found")
            return value

        mock_context.load_required_artifact = load_required_artifact

        mock__generate_review.return_value = StepResult.ok(sample_review_data)
        mock_emit_artifact_comment.return_value = ("success", "ok")

        # Mock progress comment emission to fail (e.g., DB unavailable)
        mock_emit_comment.return_value = ("error", "DB unavailable")

        step = CodeReviewStep()
        result = step.run(mock_context)

        # Verify step still succeeds (progress comment failure is non-blocking)
        assert result.success is True

        # Verify emit_comment_from_payload was called once (for progress comment)
        assert mock_emit_comment.call_count == 1

    def test_run_fails_when_no_plan_available_for_issue_workflow(self, mock_context) -> None:
        """Test that run fails when no plan is available for issue-based workflow."""
        mock_context.data = {}

        from rouge.core.workflow.step_base import StepInputError

        def load_required_artifact(_context_key, _artifact_type, _artifact_class, _extract_fn):
            raise StepInputError(f"Required artifact '{_artifact_type}' not found")

        mock_context.load_required_artifact = load_required_artifact

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
    ) -> None:
        """Test that run fails when _generate_review fails."""
        mock_context.data = {"plan_data": sample_plan_data}

        def load_required_artifact(context_key, _artifact_type, _artifact_class, _extract_fn):
            value = mock_context.data.get(context_key)
            if value is None:
                raise Exception(f"Required artifact '{_artifact_type}' not found")
            return value

        mock_context.load_required_artifact = load_required_artifact

        mock__generate_review.return_value = StepResult.fail("CodeRabbit review failed")

        step = CodeReviewStep()
        result = step.run(mock_context)

        assert result.success is False
        assert "Failed to generate CodeRabbit review" in result.error
        assert "CodeRabbit review failed" in result.error

    @patch("rouge.core.workflow.steps.code_review_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.code_review_step.emit_comment_from_payload")
    @patch.object(CodeReviewStep, "_generate_review")
    def test_run_saves_artifact(
        self,
        mock__generate_review,
        mock_emit_comment,
        mock_emit_artifact_comment,
        mock_context,
        sample_plan_data,
        sample_review_data,
    ) -> None:
        """Test that review artifact is saved."""
        mock_context.data = {"plan_data": sample_plan_data}

        def load_required_artifact(context_key, _artifact_type, _artifact_class, _extract_fn):
            value = mock_context.data.get(context_key)
            if value is None:
                raise Exception(f"Required artifact '{_artifact_type}' not found")
            return value

        mock_context.load_required_artifact = load_required_artifact

        mock__generate_review.return_value = StepResult.ok(sample_review_data)
        mock_emit_artifact_comment.return_value = ("success", "ok")
        mock_emit_comment.return_value = ("success", "Comment inserted")

        step = CodeReviewStep()
        result = step.run(mock_context)

        assert result.success is True
        mock_context.artifact_store.write_artifact.assert_called_once()

        # Check the artifact fields
        saved_artifact = mock_context.artifact_store.write_artifact.call_args[0][0]
        assert saved_artifact.artifact_type == "code-review"
        assert saved_artifact.review_data == sample_review_data
        # Verify is_clean field is set based on review content
        # Sample review has "File:" so it's not clean
        assert saved_artifact.is_clean is False

    @patch("rouge.core.workflow.steps.code_review_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.code_review_step.emit_comment_from_payload")
    @patch.object(CodeReviewStep, "_generate_review")
    def test_run_uses_base_commit_for_codereview_workflow(
        self,
        mock__generate_review,
        mock_emit_comment,
        mock_emit_artifact_comment,
        mock_context,
        sample_plan_data,
        sample_review_data,
    ) -> None:
        """Test codereview workflow passes base_commit from context to CodeRabbit."""
        mock_context.data = {
            "plan_data": sample_plan_data,
            "workflow_type": "codereview",
            "base_commit": "abc1234",
        }

        def load_required_artifact(context_key, _artifact_type, _artifact_class, _extract_fn):
            value = mock_context.data.get(context_key)
            if value is None:
                raise Exception(f"Required artifact '{_artifact_type}' not found")
            return value

        mock_context.load_required_artifact = load_required_artifact
        mock__generate_review.return_value = StepResult.ok(sample_review_data)
        mock_emit_artifact_comment.return_value = ("success", "ok")
        mock_emit_comment.return_value = ("success", "Comment inserted")

        step = CodeReviewStep()
        result = step.run(mock_context)

        assert result.success is True
        mock__generate_review.assert_called_once_with(ANY, base_commit="abc1234")

    @patch("rouge.core.workflow.steps.code_review_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.code_review_step.emit_comment_from_payload")
    @patch.object(CodeReviewStep, "_generate_review")
    def test_run_falls_back_to_plan_data_for_codereview_workflow(
        self,
        mock__generate_review,
        mock_emit_comment,
        mock_emit_artifact_comment,
        mock_context,
        sample_review_data,
    ) -> None:
        """Test codereview workflow falls back to plan_data.plan when base_commit is missing."""
        plan_data = PlanData(
            plan="def5678", summary="Derived base commit", session_id="session-123"
        )
        mock_context.data = {
            "plan_data": plan_data,
            "workflow_type": "codereview",
        }

        def load_required_artifact(context_key, _artifact_type, _artifact_class, _extract_fn):
            value = mock_context.data.get(context_key)
            if value is None:
                raise Exception(f"Required artifact '{_artifact_type}' not found")
            return value

        mock_context.load_required_artifact = load_required_artifact
        mock__generate_review.return_value = StepResult.ok(sample_review_data)
        mock_emit_artifact_comment.return_value = ("success", "ok")
        mock_emit_comment.return_value = ("success", "Comment inserted")

        step = CodeReviewStep()
        result = step.run(mock_context)

        assert result.success is True
        mock__generate_review.assert_called_once_with(ANY, base_commit="def5678")

    @patch("rouge.core.workflow.steps.code_review_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.code_review_step.emit_comment_from_payload")
    @patch.object(CodeReviewStep, "_generate_review")
    def test_run_does_not_use_plan_as_base_commit_for_non_codereview_workflow(
        self,
        mock__generate_review,
        mock_emit_comment,
        mock_emit_artifact_comment,
        mock_context,
        sample_plan_data,
        sample_review_data,
    ) -> None:
        """Test patch/main workflows never use plan markdown as CodeRabbit base_commit."""
        mock_context.data = {
            "plan_data": sample_plan_data,
            "workflow_type": "patch",
        }

        def load_required_artifact(context_key, _artifact_type, _artifact_class, _extract_fn):
            value = mock_context.data.get(context_key)
            if value is None:
                raise Exception(f"Required artifact '{_artifact_type}' not found")
            return value

        mock_context.load_required_artifact = load_required_artifact
        mock__generate_review.return_value = StepResult.ok(sample_review_data)
        mock_emit_artifact_comment.return_value = ("success", "ok")
        mock_emit_comment.return_value = ("success", "Comment inserted")

        step = CodeReviewStep()
        result = step.run(mock_context)

        assert result.success is True
        mock__generate_review.assert_called_once_with(ANY, base_commit=None)

    @patch.object(CodeReviewStep, "_post_review_summary_to_pr")
    @patch("rouge.core.workflow.steps.code_review_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.code_review_step.emit_comment_from_payload")
    @patch.object(CodeReviewStep, "_generate_review")
    def test_run_posts_review_summary_when_pr_number_set(
        self,
        mock__generate_review,
        mock_emit_comment,
        mock_emit_artifact_comment,
        mock_post_review_summary,
        mock_context,
        sample_plan_data,
        sample_review_data,
    ) -> None:
        """Test run calls _post_review_summary_to_pr when pr_number and platform are set."""
        mock_context.data = {"plan_data": sample_plan_data, "pr_number": 99}

        def load_required_artifact(context_key, _artifact_type, _artifact_class, _extract_fn):
            value = mock_context.data.get(context_key)
            if value is None:
                raise Exception(f"Required artifact '{_artifact_type}' not found")
            return value

        mock_context.load_required_artifact = load_required_artifact
        mock__generate_review.return_value = StepResult.ok(sample_review_data)
        mock_emit_artifact_comment.return_value = ("success", "ok")
        mock_emit_comment.return_value = ("success", "Comment inserted")

        with patch.dict("os.environ", {"DEV_SEC_OPS_PLATFORM": "github"}):
            step = CodeReviewStep()
            result = step.run(mock_context)

        assert result.success is True
        mock_post_review_summary.assert_called_once_with(
            review_text=sample_review_data.review_text,
            pr_number=99,
            platform="github",
            repo_path="/path/to/repo",
            adw_id=mock_context.adw_id,
            issue_id=mock_context.issue_id,
        )

    @patch.object(CodeReviewStep, "_post_review_summary_to_pr")
    @patch("rouge.core.workflow.steps.code_review_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.code_review_step.emit_comment_from_payload")
    @patch.object(CodeReviewStep, "_generate_review")
    def test_run_skips_review_summary_when_pr_number_absent(
        self,
        mock__generate_review,
        mock_emit_comment,
        mock_emit_artifact_comment,
        mock_post_review_summary,
        mock_context,
        sample_plan_data,
        sample_review_data,
    ) -> None:
        """Test run skips _post_review_summary_to_pr when pr_number is absent."""
        mock_context.data = {"plan_data": sample_plan_data}

        def load_required_artifact(context_key, _artifact_type, _artifact_class, _extract_fn):
            value = mock_context.data.get(context_key)
            if value is None:
                raise Exception(f"Required artifact '{_artifact_type}' not found")
            return value

        mock_context.load_required_artifact = load_required_artifact
        mock__generate_review.return_value = StepResult.ok(sample_review_data)
        mock_emit_artifact_comment.return_value = ("success", "ok")
        mock_emit_comment.return_value = ("success", "Comment inserted")

        with patch.dict("os.environ", {"DEV_SEC_OPS_PLATFORM": "github"}):
            step = CodeReviewStep()
            result = step.run(mock_context)

        assert result.success is True
        mock_post_review_summary.assert_not_called()

    @patch.object(CodeReviewStep, "_post_review_summary_to_pr")
    @patch("rouge.core.workflow.steps.code_review_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.code_review_step.emit_comment_from_payload")
    @patch.object(CodeReviewStep, "_generate_review")
    def test_run_skips_review_summary_when_platform_absent(
        self,
        mock__generate_review,
        mock_emit_comment,
        mock_emit_artifact_comment,
        mock_post_review_summary,
        mock_context,
        sample_plan_data,
        sample_review_data,
    ) -> None:
        """Test run skips _post_review_summary_to_pr when DEV_SEC_OPS_PLATFORM is not set."""
        mock_context.data = {"plan_data": sample_plan_data, "pr_number": 99}

        def load_required_artifact(context_key, _artifact_type, _artifact_class, _extract_fn):
            value = mock_context.data.get(context_key)
            if value is None:
                raise Exception(f"Required artifact '{_artifact_type}' not found")
            return value

        mock_context.load_required_artifact = load_required_artifact
        mock__generate_review.return_value = StepResult.ok(sample_review_data)
        mock_emit_artifact_comment.return_value = ("success", "ok")
        mock_emit_comment.return_value = ("success", "Comment inserted")

        env_without_platform = {k: v for k, v in os.environ.items() if k != "DEV_SEC_OPS_PLATFORM"}
        with patch.dict("os.environ", env_without_platform, clear=True):
            step = CodeReviewStep()
            result = step.run(mock_context)

        assert result.success is True
        mock_post_review_summary.assert_not_called()

    @patch("rouge.core.workflow.steps.code_review_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.code_review_step.emit_comment_from_payload")
    @patch.object(CodeReviewStep, "_generate_review")
    def test_run_standalone_workflow_without_issue_id(
        self,
        mock__generate_review,
        mock_emit_comment,
        mock_emit_artifact_comment,
        mock_context,
        sample_plan_data,
        sample_review_data,
    ) -> None:
        """Test that standalone codereview workflow works without issue_id."""
        # Standalone workflow: no issue_id
        mock_context.issue_id = None
        mock_context.data = {"plan_data": sample_plan_data}

        def load_required_artifact(context_key, _artifact_type, _artifact_class, _extract_fn):
            value = mock_context.data.get(context_key)
            if value is None:
                raise Exception(f"Required artifact '{_artifact_type}' not found")
            return value

        mock_context.load_required_artifact = load_required_artifact

        mock__generate_review.return_value = StepResult.ok(sample_review_data)
        mock_emit_artifact_comment.return_value = ("success", "ok")

        step = CodeReviewStep()
        result = step.run(mock_context)

        # Verify step succeeded
        assert result.success is True

        # Verify _generate_review was called (without plan_data)
        mock__generate_review.assert_called_once()

        # For standalone workflow (issue_id=None), no progress comment is emitted from run
        # emit_artifact_comment is called in run() but skipped when issue_id is None (returns "skipped")
        mock_emit_comment.assert_not_called()


class TestCodeReviewStepPostReviewSummary:
    """Tests for CodeReviewStep._post_review_summary_to_pr method."""

    @patch.object(CodeReviewStep, "_post_comment_to_pr")
    @patch("rouge.core.workflow.steps.code_review_step.execute_template")
    def test_post_review_summary_calls_post_comment_to_pr(
        self, mock_execute_template, mock_post_comment
    ) -> None:
        """Test _post_review_summary_to_pr calls _post_comment_to_pr on success."""
        from rouge.core.agents.claude import ClaudeAgentPromptResponse

        # Return JSON output with summary field (Phase 3 updated code to parse JSON)
        json_output = '{"output": "code-review-summary", "summary": "Two critical issues found."}'
        mock_execute_template.return_value = ClaudeAgentPromptResponse(
            output=json_output,
            success=True,
            session_id="sess-summary",
        )

        step = CodeReviewStep()
        step._post_review_summary_to_pr(
            review_text="File: src/app.py\nLine 10: Issue.",
            pr_number=42,
            platform="github",
            repo_path="/repo",
            adw_id="adw-1",
            issue_id=10,
        )

        mock_post_comment.assert_called_once()
        call_kwargs = mock_post_comment.call_args.kwargs
        assert call_kwargs["pr_number"] == 42
        assert call_kwargs["platform_lower"] == "github"

    def test_post_review_summary_skips_unsupported_platform(self) -> None:
        """Test _post_review_summary_to_pr returns early for unsupported platform."""
        step = CodeReviewStep()
        # Should not raise; just logs a warning and returns
        step._post_review_summary_to_pr(
            review_text="File: src/app.py\nLine 10: Issue.",
            pr_number=42,
            platform="bitbucket",
            repo_path="/repo",
            adw_id="adw-1",
            issue_id=10,
        )

    @patch("rouge.core.workflow.steps.code_review_step.execute_template")
    def test_post_review_summary_suppresses_execute_template_failure(
        self, mock_execute_template
    ) -> None:
        """Test _post_review_summary_to_pr suppresses exceptions from execute_template."""
        mock_execute_template.side_effect = RuntimeError("Claude unavailable")

        step = CodeReviewStep()
        # Should not raise; failure is suppressed (best-effort)
        step._post_review_summary_to_pr(
            review_text="File: src/app.py\nLine 10: Issue.",
            pr_number=42,
            platform="github",
            repo_path="/repo",
            adw_id="adw-1",
            issue_id=10,
        )

    @patch.object(CodeReviewStep, "_post_comment_to_pr")
    @patch("rouge.core.workflow.steps.code_review_step.execute_template")
    def test_post_review_summary_to_pr_with_structured_output(
        self, mock_execute_template, mock_post_comment
    ) -> None:
        """Test _post_review_summary_to_pr uses JSON schema and parses structured output."""
        from rouge.core.agents.claude import ClaudeAgentPromptResponse
        from rouge.core.workflow.steps.code_review_step import CODE_REVIEW_SUMMARY_JSON_SCHEMA

        # Mock execute_template to return JSON output with summary field
        json_output = '{"output": "code-review-summary", "summary": "Two critical issues found."}'
        mock_execute_template.return_value = ClaudeAgentPromptResponse(
            output=json_output,
            success=True,
            session_id="sess-summary",
        )

        step = CodeReviewStep()
        step._post_review_summary_to_pr(
            review_text="File: src/app.py\nLine 10: Issue.",
            pr_number=42,
            platform="github",
            repo_path="/repo",
            adw_id="adw-1",
            issue_id=10,
        )

        # Verify execute_template was called with json_schema and require_json=True
        mock_execute_template.assert_called_once()
        request = mock_execute_template.call_args[0][0]
        assert request.json_schema == CODE_REVIEW_SUMMARY_JSON_SCHEMA
        assert mock_execute_template.call_args[1]["require_json"] is True

        # Verify _post_comment_to_pr was called with the correctly extracted summary
        mock_post_comment.assert_called_once()
        call_kwargs = mock_post_comment.call_args.kwargs
        assert "Two critical issues found." in call_kwargs["body"]
        assert call_kwargs["pr_number"] == 42
        assert call_kwargs["platform_lower"] == "github"

    @patch.object(CodeReviewStep, "_post_comment_to_pr")
    @patch("rouge.core.workflow.steps.code_review_step.execute_template")
    def test_post_review_summary_to_pr_handles_json_parse_error(
        self, mock_execute_template, mock_post_comment
    ) -> None:
        """Test _post_review_summary_to_pr handles malformed JSON and returns early."""
        from rouge.core.agents.claude import ClaudeAgentPromptResponse

        # Mock execute_template to return malformed JSON
        mock_execute_template.return_value = ClaudeAgentPromptResponse(
            output='{invalid json syntax',
            success=True,
            session_id="sess-summary",
        )

        step = CodeReviewStep()
        # Should not raise; error is logged and method returns early
        step._post_review_summary_to_pr(
            review_text="File: src/app.py\nLine 10: Issue.",
            pr_number=42,
            platform="github",
            repo_path="/repo",
            adw_id="adw-1",
            issue_id=10,
        )

        # Verify execute_template was called
        mock_execute_template.assert_called_once()

        # Verify _post_comment_to_pr was NOT called due to JSON parse error
        mock_post_comment.assert_not_called()


class TestCodeReviewStepPostCommentToPr:
    """Tests for CodeReviewStep._post_comment_to_pr method."""

    @patch("rouge.core.workflow.steps.code_review_step.subprocess.run")
    def test_github_comment_posted_successfully(self, mock_run) -> None:
        """Test _post_comment_to_pr posts a GitHub PR comment on success."""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        step = CodeReviewStep()
        step._post_comment_to_pr(
            body="Summary text.",
            pr_number=42,
            platform_lower="github",
            repo_path="/repo",
        )

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "gh"
        assert "42" in cmd

    @patch("rouge.core.workflow.steps.code_review_step.subprocess.run")
    def test_gitlab_comment_posted_successfully(self, mock_run) -> None:
        """Test _post_comment_to_pr posts a GitLab MR comment on success."""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        step = CodeReviewStep()
        step._post_comment_to_pr(
            body="Summary text.",
            pr_number=7,
            platform_lower="gitlab",
            repo_path="/repo",
        )

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "glab"
        assert "7" in cmd

    def test_empty_repo_path_returns_early(self) -> None:
        """Test _post_comment_to_pr returns early for empty repo_path."""
        step = CodeReviewStep()
        # Should not raise; logs a warning and returns
        step._post_comment_to_pr(
            body="Summary text.",
            pr_number=42,
            platform_lower="github",
            repo_path="",
        )

    def test_empty_body_returns_early(self) -> None:
        """Test _post_comment_to_pr returns early for whitespace-only body."""
        step = CodeReviewStep()
        step._post_comment_to_pr(
            body="   ",
            pr_number=42,
            platform_lower="github",
            repo_path="/repo",
        )

    @patch("rouge.core.workflow.steps.code_review_step.subprocess.run")
    def test_subprocess_failure_is_logged(self, mock_run) -> None:
        """Test _post_comment_to_pr logs error on non-zero exit code."""
        mock_run.return_value = Mock(returncode=1, stdout="", stderr="CLI error")

        step = CodeReviewStep()
        # Should not raise; failure is logged
        step._post_comment_to_pr(
            body="Summary text.",
            pr_number=42,
            platform_lower="github",
            repo_path="/repo",
        )

    @patch("rouge.core.workflow.steps.code_review_step.subprocess.run")
    def test_subprocess_exception_is_suppressed(self, mock_run) -> None:
        """Test _post_comment_to_pr suppresses subprocess exceptions."""
        mock_run.side_effect = FileNotFoundError("gh not found")

        step = CodeReviewStep()
        # Should not raise; exception is suppressed
        step._post_comment_to_pr(
            body="Summary text.",
            pr_number=42,
            platform_lower="github",
            repo_path="/repo",
        )

    @patch.dict("os.environ", {"GITHUB_PAT": "test-pat"})
    @patch("rouge.core.workflow.steps.code_review_step.subprocess.run")
    def test_github_pat_forwarded_as_gh_token(self, mock_run) -> None:
        """Test _post_comment_to_pr forwards GITHUB_PAT as GH_TOKEN."""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        step = CodeReviewStep()
        step._post_comment_to_pr(
            body="Summary text.",
            pr_number=42,
            platform_lower="github",
            repo_path="/repo",
        )

        _, kwargs = mock_run.call_args
        env = kwargs.get("env", {})
        assert env.get("GH_TOKEN") == "test-pat"


class TestCodeReviewStepGenerateReview:
    """Tests for CodeReviewStep._generate_review method."""

    @patch("rouge.core.workflow.steps.code_review_step.subprocess.run")
    @patch("rouge.core.workflow.steps.code_review_step.os.path.exists")
    def test_generate_review_returns_correct_data(
        self,
        mock_exists,
        mock_subprocess,
    ) -> None:
        """Test _generate_review succeeds and returns correct review data."""
        mock_exists.return_value = True

        # Mock successful CodeRabbit execution
        review_text = "File: src/app.py\nLine 10: Consider refactoring for clarity."
        mock_subprocess.return_value = Mock(
            returncode=0,
            stdout=review_text,
            stderr="",
        )

        step = CodeReviewStep()
        result = step._generate_review(repo_path="/test/repo")

        # Verify review generation succeeded
        assert result.success is True
        assert result.data is not None
        assert result.data.review_text == review_text

    @patch("rouge.core.workflow.steps.code_review_step.subprocess.run")
    @patch("rouge.core.workflow.steps.code_review_step.os.path.exists")
    def test_generate_review_fails_when_config_missing(
        self,
        mock_exists,
        _mock_subprocess,
    ) -> None:
        """Test _generate_review fails when .coderabbit.yaml config is missing."""
        mock_exists.return_value = False

        step = CodeReviewStep()
        result = step._generate_review(repo_path="/test/repo")

        # Verify review generation failed
        assert result.success is False
        assert "CodeRabbit config not found" in result.error

    @patch("rouge.core.workflow.steps.code_review_step.subprocess.run")
    @patch("rouge.core.workflow.steps.code_review_step.os.path.exists")
    def test_generate_review_fails_when_subprocess_fails(
        self,
        mock_exists,
        mock_subprocess,
    ) -> None:
        """Test _generate_review fails when CodeRabbit subprocess fails."""
        mock_exists.return_value = True

        # Mock subprocess failure
        mock_subprocess.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="CodeRabbit error: invalid config",
        )

        step = CodeReviewStep()
        result = step._generate_review(repo_path="/test/repo")

        # Verify review generation failed
        assert result.success is False
        assert "CodeRabbit review failed with code 1" in result.error

    @patch("rouge.core.workflow.steps.code_review_step.subprocess.run")
    @patch("rouge.core.workflow.steps.code_review_step.os.path.exists")
    def test_generate_review_handles_timeout(
        self,
        mock_exists,
        mock_subprocess,
    ) -> None:
        """Test _generate_review handles subprocess timeout."""
        mock_exists.return_value = True

        # Mock subprocess timeout
        mock_subprocess.side_effect = subprocess.TimeoutExpired(cmd=["coderabbit"], timeout=600)

        step = CodeReviewStep()
        result = step._generate_review(repo_path="/test/repo")

        # Verify review generation failed
        assert result.success is False
        assert "timed out" in result.error


class TestCodeReviewStepProperties:
    """Tests for CodeReviewStep properties."""

    def test_step_name(self) -> None:
        """Test that CodeReviewStep has correct name."""
        step = CodeReviewStep()
        assert step.name == "Generating CodeRabbit review"

    def test_step_is_not_critical(self) -> None:
        """Test that CodeReviewStep is not critical."""
        step = CodeReviewStep()
        assert step.is_critical is False


class TestIsCleanReviewHeuristic:
    """Tests for is_clean_review function."""

    @pytest.mark.parametrize(
        "review_text,expected",
        [
            ("Review completed", True),
            ("Review completed\nFile: foo.py", False),
            ("Review completed\n\nFile: foo.py", False),
            ("File: bar.py\nSome issue", False),
            ("Some other text", False),
            ("  Review completed  ", True),
            ("Review completed\nSome text but no file marker", True),
        ],
    )
    def test_is_clean_review_heuristic(self, review_text: str, expected: bool) -> None:
        """Test is_clean_review heuristic with various review texts."""
        result = is_clean_review(review_text)
        assert result is expected
