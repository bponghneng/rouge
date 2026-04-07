"""Unit tests for rouge.core.workflow.shared helper functions."""

import os
from pathlib import Path

from rouge.core.workflow.shared import get_affected_repo_paths, get_repo_paths
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.types import ImplementData, RepoChangeDetail


class TestGetRepoPaths:
    """Tests for the get_repo_paths() helper function."""

    def test_no_env_var_returns_cwd(self, monkeypatch):
        """When REPO_PATH is unset, get_repo_paths() returns [os.getcwd()]."""
        monkeypatch.delenv("REPO_PATH", raising=False)

        result = get_repo_paths()

        assert result == [os.getcwd()]

    def test_single_path_returns_list_with_one_element(self, monkeypatch):
        """A single path in REPO_PATH is returned as a one-element list."""
        monkeypatch.setenv("REPO_PATH", "/path/to/repo")

        result = get_repo_paths()

        assert result == ["/path/to/repo"]

    def test_two_paths_separated_by_comma(self, monkeypatch):
        """Two comma-separated paths are returned as a two-element list."""
        monkeypatch.setenv("REPO_PATH", "/path/a,/path/b")

        result = get_repo_paths()

        assert result == ["/path/a", "/path/b"]

    def test_two_paths_with_surrounding_whitespace(self, monkeypatch):
        """Paths with surrounding whitespace are stripped."""
        monkeypatch.setenv("REPO_PATH", "  /path/a  ,  /path/b  ")

        result = get_repo_paths()

        assert result == ["/path/a", "/path/b"]

    def test_trailing_comma_filters_empty_string(self, monkeypatch):
        """A trailing comma produces an empty string that is filtered out."""
        monkeypatch.setenv("REPO_PATH", "/path/to/repo,")

        result = get_repo_paths()

        assert result == ["/path/to/repo"]

    def test_leading_comma_filters_empty_string(self, monkeypatch):
        """A leading comma produces an empty string that is filtered out."""
        monkeypatch.setenv("REPO_PATH", ",/path/to/repo")

        result = get_repo_paths()

        assert result == ["/path/to/repo"]

    def test_blank_env_var_returns_cwd(self, monkeypatch):
        """A blank REPO_PATH (empty string) returns [os.getcwd()]."""
        monkeypatch.setenv("REPO_PATH", "")

        result = get_repo_paths()

        assert result == [os.getcwd()]

    def test_whitespace_only_env_var_returns_cwd(self, monkeypatch):
        """A whitespace-only REPO_PATH returns [os.getcwd()]."""
        monkeypatch.setenv("REPO_PATH", "   ")

        result = get_repo_paths()

        assert result == [os.getcwd()]

    def test_returns_list_type(self, monkeypatch):
        """get_repo_paths() always returns a list."""
        monkeypatch.setenv("REPO_PATH", "/some/path")

        result = get_repo_paths()

        assert isinstance(result, list)

    def test_three_paths(self, monkeypatch):
        """Three comma-separated paths are all returned."""
        monkeypatch.setenv("REPO_PATH", "/a,/b,/c")

        result = get_repo_paths()

        assert result == ["/a", "/b", "/c"]


def _make_context(tmp_path: Path, repo_paths: list[str]) -> WorkflowContext:
    """Create a WorkflowContext with the given repo_paths."""
    return WorkflowContext(
        adw_id="test-shared",
        issue_id=1,
        repo_paths=repo_paths,
    )


class TestGetAffectedRepoPaths:
    """Tests for the get_affected_repo_paths() helper function."""

    def test_returns_all_repo_paths_when_implement_data_missing(self, tmp_path: Path) -> None:
        """Falls back to full context.repo_paths when implement data is absent."""
        context = _make_context(tmp_path, ["/repo/a", "/repo/b"])

        result = get_affected_repo_paths(context)

        assert result == ["/repo/a", "/repo/b"]

    def test_returns_all_repo_paths_when_affected_repos_empty(self, tmp_path: Path) -> None:
        """Falls back to full context.repo_paths when affected_repos is empty list."""
        context = _make_context(tmp_path, ["/repo/a", "/repo/b"])
        # Store implement data with empty affected_repos
        context.data["implement_data"] = ImplementData(output="done", affected_repos=[])

        result = get_affected_repo_paths(context)

        assert result == ["/repo/a", "/repo/b"]

    def test_returns_filtered_subset_when_affected_repos_populated(self, tmp_path: Path) -> None:
        """Returns only repos that appear in both affected_repos and context.repo_paths."""
        context = _make_context(tmp_path, ["/repo/a", "/repo/b", "/repo/c"])
        context.data["implement_data"] = ImplementData(
            output="done",
            affected_repos=[
                RepoChangeDetail(repo_path="/repo/a"),
                RepoChangeDetail(repo_path="/repo/c"),
            ],
        )

        result = get_affected_repo_paths(context)

        assert result == ["/repo/a", "/repo/c"]

    def test_preserves_original_repo_paths_ordering(self, tmp_path: Path) -> None:
        """Filtered result preserves the order from context.repo_paths, not affected_repos."""
        context = _make_context(tmp_path, ["/repo/z", "/repo/a", "/repo/m"])
        context.data["implement_data"] = ImplementData(
            output="done",
            affected_repos=[
                RepoChangeDetail(repo_path="/repo/m"),
                RepoChangeDetail(repo_path="/repo/z"),
            ],
        )

        result = get_affected_repo_paths(context)

        assert result == ["/repo/z", "/repo/m"]

    def test_ignores_affected_repos_not_in_context(self, tmp_path: Path) -> None:
        """affected_repos entries not present in context.repo_paths are ignored."""
        context = _make_context(tmp_path, ["/repo/a"])
        context.data["implement_data"] = ImplementData(
            output="done",
            affected_repos=[
                RepoChangeDetail(repo_path="/repo/a"),
                RepoChangeDetail(repo_path="/repo/unknown"),
            ],
        )

        result = get_affected_repo_paths(context)

        assert result == ["/repo/a"]
