"""CLI commands for database migration management.

This module wraps yoyo-migrations commands, providing a unified CLI interface
that automatically handles DATABASE_URL configuration from environment variables.
"""

import os
import subprocess
from typing import Optional

import typer
from dotenv import load_dotenv

app = typer.Typer(help="Database migration commands (wraps yoyo-migrations)")


def get_database_url() -> str:
    """Get DATABASE_URL from environment, constructing from SUPABASE_URL if needed.

    The function looks for DATABASE_URL or SUPABASE_URL in the environment.
    SUPABASE_URL is expected to be in PostgreSQL connection string format.

    Returns:
        str: PostgreSQL connection string for database operations.

    Raises:
        typer.Exit: If neither DATABASE_URL nor SUPABASE_URL is available.
    """
    load_dotenv()

    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return database_url

    supabase_url = os.environ.get("SUPABASE_URL")
    if supabase_url:
        return supabase_url

    typer.echo(
        "Error: DATABASE_URL or SUPABASE_URL environment variable is required.\n"
        "Set it in your environment or .env file.",
        err=True,
    )
    raise typer.Exit(1)


def _run_yoyo_command(args: list[str], database_url: Optional[str] = None) -> None:
    """Run a yoyo command with the given arguments.

    Args:
        args: Command-line arguments to pass to yoyo.
        database_url: Optional database URL. If not provided, will be retrieved
                      from environment.

    Raises:
        typer.Exit: If the yoyo command fails.
    """
    if database_url is None:
        database_url = get_database_url()

    # Build the full command
    cmd = ["uv", "run", "yoyo"] + args + ["--database", database_url]

    try:
        result = subprocess.run(
            cmd,
            check=False,
            text=True,
        )
        if result.returncode != 0:
            raise typer.Exit(result.returncode)
    except FileNotFoundError:
        typer.echo("Error: 'uv' command not found. Please ensure uv is installed.", err=True)
        raise typer.Exit(1)


@app.command("migrate")
def migrate() -> None:
    """Apply all pending database migrations.

    Applies any unapplied migrations from the migrations/ directory.
    Uses DATABASE_URL from environment or .env file.

    Example:
        rouge db migrate
    """
    typer.echo("Applying database migrations...")
    _run_yoyo_command(["apply", "--batch"])
    typer.echo("Migrations applied successfully.")


@app.command("rollback")
def rollback(
    count: Optional[int] = typer.Option(
        None,
        "--count",
        "-c",
        help="Number of migrations to rollback (default: 1)",
    ),
) -> None:
    """Rollback database migrations.

    Rolls back the most recently applied migration(s).
    Uses DATABASE_URL from environment or .env file.

    Example:
        rouge db rollback
        rouge db rollback --count 2
    """
    if count is not None and count < 1:
        typer.echo("Error: --count must be at least 1", err=True)
        raise typer.Exit(1)

    args = ["rollback", "--batch"]
    if count is not None:
        args.extend(["--revision", str(count)])

    msg = f"Rolling back {count} migration(s)..." if count else "Rolling back last migration..."
    typer.echo(msg)
    _run_yoyo_command(args)
    typer.echo("Rollback completed successfully.")


@app.command("status")
def status() -> None:
    """Show database migration status.

    Lists all migrations and their applied/unapplied status.
    Uses DATABASE_URL from environment or .env file.

    Example:
        rouge db status
    """
    _run_yoyo_command(["list"])


@app.command("new")
def new(
    name: str = typer.Argument(..., help="Name for the new migration"),
) -> None:
    """Create a new migration file.

    Creates a new migration file in the migrations/ directory.
    This command does not require DATABASE_URL.

    Example:
        rouge db new add_users_table
    """
    typer.echo(f"Creating new migration: {name}")

    cmd = ["uv", "run", "yoyo", "new", "--batch", "--message", name]

    try:
        result = subprocess.run(
            cmd,
            check=False,
            text=True,
        )
        if result.returncode != 0:
            raise typer.Exit(result.returncode)
        typer.echo("Migration file created successfully.")
    except FileNotFoundError:
        typer.echo("Error: 'uv' command not found. Please ensure uv is installed.", err=True)
        raise typer.Exit(1)
