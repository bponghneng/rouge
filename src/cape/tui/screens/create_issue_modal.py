from typing import Optional

from textual import work
from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Static

from cape.core.database import create_issue as db_create_issue
from cape.tui.components.issue_form import IssueForm


class CreateIssueModal(ModalScreen[Optional[int]]):
    """Modal form for creating new issues."""

    def compose(self) -> ComposeResult:
        """Create child widgets for the create issue modal."""
        yield Container(
            Static("Create New Issue", id="modal-header"),
            IssueForm(
                initial_title="Enter issue title ...",
                initial_text="Enter issue description ...",
                on_save_callback=self.handle_save,
                on_cancel_callback=self.handle_cancel,
            ),
            id="modal-content",
        )

    def handle_save(self, description: str, title: str) -> None:
        """Handle save action from IssueForm.

        Args:
            description: Validated description text
            title: Validated title text
        """
        self.create_issue_handler(description, title)

    def handle_cancel(self) -> None:
        """Handle cancel action from IssueForm."""
        self.dismiss(None)

    @work(exclusive=True, thread=True)
    def create_issue_handler(self, description: str, title: str) -> None:
        """Create issue in background thread.

        Args:
            description: Issue description to save
            title: Issue title to save
        """
        try:
            issue = db_create_issue(description, title=title)
            self.app.call_from_thread(self.dismiss, issue.id)
        except Exception as e:
            self.app.call_from_thread(self.notify, f"Error creating issue: {e}", severity="error")
