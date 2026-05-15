"""CLI interface for Rouge ADW."""

from pathlib import Path
from typing import Optional

import typer

from rouge.core.database import init_db_env

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

from rouge.adw.adw import execute_adw_workflow  # noqa: E402
from rouge.cli.utils import prepare_adw_id, validate_issue_id  # noqa: E402
from rouge.core.utils import get_logger, setup_logger  # noqa: E402

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
        "full",
        "--workflow-type",
        "-w",
        help="Workflow type to execute (e.g. full, patch, thin, direct)",
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

    # Normalize adw_id and workflow_type
    workflow_id = prepare_adw_id(adw_id)

    workflow_type = workflow_type.strip()
    if not workflow_type:
        typer.echo("Error: workflow_type cannot be empty", err=True)
        raise typer.Exit(1)

    # Setup logger before workflow execution
    setup_logger(workflow_id)

    try:
        success, workflow_id = execute_adw_workflow(
            workflow_id, issue_id, workflow_type=workflow_type
        )
    except typer.Exit:
        raise
    except Exception as exc:
        get_logger(workflow_id).exception("ADW workflow failed with unexpected error")
        typer.echo(f"Error executing ADW workflow: {exc}", err=True)
        raise typer.Exit(1)

    if success:
        typer.echo(f"Workflow {workflow_id} completed successfully")
    else:
        typer.echo(f"Workflow {workflow_id} failed", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
