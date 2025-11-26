import logging
from typing import List, Optional

from textual import work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import (
    Collapsible,
    Footer,
    Header,
    Static,
)

from cape.core.database import delete_issue, fetch_comments, fetch_issue
from cape.core.models import CapeComment, CapeIssue
from cape.tui.components.comments import Comments
from cape.tui.screens.confirm_delete_modal import ConfirmDeleteModal
from cape.tui.screens.edit_description_modal import EditDescriptionModal

logger = logging.getLogger(__name__)


class IssueDetailScreen(Screen):
    """Screen showing issue details and comments."""

    BINDINGS = [
        ("escape", "back", "Back"),
        ("e", "edit_description", "Edit Description"),
        ("delete", "delete_issue", "Delete Issue"),
    ]

    issue_id: int
    issue: reactive[Optional[CapeIssue]] = reactive(None)
    comments: reactive[List[CapeComment]] = reactive([])
    loading: reactive[bool] = reactive(False)
    auto_refresh_active: reactive[bool] = reactive(False)
    refresh_timer: Optional[Timer] = None

    def __init__(self, issue_id: int):
        """Initialize with issue ID."""
        super().__init__()
        self.issue_id = issue_id

    def compose(self) -> ComposeResult:
        """Create child widgets for the detail screen."""
        yield Header()
        yield VerticalScroll(
            Static("Issue Details", id="detail-header"),
            Collapsible(
                Static("Loading...", id="issue-content"), title="Description", collapsed=False
            ),
            id="detail-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the screen when mounted."""
        # Create a paused timer for auto-refresh (activated when status becomes "started")
        self.refresh_timer = self.set_interval(
            10,
            lambda: self.load_data(is_refresh=True),
            pause=True,
            name="comment_refresh",
        )
        # Initial data load
        self.load_data()

    def on_unmount(self) -> None:
        """Clean up resources when screen is unmounted."""
        # Stop the refresh timer to prevent background API calls
        if self.refresh_timer is not None:
            self.refresh_timer.stop()
            self.auto_refresh_active = False

    @work(exclusive=True, thread=True)
    def load_data(self, is_refresh: bool = False) -> None:
        """Load issue and comments in background thread.

        Args:
            is_refresh: If True, this is a periodic refresh (not initial load)
        """
        try:
            # Show loading indicator for refresh operations
            if is_refresh:
                self.app.call_from_thread(self._set_loading, True)

            issue = fetch_issue(self.issue_id)
            comments = fetch_comments(self.issue_id)
            self.app.call_from_thread(self._display_data, issue, comments)

            # Clear loading indicator
            if is_refresh:
                self.app.call_from_thread(self._set_loading, False)
        except Exception as e:
            # Clear loading indicator
            if is_refresh:
                self.app.call_from_thread(self._set_loading, False)

            # Differentiate between initial load and refresh errors
            if is_refresh:
                # For refresh errors, log but don't show intrusive notification
                logger.warning(f"Auto-refresh failed for issue {self.issue_id}: {e}")
            else:
                # For initial load errors, show error to user
                logger.error(f"Failed to load issue {self.issue_id}: {e}")
                self.app.call_from_thread(
                    self.notify,
                    f"Error loading issue: {e}",
                    severity="error",
                )

    def _set_loading(self, loading: bool) -> None:
        """Set loading state for the comments widget."""
        try:
            # Try to find Comments if it exists
            comments_widget = self.query_one(Comments)
            comments_widget.loading = loading
        except Exception:
            # Ignore errors if widget is not yet mounted or doesn't exist
            pass

    def _display_data(self, issue: CapeIssue, comments: List[CapeComment]) -> None:
        """Display issue and comments data with conditional comments visibility.

        Args:
            issue: The issue to display
            comments: List of comments for the issue
        """
        # Check if we need to add or remove the comments section
        status_changed = self.issue is None or self.issue.status != issue.status
        comments_changed = (
            self.comments != comments or len(self.comments) != len(comments) or status_changed
        )

        # Store issue for later use
        self.issue = issue
        self.comments = comments

        # Display issue details
        status_color = {"pending": "yellow", "started": "blue", "completed": "green"}.get(
            issue.status, "white"
        )

        created = issue.created_at.strftime("%Y-%m-%d %H:%M") if issue.created_at else "Unknown"
        updated = issue.updated_at.strftime("%Y-%m-%d %H:%M") if issue.updated_at else "Unknown"

        # Format assignment
        if issue.assigned_to == "tydirium-1":
            assigned_display = "Tydirium"
        elif issue.assigned_to == "alleycat-1":
            assigned_display = "Alleycat"
        else:
            assigned_display = "None"

        content = f"""[bold]Issue #{issue.id}[/bold]
Status: [{status_color}]{issue.status}[/{status_color}]
Assigned to: {assigned_display}
Created: {created}
Updated: {updated}

{issue.description}
"""
        self.query_one("#issue-content", Static).update(content)

        # Handle conditional comments section visibility
        # Comments should only be visible for "started" or "completed" issues
        should_show_comments = issue.status in ["started", "completed"]

        # Check if comments section currently exists
        try:
            comments_widget = self.query_one(Comments)
            has_comments_section = True
        except Exception:
            has_comments_section = False

        # Add or remove comments section based on status
        if should_show_comments and not has_comments_section:
            # Add comments section
            container = self.query_one("#detail-container")
            container.mount(Static("Comments", id="comments-header"))
            container.mount(Comments(id="comments-widget"))
            comments_changed = True  # Force update since we just added it
        elif not should_show_comments and has_comments_section:
            # Remove comments section
            try:
                self.query_one("#comments-header").remove()
                self.query_one(Comments).remove()
            except Exception:
                pass

        # Update comments if section is visible and data changed
        if should_show_comments and comments_changed:
            try:
                comments_widget = self.query_one(Comments)
                comments_widget.update_comments(comments)

                # Log refresh activity
                if self.auto_refresh_active:
                    logger.debug(
                        "Auto-refresh updated %s comments for issue %s",
                        len(comments),
                        self.issue_id,
                    )
            except Exception as e:
                logger.warning(f"Error updating comments: {e}")

        # Activate or deactivate auto-refresh based on issue status
        if self.refresh_timer is not None:
            if issue.status == "started":
                if not self.auto_refresh_active:
                    self.auto_refresh_active = True
                    self.refresh_timer.resume()
                    logger.info(f"Auto-refresh activated for issue {self.issue_id}")
            else:
                if self.auto_refresh_active:
                    self.auto_refresh_active = False
                    self.refresh_timer.pause()
                    logger.info(f"Auto-refresh deactivated for issue {self.issue_id}")

    def action_back(self) -> None:
        """Return to issue list."""
        self.app.pop_screen()

    def action_edit_description(self) -> None:
        """Edit the issue description if status is pending."""
        if self.issue is None:
            self.notify("Issue not loaded yet", severity="warning")
            return

        if self.issue.status != "pending":
            self.notify(
                "Only pending issues can be edited. This issue is already started or completed.",
                severity="warning",
            )
            return

        self.app.push_screen(
            EditDescriptionModal(self.issue_id, self.issue.description),
            self.on_description_updated,
        )

    def action_delete_issue(self) -> None:
        """Delete the current issue after confirmation."""
        if self.issue is None:
            self.notify("Issue not loaded yet", severity="warning")
            return

        # Only allow deletion of pending issues
        if self.issue.status != "pending":
            self.notify("Only pending issues can be deleted", severity="warning")
            return

        # Show confirmation modal
        self.app.push_screen(
            ConfirmDeleteModal(self.issue_id, self.issue.description),
            self.handle_delete_confirmation,
        )

    def handle_delete_confirmation(self, confirmed: Optional[bool]) -> None:
        """Handle the result of delete confirmation."""
        if not confirmed:
            return

        # Perform deletion in background thread
        self.delete_issue_handler()

    @work(exclusive=True, thread=True)
    def delete_issue_handler(self) -> None:
        """Delete issue in background thread."""
        try:
            delete_issue(self.issue_id)
            # Return to list screen with notification
            self.app.call_from_thread(
                self._delete_success, f"Issue #{self.issue_id} deleted successfully"
            )
        except Exception as e:
            self.app.call_from_thread(self.notify, f"Error deleting issue: {e}", severity="error")

    def _delete_success(self, message: str) -> None:
        """Navigate back and show success message (must be called from main thread)."""
        self.notify(message, severity="information")
        self.app.pop_screen()

    def on_description_updated(self, updated: Optional[bool]) -> None:
        """Callback after description edit."""
        if updated:
            self.notify("Issue description updated", severity="information")
            self.load_data()
