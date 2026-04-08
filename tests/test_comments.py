"""Unit tests for comment notification utilities."""

from unittest.mock import patch

from rouge.core.models import Comment
from rouge.core.notifications.comments import emit_comment_from_payload


class TestEmitCommentFromPayload:
    """Tests for emit_comment_from_payload helper function."""

    @patch("rouge.core.notifications.comments.create_comment")
    def test_emit_comment_from_payload_success(self, mock_create_comment) -> None:
        """Test emit_comment_from_payload creates comment successfully."""
        from rouge.core.models import CommentPayload

        payload = CommentPayload(
            issue_id=1,
            adw_id="adw-test",
            text="Test comment",
            source="system",
            kind="status",
        )

        mock_create_comment.return_value = Comment(
            id=10,
            issue_id=1,
            comment="Test comment",
            adw_id="adw-test",
        )

        status, message = emit_comment_from_payload(payload)

        assert status == "success"
        assert "Comment inserted" in message
        assert "ID=10" in message

    @patch("rouge.core.notifications.comments.create_comment")
    def test_emit_comment_from_payload_with_none_issue_id(self, mock_create_comment) -> None:
        """Test emit_comment_from_payload skips when issue_id is None."""
        from rouge.core.models import CommentPayload

        payload = CommentPayload(
            issue_id=None,
            adw_id="adw-test",
            text="Test comment",
            source="system",
            kind="status",
        )

        status, message = emit_comment_from_payload(payload)

        mock_create_comment.assert_not_called()
        assert status == "skipped"
        assert "No issue_id" in message

    @patch("rouge.core.notifications.comments.create_comment")
    def test_emit_comment_from_payload_handles_error(self, mock_create_comment) -> None:
        """Test emit_comment_from_payload handles database errors."""
        from rouge.core.models import CommentPayload

        payload = CommentPayload(
            issue_id=1,
            adw_id="adw-test",
            text="Test comment",
            source="system",
            kind="status",
        )

        mock_create_comment.side_effect = Exception("Database error")

        status, message = emit_comment_from_payload(payload)

        assert status == "error"
        assert "Failed to insert comment" in message
