"""Rouge CLI - Workflow management CLI."""

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer

from rouge import __version__
from rouge.adw.adw import execute_adw_workflow
from rouge.cli.artifact import app as artifact_app
from rouge.cli.step import app as step_app
from rouge.core.database import create_issue, init_db_env
from rouge.core.utils import make_adw_id
from rouge.core.workflow.shared import get_repo_path

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


def _prepare_workflow(working_dir: Optional[Path], adw_id: Optional[str]) -> str:
    if working_dir:
        target_dir = working_dir.expanduser()
        if not target_dir.is_absolute():
            typer.echo("Error: --working-dir must be an absolute path", err=True)
            raise typer.Exit(1)
        target_dir = target_dir.resolve()
        if not target_dir.exists():
            typer.echo(f"Error: --working-dir does not exist: {target_dir}", err=True)
            raise typer.Exit(1)
        if not target_dir.is_dir():
            typer.echo(f"Error: --working-dir is not a directory: {target_dir}", err=True)
            raise typer.Exit(1)
        os.chdir(str(target_dir))
        typer.echo(f"Working directory set to {target_dir}")

    return adw_id or make_adw_id()


@app.command()
def run(
    issue_id: int,
    adw_id: Optional[str] = typer.Option(None, help="Workflow ID (auto-generated if not provided)"),
):
    """Execute the adw_plan_build workflow for an issue.

    Args:
        issue_id: The issue ID to process
        adw_id: Optional workflow ID for tracking (auto-generated if not provided)

    Example:
        rouge run 123
        rouge run 123 --adw-id abc12345
    """
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
):
    """Execute the patch workflow for an issue.

    Args:
        issue_id: The issue ID to process
        adw_id: Optional workflow ID for tracking (auto-generated if not provided)

    Example:
        rouge patch 123
        rouge patch 123 --adw-id abc12345
    """
    # Generate ADW ID if not provided
    if not adw_id:
        adw_id = make_adw_id()

    # Execute workflow
    success, _workflow_id = execute_adw_workflow(issue_id, adw_id, workflow_type="patch")

    if not success:
        raise typer.Exit(1)


def resolve_to_sha(ref: str) -> str:
    """Resolve a git reference to a full SHA.

    Runs ``git rev-parse <ref>`` to validate the reference and return the
    resolved commit SHA.

    Args:
        ref: A git reference such as a branch name, tag, or commit SHA.

    Returns:
        The full SHA string for the resolved reference.

    Raises:
        typer.Exit: If the reference cannot be resolved.
    """
    repo_path = get_repo_path()
    try:
        result = subprocess.run(
            ["git", "rev-parse", ref],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        typer.echo(f"Error: Invalid git reference '{ref}' (from {repo_path})", err=True)
        typer.echo(f"stderr: {e.stderr if hasattr(e, 'stderr') else 'N/A'}", err=True)
        raise typer.Exit(1)
    except FileNotFoundError:
        typer.echo("Error: git is not installed or not in PATH", err=True)
        raise typer.Exit(1)


@app.command()
def codereview(
    base_commit: str = typer.Option(
        ...,
        "--base-commit",
        help="Git reference (branch, tag, or SHA) to compare against",
        show_default=False,
    ),
    adw_id: Optional[str] = typer.Option(None, help="Workflow ID (auto-generated if not provided)"),
    working_dir: Optional[Path] = typer.Option(
        None,
        "--working-dir",
        help="Absolute directory to switch into before launching the workflow.",
    ),
):
    """Run a code review workflow against a base commit.

    Resolves the provided git reference to a SHA, then executes the
    codereview workflow pipeline.

    Example:
        rouge codereview --base-commit main
        rouge codereview --base-commit abc1234
    """
    adw_id = _prepare_workflow(working_dir, adw_id)

    sha = resolve_to_sha(base_commit)
    typer.echo(f"Resolved base commit: {sha}")

    success, _workflow_id = execute_adw_workflow(
        adw_id=adw_id,
        workflow_type="codereview",
        config={"base_commit": sha},
    )

    if not success:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
