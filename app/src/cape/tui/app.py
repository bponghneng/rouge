from textual.app import App

from cape.core.utils import make_adw_id, setup_logger
from cape.tui.screens.help_modal import HelpModal
from cape.tui.screens.issue_list_screen import IssueListScreen


class CapeApp(App):
    """Main Cape TUI application."""

    CSS_PATH = None  # Will load dynamically from package
    TITLE = "Cape Issue Management"
    # ENABLE_COMMAND_PALETTE = False

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

            css_path = files("cape.tui").joinpath("cape_tui.tcss")
            self.CSS = css_path.read_text()
        except Exception:
            # Fallback: try to load from current directory (development mode)
            import os

            current_dir = os.path.dirname(__file__)
            # Try to find the CSS file in the current directory
            css_file = os.path.join(current_dir, "cape_tui.tcss")

            if not os.path.exists(css_file):
                # Try the original location relative to where the script might be run
                css_file = "cape/tui/cape_tui.tcss"

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
        self.push_screen(HelpModal())
