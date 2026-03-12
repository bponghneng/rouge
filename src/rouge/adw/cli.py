"""CLI interface for Rouge ADW."""

import sys
from typing import Optional

import typer

from rouge.adw.adw import execute_adw_workflow
from rouge.core.utils import get_logger, make_adw_id, setup_logger

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
    ),
) -> None:
    """
    Rouge ADW - Agent Development Workflow runner.
    """
    if issue_id is None:
        typer.echo("Usage: rouge-adw <issue_id> [--adw-id <workflow-id>] [--workflow-type <type>]")
        typer.echo("Use 'rouge-adw --help' for more information")
        raise typer.Exit()

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
