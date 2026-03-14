"""Shared CLI utilities."""

import re
from typing import Optional

import typer

from rouge.core.utils import make_adw_id


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


def prepare_adw_id(adw_id: Optional[str]) -> str:
    """Normalize and validate an ADW ID, generating one if not provided.

    Strips whitespace, validates format (lowercase letters, numbers, hyphens),
    and auto-generates an ID if the argument is None or empty.

    Args:
        adw_id: Optional workflow ID provided by the caller

    Returns:
        A valid, normalized workflow ID

    Raises:
        typer.Exit: If adw_id is non-empty but has an invalid format
    """
    if adw_id is not None:
        adw_id = adw_id.strip()
        if not adw_id:
            typer.echo("Error: adw_id cannot be empty or whitespace", err=True)
            raise typer.Exit(1)
        if not re.match(r"^[a-z0-9-]+$", adw_id):
            typer.echo(
                "Error: adw_id must contain only lowercase letters, numbers, and hyphens",
                err=True,
            )
            raise typer.Exit(1)
        return adw_id
    return make_adw_id()
