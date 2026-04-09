"""CLI commands for merge request listing."""

import json
from enum import Enum
from typing import Optional

import typer

from rouge.core.database import list_mr_comments

app = typer.Typer(
    help=(
        "List Rouge merge requests. In Rouge, MR is a generic term for GitHub"
        " pull requests and GitLab merge requests."
    )
)


class OutputFormat(str, Enum):
    """Output formats for list command."""

    TABLE = "table"
    JSON = "json"


def validate_platform_option(value: Optional[str]) -> Optional[str]:
    """Validate the --platform option.

    Accepts ``None``, ``"github"``, ``"gitlab"``, or ``"all"`` (treated as
    ``None`` so that no platform filter is applied).

    Args:
        value: The platform string to validate (or None)

    Returns:
        Validated platform string or None

    Raises:
        typer.BadParameter: If the value is not a recognised platform
    """
    if value is None:
        return None

    normalized = value.strip().lower()
    if normalized == "all":
        return None
    if normalized in {"github", "gitlab"}:
        return normalized

    raise typer.BadParameter(f"Must be 'github', 'gitlab', 'all', or omitted. Got: {value!r}")


def validate_positive_int(value: Optional[int], field_name: str) -> None:
    """Validate that an integer value is positive (> 0).

    Args:
        value: The integer value to validate (or None)
        field_name: Name of the field for error messages

    Raises:
        typer.BadParameter: If the value is not positive (must be > 0)
    """
    if value is None:
        return

    if value <= 0:
        raise typer.BadParameter(f"{field_name} must be greater than 0")


@app.command("list")
def list_command(
    issue_id: Optional[int] = typer.Option(
        None, "--issue-id", help="Filter by issue ID", show_default=True
    ),
    platform: Optional[str] = typer.Option(
        None,
        "--platform",
        help="Filter by platform (github, gitlab, or all)",
        show_default=True,
        callback=validate_platform_option,
    ),
    limit: int = typer.Option(
        10, "--limit", help="Maximum number of comment rows to return", show_default=True
    ),
    offset: int = typer.Option(
        0, "--offset", help="Number of comment rows to skip", show_default=True
    ),
    format: OutputFormat = typer.Option(
        OutputFormat.TABLE,
        "--format",
        "-f",
        help="Output format: 'table' for human-readable, 'json' for machine-readable",
        show_default=True,
    ),
) -> None:
    """List merge requests created by Rouge workflows.

    In Rouge, MR is a generic term covering both GitHub pull requests and
    GitLab merge requests.
    Results are derived from artifact comments in the Rouge database.
    """
    validate_positive_int(issue_id, "--issue-id")
    if limit < 1:
        typer.echo("Error: --limit must be at least 1", err=True)
        raise typer.Exit(1)
    if offset < 0:
        typer.echo("Error: --offset must be at least 0", err=True)
        raise typer.Exit(1)

    try:
        results = list_mr_comments(
            issue_id=issue_id,
            platform=platform,
            limit=limit,
            offset=offset,
        )

        if not results:
            typer.echo("No merge requests found.")
            return

        if format == OutputFormat.JSON:
            typer.echo(json.dumps(results, indent=2))
        else:
            rows = []
            for row in results:
                rows.append(
                    {
                        "Issue": str(row.get("issue_id", "")),
                        "Platform": row.get("platform") or "(none)",
                        "Repo": row.get("repo") or "(none)",
                        "Number": str(row.get("number", "")),
                        "URL": row.get("url") or "(none)",
                        "Adopted": str(row.get("adopted", False)),
                    }
                )

            columns = ["Issue", "Platform", "Repo", "Number", "URL", "Adopted"]
            widths = {
                column: max(len(column), *(len(row[column]) for row in rows)) for column in columns
            }

            def format_row(row: dict[str, str]) -> str:
                return "  ".join(f"{row[column]:<{widths[column]}}" for column in columns).rstrip()

            header = format_row({column: column for column in columns})
            typer.echo(header)
            typer.echo("-" * len(header))
            for row in rows:
                typer.echo(format_row(row))

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Unexpected error: {e}", err=True)
        raise typer.Exit(1)
