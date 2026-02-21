"""Shared CLI utilities."""

import typer


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
