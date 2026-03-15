"""Tests for ReviewFixStep dependency contract.

Focuses on:
- Failing with StepResult.fail when the code-review artifact is missing
  (required dependency declared in registry)
- Succeeding when artifact's is_clean flag short-circuits processing
"""

from unittest.mock import Mock, patch

import pytest

from rouge.core.workflow.artifacts import ArtifactStore, CodeReviewArtifact
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.review_fix_step import ReviewFixStep
from rouge.core.workflow.types import RepoReviewResult


@pytest.fixture
def store(tmp_path) -> ArtifactStore:
    """Create a temporary artifact store."""
    return ArtifactStore(workflow_id="test-review-fix", base_path=tmp_path)


@pytest.fixture
def base_context(store: ArtifactStore) -> WorkflowContext:
    """Create a workflow context with empty store (no code-review artifact)."""
    return WorkflowContext(
        adw_id="test-review-fix",
        issue_id=99,
        artifact_store=store,
    )


class TestReviewFixStepMissingArtifact:
    """Tests verifying ReviewFixStep fails when code-review artifact is missing."""

    def test_fails_when_code_review_artifact_missing(self, base_context: WorkflowContext) -> None:
        """ReviewFixStep returns StepResult.fail when code-review artifact is absent.

        The code-review dependency is declared as required (no dependency_kinds entry).
        load_required_artifact raises StepInputError which is caught, returning a fail result.
        """
        step = ReviewFixStep()
        result = step.run(base_context)

        assert result.success is False
        assert result.error is not None
        assert "code-review" in result.error.lower() or "artifact" in result.error.lower()

    def test_error_message_is_actionable(self, base_context: WorkflowContext) -> None:
        """Error message when code-review is missing is actionable."""
        step = ReviewFixStep()
        result = step.run(base_context)

        assert result.success is False
        assert result.error is not None
        # Error should be non-empty and mention the issue
        assert len(result.error) > 0


class TestReviewFixStepCleanReviewShortCircuit:
    """Tests verifying that a clean review short-circuits without addressing issues."""

    def test_skips_review_fix_when_artifact_is_clean(self, store: ArtifactStore) -> None:
        """When artifact.is_clean=True the step succeeds without addressing issues."""
        # Create a clean review artifact
        artifact = CodeReviewArtifact(
            workflow_id="test-review-fix",
            repo_reviews=[
                RepoReviewResult(
                    repo_path="/path/to/repo",
                    review_text="Code looks good",
                    is_clean=True,
                ),
            ],
            is_clean=True,
        )
        store.write_artifact(artifact)

        context = WorkflowContext(
            adw_id="test-review-fix",
            issue_id=99,
            artifact_store=store,
        )

        # Mock _address_review_issues to verify it's not called
        step = ReviewFixStep()
        with patch.object(step, "_address_review_issues") as mock_address:
            result = step.run(context)

        assert result.success is True
        # _address_review_issues should not have been called
        mock_address.assert_not_called()

    def test_succeeds_when_review_is_clean(self, store: ArtifactStore) -> None:
        """Clean review short-circuit returns success."""
        # Create a clean review artifact
        artifact = CodeReviewArtifact(
            workflow_id="test-review-fix",
            repo_reviews=[
                RepoReviewResult(
                    repo_path="/path/to/repo",
                    review_text="Code looks good",
                    is_clean=True,
                ),
            ],
            is_clean=True,
        )
        store.write_artifact(artifact)

        context = WorkflowContext(
            adw_id="test-review-fix",
            issue_id=99,
            artifact_store=store,
        )

        step = ReviewFixStep()
        result = step.run(context)

        assert result.success is True
        assert result.error is None


