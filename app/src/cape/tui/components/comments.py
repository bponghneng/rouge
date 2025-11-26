from typing import List

from textual.widgets import RichLog

from cape.core.models import CapeComment


class Comments(RichLog):
    """Widget for displaying issue comments with consistent formatting.

    This widget extends RichLog to provide specialized comment display
    functionality with timestamp formatting and empty state handling.
    """

    def __init__(self, **kwargs):
        """Initialize the comments component."""
        super().__init__(**kwargs)

    def update_comments(self, comments: List[CapeComment]) -> None:
        """Update the displayed comments.

        Args:
            comments: List of CapeComment objects to display
        """
        self.clear()

        if not comments:
            self.write("No comments yet")
        else:
            for comment in comments:
                timestamp = (
                    comment.created_at.strftime("%Y-%m-%d %H:%M")
                    if comment.created_at
                    else "Unknown"
                )
                self.write(f"[dim]{timestamp}[/dim]\n{comment.comment}\n")
