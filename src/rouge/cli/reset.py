"""CLI command for resetting failed issues."""

import logging

import typer

from rouge.cli.utils import validate_issue_id
from rouge.core.database import fetch_issue, update_issue


def reset(
    issue_id: int = typer.Argument(..., help="The issue ID to reset"),
) -> None:
    """Reset a failed or pending issue back to pending status.

    This command resets a failed or pending issue back to pending status, clears the
    assigned_to field, and optionally clears the branch field depending on
    the issue type.

    Issue type behavior:
    - full: Clears branch field (set to None)
    - patch: Preserves existing branch field

    The issue must be in 'failed' or 'pending' status to be reset.

    Args:
        issue_id: The ID of the issue to reset

    Examples:
        rouge issue reset 123
    """
    validate_issue_id(issue_id)
    try:
        # Fetch the current issue
        issue = fetch_issue(issue_id)

        # Validate issue status is 'failed' or 'pending'
        if issue.status not in ("failed", "pending"):
            typer.echo(
                f"Error: Issue {issue_id} has status '{issue.status}', "
                "can only reset 'failed' or 'pending' issues",
                err=True,
            )
            raise typer.Exit(1)

        # Call update_issue with explicit parameters
        # For full type, clear branch; for patch type, preserve existing branch
        if issue.type == "full":
            updated_issue = update_issue(issue_id, assigned_to=None, status="pending", branch=None)
        else:
            # For patch type, preserve existing branch
            updated_issue = update_issue(issue_id, assigned_to=None, status="pending")

        # Output issue ID on success for scripting compatibility
        typer.echo(f"{updated_issue.id}")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        logging.exception("Unexpected error resetting issue %s", issue_id)
        typer.echo(f"Unexpected error: {e}", err=True)
        raise typer.Exit(1)