class TestReviewFixMultiRepo:
    """Tests for ReviewFixStep multi-repo filtering and rerun limit behavior."""

    def test_review_fix_skips_clean_repos(self, store: ArtifactStore) -> None:
        """Two repos, one clean — verify _address_review_issues receives only the dirty repo's review text."""
        review_artifact = CodeReviewArtifact(
            workflow_id="test-review-fix",
            repo_reviews=[
                RepoReviewResult(
                    repo_path="/path/to/clean-repo",
                    review_text="Review completed",
                    is_clean=True,
                ),
                RepoReviewResult(
                    repo_path="/path/to/dirty-repo",
                    review_text="File: src/dirty.py\nLine 10: Bug found",
                    is_clean=False,
                    rerun_count=0,
                ),
            ],
            is_clean=False,
        )
        store.write_artifact(review_artifact)

        context = WorkflowContext(
            adw_id="test-review-fix",
            issue_id=99,
            artifact_store=store,
        )

        step = ReviewFixStep()
        with patch.object(step, "_address_review_issues") as mock_address:
            from rouge.core.workflow.types import StepResult

            mock_address.return_value = StepResult.ok(
                None, parsed_data={"issues": [], "summary": "Fixed"}
            )
            step.run(context)

        # _address_review_issues should be called with only the dirty repo's text
        mock_address.assert_called_once()
        review_text_arg = mock_address.call_args[0][2]
        assert "/path/to/dirty-repo" in review_text_arg
        assert "Bug found" in review_text_arg
        # Clean repo text should NOT appear
        assert "Review completed" not in review_text_arg or "/path/to/clean-repo" not in review_text_arg

    def test_review_fix_per_repo_rerun_limit(self, store: ArtifactStore) -> None:
        """Two repos, one at max rerun count — verify only the other repo triggers re-review."""
        review_artifact = CodeReviewArtifact(
            workflow_id="test-review-fix",
            repo_reviews=[
                RepoReviewResult(
                    repo_path="/path/to/maxed-repo",
                    review_text="File: src/maxed.py\nIssue",
                    is_clean=False,
                    rerun_count=5,
                ),
                RepoReviewResult(
                    repo_path="/path/to/active-repo",
                    review_text="File: src/active.py\nIssue",
                    is_clean=False,
                    rerun_count=0,
                ),
            ],
            is_clean=False,
        )
        store.write_artifact(review_artifact)

        context = WorkflowContext(
            adw_id="test-review-fix",
            issue_id=99,
            artifact_store=store,
        )

        step = ReviewFixStep()
        with patch.object(step, "_address_review_issues") as mock_address:
            from rouge.core.workflow.types import StepResult

            mock_address.return_value = StepResult.ok(
                None, parsed_data={"issues": [], "summary": "Fixed"}
            )
            result = step.run(context)

        # _address_review_issues should be called only with the active repo's text
        mock_address.assert_called_once()
        review_text_arg = mock_address.call_args[0][2]
        assert "/path/to/active-repo" in review_text_arg
        assert "/path/to/maxed-repo" not in review_text_arg

        # Should request rerun because the active repo still has budget
        assert result.success is True
        assert result.rerun_from is not None

    def test_review_fix_all_repos_at_limit(self, store: ArtifactStore) -> None:
        """Both repos at max — verify no rerun requested and _address_review_issues is not called."""
        review_artifact = CodeReviewArtifact(
            workflow_id="test-review-fix",
            repo_reviews=[
                RepoReviewResult(
                    repo_path="/path/to/repo-a",
                    review_text="File: src/a.py\nIssue",
                    is_clean=False,
                    rerun_count=5,
                ),
                RepoReviewResult(
                    repo_path="/path/to/repo-b",
                    review_text="File: src/b.py\nIssue",
                    is_clean=False,
                    rerun_count=5,
                ),
            ],
            is_clean=False,
        )
        store.write_artifact(review_artifact)

        context = WorkflowContext(
            adw_id="test-review-fix",
            issue_id=99,
            artifact_store=store,
        )

        step = ReviewFixStep()
        with patch.object(step, "_address_review_issues") as mock_address:
            result = step.run(context)

        # _address_review_issues should NOT be called — all repos exhausted
        mock_address.assert_not_called()
        assert result.success is True
        assert result.rerun_from is None


class TestReviewFixStepWithArtifact:
    """Tests verifying ReviewFixStep runs correctly when code-review artifact is present."""

    @patch("rouge.core.workflow.steps.review_fix_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.review_fix_step.log_artifact_comment_status")
    @patch("rouge.core.workflow.steps.review_fix_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.steps.review_fix_step.execute_template")
    def test_loads_review_from_artifact(
        self,
        mock_execute,
        mock_emit,
        _mock_log,
        mock_emit_artifact,
        base_context: WorkflowContext,
        store: ArtifactStore,
    ) -> None:
        """Step loads review_data from code-review artifact when present."""
        # Write a code-review artifact with a dirty repo
        review_artifact = CodeReviewArtifact(
            workflow_id="test-review-fix",
            repo_reviews=[
                RepoReviewResult(
                    repo_path="/path/to/repo",
                    review_text="Some review feedback",
                    is_clean=False,
                ),
            ],
        )
        store.write_artifact(review_artifact)

        # Mock agent response
        mock_response = Mock()
        mock_response.success = True
        mock_response.output = (
            '{"output": "implement-review", "summary": "done", '
            '"issues": [{"file": "a.py", "lines": "1", "type": "bug", '
            '"status": "fixed", "notes": "fixed"}]}'
        )
        mock_execute.return_value = mock_response
        mock_emit.return_value = ("success", "ok")
        mock_emit_artifact.return_value = ("success", "ok")

        step = ReviewFixStep()
        result = step.run(base_context)

        # With a successful agent response, step should succeed
        assert result.success is True
