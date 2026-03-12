"""CLI commands for issue management."""

import json
import logging
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import typer

from rouge.cli.reset import reset
from rouge.cli.utils import validate_issue_id
from rouge.core.database import (
    create_issue,
    delete_issue,
    fetch_all_issues,
    fetch_issue,
    update_issue,
)

app = typer.Typer(help="Issue management commands")

# Sentinel value to distinguish "not provided" from "provided as None"
# Using a unique string that users would never reasonably provide
_UNSET = "__UNSET_SENTINEL_VALUE__"

# Status emoji mapping for visual status indicators
STATUS_EMOJI = {
    "pending": "⏳",
    "started": "🔄",
    "completed": "✅",
    "failed": "❌",
}


def format_status(status: str) -> str:
    """Format a status string with an emoji prefix if known.

    Args:
        status: The status value to format

    Returns:
        Formatted status string with emoji prefix if status is known,
        otherwise returns the plain status string
    """
    emoji = STATUS_EMOJI.get(status, "")
    if emoji:
        return f"{emoji} {status}"
    return status


class IssueType(str, Enum):
    """Issue types supported by Rouge."""

    MAIN = "main"
    PATCH = "patch"
    CODEREVIEW = "codereview"


class OutputFormat(str, Enum):
    """Output formats for list command."""

    TABLE = "table"
    JSON = "json"


def generate_title(description: Optional[str]) -> str:
    """Generate a short title from a description.

    Takes the first 10 words of the description and appends "..." if the
    description is longer.

    Args:
        description: The full description text (or None)

    Returns:
        A shortened title string (first 10 words with "..." if truncated)
    """
    if not description or not description.strip():
        return ""

    words = description.split()
    if len(words) <= 10:
        return " ".join(words)

    return " ".join(words[:10]) + "..."


def validate_new_args(
    description: Optional[str],
    spec_file: Optional[Path],
    title: Optional[str],
    branch: Optional[str] = None,
    assigned_to: Optional[str] = None,
    parent_issue_id: Optional[int] = None,
    issue_type: IssueType = IssueType.MAIN,
) -> None:
    """Validate arguments for the new command.

    Performs validation checks for mutual exclusion, required inputs,
    and spec-file title requirement.

    Args:
        description: The issue description text (or None)
        spec_file: Path to file containing issue description (or None)
        title: Explicit title for the issue (or None)
        branch: Pre-set branch name for the issue (or None)
        assigned_to: Assignee identifier (or None)
        parent_issue_id: Parent issue ID for patch issues (or None)
        issue_type: Issue type (main, patch, or codereview)

    Raises:
        typer.Exit: If validation fails
    """
    # Validation: branch cannot be whitespace only
    if branch is not None and branch.strip() == "":
        typer.echo(
            "Error: Branch name cannot be whitespace only",
            err=True,
        )
        raise typer.Exit(1)

    # Validation: assigned_to cannot be whitespace only
    if assigned_to is not None and assigned_to.strip() == "":
        typer.echo(
            "Error: Assigned to cannot be whitespace only",
            err=True,
        )
        raise typer.Exit(1)

    # Validation: title cannot be whitespace only (when provided)
    if title is not None and title.strip() == "":
        typer.echo(
            "Error: Title cannot be whitespace only",
            err=True,
        )
        raise typer.Exit(1)

    # Validation: description cannot be whitespace only (when provided)
    if description is not None and description.strip() == "":
        typer.echo(
            "Error: Description cannot be whitespace only",
            err=True,
        )
        raise typer.Exit(1)

    # Validation: description and spec-file are mutually exclusive
    if description and spec_file:
        typer.echo(
            "Error: Cannot use both description argument and --spec-file option",
            err=True,
        )
        raise typer.Exit(1)

    # Validation: must provide either description or spec-file
    if not description and not spec_file:
        typer.echo(
            "Error: Must provide either a description argument or --spec-file option",
            err=True,
        )
        raise typer.Exit(1)

    # Validation: spec-file requires explicit --title
    if spec_file and not title:
        typer.echo(
            "Error: --spec-file requires explicit --title option",
            err=True,
        )
        raise typer.Exit(1)

    # Validation: parent_issue_id must be positive if provided
    if parent_issue_id is not None and parent_issue_id <= 0:
        typer.echo(
            f"Error: parent_issue_id must be greater than 0, got {parent_issue_id}",
            err=True,
        )
        raise typer.Exit(1)

    # Validation: for patch issues, exactly one of branch or parent_issue_id must be provided
    if issue_type == IssueType.PATCH:
        has_branch = branch is not None
        has_parent = parent_issue_id is not None

        if not has_branch and not has_parent:
            typer.echo(
                "Error: For patch issues, either --branch or --parent-issue-id must be provided",
                err=True,
            )
            raise typer.Exit(1)

        if has_branch and has_parent:
            typer.echo(
                "Error: For patch issues, cannot use both --branch and --parent-issue-id",
                err=True,
            )
            raise typer.Exit(1)

    # Validation: for non-patch issues, reject parent_issue_id if provided
    if issue_type != IssueType.PATCH and parent_issue_id is not None:
        typer.echo(
            f"Error: --parent-issue-id is only allowed for patch issues, "
            f"not {issue_type.value} issues",
            err=True,
        )
        raise typer.Exit(1)

    # Validation: for codereview issues, --branch must be provided
    if issue_type == IssueType.CODEREVIEW:
        if branch is None:
            typer.echo(
                "Error: For codereview issues, --branch must be provided",
                err=True,
            )
            raise typer.Exit(1)


