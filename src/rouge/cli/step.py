"""CLI commands for workflow step management."""

import os
from pathlib import Path
from typing import Optional

import typer

from rouge.core.database import init_db_env
from rouge.core.utils import make_adw_id
from rouge.core.workflow.pipeline import WorkflowRunner, get_default_pipeline
from rouge.core.workflow.step_registry import get_step_registry

app = typer.Typer(help="Workflow step management commands")


@app.command("list")
def list_steps() -> None:
    """List all registered workflow steps with their dependencies."""
    registry = get_step_registry()
    steps = registry.list_step_details()

    if not steps:
        typer.echo("No steps registered")
        return

    typer.echo("Registered workflow steps:\n")
    for step in steps:
        name = step["name"]
        deps = step["dependencies"]
        outputs = step["outputs"]
        is_critical = step["is_critical"]
        description = step.get("description", "")

        # Format criticality indicator
        crit_indicator = "[critical]" if is_critical else "[best-effort]"

        typer.echo(f"  {name} {crit_indicator}")
        if description:
            typer.echo(f"    Description: {description}")
        if deps:
            typer.echo(f"    Dependencies: {', '.join(deps)}")
        if outputs:
            typer.echo(f"    Outputs: {', '.join(outputs)}")
        typer.echo()


@app.command("run")
def run_step(
    step_name: str = typer.Argument(..., help="Name of the step to run"),
    issue_id: int = typer.Option(..., "--issue-id", "-i", help="Issue ID to process"),
    adw_id: Optional[str] = typer.Option(
        None,
        "--adw-id",
        "-a",
        help="Workflow ID for artifacts (auto-generated for dependency-free steps)",
    ),
    working_dir: Optional[Path] = typer.Option(
        None,
        "--working-dir",
        help="Absolute directory to switch into before loading .env and running the step.",
    ),
) -> None:
    """Run a single workflow step using artifacts for dependencies.

    This command runs a single step independently by loading any required
    dependencies from previously stored artifacts in the workflow directory.

    For steps with no dependencies (e.g., 'Fetching issue from Supabase'),
    the --adw-id is optional and will be auto-generated if not provided.

    Example:
        rouge step run "Fetching issue from Supabase" --issue-id 123
        rouge step run "Classifying issue" --issue-id 123 --adw-id abc12345
    """
    if working_dir:
        target_dir = working_dir.expanduser()
        if not target_dir.is_absolute():
            typer.echo("Error: --working-dir must be an absolute path", err=True)
            raise typer.Exit(1)
        target_dir = target_dir.resolve()
        os.chdir(target_dir)
        env_file_path = target_dir / ".env"
        if env_file_path.exists():
            init_db_env(dotenv_path=env_file_path)
        else:
            parent_env_file_path = target_dir.parent / ".env"
            if parent_env_file_path.exists():
                init_db_env(dotenv_path=parent_env_file_path)
            else:
                init_db_env()

    # Query the step registry to check dependencies
    registry = get_step_registry()
    step_metadata = registry.get_step_metadata(step_name)

    if step_metadata is None:
        typer.echo(f"Error: Step '{step_name}' not found in registry", err=True)
        raise typer.Exit(1)

    has_dependencies = len(step_metadata.dependencies) > 0

    # Validate adw_id based on dependencies
    if adw_id is None:
        if has_dependencies:
            deps_list = ", ".join(step_metadata.dependencies)
            typer.echo(
                f"Error: Step '{step_name}' requires dependencies: {deps_list}. "
                "Please provide --adw-id.",
                err=True,
            )
            raise typer.Exit(1)
        # Auto-generate workflow ID for dependency-free steps
        adw_id = make_adw_id()

    typer.echo(f"Running step '{step_name}' for issue {issue_id} (workflow: {adw_id})")

    pipeline = get_default_pipeline()
    runner = WorkflowRunner(pipeline)

    try:
        success = runner.run_single_step(
            step_name, issue_id, adw_id, has_dependencies=has_dependencies
        )
        if success:
            typer.echo(f"Step '{step_name}' completed successfully")
            typer.echo(f"Workflow ID: {adw_id}")
            return
        else:
            typer.echo(f"Step '{step_name}' failed", err=True)
            raise typer.Exit(1)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command("deps")
def show_dependencies(
    step_name: str = typer.Argument(..., help="Name of the step to show dependencies for"),
) -> None:
    """Show the dependency chain for a step.

    Lists all steps that must be executed before the specified step,
    in the order they should run.

    Example:
        rouge step deps "Implementing solution"
    """
    registry = get_step_registry()

    try:
        deps = registry.resolve_dependencies(step_name)
        if not deps:
            typer.echo(f"Step '{step_name}' has no dependencies")
            return

        typer.echo(f"Dependency chain for '{step_name}':\n")
        for i, dep in enumerate(deps, 1):
            typer.echo(f"  {i}. {dep}")
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)


@app.command("validate")
def validate_registry() -> None:
    """Validate the step registry for consistency issues.

    Checks for missing artifact producers and circular dependencies.
    """
    registry = get_step_registry()
    issues = registry.validate_registry()

    if not issues:
        typer.echo("Step registry is valid - no issues found")
        return

    typer.echo("Step registry validation issues:\n", err=True)
    for issue in issues:
        typer.echo(f"  - {issue}", err=True)
    raise typer.Exit(1)
