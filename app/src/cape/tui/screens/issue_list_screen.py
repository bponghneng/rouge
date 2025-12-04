import logging
from functools import partial
from typing import List, Optional

from textual import work
from textual.app import ComposeResult
from textual.containers import Container
from textual.coordinate import Coordinate
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Static,
)
from textual.widgets._data_table import RowKey

from cape.core.database import (
    delete_issue,
    fetch_all_issues,
    update_issue_assignment,
)
from cape.core.models import CapeIssue
from cape.tui.screens.confirm_delete_modal import ConfirmDeleteModal
from cape.tui.screens.create_issue_modal import CreateIssueModal
from cape.tui.screens.help_modal import HelpModal
from cape.tui.screens.issue_detail_screen import IssueDetailScreen
from cape.tui.screens.worker_assign_modal import WorkerAssignModal
from cape.tui.worker_utils import get_worker_display_name

logger = logging.getLogger(__name__)


class IssueListScreen(Screen):
    """Main screen displaying issue list in DataTable."""

    BINDINGS = [
        ("n", "new_issue", "New"),
        ("v", "view_detail", "View Details"),
        ("enter", "view_detail", "View Details"),
        ("r", "refresh", "Refresh"),
        ("a", "assign_worker", "Assign"),
        ("d", "delete_issue", "Delete"),
        ("delete", "delete_issue", "Delete"),
        ("q", "quit", "Quit"),
        ("?", "help", "Help"),
    ]

    loading: reactive[bool] = reactive(False)

    def compose(self) -> ComposeResult:
        """Create child widgets for the issue list screen."""
        yield Header(show_clock=True)
        yield Container(
            Static("Issues", id="content_header"),
            DataTable(
                id="issue_table",
                cell_padding=1,
                classes="table",
                header_height=2,
                zebra_stripes=True,
            ),
            Static("", id="content_footer"),
            id="content",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the screen when mounted."""
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_column("ID")
        table.add_column("Title")
        table.add_column("Status")
        table.add_column("Worker")
        self.load_issues()

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
            assigned = get_worker_display_name(issue.assigned_to) or "None"

            table.add_row(
                str(issue.id),
                issue.title,
                issue.status,
                assigned,
                height=2,
                key=str(issue.id),
            )

    def action_new_issue(self) -> None:
        """Show the create issue modal."""
        self.app.push_screen(CreateIssueModal(), self.on_issue_created)

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
        self.app.push_screen(HelpModal())

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

        # Get current assignment from database - we need to fetch the actual issue
        # to get the worker_id, since the table only shows display names
        from cape.core.database import fetch_issue

        try:
            current_issue = fetch_issue(issue_id)
            current_assignment = current_issue.assigned_to if current_issue else None
        except Exception:
            current_assignment = None

        # Show worker assignment modal with callback
        callback = partial(self.handle_worker_assignment, issue_id)
        self.app.push_screen(WorkerAssignModal(current_assignment), callback)

    def action_refresh(self) -> None:
        """Refresh the issue list."""
        self.load_issues()

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
        assigned_display = get_worker_display_name(updated_issue.assigned_to)
        worker_name = assigned_display if assigned_display else None

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