def read_spec_file(spec_file: Path) -> str:
    """Read and validate content from a spec file.

    Reads the file content with UTF-8 encoding and validates that the file
    exists, is a regular file, and contains non-empty content.

    Args:
        spec_file: Path to the spec file to read

    Returns:
        The stripped content of the spec file

    Raises:
        typer.Exit: If the file cannot be read or is invalid
    """
    if not spec_file.exists():
        typer.echo(f"Error: File not found: {spec_file}", err=True)
        raise typer.Exit(1)

    if not spec_file.is_file():
        typer.echo(f"Error: Path is not a file: {spec_file}", err=True)
        raise typer.Exit(1)

    try:
        content = spec_file.read_text(encoding="utf-8").strip()
    except UnicodeDecodeError:
        typer.echo(f"Error: File is not valid UTF-8: {spec_file}", err=True)
        raise typer.Exit(1)
    except OSError as err:
        typer.echo(f"Error: Cannot read file: {spec_file}: {err}", err=True)
        raise typer.Exit(1)

    if not content:
        typer.echo("Error: File is empty", err=True)
        raise typer.Exit(1)

    return content


def prepare_issue(
    description: Optional[str],
    spec_file: Optional[Path],
    title: Optional[str],
) -> tuple[str, str]:
    """Prepare issue title and description from inputs.

    Orchestrates reading from spec_file or validating the description,
    and generates a title if needed.

    Args:
        description: The issue description text (or None)
        spec_file: Path to file containing issue description (or None)
        title: Explicit title for the issue (or None)

    Returns:
        A tuple of (issue_title, issue_description)

    Raises:
        typer.Exit: If validation fails
    """
    if spec_file:
        # Read from file
        issue_description = read_spec_file(spec_file)
        # title is guaranteed non-None here due to validation in validate_new_args
        assert title is not None
        issue_title = title.strip()
    else:
        # Use description argument
        issue_description = description.strip() if description else ""

        if not issue_description:
            typer.echo("Error: Description cannot be empty", err=True)
            raise typer.Exit(1)

        # Auto-generate title if not provided
        # Strip title before checking emptiness
        stripped_title = title.strip() if title else ""
        if stripped_title:
            issue_title = stripped_title
        else:
            issue_title = generate_title(issue_description)

    return (issue_title, issue_description)


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


