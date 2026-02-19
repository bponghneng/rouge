"""Rouge CLI - Workflow management CLI."""

import logging
import sys
from pathlib import Path
from typing import Optional

import typer

from rouge import __version__
from rouge.cli.artifact import app as artifact_app
from rouge.cli.comment import app as comment_app
from rouge.cli.issue import app as issue_app
from rouge.cli.step import app as step_app
from rouge.cli.workflow import app as workflow_app
from rouge.core.database import init_db_env

# Configure logging for CLI commands
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Load environment variables
env_file_path = Path.cwd() / ".env"
if env_file_path.exists():
    init_db_env(dotenv_path=env_file_path)
else:
    parent_env_file_path = Path.cwd().parent / ".env"
    if parent_env_file_path.exists():
        init_db_env(dotenv_path=parent_env_file_path)
    else:
        init_db_env()


app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=True,
    help="Rouge CLI - Workflow management",
)

# Register command groups
app.add_typer(issue_app, name="issue")
app.add_typer(workflow_app, name="workflow")
app.add_typer(comment_app, name="comment")
app.add_typer(step_app, name="step")
app.add_typer(artifact_app, name="artifact")


def version_callback(value: Optional[bool]):
    """Print version and exit."""
    if value:
        typer.echo(f"Rouge CLI version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
):
    """Rouge CLI - Workflow management."""
    pass


if __name__ == "__main__":
    app()
