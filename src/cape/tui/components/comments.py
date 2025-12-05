"""Comments container widget for the TUI."""

from typing import List

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static

from cape.core.models import CapeComment
from cape.tui.components.comment_item import create_comment_widget


class Comments(Container):
    """Composite widget for displaying issue comments.

    This widget renders a scrollable list of comment items, with each
    comment rendered by a type-specific component based on its source
    and type fields.
    """

    def compose(self) -> ComposeResult:
        """Compose the comments container layout."""
        yield Container(id="comments-container")

    def update_comments(self, comments: List[CapeComment]) -> None:
        """Update the displayed comments.

        Args:
            comments: List of CapeComment objects to display
        """
        container = self.query_one("#comments-container", Container)
        container.remove_children()

        if not comments:
            container.mount(Static("No comments yet", classes="empty-state"))
        else:
            for comment in comments:
                widget = create_comment_widget(comment)
                container.mount(widget)
