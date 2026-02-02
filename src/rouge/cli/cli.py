"""Rouge CLI - Workflow management CLI."""

import logging
import os
import sys
from pathlib import Path
from typing import Optional

import typer

from rouge import __version__
from rouge.adw.adw import execute_adw_workflow
from rouge.cli.artifact import app as artifact_app
from rouge.cli.commands.code_review import app as code_review_app
from rouge.cli.step import app as step_app
from rouge.core.database import create_issue, init_db_env
from rouge.core.utils import make_adw_id

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

# Register subcommands
app.add_typer(step_app, name="step")
app.add_typer(artifact_app, name="artifact")
app.add_typer(code_review_app, name="code-review", help="Run code review commands")


def version_callback(value: bool):
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


@app.command()
def create(description: str):
    """Create a new issue from description string.

    Args:
        description: The issue description text

    Example:
        rouge create "Fix login authentication bug"
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
        rouge create-from-file issue-description.txt
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
def new_patch(
    file_path: Path = typer.Argument(
        ..., help="Path to file containing patch description", metavar="PATCH_FILE"
    ),
):
    """Create a new patch issue from description file.

    Args:
        file_path: Path to file containing patch description

    Example:
        rouge new-patch patch-description.txt
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

        # Create patch issue in database
        issue = create_issue(
            description=description,
            issue_type="patch",
        )
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
        issue_id: The issue ID to process
        adw_id: Optional workflow ID for tracking (auto-generated if not provided)

    Example:
        rouge run 123
        rouge run 123 --adw-id abc12345
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

    # Execute workflow
    success, _workflow_id = execute_adw_workflow(issue_id, adw_id)

    if not success:
        raise typer.Exit(1)


@app.command()
def patch(
    issue_id: int,
    adw_id: Optional[str] = typer.Option(None, help="Workflow ID (auto-generated if not provided)"),
    working_dir: Optional[Path] = typer.Option(
        None,
        "--working-dir",
        help="Absolute directory to switch into before launching the workflow.",
    ),
):
    """Execute the patch workflow for an issue.

    Args:
        issue_id: The issue ID to process
        adw_id: Optional workflow ID for tracking (auto-generated if not provided)

    Example:
        rouge patch 123
        rouge patch 123 --adw-id abc12345
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

    # Execute workflow
    success, _workflow_id = execute_adw_workflow(issue_id, adw_id, workflow_type="patch")

    if not success:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
