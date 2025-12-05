from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Static


class HelpModal(ModalScreen):
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
