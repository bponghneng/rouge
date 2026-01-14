"""CLI interface for Rouge ADW."""

import sys
from typing import Optional

import typer

from rouge.adw.adw import execute_adw_workflow

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
    patch_mode: bool = typer.Option(
        False,
        "--patch-mode",
        help="Use patch pipeline instead of default pipeline",
    ),
) -> None:
    """
    Rouge ADW - Agent Development Workflow runner.
    """
    if issue_id is None:
        typer.echo("Usage: rouge-adw <issue_id> [--adw-id <workflow-id>] [--patch-mode]")
        typer.echo("Use 'rouge-adw --help' for more information")
        raise typer.Exit()

    try:
        success, workflow_id = execute_adw_workflow(issue_id, adw_id, patch_mode)
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
