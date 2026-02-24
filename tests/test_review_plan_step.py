"""Tests for ReviewPlanStep base commit extraction behavior."""

from unittest.mock import patch

from rouge.core.agents.claude import ClaudeAgentPromptResponse
from rouge.core.models import Issue
from rouge.core.workflow.steps.review_plan_step import ReviewPlanStep


def _sample_issue() -> Issue:
    return Issue(
        id=123,
        description="review from base commit HEAD~3",
        status="pending",
        type="main",
        adw_id="adw-test-review-plan",
    )


@patch("rouge.core.workflow.steps.review_plan_step.execute_template")
def test_derive_base_commit_accepts_valid_ref(mock_execute_template) -> None:
    """ReviewPlanStep should accept valid extracted refs like HEAD~3."""
    mock_execute_template.return_value = ClaudeAgentPromptResponse(
        output='{"output":"plan","base_commit":"HEAD~3","summary":"Using explicit base commit."}',
        success=True,
        session_id="sess-1",
    )

    step = ReviewPlanStep()
    result = step._derive_base_commit(_sample_issue(), "adw-1")

    assert result.success is True
    assert result.data is not None
    assert result.data.plan == "HEAD~3"


@patch("rouge.core.workflow.steps.review_plan_step.execute_template")
def test_derive_base_commit_fails_on_invalid_sentinel(mock_execute_template) -> None:
    """ReviewPlanStep should fail when command returns INVALID sentinel token."""
    mock_execute_template.return_value = ClaudeAgentPromptResponse(
        output=('{"output":"plan","base_commit":"INVALID","summary":"Unsupported format."}'),
        success=True,
        session_id="sess-2",
    )

    step = ReviewPlanStep()
    result = step._derive_base_commit(_sample_issue(), "adw-2")

    assert result.success is False
    assert result.error is not None
    assert "Unsupported review format" in result.error
