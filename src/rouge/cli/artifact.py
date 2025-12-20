"""CLI commands for workflow artifact management."""

import typer

from rouge.core.workflow.artifacts import ARTIFACT_MODELS, ArtifactStore

app = typer.Typer(help="Workflow artifact management commands")


@app.command("list")
def list_artifacts(
    adw_id: str = typer.Argument(..., help="Workflow ID to list artifacts for"),
) -> None:
    """List all artifacts for a workflow.

    Shows all artifacts stored for the specified workflow ID,
    including their types and file sizes.

    Example:
        rouge artifact list adw-xyz123
    """
    store = ArtifactStore(adw_id)

    artifacts = store.list_artifacts()

    if not artifacts:
        typer.echo(f"No artifacts found for workflow '{adw_id}'")
        typer.echo(f"Workflow directory: {store.workflow_dir}")
        return

    typer.echo(f"Artifacts for workflow '{adw_id}':\n")
    for artifact_type in artifacts:
        info = store.get_artifact_info(artifact_type)
        if info:
            size_kb = info["size_bytes"] / 1024
            modified = info["modified_at"].strftime("%Y-%m-%d %H:%M:%S")
            typer.echo(f"  {artifact_type}")
            typer.echo(f"    Size: {size_kb:.2f} KB")
            typer.echo(f"    Modified: {modified}")
        else:
            typer.echo(f"  {artifact_type}")
        typer.echo()

    typer.echo(f"Total: {len(artifacts)} artifact(s)")
    typer.echo(f"Directory: {store.workflow_dir}")


@app.command("show")
def show_artifact(
    adw_id: str = typer.Argument(..., help="Workflow ID"),
    artifact_type: str = typer.Argument(..., help="Artifact type to display"),
    raw: bool = typer.Option(False, "--raw", "-r", help="Output raw JSON without formatting"),
) -> None:
    """Show the contents of a specific artifact.

    Displays the JSON content of an artifact stored in the workflow directory.

    Example:
        rouge artifact show adw-xyz123 classification
        rouge artifact show adw-xyz123 issue --raw
    """
    # Validate artifact type
    if artifact_type not in ARTIFACT_MODELS:
        valid_types = ", ".join(sorted(ARTIFACT_MODELS.keys()))
        typer.echo(f"Error: Invalid artifact type '{artifact_type}'", err=True)
        typer.echo(f"Valid types: {valid_types}", err=True)
        raise typer.Exit(1)

    store = ArtifactStore(adw_id)

    if not store.artifact_exists(artifact_type):  # type: ignore
        typer.echo(f"Artifact '{artifact_type}' not found for workflow '{adw_id}'", err=True)
        raise typer.Exit(1)

    try:
        artifact = store.read_artifact(artifact_type)  # type: ignore
        json_data = artifact.model_dump_json(indent=None if raw else 2)

        if raw:
            typer.echo(json_data)
        else:
            typer.echo(f"Artifact: {artifact_type}")
            typer.echo(f"Workflow: {adw_id}")
            typer.echo("-" * 40)
            typer.echo(json_data)
    except Exception as e:
        typer.echo(f"Error reading artifact: {e}", err=True)
        raise typer.Exit(1)


@app.command("delete")
def delete_artifact(
    adw_id: str = typer.Argument(..., help="Workflow ID"),
    artifact_type: str = typer.Argument(..., help="Artifact type to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
) -> None:
    """Delete a specific artifact from a workflow.

    Removes the artifact file from the workflow directory.

    Example:
        rouge artifact delete adw-xyz123 classification
        rouge artifact delete adw-xyz123 issue --force
    """
    # Validate artifact type
    if artifact_type not in ARTIFACT_MODELS:
        valid_types = ", ".join(sorted(ARTIFACT_MODELS.keys()))
        typer.echo(f"Error: Invalid artifact type '{artifact_type}'", err=True)
        typer.echo(f"Valid types: {valid_types}", err=True)
        raise typer.Exit(1)

    store = ArtifactStore(adw_id)

    if not store.artifact_exists(artifact_type):  # type: ignore
        typer.echo(f"Artifact '{artifact_type}' not found for workflow '{adw_id}'", err=True)
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f"Delete artifact '{artifact_type}' from workflow '{adw_id}'?")
        if not confirm:
            typer.echo("Cancelled")
            raise typer.Exit(0)

    deleted = store.delete_artifact(artifact_type)  # type: ignore
    if deleted:
        typer.echo(f"Deleted artifact '{artifact_type}' from workflow '{adw_id}'")
    else:
        typer.echo(f"Failed to delete artifact '{artifact_type}'", err=True)
        raise typer.Exit(1)


@app.command("types")
def list_types() -> None:
    """List all available artifact types.

    Shows all valid artifact type identifiers that can be stored
    and retrieved by the workflow system.
    """
    typer.echo("Available artifact types:\n")
    for artifact_type in sorted(ARTIFACT_MODELS.keys()):
        model_class = ARTIFACT_MODELS[artifact_type]
        typer.echo(f"  {artifact_type}")
        # Get docstring if available
        if model_class.__doc__:
            doc = model_class.__doc__.split("\n")[0].strip()
            if doc:
                typer.echo(f"    {doc}")
        typer.echo()

    typer.echo(f"Total: {len(ARTIFACT_MODELS)} artifact type(s)")


@app.command("path")
def show_path(
    adw_id: str = typer.Argument(..., help="Workflow ID"),
) -> None:
    """Show the filesystem path for a workflow's artifacts.

    Displays the directory path where artifacts are stored for the workflow.

    Example:
        rouge artifact path adw-xyz123
    """
    store = ArtifactStore(adw_id)
    typer.echo(str(store.workflow_dir))
