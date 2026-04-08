"""Tests for WorkflowContext with optional issue_id."""

import pytest

from rouge.core.workflow.step_base import StepInputError, WorkflowContext
from rouge.core.workflow.types import PlanData


class TestWorkflowContextCreation:
    """Tests for WorkflowContext instantiation with optional issue_id."""

    def test_context_with_issue_id_none_explicit(self) -> None:
        """Test WorkflowContext creation with issue_id explicitly set to None."""
        ctx = WorkflowContext(adw_id="adw-001", issue_id=None)

        assert ctx.adw_id == "adw-001"
        assert ctx.issue_id is None
        assert ctx.issue is None
        assert ctx.data == {}

    def test_context_with_issue_id_omitted(self) -> None:
        """Test WorkflowContext creation with issue_id omitted (defaults to None)."""
        ctx = WorkflowContext(adw_id="adw-002")

        assert ctx.adw_id == "adw-002"
        assert ctx.issue_id is None
        assert ctx.issue is None
        assert ctx.data == {}

    def test_context_with_valid_issue_id(self) -> None:
        """Test WorkflowContext creation with a valid integer issue_id."""
        ctx = WorkflowContext(adw_id="adw-003", issue_id=42)

        assert ctx.adw_id == "adw-003"
        assert ctx.issue_id == 42
        assert ctx.issue is None
        assert ctx.data == {}

    def test_context_backward_compat_keyword_args(self) -> None:
        """Test backward compatibility: existing callers using keyword args still work."""
        ctx = WorkflowContext(issue_id=1, adw_id="adw123")

        assert ctx.adw_id == "adw123"
        assert ctx.issue_id == 1

    def test_context_backward_compat_all_fields(self) -> None:
        """Test backward compatibility with all fields specified via keywords."""
        ctx = WorkflowContext(
            adw_id="adw-full",
            issue_id=99,
            issue=None,
            data={"key": "value"},
        )

        assert ctx.adw_id == "adw-full"
        assert ctx.issue_id == 99
        assert ctx.data == {"key": "value"}


class TestRequireIssueId:
    """Tests for WorkflowContext.require_issue_id property."""

    def test_require_issue_id_returns_int_when_set(self) -> None:
        """Test require_issue_id returns the issue_id when it is set."""
        ctx = WorkflowContext(adw_id="adw-req-1", issue_id=42)
        assert ctx.require_issue_id == 42

    def test_require_issue_id_raises_when_none(self) -> None:
        """Test require_issue_id raises RuntimeError when issue_id is None."""
        ctx = WorkflowContext(adw_id="adw-req-2", issue_id=None)
        with pytest.raises(RuntimeError, match="issue_id is required"):
            _ = ctx.require_issue_id

    def test_require_issue_id_raises_when_omitted(self) -> None:
        """Test require_issue_id raises RuntimeError when issue_id is omitted."""
        ctx = WorkflowContext(adw_id="adw-req-3")
        with pytest.raises(RuntimeError, match="issue_id is required"):
            _ = ctx.require_issue_id


class TestGetStepData:
    """Tests for WorkflowContext.get_step_data."""

    def test_raises_step_input_error_when_key_missing(self) -> None:
        """Test get_step_data raises StepInputError when key is not found."""
        ctx = WorkflowContext(adw_id="adw-req-missing")

        with pytest.raises(StepInputError, match="Required step data 'plan_data' not found"):
            ctx.get_step_data("plan_data")

    def test_returns_value_when_key_exists(self) -> None:
        """Test get_step_data returns the value when key exists."""
        plan_data = PlanData(plan="Test plan content", summary="Test summary")
        ctx = WorkflowContext(
            adw_id="adw-req-exists",
            data={"plan_data": plan_data},
        )

        result = ctx.get_step_data("plan_data")

        assert result is plan_data
        assert result.plan == "Test plan content"
        assert result.summary == "Test summary"

    def test_returns_cached_value_from_context_data(self) -> None:
        """Test get_step_data returns existing value from context data."""
        cached_value = PlanData(plan="Cached plan", summary="Cached summary")
        ctx = WorkflowContext(
            adw_id="adw-req-cached",
            data={"plan_data": cached_value},
        )

        result = ctx.get_step_data("plan_data")

        assert result is cached_value


class TestGetOptionalStepData:
    """Tests for WorkflowContext.get_optional_step_data."""

    def test_returns_none_when_key_missing(self) -> None:
        """Test get_optional_step_data returns None when key is not found."""
        ctx = WorkflowContext(adw_id="adw-opt-missing")

        result = ctx.get_optional_step_data("plan_data")

        assert result is None

    def test_does_not_raise_when_key_missing(self) -> None:
        """Test get_optional_step_data does not raise an exception on missing key."""
        ctx = WorkflowContext(adw_id="adw-opt-no-raise")

        # Should not raise StepInputError
        result = ctx.get_optional_step_data("plan_data")
        assert result is None

    def test_returns_value_when_key_exists(self) -> None:
        """Test get_optional_step_data returns the value when key exists."""
        plan_data = PlanData(plan="Optional plan content", summary="Optional summary")
        ctx = WorkflowContext(
            adw_id="adw-opt-exists",
            data={"plan_data": plan_data},
        )

        result = ctx.get_optional_step_data("plan_data")

        assert result is not None
        assert result.plan == "Optional plan content"
        assert result.summary == "Optional summary"

    def test_returns_cached_value_from_context_data(self) -> None:
        """Test get_optional_step_data returns existing value from context data."""
        cached_value = PlanData(plan="Cached plan", summary="Cached summary")
        ctx = WorkflowContext(
            adw_id="adw-opt-cached",
            data={"plan_data": cached_value},
        )

        result = ctx.get_optional_step_data("plan_data")

        assert result is cached_value
