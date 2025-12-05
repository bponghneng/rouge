"""CLI interface for CAPE ADW."""

import sys
from typing import Optional

import typer

from cape.adw.adw import execute_adw_workflow

app = typer.Typer(
    help="CAPE ADW - Agent Development Workflow",
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
) -> None:
    """
    CAPE ADW - Agent Development Workflow runner.
    """
    if issue_id is None:
        typer.echo("Usage: cape-adw <issue_id> [--adw-id <workflow-id>]")
        typer.echo("Use 'cape-adw --help' for more information")
        raise typer.Exit()

    try:
        success, workflow_id = execute_adw_workflow(issue_id, adw_id)
        if success:
            typer.echo(f"Workflow {workflow_id} completed successfully")
        else:
            typer.echo(f"Workflow {workflow_id} failed", err=True)
            sys.exit(1)
    except Exception as exc:
        typer.echo(f"Error executing ADW workflow: {exc}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    app()
