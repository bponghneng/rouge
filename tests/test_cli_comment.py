"""Tests for comment CLI commands."""

import json
from datetime import datetime
from unittest.mock import patch

from typer.testing import CliRunner

from rouge.cli.comment import app
from rouge.core.models import Comment

runner = CliRunner()


class TestCommentListCommand:
    """Tests for 'rouge comment list' command."""

    @patch("rouge.cli.comment.list_comments")
    def test_list_default_parameters(self, mock_list_comments):
        """Test comment list command with default parameters."""
        mock_list_comments.return_value = [
            Comment(
                id=1,
                issue_id=1,
                comment="Test comment",
                source="agent",
                type="plan",
                created_at=datetime(2024, 1, 1, 12, 0, 0),
            ),
        ]

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "Test comment" in result.output
        mock_list_comments.assert_called_once_with(
            issue_id=None, source=None, comment_type=None, limit=10, offset=0
        )

    @patch("rouge.cli.comment.list_comments")
    def test_list_with_issue_id_filter(self, mock_list_comments):
        """Test comment list command with --issue-id filter."""
        mock_list_comments.return_value = [
            Comment(
                id=1,
                issue_id=5,
                comment="Issue 5 comment",
                source="agent",
                type="plan",
                created_at=datetime(2024, 1, 1, 12, 0, 0),
            ),
        ]

        result = runner.invoke(app, ["list", "--issue-id", "5"])
        assert result.exit_code == 0
        assert "Issue 5 comment" in result.output
        mock_list_comments.assert_called_once_with(
            issue_id=5, source=None, comment_type=None, limit=10, offset=0
        )

    @patch("rouge.cli.comment.list_comments")
    def test_list_with_source_filter(self, mock_list_comments):
        """Test comment list command with --source filter."""
        mock_list_comments.return_value = [
            Comment(
                id=1,
                issue_id=1,
                comment="Agent comment",
                source="agent",
                type="plan",
                created_at=datetime(2024, 1, 1, 12, 0, 0),
            ),
        ]

        result = runner.invoke(app, ["list", "--source", "agent"])
        assert result.exit_code == 0
        assert "agent" in result.output
        mock_list_comments.assert_called_once_with(
            issue_id=None, source="agent", comment_type=None, limit=10, offset=0
        )

    @patch("rouge.cli.comment.list_comments")
    def test_list_with_type_filter(self, mock_list_comments):
        """Test comment list command with --type filter."""
        mock_list_comments.return_value = [
            Comment(
                id=1,
                issue_id=1,
                comment="Plan comment",
                source="agent",
                type="plan",
                created_at=datetime(2024, 1, 1, 12, 0, 0),
            ),
        ]

        result = runner.invoke(app, ["list", "--type", "plan"])
        assert result.exit_code == 0
        assert "plan" in result.output
        mock_list_comments.assert_called_once_with(
            issue_id=None, source=None, comment_type="plan", limit=10, offset=0
        )

    @patch("rouge.cli.comment.list_comments")
    def test_list_with_limit(self, mock_list_comments):
        """Test comment list command with --limit."""
        mock_list_comments.return_value = []

        result = runner.invoke(app, ["list", "--limit", "5"])
        assert result.exit_code == 0
        mock_list_comments.assert_called_once_with(
            issue_id=None, source=None, comment_type=None, limit=5, offset=0
        )

    @patch("rouge.cli.comment.list_comments")
    def test_list_with_offset(self, mock_list_comments):
        """Test comment list command with --offset."""
        mock_list_comments.return_value = []

        result = runner.invoke(app, ["list", "--offset", "10"])
        assert result.exit_code == 0
        mock_list_comments.assert_called_once_with(
            issue_id=None, source=None, comment_type=None, limit=10, offset=10
        )

    @patch("rouge.cli.comment.list_comments")
    def test_list_with_limit_and_offset(self, mock_list_comments):
        """Test comment list command with both --limit and --offset."""
        mock_list_comments.return_value = [
            Comment(
                id=1,
                issue_id=1,
                comment="Paginated comment",
                source="agent",
                type="plan",
                created_at=datetime(2024, 1, 1, 12, 0, 0),
            ),
        ]

        result = runner.invoke(app, ["list", "--limit", "5", "--offset", "10"])
        assert result.exit_code == 0
        mock_list_comments.assert_called_once_with(
            issue_id=None, source=None, comment_type=None, limit=5, offset=10
        )

    @patch("rouge.cli.comment.list_comments")
    def test_list_with_all_filters(self, mock_list_comments):
        """Test comment list command with all filters combined."""
        mock_list_comments.return_value = []

        result = runner.invoke(
            app,
            [
                "list",
                "--issue-id",
                "5",
                "--source",
                "agent",
                "--type",
                "plan",
                "--limit",
                "20",
                "--offset",
                "5",
            ],
        )
        assert result.exit_code == 0
        mock_list_comments.assert_called_once_with(
            issue_id=5, source="agent", comment_type="plan", limit=20, offset=5
        )

    @patch("rouge.cli.comment.list_comments")
    def test_list_invalid_limit_zero(self, mock_list_comments):
        """Test comment list command with --limit 0 (invalid) exits with code 1."""
        result = runner.invoke(app, ["list", "--limit", "0"])
        assert result.exit_code == 1
        assert "--limit must be at least 1" in result.output
        mock_list_comments.assert_not_called()

    @patch("rouge.cli.comment.list_comments")
    def test_list_invalid_limit_negative(self, mock_list_comments):
        """Test comment list command with negative --limit."""
        result = runner.invoke(app, ["list", "--limit", "-5"])
        assert result.exit_code == 1
        assert "--limit must be at least 1" in result.output
        mock_list_comments.assert_not_called()

    @patch("rouge.cli.comment.list_comments")
    def test_list_invalid_offset_negative(self, mock_list_comments):
        """Test comment list command with --offset -1 (invalid) exits with code 1."""
        result = runner.invoke(app, ["list", "--offset", "-1"])
        assert result.exit_code == 1
        assert "--offset must be at least 0" in result.output
        mock_list_comments.assert_not_called()

    @patch("rouge.cli.comment.list_comments")
    def test_list_empty_results(self, mock_list_comments):
        """Test comment list command prints 'No comments found.' when no results."""
        mock_list_comments.return_value = []

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No comments found." in result.output

    @patch("rouge.cli.comment.list_comments")
    def test_list_database_error(self, mock_list_comments):
        """Test comment list command handles ValueError from database layer."""
        mock_list_comments.side_effect = ValueError("Database connection failed")

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 1
        assert "Error: Database connection failed" in result.output

    @patch("rouge.cli.comment.list_comments")
    def test_list_unexpected_error(self, mock_list_comments):
        """Test comment list command handles unexpected errors."""
        mock_list_comments.side_effect = Exception("Unexpected failure")

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 1
        assert "Unexpected error: Unexpected failure" in result.output

    @patch("rouge.cli.comment.list_comments")
    def test_list_multiple_comments(self, mock_list_comments):
        """Test comment list command displays multiple comments correctly."""
        mock_list_comments.return_value = [
            Comment(
                id=1,
                issue_id=1,
                comment="First comment",
                source="agent",
                type="plan",
                created_at=datetime(2024, 1, 1, 12, 0, 0),
            ),
            Comment(
                id=2,
                issue_id=2,
                comment="Second comment",
                source="system",
                type="note",
                created_at=datetime(2024, 1, 2, 12, 0, 0),
            ),
        ]

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "First comment" in result.output
        assert "Second comment" in result.output
        assert "ID" in result.output  # Header
        assert "Issue" in result.output  # Header

    @patch("rouge.cli.comment.list_comments")
    def test_list_truncates_long_comments(self, mock_list_comments):
        """Test comment list command truncates very long comments in table format."""
        long_comment = "This is a very long comment that should be truncated in the table view" * 10
        mock_list_comments.return_value = [
            Comment(
                id=1,
                issue_id=1,
                comment=long_comment,
                source="agent",
                type="plan",
                created_at=datetime(2024, 1, 1, 12, 0, 0),
            ),
        ]

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        # Comment should be truncated with "..."
        assert "..." in result.output
        # Full comment should not appear in table output
        assert long_comment not in result.output

    @patch("rouge.cli.comment.list_comments")
    def test_list_handles_none_fields(self, mock_list_comments):
        """Test comment list command handles None values in optional fields."""
        mock_list_comments.return_value = [
            Comment(
                id=1,
                issue_id=1,
                comment="Minimal comment",
                source=None,
                type=None,
                created_at=None,
            ),
        ]

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "Minimal comment" in result.output
        assert "(none)" in result.output  # Should show "(none)" for None fields


