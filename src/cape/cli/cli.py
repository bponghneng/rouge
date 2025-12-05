"""Cape CLI - TUI-first workflow management CLI."""

import os
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

from cape import __version__
from cape.core.database import create_issue
from cape.core.utils import make_adw_id, setup_logger
from cape.core.workflow import execute_workflow

# Load environment variables
load_dotenv()

app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    help="Cape CLI - TUI-first workflow management",
)


def version_callback(value: bool):
    """Print version and exit."""
    if value:
        typer.echo(f"Cape CLI version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
):
    """Main entry point. Launches TUI if no subcommand provided."""
    if ctx.invoked_subcommand is None:
        # Import TUI here to avoid import errors if textual isn't installed
        try:
            from cape.tui.app import CapeApp

            tui_app = CapeApp()
            tui_app.run()
        except ImportError as e:
            typer.echo(f"Error: TUI dependencies not available: {e}", err=True)
            typer.echo("Please install with: uv pip install cape-cli", err=True)
            raise typer.Exit(1)
        except Exception as e:
            typer.echo(f"Error launching TUI: {e}", err=True)
            raise typer.Exit(1)


@app.command()
def create(description: str):
    """Create a new issue from description string.

    Args:
        description: The issue description text

    Example:
        cape create "Fix login authentication bug"
    """
    try:
        # Create issue in database
        issue = create_issue(description)
        typer.echo(f"{issue.id}")  # Output only the ID for scripting
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Unexpected error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def create_from_file(file_path: Path):
    """Create a new issue from description file.

    Args:
        file_path: Path to file containing issue description

    Example:
        cape create-from-file issue-description.txt
    """
    try:
        # Validate file exists
        if not file_path.exists():
            typer.echo(f"Error: File not found: {file_path}", err=True)
            raise typer.Exit(1)

        # Validate it's a file, not a directory
        if not file_path.is_file():
            typer.echo(f"Error: Path is not a file: {file_path}", err=True)
            raise typer.Exit(1)

        # Read file content
        description = file_path.read_text(encoding="utf-8").strip()

        if not description:
            typer.echo("Error: File is empty", err=True)
            raise typer.Exit(1)

        # Create issue in database
        issue = create_issue(description)
        typer.echo(f"{issue.id}")  # Output only the ID for scripting

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except UnicodeDecodeError:
        typer.echo(f"Error: File is not valid UTF-8: {file_path}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Unexpected error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def run(
    issue_id: int,
    adw_id: Optional[str] = typer.Option(None, help="Workflow ID (auto-generated if not provided)"),
    working_dir: Optional[Path] = typer.Option(
        None,
        "--working-dir",
        help="Absolute directory to switch into before launching the workflow.",
    ),
):
    """Execute the adw_plan_build workflow for an issue.

    Args:
        issue_id: The Cape issue ID to process
        adw_id: Optional workflow ID for tracking (auto-generated if not provided)

    Example:
        cape run 123
        cape run 123 --adw-id abc12345
    """
    # Adjust working directory if requested
    if working_dir:
        target_dir = working_dir.expanduser()
        if not target_dir.is_absolute():
            typer.echo("Error: --working-dir must be an absolute path", err=True)
            raise typer.Exit(1)
        target_dir = target_dir.resolve()
        os.chdir(target_dir)
        typer.echo(f"Working directory set to {target_dir}")

    # Generate ADW ID if not provided
    if not adw_id:
        adw_id = make_adw_id()

    # Set up logger
    logger = setup_logger(adw_id, "adw_plan_build")

    # Execute workflow
    success = execute_workflow(issue_id, adw_id, logger)

    if not success:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
