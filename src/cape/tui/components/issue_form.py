from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, Input, Rule, TextArea


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

    def __init__(
        self,
        initial_text: str = "",
        initial_title: str = "",
        on_save_callback=None,
        on_cancel_callback=None,
    ):
        """Initialize the form with optional callbacks."""
        super().__init__()
        self.initial_text = initial_text
        self.initial_title = initial_title
        self.on_save_callback = on_save_callback
        self.on_cancel_callback = on_cancel_callback

    def compose(self) -> ComposeResult:
        """Create child widgets for the form."""
        yield Container(
            Input(id="title", placeholder="Enter issue title ..."),
            Rule(line_style="dashed", classes="divider"),
            TextArea(id="issue-description", language="markdown"),
            Horizontal(
                Button("Save", variant="success", compact=True, flat=True, id="save-btn"),
                Button("Cancel", variant="error", compact=True, flat=True, id="cancel-btn"),
                id="button-row",
            ),
            id="issue-form",
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
        input_widget = self.query_one(Input)
        text_area = self.query_one(TextArea)
        title = input_widget.value.strip()
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
            self.on_save_callback(description, title)

    def action_cancel(self) -> None:
        """Trigger cancel callback."""
        if self.on_cancel_callback:
            self.on_cancel_callback()