class TestCommentReadCommand:
    """Tests for 'rouge comment read' command."""

    @patch("rouge.cli.comment.fetch_comment")
    def test_read_with_default_format(self, mock_fetch_comment):
        """Test comment read command with default format (text)."""
        mock_fetch_comment.return_value = Comment(
            id=123,
            issue_id=1,
            comment="Test comment",
            source="agent",
            type="plan",
            adw_id="adw-test-123",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
        )

        result = runner.invoke(app, ["read", "123"])
        assert result.exit_code == 0
        assert "Comment #123" in result.output
        assert "Issue ID:    1" in result.output
        assert "Source:      agent" in result.output
        assert "Type:        plan" in result.output
        assert "ADW ID:      adw-test-123" in result.output
        mock_fetch_comment.assert_called_once_with(123)

    @patch("rouge.cli.comment.fetch_comment")
    def test_read_with_text_format_explicit(self, mock_fetch_comment):
        """Test comment read command with explicit --format text."""
        mock_fetch_comment.return_value = Comment(
            id=123,
            issue_id=1,
            comment="Test comment",
            source="agent",
            type="note",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
        )

        result = runner.invoke(app, ["read", "123", "--format", "text"])
        assert result.exit_code == 0
        assert "Comment #123" in result.output
        assert "Test comment" in result.output

    @patch("rouge.cli.comment.fetch_comment")
    def test_read_with_json_format(self, mock_fetch_comment):
        """Test comment read command with --format json (raw output)."""
        mock_comment = Comment(
            id=123,
            issue_id=1,
            comment="Test comment",
            source="agent",
            type="plan",
            adw_id="adw-test-123",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
        )
        mock_fetch_comment.return_value = mock_comment

        result = runner.invoke(app, ["read", "123", "--format", "json"])
        assert result.exit_code == 0

        # Verify JSON output
        output_data = json.loads(result.output)
        assert output_data["id"] == 123
        assert output_data["issue_id"] == 1
        assert output_data["comment"] == "Test comment"
        assert output_data["source"] == "agent"
        assert output_data["type"] == "plan"
        assert output_data["adw_id"] == "adw-test-123"
        mock_fetch_comment.assert_called_once_with(123)

    @patch("rouge.cli.comment.fetch_comment")
    def test_read_with_json_format_short_flag(self, mock_fetch_comment):
        """Test comment read command with -f json short flag."""
        mock_comment = Comment(
            id=456,
            issue_id=2,
            comment="Another comment",
            source="system",
            type="note",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
        )
        mock_fetch_comment.return_value = mock_comment

        result = runner.invoke(app, ["read", "456", "-f", "json"])
        assert result.exit_code == 0

        # Verify JSON output
        output_data = json.loads(result.output)
        assert output_data["id"] == 456
        assert output_data["comment"] == "Another comment"

    @patch("rouge.cli.comment.fetch_comment")
    def test_read_plan_artifact_markdown_rendering(self, mock_fetch_comment):
        """Test comment read with --format text for plan artifact (markdown rendering)."""
        mock_fetch_comment.return_value = Comment(
            id=123,
            issue_id=1,
            comment="Plan artifact",
            source="agent",
            type="plan",
            raw={
                "artifact": {
                    "artifact_type": "plan",
                    "plan_data": {
                        "plan": (
                            "# Plan Title\n\n## Step 1\nDo something\n\n"
                            "## Step 2\nDo something else"
                        )
                    },
                }
            },
            created_at=datetime(2024, 1, 1, 12, 0, 0),
        )

        result = runner.invoke(app, ["read", "123", "--format", "text"])
        assert result.exit_code == 0
        assert "Comment #123" in result.output
        assert "Plan:" in result.output
        assert "# Plan Title" in result.output
        assert "## Step 1" in result.output
        assert "## Step 2" in result.output

    @patch("rouge.cli.comment.fetch_comment")
    def test_read_compose_request_artifact_markdown_rendering(self, mock_fetch_comment):
        """Test comment read with --format text for compose-request artifact."""
        mock_fetch_comment.return_value = Comment(
            id=124,
            issue_id=1,
            comment="Compose request artifact",
            source="agent",
            type="compose-request",
            raw={
                "artifact": {
                    "artifact_type": "compose-request",
                    "summary": (
                        "## Summary\n\nFixed the login bug\n\n"
                        "## Changes\n- Updated auth.py\n- Added tests"
                    ),
                }
            },
            created_at=datetime(2024, 1, 1, 12, 0, 0),
        )

        result = runner.invoke(app, ["read", "124", "--format", "text"])
        assert result.exit_code == 0
        assert "Comment #124" in result.output
        assert "Pull Request Summary:" in result.output
        assert "## Summary" in result.output
        assert "Fixed the login bug" in result.output
        assert "## Changes" in result.output

    @patch("rouge.cli.comment.fetch_comment")
    def test_read_non_markdown_artifact_formatted_fallback(self, mock_fetch_comment):
        """Test comment read with --format text for non-markdown artifact (formatted fallback)."""
        mock_fetch_comment.return_value = Comment(
            id=125,
            issue_id=1,
            comment="Regular comment",
            source="system",
            type="note",
            raw={"metadata": {"key": "value"}, "other_data": [1, 2, 3]},
            created_at=datetime(2024, 1, 1, 12, 0, 0),
        )

        result = runner.invoke(app, ["read", "125", "--format", "text"])
        assert result.exit_code == 0
        assert "Comment #125" in result.output
        assert "Comment:" in result.output
        assert "Regular comment" in result.output
        assert "Raw Data (JSON):" in result.output
        # Should have pretty-printed JSON
        assert '"metadata"' in result.output
        assert '"key"' in result.output
        assert '"value"' in result.output

    @patch("rouge.cli.comment.fetch_comment")
    def test_read_comment_without_raw_data(self, mock_fetch_comment):
        """Test comment read with no raw data."""
        mock_fetch_comment.return_value = Comment(
            id=126,
            issue_id=1,
            comment="Simple comment",
            source="system",
            type="note",
            raw={},
            created_at=datetime(2024, 1, 1, 12, 0, 0),
        )

        result = runner.invoke(app, ["read", "126", "--format", "text"])
        assert result.exit_code == 0
        assert "Comment #126" in result.output
        assert "Simple comment" in result.output
        # Should not show raw data section for empty dict
        assert "Raw Data (JSON):" not in result.output

    @patch("rouge.cli.comment.fetch_comment")
    def test_read_comment_with_minimal_fields(self, mock_fetch_comment):
        """Test comment read with minimal fields (only required ones)."""
        mock_fetch_comment.return_value = Comment(
            id=127,
            issue_id=1,
            comment="Minimal comment",
            source=None,
            type=None,
            adw_id=None,
            created_at=None,
        )

        result = runner.invoke(app, ["read", "127", "--format", "text"])
        assert result.exit_code == 0
        assert "Comment #127" in result.output
        assert "Issue ID:    1" in result.output
        assert "Source:      (none)" in result.output
        assert "Type:        (none)" in result.output
        # ADW ID and Created should not appear if None
        assert "ADW ID:" not in result.output
        assert "Created:" not in result.output

    @patch("rouge.cli.comment.fetch_comment")
    def test_read_invalid_comment_id(self, mock_fetch_comment):
        """Test comment read with invalid ID (not found)."""
        mock_fetch_comment.side_effect = ValueError("Comment with id 999 not found")

        result = runner.invoke(app, ["read", "999"])
        assert result.exit_code == 1
        assert "Error: Comment with id 999 not found" in result.output
        mock_fetch_comment.assert_called_once_with(999)

    @patch("rouge.cli.comment.fetch_comment")
    def test_read_database_error(self, mock_fetch_comment):
        """Test comment read handles database errors."""
        mock_fetch_comment.side_effect = ValueError("Database connection failed")

        result = runner.invoke(app, ["read", "123"])
        assert result.exit_code == 1
        assert "Error: Database connection failed" in result.output

    @patch("rouge.cli.comment.fetch_comment")
    def test_read_unexpected_error(self, mock_fetch_comment):
        """Test comment read handles unexpected errors."""
        mock_fetch_comment.side_effect = Exception("Unexpected failure")

        result = runner.invoke(app, ["read", "123"])
        assert result.exit_code == 1
        assert "Unexpected error: Unexpected failure" in result.output

    @patch("rouge.cli.comment.fetch_comment")
    def test_read_plan_artifact_with_empty_plan_data(self, mock_fetch_comment):
        """Test comment read with plan artifact but empty plan_data."""
        mock_fetch_comment.return_value = Comment(
            id=128,
            issue_id=1,
            comment="Plan with empty data",
            source="agent",
            type="plan",
            raw={"artifact": {"artifact_type": "plan", "plan_data": {}}},
            created_at=datetime(2024, 1, 1, 12, 0, 0),
        )

        result = runner.invoke(app, ["read", "128", "--format", "text"])
        assert result.exit_code == 0
        assert "Comment #128" in result.output
        assert "Plan:" in result.output
        # Should handle empty plan gracefully

    @patch("rouge.cli.comment.fetch_comment")
    def test_read_compose_request_artifact_with_empty_summary(self, mock_fetch_comment):
        """Test comment read with compose-request artifact but empty summary."""
        mock_fetch_comment.return_value = Comment(
            id=129,
            issue_id=1,
            comment="Compose request with empty summary",
            source="agent",
            type="compose-request",
            raw={"artifact": {"artifact_type": "compose-request", "summary": ""}},
            created_at=datetime(2024, 1, 1, 12, 0, 0),
        )

        result = runner.invoke(app, ["read", "129", "--format", "text"])
        assert result.exit_code == 0
        assert "Comment #129" in result.output
        assert "Pull Request Summary:" in result.output
        # Should handle empty summary gracefully

    @patch("rouge.cli.comment.fetch_comment")
    def test_read_malformed_artifact_data(self, mock_fetch_comment):
        """Test comment read with malformed artifact data (missing expected keys)."""
        mock_fetch_comment.return_value = Comment(
            id=130,
            issue_id=1,
            comment="Malformed artifact",
            source="agent",
            type="plan",
            raw={"artifact": {"artifact_type": "plan"}},  # Missing plan_data
            created_at=datetime(2024, 1, 1, 12, 0, 0),
        )

        result = runner.invoke(app, ["read", "130", "--format", "text"])
        assert result.exit_code == 0
        assert "Comment #130" in result.output
        # Should handle gracefully without crashing

    @patch("rouge.cli.comment.fetch_comment")
    def test_read_artifact_type_mismatch(self, mock_fetch_comment):
        """Test comment read when artifact_type doesn't match comment type field."""
        mock_fetch_comment.return_value = Comment(
            id=131,
            issue_id=1,
            comment="Type mismatch",
            source="agent",
            type="note",  # Comment type is 'note'
            raw={
                "artifact": {
                    "artifact_type": "plan",  # But artifact type is 'plan'
                    "plan_data": {"plan": "# Plan\n\nSome content"},
                }
            },
            created_at=datetime(2024, 1, 1, 12, 0, 0),
        )

        result = runner.invoke(app, ["read", "131", "--format", "text"])
        assert result.exit_code == 0
        assert "Comment #131" in result.output
        # Should render based on artifact_type in raw data, not comment.type
        assert "Plan:" in result.output