@app.command()
def create(
    description: Optional[str] = typer.Argument(None, help="The issue description text"),
    title: Optional[str] = typer.Option(
        None, "--title", "-t", help="Explicit title for the issue", show_default=True
    ),
    spec_file: Optional[Path] = typer.Option(
        None,
        "--spec-file",
        "-f",
        help="Path to file containing issue description",
        show_default=True,
    ),
    issue_type: IssueType = typer.Option(
        IssueType.MAIN,
        "--type",
        help=(
            "Issue type: 'main' for primary issues, 'patch' for patch issues, "
            "'codereview' for code review issues (requires --branch)"
        ),
        show_default=True,
    ),
    branch: Optional[str] = typer.Option(
        None, "--branch", "-b", help="Pre-set branch name for the issue.", show_default=True
    ),
    assigned_to: Optional[str] = typer.Option(
        None,
        "--assigned-to",
        help="Assignee identifier (email, agent name, or custom ID)",
        show_default=True,
    ),
    parent_issue_id: Optional[int] = typer.Option(
        None,
        "--parent-issue-id",
        help="Parent issue ID for patch issues (mutually exclusive with --branch for patch issues)",
        show_default=True,
    ),
) -> None:
    """Create a new issue.

    Supports multiple input modes:
    - Description only: `rouge issue create "Fix the login bug"` (auto-generates title)
    - Description + title: `rouge issue create "Fix the login bug" --title "Login fix"`
    - Spec file + title: `rouge issue create --spec-file spec.txt --title "Feature X"`
    - With type: `rouge issue create --spec-file patch.txt --title "Patch fix" --type patch`

    Branch specification options:
    - --branch: Explicitly set the branch name for any issue type
    - --parent-issue-id: For patch issues only, inherit branch from parent issue

    Patch issue validation rules:
    - For patch issues, exactly one of --branch or --parent-issue-id must be provided
    - The --parent-issue-id option is only valid for patch issues
    - If --parent-issue-id is provided, the branch will be inherited from the parent issue
    - The parent issue must exist and have a branch assigned

    Code review issue validation rules:
    - For codereview issues, --branch is required

    Examples:
        rouge issue create "Fix authentication bug in login flow"
        rouge issue create "Implement dark mode" --title "Dark mode feature"
        rouge issue create --spec-file feature-spec.txt --title "New feature"
        rouge issue create --spec-file patch-spec.txt --title "Bug fix" \\
            --type patch --branch my-branch
        rouge issue create "Fix typo" --type patch --parent-issue-id 123
    """
    validate_new_args(
        description, spec_file, title, branch, assigned_to, parent_issue_id, issue_type
    )
    issue_title, issue_description = prepare_issue(description, spec_file, title)

    normalized_branch = branch.strip() if branch is not None else None
    normalized_assigned_to = assigned_to.strip() if assigned_to is not None else None

    # If parent_issue_id is provided, fetch parent and extract branch
    if parent_issue_id is not None:
        try:
            parent = fetch_issue(parent_issue_id)
            if parent.branch is None:
                typer.echo(
                    f"Error: Parent issue {parent_issue_id} has no branch",
                    err=True,
                )
                raise typer.Exit(1)
            normalized_branch = parent.branch
        except ValueError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

    try:
        issue = create_issue(
            description=issue_description,
            title=issue_title,
            issue_type=issue_type.value,
            branch=normalized_branch,
            assigned_to=normalized_assigned_to,
        )
        typer.echo(f"{issue.id}")  # Output only the ID for scripting

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        logging.exception("Unexpected error in create command")
        typer.echo(f"Unexpected error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def read(
    issue_id: int = typer.Argument(..., help="The issue ID to read"),
) -> None:
    """Read and display an issue.

    Fetches the issue from the database and displays it in a human-readable format.

    Args:
        issue_id: The ID of the issue to read

    Example:
        rouge issue read 123
    """
    validate_issue_id(issue_id)
    try:
        issue = fetch_issue(issue_id)

        # Format the output for human readability
        typer.echo(f"Issue #{issue.id}")
        typer.echo(f"Title: {issue.title or '(none)'}")
        typer.echo(f"Type: {issue.type}")
        typer.echo(f"Status: {format_status(issue.status)}")
        typer.echo(f"Assigned to: {issue.assigned_to or '(none)'}")
        if issue.branch:
            typer.echo(f"Branch: {issue.branch}")
        if issue.adw_id:
            typer.echo(f"ADW ID: {issue.adw_id}")
        typer.echo("Description:")
        typer.echo(issue.description)
        if issue.created_at:
            typer.echo(f"Created: {issue.created_at}")
        if issue.updated_at:
            typer.echo(f"Updated: {issue.updated_at}")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        logging.exception("Unexpected error in read command")
        typer.echo(f"Unexpected error: {e}", err=True)
        raise typer.Exit(1)


