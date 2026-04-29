"""CLI commands for comment management."""

import json
from enum import Enum
from typing import Optional

import typer

from rouge.core.database import fetch_comment, list_comments
from rouge.core.models import Comment

app = typer.Typer(help="Comment management commands")


class OutputFormat(str, Enum):
    """Output formats for read command."""

    TEXT = "text"
    JSON = "json"


def truncate_string(s: Optional[str], max_length: int) -> str:
    """Truncate a string to max_length characters with ellipsis.

    Args:
        s: The string to truncate (or None)
        max_length: Maximum length including ellipsis

    Returns:
        Truncated string with "..." if needed, or "(none)" if None
    """
    if s is None:
        return "(none)"

    # Handle edge cases for max_length
    if max_length <= 0:
        return ""
    if 1 <= max_length <= 3:
        return "..."[:max_length]

    if len(s) <= max_length:
        return s

    # Reserve 3 characters for "..."
    return s[: max_length - 3] + "..."


def validate_string_option(value: Optional[str]) -> Optional[str]:
    """Validate string options: trim whitespace and reject empty strings.

    Args:
        value: The string value to validate (or None)

    Returns:
        Trimmed string or None if input is None

    Raises:
        typer.BadParameter: If the string is empty or whitespace-only after trimming
    """
    if value is None:
        return None

    trimmed = value.strip()

    if trimmed == "":
        raise typer.BadParameter("Value cannot be empty or whitespace-only")

    return trimmed


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


def render_comment_text(comment: Comment) -> str:
    """Render a comment in human-readable text format.

    Handles special rendering for artifact types:
    - plan: Displays plan markdown from plan_data.plan
    - compose-request: Displays PR summary
    - other artifacts: Pretty-printed JSON of raw field

    Args:
        comment: Comment object to render

    Returns:
        Human-readable text representation of the comment
    """
    lines = []

    # Header with comment metadata
    lines.append("=" * 80)
    lines.append(f"Comment #{comment.id}")
    lines.append("=" * 80)
    lines.append(f"Issue ID:    {comment.issue_id}")
    lines.append(f"Source:      {comment.source or '(none)'}")
    lines.append(f"Type:        {comment.type or '(none)'}")
    if comment.adw_id:
        lines.append(f"ADW ID:      {comment.adw_id}")
    if comment.created_at:
        lines.append(f"Created:     {comment.created_at}")
    lines.append("=" * 80)
    lines.append("")

    # Check for artifact in raw data
    artifact = comment.raw.get("artifact", {}) if comment.raw else {}
    artifact_type = artifact.get("artifact_type")

    if artifact_type == "plan":
        # Extract and format plan markdown
        plan_data = artifact.get("plan_data", {})
        plan_text = plan_data.get("plan", "")

        lines.append("Plan:")
        lines.append("-" * 80)
        lines.append(plan_text)
        lines.append("-" * 80)

    elif artifact_type == "compose-request":
        repos = artifact.get("repos") or []
        summaries = [
            r.get("summary", "") for r in repos if isinstance(r, dict) and r.get("summary")
        ]
        summary = "\n\n---\n\n".join(summaries)

        lines.append("Pull Request Summary:")
        lines.append("-" * 80)
        lines.append(summary)
        lines.append("-" * 80)

    else:
        # Default: display comment text and raw JSON
        lines.append("Comment:")
        lines.append("-" * 80)
        lines.append(comment.comment)
        lines.append("-" * 80)

        # Display raw data as pretty-printed JSON
        if comment.raw:
            lines.append("")
            lines.append("Raw Data (JSON):")
            lines.append("-" * 80)
            lines.append(json.dumps(comment.raw, indent=2, ensure_ascii=False))
            lines.append("-" * 80)

    return "\n".join(lines)


@app.command("list")
def list_command(
    issue_id: Optional[int] = typer.Option(
        None, "--issue-id", help="Filter by issue ID", show_default=True
    ),
    source: Optional[str] = typer.Option(
        None,
        "--source",
        help="Filter by source",
        show_default=True,
        callback=validate_string_option,
    ),
    comment_type: Optional[str] = typer.Option(
        None,
        "--type",
        help="Filter by comment type",
        show_default=True,
        callback=validate_string_option,
    ),
    limit: int = typer.Option(
        10, "--limit", help="Maximum number of comments to return", show_default=True
    ),
    offset: int = typer.Option(0, "--offset", help="Number of comments to skip", show_default=True),
) -> None:
    """List comments with optional filters and pagination.

    Fetches comments from the database ordered by creation date (newest first).

    Examples:
        rouge comment list
        rouge comment list --issue-id 5
        rouge comment list --source agent --type plan --limit 5 --offset 10
    """
    validate_positive_int(issue_id, "--issue-id")
    if limit < 1:
        typer.echo("Error: --limit must be at least 1", err=True)
        raise typer.Exit(1)
    if offset < 0:
        typer.echo("Error: --offset must be at least 0", err=True)
        raise typer.Exit(1)

    try:
        comments = list_comments(
            issue_id=issue_id,
            source=source,
            comment_type=comment_type,
            limit=limit,
            offset=offset,
        )

        if not comments:
            typer.echo("No comments found.")
            return

        typer.echo(
            f"{'ID':<8} {'Issue':<8} {'Source':<12} {'Type':<12} {'Comment':<40} {'Created':<20}"
        )
        typer.echo("-" * 102)

        for comment in comments:
            truncated = truncate_string(comment.comment, 38)
            created = str(comment.created_at)[:19] if comment.created_at else "(none)"
            row = (
                f"{comment.id or '(none)'!s:<8} {comment.issue_id!s:<8} "
                f"{comment.source or '(none)':<12} {comment.type or '(none)':<12} "
                f"{truncated:<40} {created:<20}"
            )
            typer.echo(row)

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Unexpected error: {e}", err=True)
        raise typer.Exit(1)


@app.command("read")
def read_command(
    comment_id: int = typer.Argument(..., help="The comment ID to read"),
    format: OutputFormat = typer.Option(
        OutputFormat.TEXT,
        "--format",
        "-f",
        help="Output format: 'text' for human-readable, 'json' for machine-readable",
        show_default=True,
    ),
) -> None:
    """Read and display a comment.

    Fetches a comment from the database and displays it in the specified format.

    Formats:
        - text: Human-readable format with rendered content
        - json: Machine-readable JSON format

    Args:
        comment_id: The ID of the comment to read
        format: Output format (text or json)

    Examples:
        rouge comment read 123
        rouge comment read 123 --format text
        rouge comment read 123 --format json
    """
    validate_positive_int(comment_id, "comment_id")
    try:
        comment = fetch_comment(comment_id)

        if format == OutputFormat.JSON:
            # JSON format: output the comment as JSON
            typer.echo(comment.model_dump_json(indent=2))
        else:
            # Text format: use the rendering helper
            typer.echo(render_comment_text(comment))

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Unexpected error: {e}", err=True)
        raise typer.Exit(1)
