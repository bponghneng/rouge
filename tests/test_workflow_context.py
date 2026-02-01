"""Tests for WorkflowContext with optional issue_id."""

from unittest.mock import MagicMock

import pytest

from rouge.core.workflow.artifacts import ArtifactStore
from rouge.core.workflow.step_base import WorkflowContext


class TestWorkflowContextCreation:
    """Tests for WorkflowContext instantiation with optional issue_id."""

    def test_context_with_issue_id_none_explicit(self):
        """Test WorkflowContext creation with issue_id explicitly set to None."""
        ctx = WorkflowContext(adw_id="adw-001", issue_id=None)

        assert ctx.adw_id == "adw-001"
        assert ctx.issue_id is None
        assert ctx.issue is None
        assert ctx.data == {}
        assert ctx.artifact_store is None

    def test_context_with_issue_id_omitted(self):
        """Test WorkflowContext creation with issue_id omitted (defaults to None)."""
        ctx = WorkflowContext(adw_id="adw-002")

        assert ctx.adw_id == "adw-002"
        assert ctx.issue_id is None
        assert ctx.issue is None
        assert ctx.data == {}
        assert ctx.artifact_store is None

    def test_context_with_valid_issue_id(self):
        """Test WorkflowContext creation with a valid integer issue_id."""
        ctx = WorkflowContext(adw_id="adw-003", issue_id=42)

        assert ctx.adw_id == "adw-003"
        assert ctx.issue_id == 42
        assert ctx.issue is None
        assert ctx.data == {}

    def test_context_backward_compat_keyword_args(self):
        """Test backward compatibility: existing callers using keyword args still work."""
        ctx = WorkflowContext(issue_id=1, adw_id="adw123")

        assert ctx.adw_id == "adw123"
        assert ctx.issue_id == 1

    def test_context_backward_compat_all_fields(self):
        """Test backward compatibility with all fields specified via keywords."""
        ctx = WorkflowContext(
            adw_id="adw-full",
            issue_id=99,
            issue=None,
            data={"key": "value"},
            artifact_store=None,
        )

        assert ctx.adw_id == "adw-full"
        assert ctx.issue_id == 99
        assert ctx.data == {"key": "value"}


class TestRequireIssueId:
    """Tests for WorkflowContext.require_issue_id property."""

    def test_require_issue_id_returns_int_when_set(self):
        """Test require_issue_id returns the issue_id when it is set."""
        ctx = WorkflowContext(adw_id="adw-req-1", issue_id=42)
        assert ctx.require_issue_id == 42

    def test_require_issue_id_raises_when_none(self):
        """Test require_issue_id raises RuntimeError when issue_id is None."""
        ctx = WorkflowContext(adw_id="adw-req-2", issue_id=None)
        with pytest.raises(RuntimeError, match="issue_id is required"):
            _ = ctx.require_issue_id

    def test_require_issue_id_raises_when_omitted(self):
        """Test require_issue_id raises RuntimeError when issue_id is omitted."""
        ctx = WorkflowContext(adw_id="adw-req-3")
        with pytest.raises(RuntimeError, match="issue_id is required"):
            _ = ctx.require_issue_id


class TestWorkflowContextArtifacts:
    """Tests for artifact store behavior when issue_id is None."""

    def test_artifacts_not_enabled_by_default(self):
        """Test that artifacts_enabled is False when no store is set."""
        ctx = WorkflowContext(adw_id="adw-art-1")

        assert ctx.artifacts_enabled is False

    def test_artifacts_enabled_with_store(self, tmp_path):
        """Test that artifacts_enabled is True when a store is provided."""
        store = ArtifactStore(workflow_id="adw-art-2", base_path=tmp_path)
        ctx = WorkflowContext(adw_id="adw-art-2", artifact_store=store)

        assert ctx.artifacts_enabled is True

    def test_artifact_store_works_with_none_issue_id(self, tmp_path):
        """Test that artifact_store functions correctly when issue_id is None."""
        store = ArtifactStore(workflow_id="adw-art-3", base_path=tmp_path)
        ctx = WorkflowContext(adw_id="adw-art-3", issue_id=None, artifact_store=store)

        assert ctx.artifacts_enabled is True
        assert ctx.issue_id is None
        assert ctx.artifact_store is not None

    def test_load_artifact_if_missing_returns_none_without_store(self):
        """Test load_artifact_if_missing returns None when no store is configured."""
        ctx = WorkflowContext(adw_id="adw-no-store", issue_id=None)

        result = ctx.load_artifact_if_missing(
            context_key="test_key",
            artifact_type="plan",
            artifact_class=MagicMock,
            extract_fn=lambda a: a,
        )

        assert result is None

    def test_load_artifact_if_missing_returns_existing_data(self):
        """Test load_artifact_if_missing returns existing data from context."""
        ctx = WorkflowContext(
            adw_id="adw-existing",
            issue_id=None,
            data={"test_key": "existing_value"},
        )

        result = ctx.load_artifact_if_missing(
            context_key="test_key",
            artifact_type="plan",
            artifact_class=MagicMock,
            extract_fn=lambda a: a,
        )

        assert result == "existing_value"

    def test_load_artifact_if_missing_handles_file_not_found(self, tmp_path):
        """Test load_artifact_if_missing returns None when artifact file is missing."""
        store = ArtifactStore(workflow_id="adw-missing", base_path=tmp_path)
        ctx = WorkflowContext(
            adw_id="adw-missing",
            issue_id=None,
            artifact_store=store,
        )

        result = ctx.load_artifact_if_missing(
            context_key="missing_key",
            artifact_type="plan",
            artifact_class=MagicMock,
            extract_fn=lambda a: a,
        )

        assert result is None

    def test_load_issue_artifact_if_missing_returns_none_without_store(self):
        """Test load_issue_artifact_if_missing returns None when no store and issue_id is None."""
        ctx = WorkflowContext(adw_id="adw-no-issue", issue_id=None)

        result = ctx.load_issue_artifact_if_missing(
            artifact_class=MagicMock,
            extract_fn=lambda a: a.issue,
        )

        assert result is None