@app.command("list")
def list_issues(
    format: OutputFormat = typer.Option(
        OutputFormat.TABLE,
        "--format",
        "-f",
        help="Output format: 'table' for human-readable, 'json' for scripting",
        show_default=True,
    ),
    limit: int = typer.Option(
        5,
        "--limit",
        "-l",
        help="Maximum number of issues to return (default: 5)",
        show_default=True,
    ),
    issue_type: Optional[str] = typer.Option(
        None,
        "--type",
        "-t",
        help="Filter by issue type",
        case_sensitive=False,
    ),
    status: Optional[str] = typer.Option(
        None,
        "--status",
        "-s",
        help="Filter by status",
        case_sensitive=False,
    ),
) -> None:
    """List all issues.

    Fetches issues from the database and displays them in the specified format.
    Issues are ordered by creation date (newest first).

    Formats:
        - table: Human-readable table with columns: ID, Title, Type, Status, Branch, Assigned To
        - json: Machine-readable JSON array of issue objects

    Filter Options:
        - limit: Maximum number of issues to return (default: 5)
        - issue_type: Filter by issue type ('main', 'patch', 'codereview')
        - status: Filter by status ('pending', 'started', 'completed', 'failed')

    Examples:
        rouge issue list
        rouge issue list --limit 10
        rouge issue list --type main --status pending
        rouge issue list --format json --limit 20
    """
    # Trim and validate string options
    if issue_type is not None:
        issue_type = issue_type.strip()
        if not issue_type:
            raise typer.BadParameter("Issue type cannot be empty or whitespace-only")
    if status is not None:
        status = status.strip()
        if not status:
            raise typer.BadParameter("Status cannot be empty or whitespace-only")

    try:
        issues = fetch_all_issues(limit=limit, issue_type=issue_type, status=status)

        if format == OutputFormat.JSON:
            # JSON format: output array of issue objects
            issues_data = [issue.model_dump(mode="json") for issue in issues]
            typer.echo(json.dumps(issues_data, indent=2, default=str))
        else:
            # Table format: human-readable output
            if not issues:
                typer.echo("No issues found.")
                return

            # Print header
            typer.echo(
                f"{'ID':<6} {'Title':<32} {'Type':<10} {'Status':<12} "
                f"{'Br':<3} {'Assigned To':<12}"
            )
            typer.echo("-" * 79)

            # Print each issue
            for issue in issues:
                truncated_title = truncate_string(issue.title, 30)
                assigned_to = issue.assigned_to or "(none)"
                branch_indicator = "✅" if issue.branch else "❌"

                # Format the row with proper spacing
                row = (
                    f"{issue.id:<6} {truncated_title:<32} "
                    f"{issue.type:<10} {format_status(issue.status):<12} "
                    f"{branch_indicator:<3} {assigned_to:<12}"
                )
                typer.echo(row)

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        logging.exception("Unexpected error in list command")
        typer.echo(f"Unexpected error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def update(
    issue_id: int = typer.Argument(..., help="The issue ID to update"),
    assigned_to: Optional[str] = typer.Option(
        None,
        "--assigned-to",
        help="Assignee identifier (email, agent name, or custom ID)",
        show_default=True,
    ),
    issue_type: Optional[str] = typer.Option(
        None, "--type", help="Issue type: 'main', 'patch', or 'codereview'", show_default=True
    ),
    title: Optional[str] = typer.Option(None, "--title", help="Issue title", show_default=True),
    description: Optional[str] = typer.Option(
        None, "--description", help="Issue description", show_default=True
    ),
    branch: Optional[str] = typer.Option(
        _UNSET, "--branch", help="Branch name", show_default=False
    ),
) -> None:
    """Update an existing issue.

    Updates one or more fields on an issue. Only provided options will be updated.
    At least one field must be specified for update.

    Special behavior:
    - When changing type to 'main', the branch is automatically cleared (set to None)
      unless --branch is explicitly provided

    Args:
        issue_id: The ID of the issue to update
        assigned_to: Worker ID to assign the issue to
        issue_type: Issue type ('main' or 'patch')
        title: New title for the issue
        description: New description for the issue
        branch: Branch name (explicit --branch takes precedence over auto-clear)

    Examples:
        rouge issue update 123 --title "New Title"
        rouge issue update 123 --assigned-to tydirium-1 --type main
        rouge issue update 123 --description "Updated description"
        rouge issue update 123 --title "Title" --description "Description"
        rouge issue update 123 --type main  # Auto-clears branch
        rouge issue update 123 --type main --branch my-branch  # Keeps branch
    """
    validate_issue_id(issue_id)
    try:
        # Validate whitespace-only fields before normalization
        if assigned_to is not None and assigned_to.strip() == "":
            raise ValueError("Field 'assigned_to' cannot be whitespace only")

        if title is not None and title.strip() == "":
            raise ValueError("Field 'title' cannot be whitespace only")

        if description is not None and description.strip() == "":
            raise ValueError("Field 'description' cannot be whitespace only")

        if branch != _UNSET and branch is not None and branch.strip() == "":
            raise ValueError("Field 'branch' cannot be whitespace only")

        # Normalize string fields: trim and convert empty strings to None
        if assigned_to is not None:
            assigned_to = assigned_to.strip() or None
        if title is not None:
            title = title.strip() or None
        if description is not None:
            description = description.strip() or None
        if branch != _UNSET and branch is not None:
            branch = branch.strip() or None

        # Validate and normalize issue_type
        normalized_issue_type: Optional[str] = None
        if issue_type is not None:
            if issue_type.strip() == "":
                raise ValueError("Field 'issue_type' cannot be whitespace only")
            issue_type = issue_type.strip()
            if issue_type:
                try:
                    # Parse to IssueType enum for validation
                    parsed_type = IssueType(issue_type.lower())
                    normalized_issue_type = parsed_type.value
                except ValueError:
                    valid_types = ", ".join([t.value for t in IssueType])
                    raise ValueError(
                        f"Invalid issue type '{issue_type}'. Must be one of: {valid_types}"
                    )

        # Auto-clear branch when changing to type 'main', unless --branch was explicitly provided
        if normalized_issue_type == "main" and branch == _UNSET:
            # branch was not explicitly provided, so auto-clear it
            branch = None

        # Check if all normalized fields are None or UNSET
        if all(
            field is None or field == _UNSET
            for field in [assigned_to, normalized_issue_type, title, description, branch]
        ):
            raise ValueError("No fields provided for update. At least one field must be specified.")

        # Build kwargs dict with only non-None and non-UNSET values
        kwargs: dict[str, Any] = {}
        if assigned_to is not None:
            kwargs["assigned_to"] = assigned_to
        if normalized_issue_type is not None:
            kwargs["issue_type"] = normalized_issue_type
        if title is not None:
            kwargs["title"] = title
        if description is not None:
            kwargs["description"] = description
        if branch != _UNSET:
            kwargs["branch"] = branch

        # Call update_issue with the constructed kwargs
        issue = update_issue(issue_id, **kwargs)

        # Output issue ID on success (for scripting compatibility)
        typer.echo(f"{issue.id}")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except TypeError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        logging.exception("Unexpected error in update command")
        typer.echo(f"Unexpected error: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def delete(
    issue_id: int = typer.Argument(..., help="The issue ID to delete"),
    force: bool = typer.Option(
        False, "--force", help="Skip confirmation prompt", show_default=True
    ),
) -> None:
    """Delete an issue.

    Deletes an issue from the database. Requires confirmation by default to prevent
    accidental data loss. Use --force to skip the confirmation prompt.

    Args:
        issue_id: The ID of the issue to delete
        force: If True, skip confirmation prompt

    Examples:
        rouge issue delete 123
        rouge issue delete 123 --force
    """
    validate_issue_id(issue_id)
    try:
        # Prompt for confirmation unless --force is used
        if not force:
            if not typer.confirm(f"Delete issue {issue_id}?"):
                raise typer.Exit(0)

        # Delete the issue
        delete_issue(issue_id)

        # Output success message
        typer.echo(f"Issue {issue_id} deleted successfully.")

    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except typer.Exit:
        raise
    except Exception as e:
        logging.exception("Unexpected error in delete command")
        typer.echo(f"Unexpected error: {e}", err=True)
        raise typer.Exit(1)


app.command("reset")(reset)
