from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Static


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
