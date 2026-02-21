"""CLI command for resetting failed issues."""

import typer

from rouge.core.database import fetch_issue, update_issue


def validate_issue_id(issue_id: int) -> None:
    """Validate that issue_id is a positive integer.

    Args:
        issue_id: The issue ID to validate

    Raises:
        typer.Exit: If issue_id is not positive (<=0)
    """
    if issue_id <= 0:
        typer.echo(f"Error: issue_id must be greater than 0, got {issue_id}", err=True)
        raise typer.Exit(1)


def reset(
    issue_id: int = typer.Argument(..., help="The issue ID to reset"),
) -> None:
    """Reset a failed issue back to pending status.

    This command resets a failed issue back to pending status, clears the
    assigned_to field, and optionally clears the branch field depending on
    the issue type.

    Issue type behavior:
    - main/codereview: Clears branch field (set to None)
    - patch: Preserves existing branch field

    The issue must be in 'failed' status to be reset.

    Args:
        issue_id: The ID of the issue to reset

    Examples:
        rouge reset 123
    """
    validate_issue_id(issue_id)
    try:
        # Fetch the current issue
        issue = fetch_issue(issue_id)

        # Validate issue status is 'failed'
        if issue.status != "failed":
            typer.echo(
                f"Error: Issue {issue_id} has status '{issue.status}', "
                "can only reset 'failed' issues",
                err=True,
            )
            raise typer.Exit(1)

        # Call update_issue with explicit parameters
        # For main and codereview types, clear branch
        if issue.type in ("main", "codereview"):
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
        typer.echo(f"Unexpected error: {e}", err=True)
        raise typer.Exit(1)
