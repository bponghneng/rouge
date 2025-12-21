"""CLI commands for workflow step management."""

import typer

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
    adw_id: str = typer.Option(..., "--adw-id", "-a", help="Workflow ID for artifacts"),
) -> None:
    """Run a single workflow step using artifacts for dependencies.

    This command runs a single step independently by loading any required
    dependencies from previously stored artifacts in the workflow directory.

    Example:
        rouge step run "Classifying issue" --issue-id 123 --adw-id adw-xyz123
    """
    typer.echo(f"Running step '{step_name}' for issue {issue_id} (workflow: {adw_id})")

    pipeline = get_default_pipeline()
    runner = WorkflowRunner(pipeline, enable_artifacts=True)

    try:
        success = runner.run_single_step(step_name, issue_id, adw_id)
        if success:
            typer.echo(f"Step '{step_name}' completed successfully")
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