class TestTruncateStringHelper:
    """Tests for the truncate_string helper function."""

    def test_truncate_none_returns_none_string(self):
        """Test truncate_string with None returns '(none)'."""
        from rouge.cli.comment import truncate_string

        assert truncate_string(None, 10) == "(none)"

    def test_truncate_short_string_unchanged(self):
        """Test truncate_string with string shorter than max_length."""
        from rouge.cli.comment import truncate_string

        assert truncate_string("short", 10) == "short"

    def test_truncate_exact_length_unchanged(self):
        """Test truncate_string with string exactly at max_length."""
        from rouge.cli.comment import truncate_string

        assert truncate_string("exactly10!", 10) == "exactly10!"

    def test_truncate_long_string_with_ellipsis(self):
        """Test truncate_string with string longer than max_length adds ellipsis."""
        from rouge.cli.comment import truncate_string

        result = truncate_string("This is a very long string", 10)
        assert result == "This is..."
        assert len(result) == 10

    def test_truncate_zero_max_length(self):
        """Test truncate_string with max_length of 0."""
        from rouge.cli.comment import truncate_string

        assert truncate_string("test", 0) == ""

    def test_truncate_max_length_1_2_3(self):
        """Test truncate_string with max_length 1, 2, 3 (edge cases)."""
        from rouge.cli.comment import truncate_string

        assert truncate_string("test", 1) == "."
        assert truncate_string("test", 2) == ".."
        assert truncate_string("test", 3) == "..."


