"""CLI commands for workflow execution."""

from typing import Optional

import typer

from rouge.adw.adw import execute_adw_workflow
from rouge.cli.utils import prepare_adw_id, validate_issue_id
from rouge.core.utils import get_logger, setup_logger

app = typer.Typer(help="Workflow execution commands")


def _run_workflow(issue_id: int, adw_id: Optional[str], workflow_type: str) -> None:
    """Execute a workflow of the given type for the specified issue.

    Validates the issue ID, normalizes the ADW ID, sets up logging,
    and delegates to :func:`execute_adw_workflow`.

    Args:
        issue_id: The issue ID to process
        adw_id: Optional workflow ID (auto-generated if None or empty)
        workflow_type: The workflow type identifier (e.g. "full", "patch")

    Raises:
        typer.Exit: On validation failure, execution failure, or unexpected error
    """
    try:
        validate_issue_id(issue_id)
        adw_id = prepare_adw_id(adw_id)
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
    _run_workflow(issue_id, adw_id, workflow_type="full")


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
def thin(
    issue_id: int,
    adw_id: Optional[str] = typer.Option(
        None, help="Workflow ID (auto-generated if not provided)", show_default=True
    ),
) -> None:
    """Execute the thin workflow for a straightforward issue.

    Args:
        issue_id: The issue ID to process
        adw_id: Optional workflow ID for tracking (auto-generated if not provided)

    Example:
        rouge workflow thin 123
        rouge workflow thin 123 --adw-id abc12345
    """
    _run_workflow(issue_id, adw_id, workflow_type="thin")


@app.command()
def direct(
    issue_id: int,
    adw_id: Optional[str] = typer.Option(
        None, help="Workflow ID (auto-generated if not provided)", show_default=True
    ),
) -> None:
    """Execute the direct workflow for a straightforward issue.

    Args:
        issue_id: The issue ID to process
        adw_id: Optional workflow ID for tracking (auto-generated if not provided)

    Example:
        rouge workflow direct 123
        rouge workflow direct 123 --adw-id abc12345
    """
    _run_workflow(issue_id, adw_id, workflow_type="direct")
