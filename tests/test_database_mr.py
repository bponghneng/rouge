"""Tests for list_mr_comments database operation."""

from unittest.mock import Mock, patch

import pytest

from rouge.core.database import list_mr_comments


def _make_comment_row(
    *,
    id=1,
    issue_id=42,
    adw_id="adw-abc123",
    comment="PR artifact",
    source="artifact",
    type="gh-pull-request",
    platform="github",
    pull_requests=None,
    created_at="2024-01-01T12:00:00",
) -> dict:
    """Build a realistic comment row dict for mocking."""
    if pull_requests is None:
        pull_requests = [
            {
                "repo": "org/repo",
                "number": 123,
                "url": "https://github.com/org/repo/pull/123",
                "adopted": False,
            }
        ]
    return {
        "id": id,
        "issue_id": issue_id,
        "adw_id": adw_id,
        "comment": comment,
        "source": source,
        "type": type,
        "raw": {
            "artifact": {
                "platform": platform,
                "pull_requests": pull_requests,
            }
        },
        "created_at": created_at,
    }


def _build_mock_chain(mock_client: Mock, data: list) -> dict[str, Mock]:
    """Wire up the Supabase query chain and return the leaf mocks.

    Returns a dict of named mocks so callers can assert on intermediate calls.
    """
    mock_table = Mock()
    mock_select = Mock()
    mock_eq_source = Mock()
    mock_in = Mock()
    mock_order = Mock()
    mock_limit = Mock()
    mock_offset = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq_source
    mock_eq_source.in_.return_value = mock_in
    # .eq on mock_in handles the optional issue_id filter; it should return
    # itself so the chain can continue to .order().
    mock_in.eq.return_value = mock_in
    mock_in.order.return_value = mock_order
    mock_order.limit.return_value = mock_limit
    mock_limit.offset.return_value = mock_offset
    mock_execute.data = data
    mock_offset.execute.return_value = mock_execute

    return {
        "table": mock_table,
        "select": mock_select,
        "eq_source": mock_eq_source,
        "in_": mock_in,
        "order": mock_order,
        "limit": mock_limit,
        "offset": mock_offset,
        "execute": mock_execute,
    }


class TestListMrComments:
    """Tests for list_mr_comments()."""

    @patch("rouge.core.database.get_client")
    def test_happy_path_two_comments(self, mock_get_client: Mock) -> None:
        """Two comment rows each with one PR return two flattened dicts."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        rows = [
            _make_comment_row(id=1, issue_id=42, adw_id="adw-abc123"),
            _make_comment_row(
                id=2,
                issue_id=43,
                adw_id="adw-def456",
                pull_requests=[
                    {
                        "repo": "org/other",
                        "number": 456,
                        "url": "https://github.com/org/other/pull/456",
                        "adopted": True,
                    }
                ],
            ),
        ]
        _build_mock_chain(mock_client, rows)

        results = list_mr_comments()

        assert len(results) == 2
        assert results[0]["issue_id"] == 42
        assert results[0]["adw_id"] == "adw-abc123"
        assert results[0]["platform"] == "github"
        assert results[0]["repo"] == "org/repo"
        assert results[0]["number"] == 123
        assert results[0]["url"] == "https://github.com/org/repo/pull/123"
        assert results[0]["adopted"] is False

        assert results[1]["issue_id"] == 43
        assert results[1]["adw_id"] == "adw-def456"
        assert results[1]["number"] == 456
        assert results[1]["adopted"] is True

    @patch("rouge.core.database.get_client")
    def test_multi_pr_artifact(self, mock_get_client: Mock) -> None:
        """One comment with two PRs produces two flattened rows."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        rows = [
            _make_comment_row(
                pull_requests=[
                    {
                        "repo": "org/repo",
                        "number": 1,
                        "url": "https://github.com/org/repo/pull/1",
                        "adopted": False,
                    },
                    {
                        "repo": "org/repo",
                        "number": 2,
                        "url": "https://github.com/org/repo/pull/2",
                        "adopted": True,
                    },
                ]
            )
        ]
        _build_mock_chain(mock_client, rows)

        results = list_mr_comments()

        assert len(results) == 2
        assert results[0]["number"] == 1
        assert results[1]["number"] == 2

    @patch("rouge.core.database.get_client")
    def test_filter_by_issue_id(self, mock_get_client: Mock) -> None:
        """Passing issue_id inserts an extra .eq call."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        rows = [_make_comment_row(issue_id=5)]
        mocks = _build_mock_chain(mock_client, rows)

        list_mr_comments(issue_id=5)

        mocks["in_"].eq.assert_called_with("issue_id", 5)

    @patch("rouge.core.database.get_client")
    def test_filter_by_platform_github(self, mock_get_client: Mock) -> None:
        """platform='github' filters to gh-pull-request only."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        rows = [_make_comment_row()]
        mocks = _build_mock_chain(mock_client, rows)

        list_mr_comments(platform="github")

        mocks["eq_source"].in_.assert_called_with("type", ["gh-pull-request"])

    @patch("rouge.core.database.get_client")
    def test_filter_by_platform_gitlab(self, mock_get_client: Mock) -> None:
        """platform='gitlab' filters to glab-pull-request only."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        rows = [_make_comment_row(type="glab-pull-request", platform="gitlab")]
        mocks = _build_mock_chain(mock_client, rows)

        list_mr_comments(platform="gitlab")

        mocks["eq_source"].in_.assert_called_with("type", ["glab-pull-request"])

    @patch("rouge.core.database.get_client")
    def test_no_platform_filter(self, mock_get_client: Mock) -> None:
        """platform=None includes both PR types."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        rows = [_make_comment_row()]
        mocks = _build_mock_chain(mock_client, rows)

        list_mr_comments(platform=None)

        mocks["eq_source"].in_.assert_called_with("type", ["gh-pull-request", "glab-pull-request"])

    @patch("rouge.core.database.get_client")
    def test_empty_results(self, mock_get_client: Mock) -> None:
        """No matching comments returns an empty list."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        _build_mock_chain(mock_client, [])

        results = list_mr_comments()

        assert results == []

    @patch("rouge.core.database.get_client")
    def test_malformed_payload_missing_pull_requests(self, mock_get_client: Mock) -> None:
        """Comment with raw missing artifact.pull_requests is skipped."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        row = {
            "id": 1,
            "issue_id": 42,
            "adw_id": "adw-abc123",
            "comment": "PR artifact",
            "source": "artifact",
            "type": "gh-pull-request",
            "raw": {"something_else": True},
            "created_at": "2024-01-01T12:00:00",
        }
        _build_mock_chain(mock_client, [row])

        results = list_mr_comments()

        assert results == []

    @patch("rouge.core.database.get_client")
    def test_empty_pull_requests_array(self, mock_get_client: Mock) -> None:
        """Comment with empty pull_requests list produces no rows."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        rows = [_make_comment_row(pull_requests=[])]
        _build_mock_chain(mock_client, rows)

        results = list_mr_comments()

        assert results == []

    def test_validation_errors(self) -> None:
        """Invalid arguments raise ValueError without hitting the DB."""
        with pytest.raises(ValueError, match="limit must be >= 1"):
            list_mr_comments(limit=0)

        with pytest.raises(ValueError, match="offset must be >= 0"):
            list_mr_comments(offset=-1)

        with pytest.raises(ValueError, match="issue_id must be > 0"):
            list_mr_comments(issue_id=-1)

        with pytest.raises(ValueError, match="platform must be"):
            list_mr_comments(platform="bitbucket")
