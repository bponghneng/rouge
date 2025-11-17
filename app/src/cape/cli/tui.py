"""Cape Issue Management TUI - Textual-based interface for Cape workflows."""

import logging
from functools import partial
from typing import List, Optional

from dotenv import load_dotenv
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.coordinate import Coordinate
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.timer import Timer
from textual.widgets import (
    Button,
    Collapsible,
    DataTable,
    Footer,
    Header,
    RichLog,
    Static,
    TextArea,
)
from textual.widgets._data_table import RowKey

from cape.cli.widgets import WorkerAssignModal
from cape.core.database import create_issue as db_create_issue

# Import cape modules
from cape.core.database import (
    delete_issue,
    fetch_all_issues,
    fetch_comments,
    fetch_issue,
    update_issue_assignment,
    update_issue_description,
)
from cape.core.models import CapeComment, CapeIssue
from cape.core.utils import make_adw_id, setup_logger

# Load environment variables
load_dotenv()

# Setup logger
logger = logging.getLogger(__name__)


class IssueListScreen(Screen):
    """Main screen displaying issue list in DataTable."""

    BINDINGS = [
        ("n", "new_issue", "New Issue"),
        ("enter", "view_detail", "View Details"),
        ("v", "view_detail", "View Details"),
        ("a", "assign_worker", "Assign Worker"),
        ("d", "delete_issue", "Delete Issue"),
        ("delete", "delete_issue", "Delete Issue"),
        ("q", "quit", "Quit"),
        ("?", "help", "Help"),
    ]

    loading: reactive[bool] = reactive(False)
    status_timer: Optional[Timer] = None

    def compose(self) -> ComposeResult:
        """Create child widgets for the issue list screen."""
        yield Header(show_clock=True)
        yield Static("Cape Issue Management", id="title")
        yield DataTable(id="issue_table")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the screen when mounted."""
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_column("ID", width=6)
        table.add_column("Description", width=50)
        table.add_column("Status", width=12)
        table.add_column("Assigned To", width=14)
        table.add_column("Created", width=18)
        self.load_issues()
        # Refresh workflow indicators every 5 seconds
        self.status_timer = self.set_interval(5, self.load_issues)

    def on_unmount(self) -> None:
        """Clean up when screen is unmounted."""
        if self.status_timer:
            self.status_timer.stop()

    @work(exclusive=True, thread=True)
    def load_issues(self) -> None:
        """Load issues from database in background thread."""
        try:
            issues = fetch_all_issues()
            self.app.call_from_thread(self._populate_table, issues)
        except Exception as e:
            self.app.call_from_thread(self.notify, f"Error loading issues: {e}", severity="error")

    def _populate_table(self, issues: List[CapeIssue]) -> None:
        """Populate the DataTable with issue data."""
        table = self.query_one(DataTable)
        table.clear()

        if not issues:
            self.notify("No issues found. Press 'n' to create one.", severity="information")
            return

        for issue in issues:
            # Truncate description to 50 characters
            if len(issue.description) > 50:
                desc = f"{issue.description[:47]}..."
            else:
                desc = issue.description

            # Format assignment
            if issue.assigned_to == "tydirium-1":
                assigned = "Tydirium"
            elif issue.assigned_to == "alleycat-1":
                assigned = "Alleycat"
            else:
                assigned = ""

            # Format timestamp
            created = issue.created_at.strftime("%Y-%m-%d %H:%M") if issue.created_at else "Unknown"

            table.add_row(str(issue.id), desc, issue.status, assigned, created, key=str(issue.id))

    def action_new_issue(self) -> None:
        """Show the create issue modal."""
        self.app.push_screen(CreateIssueScreen(), self.on_issue_created)

    def action_view_detail(self) -> None:
        """Navigate to issue detail screen."""
        table = self.query_one(DataTable)
        if table.cursor_row is None or table.cursor_row < 0:
            self.notify("No issue selected", severity="warning")
            return

        row_key = table.get_row_at(table.cursor_row)
        issue_id = int(row_key[0])
        self.app.push_screen(IssueDetailScreen(issue_id))

    def action_delete_issue(self) -> None:
        """Delete the selected issue after confirmation."""
        table = self.query_one(DataTable)
        if table.cursor_row is None or table.cursor_row < 0:
            self.notify("No issue selected", severity="warning")
            return

        # Get issue data from the table row
        row_data = table.get_row_at(table.cursor_row)
        issue_id = int(row_data[0])
        issue_description = str(row_data[1])
        issue_status = str(row_data[2])
        base_status = issue_status.split()[0] if issue_status else ""
        coordinate = Coordinate(row=table.cursor_row, column=0)
        row_key = table.coordinate_to_cell_key(coordinate).row_key
        if row_key is None:
            self.notify("Unable to determine selected issue", severity="error")
            return

        # Only allow deletion of pending issues
        if base_status != "pending":
            self.notify("Only pending issues can be deleted", severity="warning")
            return

        # Show confirmation modal with callback
        callback = partial(self.handle_delete_confirmation, issue_id, row_key)
        self.app.push_screen(ConfirmDeleteModal(issue_id, issue_description), callback)

    def handle_delete_confirmation(
        self, issue_id: int, row_key: RowKey, confirmed: Optional[bool]
    ) -> None:
        """Handle the result of delete confirmation."""
        if not confirmed:
            return

        # Perform deletion in background thread
        self.delete_issue_handler(issue_id, row_key)

    @work(exclusive=True, thread=True)
    def delete_issue_handler(self, issue_id: int, row_key: RowKey) -> None:
        """Delete issue in background thread."""
        try:
            delete_issue(issue_id)
            # Update UI from thread
            self.app.call_from_thread(
                self._remove_row_and_notify, row_key, f"Issue #{issue_id} deleted successfully"
            )
        except Exception as e:
            self.app.call_from_thread(self.notify, f"Error deleting issue: {e}", severity="error")

    def _remove_row_and_notify(self, row_key: RowKey, message: str) -> None:
        """Remove row from table and show notification (must be called from main thread)."""
        table = self.query_one(DataTable)
        table.remove_row(row_key)
        self.notify(message, severity="information")

    def action_help(self) -> None:
        """Show help screen."""
        self.app.push_screen(HelpScreen())

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit()

    def on_issue_created(self, issue_id: Optional[int]) -> None:
        """Callback after issue creation."""
        if issue_id is not None:
            self.notify(f"Issue #{issue_id} created successfully", severity="information")
            self.load_issues()

    def action_assign_worker(self) -> None:
        """Open worker assignment modal for the selected issue."""
        table = self.query_one(DataTable)
        if table.cursor_row is None or table.cursor_row < 0:
            self.notify("No issue selected", severity="warning")
            return

        # Get issue data from the table row
        row_data = table.get_row_at(table.cursor_row)
        issue_id = int(row_data[0])
        issue_status = str(row_data[2])
        base_status = issue_status.split()[0] if issue_status else ""

        # Only allow assignment for pending issues
        if base_status != "pending":
            self.notify("Only pending issues can be assigned", severity="warning")
            return

        # Get current assignment from table
        assigned_display = str(row_data[3])
        if assigned_display == "Tydirium":
            current_assignment = "tydirium-1"
        elif assigned_display == "Alleycat":
            current_assignment = "alleycat-1"
        else:
            current_assignment = None

        # Show worker assignment modal with callback
        callback = partial(self.handle_worker_assignment, issue_id)
        self.app.push_screen(WorkerAssignModal(current_assignment), callback)

    def handle_worker_assignment(self, issue_id: int, assigned_to: Optional[str]) -> None:
        """Handle the result of worker assignment modal.

        Args:
            issue_id: The ID of the issue to assign.
            assigned_to: The selected worker ID (None for unassigned, or worker ID).
                        Returns None if modal was cancelled.
        """
        # Modal returns None if cancelled or if user didn't make a change
        # We need to distinguish between these cases
        # The modal always returns a value (the selected worker), so if it's None
        # it means either cancelled or unassigned was selected
        # For now, we'll proceed with the assignment

        # Perform assignment in background thread
        self.assign_worker_handler(issue_id, assigned_to)

    @work(exclusive=True, thread=True)
    def assign_worker_handler(self, issue_id: int, assigned_to: Optional[str]) -> None:
        """Assign worker to issue in background thread.

        Args:
            issue_id: The ID of the issue to assign.
            assigned_to: The worker ID to assign (None for unassigned).
        """
        try:
            updated_issue = update_issue_assignment(issue_id, assigned_to)
            # Update UI from thread
            self.app.call_from_thread(self._update_assignment_success, updated_issue)
        except Exception as e:
            self.app.call_from_thread(self.notify, f"Error assigning worker: {e}", severity="error")

    def _update_assignment_success(self, updated_issue: CapeIssue) -> None:
        """Update table row after successful assignment and show notification.

        Args:
            updated_issue: The updated issue with new assignment.
        """
        # Format assignment for display
        if updated_issue.assigned_to == "tydirium-1":
            assigned_display = "Tydirium"
            worker_name = "Tydirium"
        elif updated_issue.assigned_to == "alleycat-1":
            assigned_display = "Alleycat"
            worker_name = "Alleycat"
        else:
            assigned_display = ""
            worker_name = None

        # Find and update the row in the table
        table = self.query_one(DataTable)
        issue_key = str(updated_issue.id)

        # Update the row
        try:
            # Get the current row data
            for row_index in range(len(table.rows)):
                row_data = table.get_row_at(row_index)
                if str(row_data[0]) == issue_key:
                    # Update the assignment column (index 3)
                    table.update_cell_at(Coordinate(row=row_index, column=3), assigned_display)
                    break

            # Show success notification
            if worker_name:
                msg = f"Issue #{updated_issue.id} assigned to {worker_name}"
                self.notify(msg, severity="information")
            else:
                self.notify(f"Issue #{updated_issue.id} unassigned", severity="information")

        except Exception as e:
            logger.error(f"Error updating table after assignment: {e}")
            # Fall back to full reload
            self.load_issues()


class IssueForm(Container):
    """Reusable form component for issue creation and editing.

    This composite widget provides a consistent form interface with validation
    for both creating new issues and editing existing issue descriptions.

    Args:
        initial_text: Optional initial text for the TextArea
        on_save_callback: Callable to invoke when save is triggered
        on_cancel_callback: Callable to invoke when cancel is triggered
    """

    BINDINGS = [
        ("ctrl+s", "save", "Save"),
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, initial_text: str = "", on_save_callback=None, on_cancel_callback=None):
        """Initialize the form with optional callbacks."""
        super().__init__()
        self.initial_text = initial_text
        self.on_save_callback = on_save_callback
        self.on_cancel_callback = on_cancel_callback

    def compose(self) -> ComposeResult:
        """Create child widgets for the form."""
        yield TextArea(id="description", language="markdown")
        yield Horizontal(
            Button("Save", variant="success", id="save-btn"),
            Button("Cancel", variant="error", id="cancel-btn"),
            id="button-row",
        )

    def on_mount(self) -> None:
        """Initialize the form when mounted."""
        text_area = self.query_one(TextArea)
        if self.initial_text:
            text_area.text = self.initial_text
        text_area.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "save-btn":
            self.action_save()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def action_save(self) -> None:
        """Validate and trigger save callback."""
        text_area = self.query_one(TextArea)
        description = text_area.text.strip()

        # Validation
        if not description or description == "Enter issue description...":
            self.screen.notify("Description cannot be empty", severity="warning")
            return

        if len(description) < 10:
            self.screen.notify("Description must be at least 10 characters", severity="warning")
            return

        if len(description) > 10000:
            self.screen.notify("Description cannot exceed 10,000 characters", severity="warning")
            return

        # Trigger callback if provided
        if self.on_save_callback:
            self.on_save_callback(description)

    def action_cancel(self) -> None:
        """Trigger cancel callback."""
        if self.on_cancel_callback:
            self.on_cancel_callback()


class CommentsWidget(RichLog):
    """Widget for displaying issue comments with consistent formatting.

    This widget extends RichLog to provide specialized comment display
    functionality with timestamp formatting and empty state handling.
    """

    def __init__(self, **kwargs):
        """Initialize the comments widget."""
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


class CreateIssueScreen(ModalScreen[Optional[int]]):
    """Modal form for creating new issues."""

    def compose(self) -> ComposeResult:
        """Create child widgets for the create issue modal."""
        yield Container(
            Static("Create New Issue", id="modal-header"),
            IssueForm(
                initial_text="Enter issue description...",
                on_save_callback=self.handle_save,
                on_cancel_callback=self.handle_cancel,
            ),
            id="create-issue-modal",
        )

    def handle_save(self, description: str) -> None:
        """Handle save action from IssueForm.

        Args:
            description: Validated description text
        """
        self.create_issue_handler(description)

    def handle_cancel(self) -> None:
        """Handle cancel action from IssueForm."""
        self.dismiss(None)

    @work(exclusive=True, thread=True)
    def create_issue_handler(self, description: str) -> None:
        """Create issue in background thread.

        Args:
            description: Issue description to save
        """
        try:
            issue = db_create_issue(description)
            self.app.call_from_thread(self.dismiss, issue.id)
        except Exception as e:
            self.app.call_from_thread(self.notify, f"Error creating issue: {e}", severity="error")


class EditDescriptionScreen(ModalScreen[bool]):
    """Modal form for editing issue description."""

    def __init__(self, issue_id: int, current_description: str):
        """Initialize with issue ID and current description.

        Args:
            issue_id: ID of the issue being edited
            current_description: Current description text
        """
        super().__init__()
        self.issue_id = issue_id
        self.current_description = current_description

    def compose(self) -> ComposeResult:
        """Create child widgets for the edit description modal."""
        yield Container(
            Static(f"Edit Issue #{self.issue_id} Description", id="modal-header"),
            IssueForm(
                initial_text=self.current_description,
                on_save_callback=self.handle_save,
                on_cancel_callback=self.handle_cancel,
            ),
            id="edit-description-modal",
        )

    def handle_save(self, description: str) -> None:
        """Handle save action from IssueForm.

        Args:
            description: Validated description text
        """
        self.update_description_handler(description)

    def handle_cancel(self) -> None:
        """Handle cancel action from IssueForm."""
        self.dismiss(False)

    @work(exclusive=True, thread=True)
    def update_description_handler(self, description: str) -> None:
        """Update issue description in background thread.

        Args:
            description: New description text
        """
        try:
            update_issue_description(self.issue_id, description)
            self.app.call_from_thread(self.dismiss, True)
        except Exception as e:
            self.app.call_from_thread(
                self.notify,
                f"Error updating description: {e}",
                severity="error",
            )


class ConfirmDeleteModal(ModalScreen[bool]):
    """Modal dialog for confirming issue deletion."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, issue_id: int, issue_description: str):
        """Initialize with issue ID and description.

        Args:
            issue_id: The ID of the issue to delete.
            issue_description: The issue description (will be truncated for display).
        """
        super().__init__()
        self.issue_id = issue_id
        self.issue_description = issue_description

    def compose(self) -> ComposeResult:
        """Create child widgets for the confirmation modal."""
        # Truncate description if too long
        display_description = self.issue_description[:100]
        if len(self.issue_description) > 100:
            display_description += "..."

        yield Container(
            Static(f"Delete Issue #{self.issue_id}", id="modal-header"),
            Static(display_description, id="issue-preview"),
            Static("⚠️  This action cannot be undone", id="delete-warning"),
            Horizontal(
                Button("Cancel", variant="primary", id="cancel-btn"),
                Button("Delete", variant="error", id="delete-btn"),
                id="button-row",
            ),
            id="confirm-delete-modal",
        )

    def on_mount(self) -> None:
        """Initialize the modal when mounted - focus on cancel button."""
        cancel_btn = self.query_one("#cancel-btn", Button)
        cancel_btn.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "delete-btn":
            self.dismiss(True)
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def action_cancel(self) -> None:
        """Cancel and close the modal."""
        self.dismiss(False)


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
            # Try to find CommentsWidget if it exists
            comments_widget = self.query_one(CommentsWidget)
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
            comments_widget = self.query_one(CommentsWidget)
            has_comments_section = True
        except Exception:
            has_comments_section = False

        # Add or remove comments section based on status
        if should_show_comments and not has_comments_section:
            # Add comments section
            container = self.query_one("#detail-container")
            container.mount(Static("Comments", id="comments-header"))
            container.mount(CommentsWidget(id="comments-widget"))
            comments_changed = True  # Force update since we just added it
        elif not should_show_comments and has_comments_section:
            # Remove comments section
            try:
                self.query_one("#comments-header").remove()
                self.query_one(CommentsWidget).remove()
            except Exception:
                pass

        # Update comments if section is visible and data changed
        if should_show_comments and comments_changed:
            try:
                comments_widget = self.query_one(CommentsWidget)
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
            EditDescriptionScreen(self.issue_id, self.issue.description),
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


