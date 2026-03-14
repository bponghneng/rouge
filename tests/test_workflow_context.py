"""Tests for WorkflowContext with optional issue_id."""

from pathlib import Path

import pytest

from rouge.core.workflow.artifacts import ArtifactStore, PlanArtifact
from rouge.core.workflow.step_base import StepInputError, WorkflowContext
from rouge.core.workflow.types import PlanData


class TestWorkflowContextCreation:
    """Tests for WorkflowContext instantiation with optional issue_id."""

    def test_context_with_issue_id_none_explicit(self, tmp_path: Path) -> None:
        """Test WorkflowContext creation with issue_id explicitly set to None."""
        store = ArtifactStore(workflow_id="adw-001", base_path=tmp_path)
        ctx = WorkflowContext(adw_id="adw-001", issue_id=None, artifact_store=store)

        assert ctx.adw_id == "adw-001"
        assert ctx.issue_id is None
        assert ctx.issue is None
        assert ctx.data == {}
        assert ctx.artifact_store is store

    def test_context_with_issue_id_omitted(self, tmp_path: Path) -> None:
        """Test WorkflowContext creation with issue_id omitted (defaults to None)."""
        store = ArtifactStore(workflow_id="adw-002", base_path=tmp_path)
        ctx = WorkflowContext(adw_id="adw-002", artifact_store=store)

        assert ctx.adw_id == "adw-002"
        assert ctx.issue_id is None
        assert ctx.issue is None
        assert ctx.data == {}

    def test_context_with_valid_issue_id(self, tmp_path: Path) -> None:
        """Test WorkflowContext creation with a valid integer issue_id."""
        store = ArtifactStore(workflow_id="adw-003", base_path=tmp_path)
        ctx = WorkflowContext(adw_id="adw-003", issue_id=42, artifact_store=store)

        assert ctx.adw_id == "adw-003"
        assert ctx.issue_id == 42
        assert ctx.issue is None
        assert ctx.data == {}

    def test_context_backward_compat_keyword_args(self, tmp_path: Path) -> None:
        """Test backward compatibility: existing callers using keyword args still work."""
        store = ArtifactStore(workflow_id="adw123", base_path=tmp_path)
        ctx = WorkflowContext(issue_id=1, adw_id="adw123", artifact_store=store)

        assert ctx.adw_id == "adw123"
        assert ctx.issue_id == 1

    def test_context_backward_compat_all_fields(self, tmp_path: Path) -> None:
        """Test backward compatibility with all fields specified via keywords."""
        store = ArtifactStore(workflow_id="adw-full", base_path=tmp_path)
        ctx = WorkflowContext(
            adw_id="adw-full",
            issue_id=99,
            issue=None,
            data={"key": "value"},
            artifact_store=store,
        )

        assert ctx.adw_id == "adw-full"
        assert ctx.issue_id == 99
        assert ctx.data == {"key": "value"}


class TestRequireIssueId:
    """Tests for WorkflowContext.require_issue_id property."""

    def test_require_issue_id_returns_int_when_set(self, tmp_path: Path) -> None:
        """Test require_issue_id returns the issue_id when it is set."""
        store = ArtifactStore(workflow_id="adw-req-1", base_path=tmp_path)
        ctx = WorkflowContext(adw_id="adw-req-1", issue_id=42, artifact_store=store)
        assert ctx.require_issue_id == 42

    def test_require_issue_id_raises_when_none(self, tmp_path: Path) -> None:
        """Test require_issue_id raises RuntimeError when issue_id is None."""
        store = ArtifactStore(workflow_id="adw-req-2", base_path=tmp_path)
        ctx = WorkflowContext(adw_id="adw-req-2", issue_id=None, artifact_store=store)
        with pytest.raises(RuntimeError, match="issue_id is required"):
            _ = ctx.require_issue_id

    def test_require_issue_id_raises_when_omitted(self, tmp_path: Path) -> None:
        """Test require_issue_id raises RuntimeError when issue_id is omitted."""
        store = ArtifactStore(workflow_id="adw-req-3", base_path=tmp_path)
        ctx = WorkflowContext(adw_id="adw-req-3", artifact_store=store)
        with pytest.raises(RuntimeError, match="issue_id is required"):
            _ = ctx.require_issue_id


class TestWorkflowContextArtifacts:
    """Tests for artifact store behavior."""

    def test_artifact_store_is_set(self, tmp_path: Path) -> None:
        """Test that artifact_store is accessible after construction."""
        store = ArtifactStore(workflow_id="adw-art-2", base_path=tmp_path)
        ctx = WorkflowContext(adw_id="adw-art-2", artifact_store=store)

        assert ctx.artifact_store is store

    def test_artifact_store_works_with_none_issue_id(self, tmp_path: Path) -> None:
        """Test that artifact_store functions correctly when issue_id is None."""
        store = ArtifactStore(workflow_id="adw-art-3", base_path=tmp_path)
        ctx = WorkflowContext(adw_id="adw-art-3", issue_id=None, artifact_store=store)

        assert ctx.issue_id is None
        assert ctx.artifact_store is not None


