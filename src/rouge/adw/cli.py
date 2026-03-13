"""CLI interface for Rouge ADW."""

import re
import sys
from typing import Optional

import typer

from rouge.adw.adw import execute_adw_workflow
from rouge.cli.utils import validate_issue_id
from rouge.core.utils import get_logger, make_adw_id, setup_logger
from rouge.core.workflow.workflow_registry import get_workflow_registry

app = typer.Typer(
    help="Rouge ADW - Agent Development Workflow",
    invoke_without_command=True,
)


@app.callback()
def main(
    issue_id: Optional[int] = typer.Argument(
        None,
        help="The ID of the issue to process",
    ),
    adw_id: Optional[str] = typer.Option(
        None,
        "--adw-id",
        help="Optional workflow identifier (auto-generated if omitted)",
    ),
    workflow_type: str = typer.Option(
        "main",
        "--workflow-type",
        "-w",
        help="Workflow type to execute (e.g. main, patch, codereview).",
        show_default=True,
    ),
) -> None:
    """
    Rouge ADW - Agent Development Workflow runner.
    """
    if issue_id is None:
        typer.echo("Usage: rouge-adw <issue_id> [--adw-id <workflow-id>] [--workflow-type <type>]")
        typer.echo("Use 'rouge-adw --help' for more information")
        raise typer.Exit()

    # Validate issue_id is a positive integer
    validate_issue_id(issue_id)

    # Strip and validate adw_id format if provided
    if adw_id:
        adw_id = adw_id.strip()
        if not adw_id:
            typer.echo("Error: adw_id cannot be empty", err=True)
            raise typer.Exit(1)
        if not re.match(r"^[a-z0-9-]+$", adw_id):
            typer.echo(
                "Error: adw_id must contain only lowercase letters, numbers, and hyphens",
                err=True,
            )
            raise typer.Exit(1)

    # Strip and validate workflow_type is a known type
    workflow_type = workflow_type.strip()
    if not workflow_type:
        typer.echo("Error: workflow_type cannot be empty", err=True)
        raise typer.Exit(1)

    registry = get_workflow_registry()
    if not registry.is_registered(workflow_type):
        valid_workflow_types = registry.list_types()
        typer.echo(
            f"Error: workflow_type must be one of {', '.join(valid_workflow_types)}",
            err=True,
        )
        raise typer.Exit(1)

    # Generate adw_id if not provided
    workflow_id = adw_id or make_adw_id()

    # Setup logger before workflow execution
    setup_logger(workflow_id)

    try:
        success, workflow_id = execute_adw_workflow(
            workflow_id, issue_id, workflow_type=workflow_type
        )
        if success:
            typer.echo(f"Workflow {workflow_id} completed successfully")
        else:
            typer.echo(f"Workflow {workflow_id} failed", err=True)
            sys.exit(1)
    except Exception as exc:
        get_logger(workflow_id).exception("ADW workflow failed with unexpected error")
        typer.echo(f"Error executing ADW workflow: {exc}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    app()
