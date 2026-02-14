"""Rouge CLI - Workflow management CLI."""

import logging
import os
import subprocess
import sys
from enum import Enum
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


class IssueType(str, Enum):
    """Issue types supported by Rouge."""

    MAIN = "main"
    PATCH = "patch"


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


def generate_title(description: Optional[str]) -> str:
    """Generate a short title from a description.

    Takes the first 10 words of the description and appends "..." if the
    description is longer.

    Args:
        description: The full description text (or None)

    Returns:
        A shortened title string (first 10 words with "..." if truncated)
    """
    if not description or not description.strip():
        return ""

    words = description.split()
    if len(words) <= 10:
        return " ".join(words)

    return " ".join(words[:10]) + "..."


def validate_new_args(
    description: Optional[str],
    spec_file: Optional[Path],
    title: Optional[str],
) -> None:
    """Validate arguments for the new command.

    Performs validation checks for mutual exclusion, required inputs,
    and spec-file title requirement.

    Args:
        description: The issue description text (or None)
        spec_file: Path to file containing issue description (or None)
        title: Explicit title for the issue (or None)

    Raises:
        typer.Exit: If validation fails
    """
    # Validation: description and spec-file are mutually exclusive
    if description and spec_file:
        typer.echo(
            "Error: Cannot use both description argument and --spec-file option",
            err=True,
        )
        raise typer.Exit(1)

    # Validation: must provide either description or spec-file
    if not description and not spec_file:
        typer.echo(
            "Error: Must provide either a description argument or --spec-file option",
            err=True,
        )
        raise typer.Exit(1)

    # Validation: spec-file requires explicit --title
    if spec_file and not title:
        typer.echo(
            "Error: --spec-file requires explicit --title option",
            err=True,
        )
        raise typer.Exit(1)


def read_spec_file(spec_file: Path) -> str:
    """Read and validate content from a spec file.

    Reads the file content with UTF-8 encoding and validates that the file
    exists, is a regular file, and contains non-empty content.

    Args:
        spec_file: Path to the spec file to read

    Returns:
        The stripped content of the spec file

    Raises:
        typer.Exit: If the file cannot be read or is invalid
    """
    if not spec_file.exists():
        typer.echo(f"Error: File not found: {spec_file}", err=True)
        raise typer.Exit(1)

    if not spec_file.is_file():
        typer.echo(f"Error: Path is not a file: {spec_file}", err=True)
        raise typer.Exit(1)

    try:
        content = spec_file.read_text(encoding="utf-8").strip()
    except UnicodeDecodeError:
        typer.echo(f"Error: File is not valid UTF-8: {spec_file}", err=True)
        raise typer.Exit(1)
    except OSError as err:
        typer.echo(f"Error: Cannot read file: {spec_file}: {err}", err=True)
        raise typer.Exit(1)

    if not content:
        typer.echo("Error: File is empty", err=True)
        raise typer.Exit(1)

    return content


def prepare_issue(
    description: Optional[str],
    spec_file: Optional[Path],
    title: Optional[str],
) -> tuple[str, str]:
    """Prepare issue title and description from inputs.

    Orchestrates reading from spec_file or validating the description,
    and generates a title if needed.

    Args:
        description: The issue description text (or None)
        spec_file: Path to file containing issue description (or None)
        title: Explicit title for the issue (or None)

    Returns:
        A tuple of (issue_title, issue_description)

    Raises:
        typer.Exit: If validation fails
    """
    if spec_file:
        # Read from file
        issue_description = read_spec_file(spec_file)
        # title is guaranteed non-None here due to validation in validate_new_args
        assert title is not None
        issue_title = title
    else:
        # Use description argument
        issue_description = description.strip() if description else ""

        if not issue_description:
            typer.echo("Error: Description cannot be empty", err=True)
            raise typer.Exit(1)

        # Auto-generate title if not provided
        issue_title = title if title else generate_title(issue_description)

    return (issue_title, issue_description)


@app.command()
def new(
    description: Optional[str] = typer.Argument(None, help="The issue description text"),
    title: Optional[str] = typer.Option(
        None, "--title", "-t", help="Explicit title for the issue", show_default=True
    ),
    spec_file: Optional[Path] = typer.Option(
        None,
        "--spec-file",
        "-f",
        help="Path to file containing issue description",
        show_default=True,
    ),
    issue_type: IssueType = typer.Option(
        IssueType.MAIN,
        "--type",
        help="Issue type: 'main' for primary issues, 'patch' for patch issues",
        show_default=True,
    ),
) -> None:
    """Create a new issue.

    Supports multiple input modes:
    - Description only: `rouge new "Fix the login bug"` (auto-generates title)
    - Description + title: `rouge new "Fix the login bug" --title "Login fix"`
    - Spec file + title: `rouge new --spec-file spec.txt --title "Feature X"`
    - With type: `rouge new --spec-file patch.txt --title "Patch fix" --type patch`

    Examples:
        rouge new "Fix authentication bug in login flow"
        rouge new "Implement dark mode" --title "Dark mode feature"
        rouge new --spec-file feature-spec.txt --title "New feature"
        rouge new --spec-file patch-spec.txt --title "Bug fix" --type patch
    """
    validate_new_args(description, spec_file, title)
    issue_title, issue_description = prepare_issue(description, spec_file, title)

    try:
        issue = create_issue(
            description=issue_description, title=issue_title, issue_type=issue_type.value
        )
        typer.echo(f"{issue.id}")  # Output only the ID for scripting

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except typer.Exit:
        raise
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