class TestLoadRequiredArtifact:
    """Tests for WorkflowContext.load_required_artifact."""

    def test_raises_step_input_error_when_artifact_not_found(self, tmp_path: Path) -> None:
        """Test load_required_artifact raises StepInputError when artifact file is not found."""
        store = ArtifactStore(workflow_id="adw-req-missing", base_path=tmp_path)
        ctx = WorkflowContext(adw_id="adw-req-missing", artifact_store=store)

        with pytest.raises(StepInputError, match="Required artifact 'plan' not found"):
            ctx.load_required_artifact(
                context_key="plan_data",
                artifact_type="plan",
                artifact_class=PlanArtifact,
                extract_fn=lambda a: a.plan_data,
            )

    def test_returns_extracted_value_when_artifact_exists(self, tmp_path: Path) -> None:
        """Test load_required_artifact returns the extracted value when artifact exists."""
        store = ArtifactStore(workflow_id="adw-req-exists", base_path=tmp_path)

        plan_data = PlanData(plan="Required plan content", summary="Required summary")
        plan_artifact = PlanArtifact(workflow_id="adw-req-exists", plan_data=plan_data)
        store.write_artifact(plan_artifact)

        ctx = WorkflowContext(adw_id="adw-req-exists", artifact_store=store)

        result = ctx.load_required_artifact(
            context_key="plan_data",
            artifact_type="plan",
            artifact_class=PlanArtifact,
            extract_fn=lambda a: a.plan_data,
        )

        assert result is not None
        assert result.plan == "Required plan content"
        assert result.summary == "Required summary"
        assert ctx.data["plan_data"] == result

    def test_returns_cached_value_from_context_data(self, tmp_path: Path) -> None:
        """Test load_required_artifact returns existing value from context cache."""
        store = ArtifactStore(workflow_id="adw-req-cached", base_path=tmp_path)
        cached_value = PlanData(plan="Cached plan", summary="Cached summary")
        ctx = WorkflowContext(
            adw_id="adw-req-cached",
            artifact_store=store,
            data={"plan_data": cached_value},
        )

        result = ctx.load_required_artifact(
            context_key="plan_data",
            artifact_type="plan",
            artifact_class=PlanArtifact,
            extract_fn=lambda a: a.plan_data,
        )

        assert result is cached_value


class TestLoadOptionalArtifact:
    """Tests for WorkflowContext.load_optional_artifact."""

    def test_returns_none_when_artifact_not_found(self, tmp_path: Path) -> None:
        """Test load_optional_artifact returns None when artifact file is not found."""
        store = ArtifactStore(workflow_id="adw-opt-missing", base_path=tmp_path)
        ctx = WorkflowContext(adw_id="adw-opt-missing", artifact_store=store)

        result = ctx.load_optional_artifact(
            context_key="plan_data",
            artifact_type="plan",
            artifact_class=PlanArtifact,
            extract_fn=lambda a: a.plan_data,
        )

        assert result is None

    def test_does_not_raise_when_artifact_not_found(self, tmp_path: Path) -> None:
        """Test load_optional_artifact does not raise an exception on missing artifact."""
        store = ArtifactStore(workflow_id="adw-opt-no-raise", base_path=tmp_path)
        ctx = WorkflowContext(adw_id="adw-opt-no-raise", artifact_store=store)

        # Should not raise StepInputError or FileNotFoundError
        result = ctx.load_optional_artifact(
            context_key="plan_data",
            artifact_type="plan",
            artifact_class=PlanArtifact,
            extract_fn=lambda a: a.plan_data,
        )
        assert result is None

    def test_returns_extracted_value_when_artifact_exists(self, tmp_path: Path) -> None:
        """Test load_optional_artifact returns the extracted value when artifact exists."""
        store = ArtifactStore(workflow_id="adw-opt-exists", base_path=tmp_path)

        plan_data = PlanData(plan="Optional plan content", summary="Optional summary")
        plan_artifact = PlanArtifact(workflow_id="adw-opt-exists", plan_data=plan_data)
        store.write_artifact(plan_artifact)

        ctx = WorkflowContext(adw_id="adw-opt-exists", artifact_store=store)

        result = ctx.load_optional_artifact(
            context_key="plan_data",
            artifact_type="plan",
            artifact_class=PlanArtifact,
            extract_fn=lambda a: a.plan_data,
        )

        assert result is not None
        assert result.plan == "Optional plan content"
        assert result.summary == "Optional summary"
        assert ctx.data["plan_data"] == result

    def test_returns_cached_value_from_context_data(self, tmp_path: Path) -> None:
        """Test load_optional_artifact returns existing value from context cache."""
        store = ArtifactStore(workflow_id="adw-opt-cached", base_path=tmp_path)
        cached_value = PlanData(plan="Cached plan", summary="Cached summary")
        ctx = WorkflowContext(
            adw_id="adw-opt-cached",
            artifact_store=store,
            data={"plan_data": cached_value},
        )

        result = ctx.load_optional_artifact(
            context_key="plan_data",
            artifact_type="plan",
            artifact_class=PlanArtifact,
            extract_fn=lambda a: a.plan_data,
        )

        assert result is cached_value
