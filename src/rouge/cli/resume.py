"""CLI command for resuming failed workflows."""

import logging
from typing import Optional

import typer

from rouge.adw.adw import execute_adw_workflow
from rouge.cli.utils import validate_issue_id
from rouge.core.database import fetch_issue, update_issue
from rouge.core.paths import RougePaths
from rouge.core.workflow.artifacts import ArtifactStore, WorkflowStateArtifact
from rouge.worker.worker_artifact import (
    read_worker_artifact,
    transition_worker_artifact,
)

logger = logging.getLogger(__name__)


def resume(
    issue_id: int = typer.Argument(..., help="The issue ID to resume"),
    resume_from: Optional[str] = typer.Option(
        None,
        "--resume-from",
        help="Step name to resume from, overrides failed_step in workflow-state artifact",
    ),
) -> None:
    """Resume a failed workflow from the last completed step.

    This command resumes a failed issue workflow by:
    1. Validating the issue exists, has an adw_id set, and status=failed
    2. Loading the workflow state artifact to find the failed step
    3. Resetting the issue status from failed to started
    4. Resuming workflow execution from the failed step
    5. Updating any associated worker artifacts back to ready state

    The operator is responsible for ensuring the git workspace is in the
    correct state before resuming. Artifacts are filesystem-local, so
    resume only works on the same host where the workflow failed.

    Args:
        issue_id: The ID of the issue to resume

    Examples:
        rouge resume 123
    """
    validate_issue_id(issue_id)
    try:
        # Fetch the current issue
        issue = fetch_issue(issue_id)

        # Validate issue has adw_id set
        if not issue.adw_id:
            typer.echo(
                f"Error: Issue {issue_id} has no adw_id set, " "cannot resume without workflow ID",
                err=True,
            )
            raise typer.Exit(1)

        # Validate issue status is 'failed'
        if issue.status != "failed":
            typer.echo(
                f"Error: Issue {issue_id} has status '{issue.status}', "
                "can only resume 'failed' issues",
                err=True,
            )
            raise typer.Exit(1)

        # Load workflow state artifact
        store = ArtifactStore(issue.adw_id)
        if not store.artifact_exists("workflow-state"):
            typer.echo(
                f"Error: Workflow state artifact not found for adw_id '{issue.adw_id}' "
                f"at {store.workflow_dir / 'workflow-state.json'}",
                err=True,
            )
            raise typer.Exit(1)

        try:
            workflow_state = store.read_artifact("workflow-state", WorkflowStateArtifact)
        except (FileNotFoundError, ValueError) as e:
            typer.echo(
                f"Error: Failed to load workflow state artifact: {e}",
                err=True,
            )
            raise typer.Exit(1)

        # Extract resume_from_step and pipeline_type from artifact
        if resume_from is not None:
            resume_from_step = resume_from
        else:
            if not workflow_state.failed_step:
                typer.echo(
                    "Error: Workflow state artifact has no failed_step set, "
                    "cannot determine resume point",
                    err=True,
                )
                raise typer.Exit(1)
            resume_from_step = workflow_state.failed_step

        pipeline_type = workflow_state.pipeline_type or "main"

        # Execute workflow with resume parameters
        try:
            # Reset issue status from 'failed' to 'started'
            update_issue(issue_id, status="started")
            logger.info("Reset issue %s status from 'failed' to 'started'", issue_id)

            success, workflow_id = execute_adw_workflow(
                issue_id,
                adw_id=issue.adw_id,
                resume_from=resume_from_step,
                workflow_type=pipeline_type,
            )
        except Exception as e:
            update_issue(issue_id, status="failed")
            logger.error("Workflow execution failed during resume: %s", e)
            typer.echo(
                f"Error: Workflow execution failed during resume: {e}",
                err=True,
            )
            raise typer.Exit(1)

        if not success:
            update_issue(issue_id, status="failed")
            typer.echo(
                "Error: Workflow execution failed during resume",
                err=True,
            )
            raise typer.Exit(1)

        # Scan for worker artifacts with matching current_issue_id
        # and update to state=ready
        try:
            workers_dir = RougePaths.get_base_dir() / "workers"
            if workers_dir.exists():
                updated_workers = []
                for worker_path in workers_dir.iterdir():
                    if not worker_path.is_dir():
                        continue

                    worker_id = worker_path.name
                    worker_artifact = read_worker_artifact(worker_id)

                    if worker_artifact and worker_artifact.current_issue_id == issue_id:
                        # Update worker to ready state
                        transition_worker_artifact(worker_artifact, "ready", clear_issue=True)
                        updated_workers.append(worker_id)
                        logger.info("Updated worker %s to ready state", worker_id)

                if updated_workers:
                    logger.info("Updated %s worker(s) to ready state", len(updated_workers))
                else:
                    logger.info("No workers found with current_issue_id=%s", issue_id)
        except OSError as e:
            logger.warning(
                "Failed to scan/update worker artifacts for issue_id=%s: %s",
                issue_id,
                e,
            )

        # Output workflow ID on success for scripting compatibility
        typer.echo(f"{workflow_id}")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Unexpected error: {e}", err=True)
        raise typer.Exit(1)
