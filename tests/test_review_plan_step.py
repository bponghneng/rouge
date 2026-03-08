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


@patch("rouge.core.workflow.steps.review_plan_step.execute_template")
def test_derive_base_commit_extracts_pr_number(mock_execute_template) -> None:
    """ReviewPlanStep should extract pr_number from JSON output when present."""
    mock_execute_template.return_value = ClaudeAgentPromptResponse(
        output='{"output":"plan","base_commit":"HEAD~3","summary":"Using explicit base commit.","pr_number":42}',
        success=True,
        session_id="sess-3",
    )

    step = ReviewPlanStep()
    result = step._derive_base_commit(_sample_issue(), "adw-3")

    assert result.success is True
    assert result.data is not None
    assert result.data.pr_number == 42


@patch("rouge.core.workflow.steps.review_plan_step.execute_template")
def test_derive_base_commit_treats_missing_pr_number_as_none(mock_execute_template) -> None:
    """ReviewPlanStep should treat absent pr_number as None."""
    mock_execute_template.return_value = ClaudeAgentPromptResponse(
        output='{"output":"plan","base_commit":"HEAD~3","summary":"Using explicit base commit."}',
        success=True,
        session_id="sess-4",
    )

    step = ReviewPlanStep()
    result = step._derive_base_commit(_sample_issue(), "adw-4")

    assert result.success is True
    assert result.data is not None
    assert result.data.pr_number is None


@patch("rouge.core.workflow.steps.review_plan_step.execute_template")
def test_derive_base_commit_treats_invalid_pr_number_type_as_none(mock_execute_template) -> None:
    """ReviewPlanStep should warn and treat non-int pr_number as None."""
    mock_execute_template.return_value = ClaudeAgentPromptResponse(
        output='{"output":"plan","base_commit":"HEAD~3","summary":"Using explicit base commit.","pr_number":"not-a-number"}',
        success=True,
        session_id="sess-5",
    )

    step = ReviewPlanStep()
    result = step._derive_base_commit(_sample_issue(), "adw-5")

    assert result.success is True
    assert result.data is not None
    assert result.data.pr_number is None


@patch("rouge.core.workflow.steps.review_plan_step.execute_template")
def test_derive_base_commit_treats_non_positive_pr_number_as_none(mock_execute_template) -> None:
    """ReviewPlanStep should warn and treat pr_number <= 0 as None."""
    mock_execute_template.return_value = ClaudeAgentPromptResponse(
        output='{"output":"plan","base_commit":"HEAD~3","summary":"Using explicit base commit.","pr_number":0}',
        success=True,
        session_id="sess-6",
    )

    step = ReviewPlanStep()
    result = step._derive_base_commit(_sample_issue(), "adw-6")

    assert result.success is True
    assert result.data is not None
    assert result.data.pr_number is None