class TestRenderCommentTextHelper:
    """Tests for the render_comment_text helper function."""

    def test_render_basic_comment(self):
        """Test render_comment_text with basic comment (no artifact)."""
        from rouge.cli.comment import render_comment_text

        comment = Comment(
            id=1,
            issue_id=1,
            comment="Basic comment",
            source="system",
            type="note",
            created_at=datetime(2024, 1, 1, 12, 0, 0),
        )

        result = render_comment_text(comment)
        assert "Comment #1" in result
        assert "Issue ID:    1" in result
        assert "Source:      system" in result
        assert "Type:        note" in result
        assert "Basic comment" in result

    def test_render_plan_artifact(self):
        """Test render_comment_text with plan artifact."""
        from rouge.cli.comment import render_comment_text

        comment = Comment(
            id=2,
            issue_id=1,
            comment="Plan artifact",
            source="agent",
            type="plan",
            raw={
                "artifact": {
                    "artifact_type": "plan",
                    "plan_data": {"plan": "# Plan\n\nStep 1\nStep 2"},
                }
            },
            created_at=datetime(2024, 1, 1, 12, 0, 0),
        )

        result = render_comment_text(comment)
        assert "Comment #2" in result
        assert "Plan:" in result
        assert "# Plan" in result
        assert "Step 1" in result

    def test_render_compose_request_artifact(self):
        """Test render_comment_text with compose-request artifact."""
        from rouge.cli.comment import render_comment_text

        comment = Comment(
            id=3,
            issue_id=1,
            comment="PR summary",
            source="agent",
            type="compose-request",
            raw={
                "artifact": {
                    "artifact_type": "compose-request",
                    "summary": "## Summary\n\nFixed bugs",
                }
            },
            created_at=datetime(2024, 1, 1, 12, 0, 0),
        )

        result = render_comment_text(comment)
        assert "Comment #3" in result
        assert "Pull Request Summary:" in result
        assert "## Summary" in result
        assert "Fixed bugs" in result

    def test_render_comment_with_raw_data(self):
        """Test render_comment_text with raw data (no special artifact)."""
        from rouge.cli.comment import render_comment_text

        comment = Comment(
            id=4,
            issue_id=1,
            comment="Regular comment",
            source="system",
            type="note",
            raw={"key": "value"},
            created_at=datetime(2024, 1, 1, 12, 0, 0),
        )

        result = render_comment_text(comment)
        assert "Comment #4" in result
        assert "Regular comment" in result
        assert "Raw Data (JSON):" in result
        assert '"key"' in result
        assert '"value"' in result
