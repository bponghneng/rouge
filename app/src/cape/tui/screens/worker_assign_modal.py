"""Worker assignment modal widget for Cape TUI."""

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Static

# Worker options: (display_name, worker_id)
WORKER_OPTIONS = [
    ("Unassigned", None),
    ("Tydirium (tydirium-1)", "tydirium-1"),
    ("Alleycat (alleycat-1)", "alleycat-1"),
]


class WorkerAssignModal(ModalScreen[Optional[str]]):
    """Modal for assigning an issue to a worker."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    def __init__(self, current_assignment: Optional[str] = None):
        """Initialize the worker assignment modal.

        Args:
            current_assignment: The current worker assignment (None, 'tydirium-1', or 'alleycat-1').
        """
        super().__init__()
        self.current_assignment = current_assignment
        self.selected_worker: Optional[str] = current_assignment

    def compose(self) -> ComposeResult:
        """Create child widgets for the worker assignment modal."""
        # Create worker option buttons
        worker_buttons = []
        for display_name, worker_id in WORKER_OPTIONS:
            button_id = f"worker-{worker_id if worker_id else 'none'}"
            # Highlight current assignment
            if worker_id == self.current_assignment:
                worker_buttons.append(
                    Button(
                        f"✓ {display_name}",
                        variant="success",
                        id=button_id,
                        classes="worker-option",
                    )
                )
            else:
                worker_buttons.append(
                    Button(display_name, variant="default", id=button_id, classes="worker-option")
                )

        yield Container(
            Static("Assign Worker", id="modal-header"),
            Static("Select a worker to assign this issue:", id="modal-description"),
            *worker_buttons,
            Horizontal(
                Button("Cancel", variant="primary", id="cancel-btn"),
                Button("Save", variant="success", id="save-btn"),
                id="button-row",
            ),
            id="worker-assign-modal",
        )

    def on_mount(self) -> None:
        """Initialize the modal when mounted - focus on save button."""
        save_btn = self.query_one("#save-btn", Button)
        save_btn.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "save-btn":
            # Return the selected worker
            self.dismiss(self.selected_worker)
        elif button_id == "cancel-btn":
            self.action_cancel()
        elif button_id and button_id.startswith("worker-"):
            # Handle worker selection
            self._select_worker(button_id)

    def _select_worker(self, button_id: str) -> None:
        """Update the selected worker and refresh button styles.

        Args:
            button_id: The ID of the clicked worker button.
        """
        # Parse worker_id from button_id
        if button_id == "worker-none":
            self.selected_worker = None
        elif button_id == "worker-tydirium-1":
            self.selected_worker = "tydirium-1"
        elif button_id == "worker-alleycat-1":
            self.selected_worker = "alleycat-1"

        # Update button styles to show selection
        for display_name, worker_id in WORKER_OPTIONS:
            btn_id = f"worker-{worker_id if worker_id else 'none'}"
            button = self.query_one(f"#{btn_id}", Button)

            if worker_id == self.selected_worker:
                button.variant = "success"
                button.label = f"✓ {display_name}"
            else:
                button.variant = "default"
                button.label = display_name

    def action_cancel(self) -> None:
        """Cancel and close the modal without making changes."""
        self.dismiss(None)
