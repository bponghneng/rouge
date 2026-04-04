"""Tests for repo_filter shared helper."""

from pathlib import Path

import pytest

from rouge.core.workflow.artifacts import ArtifactStore, ImplementArtifact
from rouge.core.workflow.repo_filter import get_affected_repos
from rouge.core.workflow.step_base import StepInputError, WorkflowContext
from rouge.core.workflow.types import ImplementData


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    """Create a temporary artifact store."""
    return ArtifactStore(workflow_id="test-repo-filter", base_path=tmp_path)


@pytest.fixture
def base_context(store: ArtifactStore) -> WorkflowContext:
    """Create a workflow context with multiple repo paths."""
    return WorkflowContext(
        adw_id="test-repo-filter",
        issue_id=99,
        artifact_store=store,
        repo_paths=["/repo/alpha", "/repo/beta", "/repo/gamma"],
    )


class TestGetAffectedRepos:
    """Tests for get_affected_repos helper."""

    def test_raises_when_no_implement_artifact(self, base_context: WorkflowContext) -> None:
        """Raises StepInputError when implement artifact is missing."""
        with pytest.raises(StepInputError, match="Required artifact 'implement' not found"):
            get_affected_repos(base_context)

    def test_returns_filtered_repos_in_order(
        self, base_context: WorkflowContext, store: ArtifactStore
    ) -> None:
        """Returns only affected repos, preserving context.repo_paths order."""
        implement_data = ImplementData(
            output="done",
            affected_repos=["/repo/gamma", "/repo/alpha"],
        )
        artifact = ImplementArtifact(
            workflow_id="test-repo-filter",
            implement_data=implement_data,
        )
        store.write_artifact(artifact)

        repos, data = get_affected_repos(base_context)

        # Should be in context.repo_paths order, not affected_repos order
        assert repos == ["/repo/alpha", "/repo/gamma"]
        assert data is not None
        assert data.affected_repos == ["/repo/gamma", "/repo/alpha"]

    def test_returns_empty_when_no_repos_affected(
        self, base_context: WorkflowContext, store: ArtifactStore
    ) -> None:
        """Returns empty list when affected_repos is empty."""
        implement_data = ImplementData(output="done", affected_repos=[])
        artifact = ImplementArtifact(
            workflow_id="test-repo-filter",
            implement_data=implement_data,
        )
        store.write_artifact(artifact)

        repos, data = get_affected_repos(base_context)
        assert repos == []
        assert data is not None

    def test_warns_on_unknown_repos(
        self, base_context: WorkflowContext, store: ArtifactStore, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Logs warning when affected_repos contains paths not in context.repo_paths."""
        implement_data = ImplementData(
            output="done",
            affected_repos=["/repo/alpha", "/repo/unknown"],
        )
        artifact = ImplementArtifact(
            workflow_id="test-repo-filter",
            implement_data=implement_data,
        )
        store.write_artifact(artifact)

        import logging

        with caplog.at_level(logging.WARNING):
            repos, data = get_affected_repos(base_context)

        assert repos == ["/repo/alpha"]
        assert "/repo/unknown" in caplog.text or any("unknown" in r.message for r in caplog.records)

    def test_single_repo_all_affected(self, store: ArtifactStore) -> None:
        """Single repo context with that repo affected returns it."""
        context = WorkflowContext(
            adw_id="test-repo-filter",
            issue_id=99,
            artifact_store=store,
            repo_paths=["/repo/only"],
        )
        implement_data = ImplementData(
            output="done",
            affected_repos=["/repo/only"],
        )
        artifact = ImplementArtifact(
            workflow_id="test-repo-filter",
            implement_data=implement_data,
        )
        store.write_artifact(artifact)

        repos, data = get_affected_repos(context)
        assert repos == ["/repo/only"]
