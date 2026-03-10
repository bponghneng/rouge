"""Command-line interface for the Rouge Worker."""

import os
import sys
from typing import Optional

import typer

from .config import WorkerConfig
from .worker import IssueWorker
from .worker_artifact import read_worker_artifact, write_worker_artifact


# Compute defaults from environment
def _get_default_timeout() -> int:
    default_timeout = 3600
    timeout_env = os.environ.get("ROUGE_WORKFLOW_TIMEOUT_SECONDS")
    if timeout_env:
        try:
            parsed = int(timeout_env)
            if parsed > 0:
                return parsed
            else:
                print(
                    f"Warning: ROUGE_WORKFLOW_TIMEOUT_SECONDS must be positive, "
                    f"got '{timeout_env}', using default {default_timeout} seconds",
                    file=sys.stderr,
                )
        except ValueError:
            print(
                f"Warning: Invalid value for ROUGE_WORKFLOW_TIMEOUT_SECONDS "
                f"'{timeout_env}', using default {default_timeout} seconds",
                file=sys.stderr,
            )
    return default_timeout


def _get_default_log_level() -> str:
    level = os.environ.get("ROUGE_LOG_LEVEL", "INFO").upper()
    if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        return "INFO"
    return level


app = typer.Typer(invoke_without_command=True)


@app.callback()
def main(
    ctx: typer.Context,
    worker_id: Optional[str] = typer.Option(
        None,
        "--worker-id",
        help="Unique identifier for this worker instance (e.g., 'alleycat-1')",
    ),
    poll_interval: int = typer.Option(
        10,
        "--poll-interval",
        help="Number of seconds to wait between polls (default: 10)",
        show_default=True,
    ),
    log_level: Optional[str] = typer.Option(
        None,
        "--log-level",
        help="Logging level",
    ),
    workflow_timeout: Optional[int] = typer.Option(
        None,
        "--workflow-timeout",
        help="Timeout in seconds for workflow execution",
    ),
) -> None:
    """Rouge Issue Worker Daemon."""
    if ctx.invoked_subcommand is not None:
        return
    worker_id = worker_id.strip() if worker_id else worker_id
    if not worker_id:
        typer.echo("Error: --worker-id is required", err=True)
        raise typer.Exit(1)
    resolved_log_level = (
        log_level.strip().upper() if log_level is not None else _get_default_log_level()
    )
    valid_log_levels = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
    if resolved_log_level not in valid_log_levels:
        typer.echo(
            f"Error: --log-level must be one of {list(valid_log_levels)}, got '{log_level}'",
            err=True,
        )
        raise typer.Exit(1)
    resolved_timeout = workflow_timeout if workflow_timeout is not None else _get_default_timeout()
    config = WorkerConfig(
        worker_id=worker_id,
        poll_interval=poll_interval,
        log_level=resolved_log_level,
        workflow_timeout=resolved_timeout,
    )
    IssueWorker(config).run()


@app.command("reset")
def reset_worker(
    worker_id: str = typer.Argument(..., help="Worker ID to reset"),
) -> None:
    """Reset a failed worker back to ready state."""
    worker_id = worker_id.strip()
    if not worker_id:
        typer.echo("Error: worker-id cannot be empty", err=True)
        raise typer.Exit(1)
    artifact = read_worker_artifact(worker_id)
    if artifact is None:
        typer.echo(f"Error: No artifact found for worker '{worker_id}'", err=True)
        raise typer.Exit(1)
    if artifact.state != "failed":
        typer.echo(
            f"Error: Worker '{worker_id}' is in state '{artifact.state}', "
            f"can only reset 'failed' workers",
            err=True,
        )
        raise typer.Exit(1)
    artifact.state = "ready"
    artifact.current_issue_id = None
    artifact.current_adw_id = None
    artifact.refresh_timestamp()
    write_worker_artifact(artifact)
    typer.echo(f"Worker '{worker_id}' reset to ready.")


def main_entry() -> None:
    """Entry point for the rouge-worker CLI."""
    app()
