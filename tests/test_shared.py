"""Unit tests for rouge.core.workflow.shared helper functions."""

import os

import pytest

from rouge.core.workflow.shared import get_repo_paths


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