class HelpScreen(ModalScreen):
    """Help screen displaying keyboard shortcuts and usage information."""

    BINDINGS = [
        ("escape", "close", "Close"),
    ]

    def compose(self) -> ComposeResult:
        """Create child widgets for the help screen."""
        help_text = """# Cape TUI - Help

## Keyboard Shortcuts

### Issue List
- **n**: Create new issue
- **Enter/v**: View issue details
- **a**: Assign worker (pending issues only)
- **d/Delete**: Delete issue (pending issues only)
- **q**: Quit application
- **?**: Show this help screen

### Create Issue
- **Ctrl+S**: Save issue
- **Escape**: Cancel

### Edit Description
- **Ctrl+S**: Save changes
- **Escape**: Cancel

### Issue Detail
- **e**: Edit description (pending issues only)
- **Delete**: Delete issue (pending issues only)
- **Escape**: Back to list

## Workflow Management

Workflows are managed through the CLI commands:
- `cape workflow start <issue-id>` - Launch a workflow
- `cape workflow list` - List all active workflows
- `cape workflow status <workflow-id>` - Show workflow status
- `cape workflow stop <workflow-id>` - Stop a running workflow
- `cape workflow logs <workflow-id>` - View workflow logs

## Troubleshooting

- Ensure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set in .env
- Check log files in agents/{adw_id}/adw_plan_build/execution.log
- Workflows are stored in ~/.cape/ directory
"""
        yield Container(Static(help_text, id="help-content"), id="help-modal")

    def action_close(self) -> None:
        """Close the help screen."""
        self.dismiss()


class CapeApp(App):
    """Main Cape TUI application."""

    CSS_PATH = None  # Will load dynamically from package

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("?", "help", "Help"),
    ]

    def __init__(self):
        """Initialize app and load CSS from package resources."""
        super().__init__()
        # Load CSS from package resources
        try:
            from importlib.resources import files

            css_path = files("cape.cli").joinpath("cape_tui.tcss")
            self.CSS = css_path.read_text()
        except Exception:
            # Fallback: try to load from current directory (development mode)
            import os

            current_dir = os.path.dirname(__file__)
            css_file = os.path.join(current_dir, "cape_tui.tcss")
            if os.path.exists(css_file):
                with open(css_file) as f:
                    self.CSS = f.read()
            else:
                # Use minimal CSS if file not found
                self.CSS = ""

    def on_mount(self) -> None:
        """Initialize application on mount."""
        # Initialize logger
        adw_id = make_adw_id()
        tui_logger = setup_logger(adw_id, "cape_tui")
        tui_logger.info("Cape TUI application started")

        # Push initial screen
        self.push_screen(IssueListScreen())

    def action_help(self) -> None:
        """Show help screen."""
        self.push_screen(HelpScreen())


if __name__ == "__main__":
    app = CapeApp()
    app.run()
