"""Tests for merge request CLI commands."""

import json
from unittest.mock import patch

from typer.testing import CliRunner

from rouge.cli.mr import app

runner = CliRunner()


SAMPLE_MR_ROWS = [
    {
        "issue_id": 42,
        "adw_id": "adw-abc123",
        "platform": "github",
        "repo": "org/repo",
        "number": 123,
        "url": "https://github.com/org/repo/pull/123",
        "adopted": False,
    }
]


class TestMrListCommand:
    """Tests for 'rouge mr list' command."""

    @patch("rouge.cli.mr.list_mr_comments")
    def test_list_table_output_default(self, mock_list_mr_comments) -> None:
        """Test mr list command with default table output."""
        mock_list_mr_comments.return_value = SAMPLE_MR_ROWS

        result = runner.invoke(app, [])
        assert result.exit_code == 0
        # Table headers
        assert "Issue" in result.output
        assert "Platform" in result.output
        assert "Repo" in result.output
        assert "Number" in result.output
        assert "URL" in result.output
        assert "Adopted" in result.output
        # Data values
        assert "42" in result.output
        assert "github" in result.output
        assert "org/repo" in result.output
        assert "123" in result.output
        assert "https://github.com/org/repo/pull/123" in result.output
        assert "False" in result.output

    @patch("rouge.cli.mr.list_mr_comments")
    def test_list_json_output(self, mock_list_mr_comments) -> None:
        """Test mr list command with --format json."""
        mock_list_mr_comments.return_value = SAMPLE_MR_ROWS

        result = runner.invoke(app, ["--format", "json"])
        assert result.exit_code == 0

        output_data = json.loads(result.output)
        assert isinstance(output_data, list)
        assert len(output_data) == 1
        assert output_data[0]["issue_id"] == 42
        assert output_data[0]["platform"] == "github"
        assert output_data[0]["repo"] == "org/repo"
        assert output_data[0]["number"] == 123
        assert output_data[0]["url"] == "https://github.com/org/repo/pull/123"
        assert output_data[0]["adopted"] is False

    @patch("rouge.cli.mr.list_mr_comments")
    def test_list_filter_by_issue_id(self, mock_list_mr_comments) -> None:
        """Test mr list command with --issue-id filter."""
        mock_list_mr_comments.return_value = SAMPLE_MR_ROWS

        result = runner.invoke(app, ["--issue-id", "5"])
        assert result.exit_code == 0
        mock_list_mr_comments.assert_called_once_with(issue_id=5, platform=None, limit=10, offset=0)

    @patch("rouge.cli.mr.list_mr_comments")
    def test_list_filter_by_platform(self, mock_list_mr_comments) -> None:
        """Test mr list command with --platform github filter."""
        mock_list_mr_comments.return_value = SAMPLE_MR_ROWS

        result = runner.invoke(app, ["--platform", "github"])
        assert result.exit_code == 0
        mock_list_mr_comments.assert_called_once_with(
            issue_id=None, platform="github", limit=10, offset=0
        )

    @patch("rouge.cli.mr.list_mr_comments")
    def test_list_platform_all(self, mock_list_mr_comments) -> None:
        """Test mr list command with --platform all passes platform=None."""
        mock_list_mr_comments.return_value = SAMPLE_MR_ROWS

        result = runner.invoke(app, ["--platform", "all"])
        assert result.exit_code == 0
        mock_list_mr_comments.assert_called_once_with(
            issue_id=None, platform=None, limit=10, offset=0
        )

    @patch("rouge.cli.mr.list_mr_comments")
    def test_list_empty_results(self, mock_list_mr_comments) -> None:
        """Test mr list command prints 'No merge requests found.' when no results."""
        mock_list_mr_comments.return_value = []

        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "No merge requests found." in result.output

    def test_list_invalid_platform(self) -> None:
        """Test mr list command with invalid --platform value exits with non-zero."""
        result = runner.invoke(app, ["--platform", "bitbucket"])
        assert result.exit_code != 0

    @patch("rouge.cli.mr.list_mr_comments")
    def test_list_database_error(self, mock_list_mr_comments) -> None:
        """Test mr list command handles ValueError from database layer."""
        mock_list_mr_comments.side_effect = ValueError("DB error")

        result = runner.invoke(app, [])
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_list_help_text(self) -> None:
        """Test mr list --help includes 'generic term' in help output."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "generic term" in result.output

    @patch("rouge.cli.mr.list_mr_comments")
    def test_list_with_limit_and_offset(self, mock_list_mr_comments) -> None:
        """Test mr list command with --limit and --offset."""
        mock_list_mr_comments.return_value = SAMPLE_MR_ROWS

        result = runner.invoke(app, ["--limit", "5", "--offset", "10"])
        assert result.exit_code == 0
        mock_list_mr_comments.assert_called_once_with(
            issue_id=None, platform=None, limit=5, offset=10
        )
