"""CLI commands for workflow execution."""

from typing import Optional

import typer

from rouge.adw.adw import execute_adw_workflow
from rouge.cli.utils import validate_issue_id
from rouge.core.utils import get_logger, make_adw_id, setup_logger

app = typer.Typer(help="Workflow execution commands")


def _run_workflow(issue_id: int, adw_id: Optional[str], workflow_type: str) -> None:
    """Execute a workflow of the given type for the specified issue.

    Validates the issue ID, normalizes the ADW ID, sets up logging,
    and delegates to :func:`execute_adw_workflow`.

    Args:
        issue_id: The issue ID to process
        adw_id: Optional workflow ID (auto-generated if None or empty)
        workflow_type: The workflow type identifier (e.g. "main", "patch", "codereview")

    Raises:
        typer.Exit: On validation failure, execution failure, or unexpected error
    """
    try:
        validate_issue_id(issue_id)

        if adw_id is not None:
            adw_id = adw_id.strip()
            if not adw_id:
                typer.echo("Error: adw_id cannot be empty or whitespace", err=True)
                raise typer.Exit(1)

        if not adw_id:
            adw_id = make_adw_id()

        setup_logger(adw_id)

        success, _workflow_id = execute_adw_workflow(adw_id, issue_id, workflow_type=workflow_type)

        if not success:
            raise typer.Exit(1)

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        effective_adw_id = adw_id or "unknown"
        setup_logger(effective_adw_id)
        get_logger(effective_adw_id).exception("Unexpected error in workflow command")
        typer.echo(f"Unexpected error: {e}", err=True)
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
    _run_workflow(issue_id, adw_id, workflow_type="main")


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
    _run_workflow(issue_id, adw_id, workflow_type="patch")


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
    _run_workflow(issue_id, adw_id, workflow_type="codereview")
