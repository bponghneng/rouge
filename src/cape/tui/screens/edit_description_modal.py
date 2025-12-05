from typing import Optional

from textual import work
from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Static

from cape.core.database import update_issue_description
from cape.tui.components.issue_form import IssueForm


class EditDescriptionModal(ModalScreen[bool]):
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

    def handle_save(self, description: str, title: Optional[str] = None) -> None:
        """Handle save action from IssueForm.

        Args:
            description: Validated description text
            title: Optional title value (ignored for description edits)
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
