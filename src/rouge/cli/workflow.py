"""CLI commands for workflow execution."""

import subprocess
from typing import Optional

import typer

from rouge.adw.adw import execute_adw_workflow
from rouge.core.utils import make_adw_id
from rouge.core.workflow.shared import get_repo_path

app = typer.Typer(help="Workflow execution commands")


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
def run(
    issue_id: int,
    adw_id: Optional[str] = typer.Option(
        None, help="Workflow ID (auto-generated if not provided)", show_default=True
    ),
) -> None:
    """Execute the adw_plan_build workflow for an issue.

    Args:
        issue_id: The issue ID to process
        adw_id: Optional workflow ID for tracking (auto-generated if not provided)

    Example:
        rouge workflow run 123
        rouge workflow run 123 --adw-id abc12345
    """
    try:
        # Validate issue_id
        if issue_id <= 0:
            typer.echo(f"Error: issue_id must be greater than 0, got {issue_id}", err=True)
            raise typer.Exit(1)

        # Normalize and validate ADW ID if provided
        if adw_id is not None:
            adw_id = adw_id.strip()
            if not adw_id:
                typer.echo("Error: adw_id cannot be empty or whitespace", err=True)
                raise typer.Exit(1)

        # Generate ADW ID if not provided
        if not adw_id:
            adw_id = make_adw_id()

        # Execute workflow
        success, _workflow_id = execute_adw_workflow(issue_id, adw_id)

        if not success:
            raise typer.Exit(1)

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Unexpected error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def patch(
    issue_id: int,
    adw_id: Optional[str] = typer.Option(
        None, help="Workflow ID (auto-generated if not provided)", show_default=True
    ),
) -> None:
    """Execute the patch workflow for an issue.

    Args:
        issue_id: The issue ID to process
        adw_id: Optional workflow ID for tracking (auto-generated if not provided)

    Example:
        rouge workflow patch 123
        rouge workflow patch 123 --adw-id abc12345
    """
    try:
        # Validate issue_id
        if issue_id <= 0:
            typer.echo(f"Error: issue_id must be greater than 0, got {issue_id}", err=True)
            raise typer.Exit(1)

        # Normalize and validate ADW ID if provided
        if adw_id is not None:
            adw_id = adw_id.strip()
            if not adw_id:
                typer.echo("Error: adw_id cannot be empty or whitespace", err=True)
                raise typer.Exit(1)

        # Generate ADW ID if not provided
        if not adw_id:
            adw_id = make_adw_id()

        # Execute workflow
        success, _workflow_id = execute_adw_workflow(issue_id, adw_id, workflow_type="patch")

        if not success:
            raise typer.Exit(1)

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Unexpected error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def codereview(
    issue_id: int = typer.Argument(..., help="The issue ID to process"),
    adw_id: Optional[str] = typer.Option(
        None, help="Workflow ID (auto-generated if not provided)", show_default=True
    ),
) -> None:
    """Execute the code review workflow for an issue.

    The base commit is derived from the issue description by the workflow.

    Args:
        issue_id: The issue ID to process
        adw_id: Optional workflow ID for tracking (auto-generated if not provided)

    Example:
        rouge workflow codereview 123
        rouge workflow codereview 123 --adw-id abc12345
    """
    try:
        # Validate issue_id
        if issue_id <= 0:
            typer.echo(f"Error: issue_id must be greater than 0, got {issue_id}", err=True)
            raise typer.Exit(1)

        # Normalize and validate ADW ID if provided
        if adw_id is not None:
            adw_id = adw_id.strip()
            if not adw_id:
                typer.echo("Error: adw_id cannot be empty or whitespace", err=True)
                raise typer.Exit(1)

        # Generate ADW ID if not provided
        if not adw_id:
            adw_id = make_adw_id()

        # Execute workflow
        success, _workflow_id = execute_adw_workflow(issue_id, adw_id, workflow_type="codereview")

        if not success:
            raise typer.Exit(1)

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Unexpected error: {e}", err=True)
        raise typer.Exit(1)
