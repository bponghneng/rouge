"""Cape Issue Management TUI - Textual-based interface for Cape workflows."""

from dotenv import load_dotenv

from cape.tui.app import CapeApp

# Load environment variables
load_dotenv()


if __name__ == "__main__":
    app = CapeApp()
    app.run()
