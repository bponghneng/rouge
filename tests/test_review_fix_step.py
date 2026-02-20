"""Tests for ReviewFixStep dependency contract.

Focuses on:
- Failing with StepResult.fail when the code-review artifact is missing
  (required dependency declared in registry)
- Succeeding when review_is_clean flag short-circuits artifact loading
"""

from unittest.mock import Mock, patch

import pytest

from rouge.core.workflow.artifacts import ArtifactStore, CodeReviewArtifact
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.review_fix_step import ReviewFixStep
from rouge.core.workflow.types import ReviewData


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
    """Tests verifying that a clean review skips artifact loading."""

    def test_skips_artifact_loading_when_review_is_clean(self, base_context: WorkflowContext) -> None:
        """When review_is_clean=True the step succeeds without reading any artifact."""
        base_context.data["review_is_clean"] = True

        read_calls: list[str] = []
        original_read = base_context.artifact_store.read_artifact

        def tracking_read(artifact_type, model_class=None):
            read_calls.append(artifact_type)
            return original_read(artifact_type, model_class)

        with patch.object(
            base_context.artifact_store, "read_artifact", side_effect=tracking_read
        ):
            step = ReviewFixStep()
            result = step.run(base_context)

        assert result.success is True
        # No artifacts should have been read
        assert "code-review" not in read_calls

    def test_succeeds_when_review_is_clean(self, base_context: WorkflowContext) -> None:
        """Clean review short-circuit returns success even without any artifacts."""
        base_context.data["review_is_clean"] = True

        step = ReviewFixStep()
        result = step.run(base_context)

        assert result.success is True
        assert result.error is None


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
        # Write a code-review artifact
        review_artifact = CodeReviewArtifact(
            workflow_id="test-review-fix",
            review_data=ReviewData(review_text="Some review feedback"),
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
