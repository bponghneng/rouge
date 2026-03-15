"""Unit tests for WorkflowContext in rouge.core.workflow.step_base."""

import os
from unittest.mock import MagicMock

from rouge.core.workflow.step_base import WorkflowContext


def _make_context(**kwargs) -> WorkflowContext:
    """Helper to create a minimal WorkflowContext with a mock artifact store."""
    defaults = {
        "adw_id": "adw-test-001",
        "artifact_store": MagicMock(),
    }
    defaults.update(kwargs)
    return WorkflowContext(**defaults)


class TestWorkflowContextRepoPaths:
    """Tests for WorkflowContext.repo_paths field population."""

    def test_repo_paths_default_is_cwd_when_env_unset(self, monkeypatch):
        """When REPO_PATH is not set, repo_paths defaults to [os.getcwd()]."""
        monkeypatch.delenv("REPO_PATH", raising=False)

        context = _make_context()

        assert context.repo_paths == [os.getcwd()]

    def test_repo_paths_single_path_from_env(self, monkeypatch):
        """A single REPO_PATH value is reflected in repo_paths."""
        monkeypatch.setenv("REPO_PATH", "/path/to/repo")

        context = _make_context()

        assert context.repo_paths == ["/path/to/repo"]

    def test_repo_paths_two_paths_from_env(self, monkeypatch):
        """Two comma-separated paths in REPO_PATH produce a two-element list."""
        monkeypatch.setenv("REPO_PATH", "/path/a,/path/b")

        context = _make_context()

        assert context.repo_paths == ["/path/a", "/path/b"]

    def test_repo_paths_whitespace_stripped(self, monkeypatch):
        """Whitespace around paths in REPO_PATH is stripped."""
        monkeypatch.setenv("REPO_PATH", "  /path/a  ,  /path/b  ")

        context = _make_context()

        assert context.repo_paths == ["/path/a", "/path/b"]

    def test_repo_paths_can_be_overridden_explicitly(self, monkeypatch):
        """repo_paths can be set explicitly regardless of the environment."""
        monkeypatch.setenv("REPO_PATH", "/env/path")

        context = _make_context(repo_paths=["/explicit/path"])

        assert context.repo_paths == ["/explicit/path"]

    def test_repo_paths_is_list_type(self, monkeypatch):
        """repo_paths is always a list."""
        monkeypatch.delenv("REPO_PATH", raising=False)

        context = _make_context()

        assert isinstance(context.repo_paths, list)

    def test_repo_paths_first_element_is_primary_repo(self, monkeypatch):
        """The first element of repo_paths is accessible via index 0."""
        monkeypatch.setenv("REPO_PATH", "/primary/repo,/secondary/repo")

        context = _make_context()

        assert context.repo_paths[0] == "/primary/repo"

    def test_repo_paths_single_path_backwards_compatible(self, monkeypatch):
        """Single-path REPO_PATH works exactly as the old get_repo_path() did."""
        monkeypatch.setenv("REPO_PATH", "/legacy/single/repo")

        context = _make_context()

        # Accessing [0] mirrors the old single-repo behaviour
        assert context.repo_paths[0] == "/legacy/single/repo"
        assert len(context.repo_paths) == 1
