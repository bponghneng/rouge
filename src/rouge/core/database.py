"""
Database configuration and client initialization.
"""

import logging
import os
from pathlib import Path
from typing import Any, Optional

import httpx
from dotenv import find_dotenv, load_dotenv
from postgrest.exceptions import APIError
from supabase import Client, ClientOptions, create_client

from rouge.core.models import Comment, Issue
from rouge.core.utils import make_adw_id

logger = logging.getLogger(__name__)


# Sentinel object for distinguishing unset parameters from None
class _Unset:
    """Sentinel value to distinguish unset parameters from None."""

    def __repr__(self) -> str:
        return "UNSET"


UNSET = _Unset()

MAX_LIMIT = 100


def init_db_env(dotenv_path: Optional[Path] = None) -> None:
    """Initialize database environment variables.

    Args:
        dotenv_path: Optional path to .env file
    """
    if dotenv_path:
        load_dotenv(dotenv_path)
    else:
        # Ensure we search from the current working directory, not the caller's file path.
        found_path = find_dotenv(usecwd=True)
        if found_path:
            load_dotenv(found_path)
        else:
            logger.debug("No .env file found from cwd search; skipping dotenv load")


class SupabaseConfig:
    """Configuration for Supabase client."""

    @property
    def url(self) -> str:
        url = os.getenv("SUPABASE_URL")
        if not url:
            raise ValueError("SUPABASE_URL environment variable is not set")
        return url

    @property
    def key(self) -> str:
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not key:
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY environment variable is not set")
        return key

    def validate(self) -> None:
        """Validate that all required configuration is present.

        Raises:
            ValueError: If any required configuration is missing
        """
        # Access properties to trigger validation
        _ = self.url
        _ = self.key


# Global client instance
_client: Optional[Client] = None


def _build_http_client(timeout: int, verify: bool) -> httpx.Client:
    """Build HTTP client with specific configuration.

    Args:
        timeout: Request timeout in seconds
        verify: Whether to verify SSL certificates

    Returns:
        Configured httpx.Client
    """
    return httpx.Client(timeout=timeout, verify=verify)


def _get_http_client() -> httpx.Client:
    """Get HTTP client based on environment configuration.

    Returns:
        Configured httpx.Client
    """
    timeout = int(os.getenv("SUPABASE_HTTP_TIMEOUT", "30"))
    verify = os.getenv("SUPABASE_HTTP_VERIFY", "true").lower() == "true"
    return _build_http_client(timeout, verify)


def get_client() -> Client:
    """Get or create the global Supabase client instance.

    Returns:
        Supabase client instance

    Raises:
        ValueError: If required environment variables are missing
    """
    global _client
    if _client is None:
        config = SupabaseConfig()
        options = ClientOptions(httpx_client=_get_http_client())
        _client = create_client(config.url, config.key, options=options)
    return _client


def reset_client() -> None:
    """Reset the global Supabase client instance.

    This clears any stale HTTP keep-alive connections by setting the module-level
    _client variable to None, forcing get_client() to recreate it on the next call.

    Useful for:
    - Recovering from connection issues in long-running processes
    - Clearing stale HTTP connections after network errors
    - Worker daemons that need to reset state periodically
    """
    global _client
    _client = None


# ============================================================================
# Issue Operations
# ============================================================================


def fetch_issue(issue_id: int) -> Issue:
    """Fetch an issue by ID.

    Args:
        issue_id: ID of the issue to fetch

    Returns:
        Issue object

    Raises:
        ValueError: If issue is not found or fetch fails
    """
    try:
        client = get_client()
        response = client.table("issues").select("*").eq("id", issue_id).execute()

        # Handle empty response (postgrest returns empty list if not found)
        # response.data can be None or [] in some versions/cases
        response_data = response.data[0] if response.data else None

        if response_data is None:
            raise ValueError(f"Issue with id {issue_id} not found")

        if not isinstance(response_data, dict):
            raise TypeError(
                f"Expected dict from database for issue {issue_id}, got {type(response_data)}"
            )

        return Issue.from_supabase(response_data)

    except APIError as e:
        logger.exception("Database error fetching issue %s", issue_id)
        raise ValueError(f"Failed to fetch issue {issue_id}: {e}") from e


def fetch_all_issues(
    limit: int = 5,
    issue_type: Optional[str] = None,
    status: Optional[str] = None,
) -> list[Issue]:
    """Fetch all issues ordered by creation date (newest first).

    Args:
        limit: Maximum number of issues to return (default: 5)
        issue_type: Filter by issue type (e.g., 'full', 'patch')
        status: Filter by status (e.g., 'pending', 'started', 'completed', 'failed')

    Returns:
        List of Issue objects

    Raises:
        ValueError: If fetch fails
    """
    try:
        client = get_client()
        query = client.table("issues").select("*")

        # Apply filters before ordering
        if issue_type is not None:
            query = query.eq("type", issue_type)
        if status is not None:
            query = query.eq("status", status)

        # Apply ordering and limit
        response = query.order("created_at", desc=True).limit(limit).execute()

        rows = response.data
        if not rows:
            return []

        # Validate all rows are dicts before processing
        issues = []
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(
                    f"Invalid row at index {i}: expected dict, got {type(row).__name__}. "
                    f"Value preview: {str(row)[:100]}"
                )
            issues.append(Issue.from_supabase(row))
        return issues

    except APIError as e:
        logger.exception("Database error fetching all issues")
        raise ValueError(f"Failed to fetch issues: {e}") from e


# ============================================================================
# Comment Operations
# ============================================================================


def fetch_comment(comment_id: int) -> Comment:
    """Fetch a comment by ID.

    Args:
        comment_id: ID of the comment to fetch

    Returns:
        Comment object

    Raises:
        ValueError: If comment is not found or fetch fails
    """
    if comment_id <= 0:
        raise ValueError(f"comment_id must be > 0, got {comment_id}")
    try:
        client = get_client()
        response = client.table("comments").select("*").eq("id", comment_id).execute()

        # Handle empty response (postgrest returns empty list if not found)
        # response.data can be None or [] in some versions/cases
        response_data = response.data[0] if response.data else None

        if response_data is None:
            raise ValueError(f"Comment with id {comment_id} not found")

        if not isinstance(response_data, dict):
            raise TypeError(
                f"Expected dict from database for comment {comment_id}, got {type(response_data)}"
            )

        return Comment.from_supabase(response_data)

    except APIError as e:
        logger.exception("Database error fetching comment %s", comment_id)
        raise ValueError(f"Failed to fetch comment {comment_id}: {e}") from e


def create_comment(comment: Comment) -> Comment:
    """Create a new comment in the database.

    Args:
        comment: Comment object to create (id can be None)

    Returns:
        Created Comment object with ID and timestamps populated

    Raises:
        ValueError: If creation fails
    """
    try:
        client = get_client()
        data = comment.to_supabase()

        response = client.table("comments").insert(data).execute()

        if not response.data:
            raise ValueError("Comment creation returned no data")

        response_data = response.data[0]
        if not isinstance(response_data, dict):
            raise ValueError(f"Expected dict from database, got {type(response_data)}")

        return Comment.from_supabase(response_data)

    except APIError as e:
        logger.exception("Database error creating comment")
        raise ValueError(f"Failed to create comment: {e}") from e


def list_comments(
    *,
    issue_id: Optional[int] = None,
    source: Optional[str] = None,
    comment_type: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
) -> list[Comment]:
    """List comments with optional filters.

    Args:
        issue_id: Optional issue ID to filter by
        source: Optional source to filter by
        comment_type: Optional comment type to filter by
        limit: Maximum number of comments to return (default 10)
        offset: Number of comments to skip (default 0)

    Returns:
        List of Comment objects ordered by creation date (newest first)

    Raises:
        ValueError: If fetch fails
    """
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")
    if limit > MAX_LIMIT:
        limit = MAX_LIMIT
    if offset < 0:
        raise ValueError(f"offset must be >= 0, got {offset}")
    if issue_id is not None and issue_id <= 0:
        raise ValueError(f"issue_id must be > 0, got {issue_id}")
    if source is not None:
        source = source.strip() or None
    if comment_type is not None:
        comment_type = comment_type.strip() or None
    try:
        client = get_client()
        query = client.table("comments").select("*")
        if issue_id is not None:
            query = query.eq("issue_id", issue_id)
        if source is not None:
            query = query.eq("source", source)
        if comment_type is not None:
            query = query.eq("type", comment_type)
        response = query.order("created_at", desc=True).limit(limit).offset(offset).execute()

        if not response.data:
            return []

        # Validate all rows are dicts before processing
        comments = []
        for i, row in enumerate(response.data):
            if not isinstance(row, dict):
                raise ValueError(
                    f"Invalid row at index {i}: expected dict, got {type(row).__name__}. "
                    f"Value preview: {str(row)[:100]}"
                )
            comments.append(Comment.from_supabase(row))
        return comments

    except APIError as e:
        logger.exception("Database error listing comments")
        raise ValueError(f"Failed to list comments: {e}") from e


# ============================================================================
# Issue Updates
# ============================================================================


def create_issue(
    description: str,
    title: Optional[str] = None,
    issue_type: str = "full",
    adw_id: Optional[str] = None,
    branch: Optional[str] = None,
    assigned_to: Optional[str] = None,
) -> Issue:
    """Create a new issue.

    Args:
        description: Issue description/body
        title: Optional issue title
        issue_type: Issue type - 'full' for primary issues, 'patch' for patch issues.
            Defaults to 'full'.
        adw_id: Agent Development Workflow identifier. If not provided,
            a new 8-character UUID will be generated by the workflow.
        branch: Optional branch name to pre-set on the issue.
        assigned_to: Optional assignee identifier (email, agent name, or custom ID).

    Returns:
        Created Issue object

    Raises:
        ValueError: If creation fails or validation fails
    """
    try:
        client = get_client()

        # Validate inputs
        if not description or not description.strip():
            raise ValueError("Description cannot be empty")

        if len(description.strip()) < 10:
            raise ValueError("Description must be at least 10 characters")

        if title and not title.strip():
            raise ValueError("Title cannot be empty/whitespace if provided")

        # Validate issue_type
        valid_types = {"full", "patch"}
        if issue_type not in valid_types:
            raise ValueError(
                f"Invalid issue_type '{issue_type}'. Must be one of: {', '.join(valid_types)}"
            )

        # Generate adw_id if not provided or if it's whitespace-only
        normalized = adw_id.strip() if adw_id is not None else ""
        issue_adw_id = normalized or make_adw_id()

        data = {
            "description": description,
            "status": "pending",
            "type": issue_type,
            "adw_id": issue_adw_id,
        }
        if title:
            data["title"] = title
        if branch is not None:
            branch = branch.strip()
            if not branch:
                raise ValueError("Branch cannot be empty")
            data["branch"] = branch
        if assigned_to is not None:
            assigned_to = assigned_to.strip()
            if not assigned_to:
                raise ValueError("Assigned to cannot be empty")
            data["assigned_to"] = assigned_to

        response = client.table("issues").insert(data).execute()

        if not response.data:
            raise ValueError("Issue creation returned no data")

        response_data = response.data[0]
        if not isinstance(response_data, dict):
            raise ValueError(f"Expected dict from database, got {type(response_data)}")

        return Issue.from_supabase(response_data)

    except APIError as e:
        logger.exception("Database error creating issue")
        raise ValueError(f"Failed to create issue: {e}") from e


def delete_issue(issue_id: int) -> bool:
    """Delete an issue.

    Args:
        issue_id: Issue ID to delete

    Returns:
        True if the issue was deleted successfully

    Raises:
        ValueError: If deletion fails or issue not found
    """
    try:
        client = get_client()
        response = client.table("issues").delete().eq("id", issue_id).execute()
        # PostgREST delete returns the deleted rows
        if not response.data:
            raise ValueError(f"Issue with id {issue_id} not found")
        return True

    except APIError as e:
        logger.exception("Database error deleting issue %s", issue_id)
        raise ValueError(f"Failed to delete issue {issue_id}: {e}") from e


def update_issue(
    issue_id: int,
    *,
    assigned_to: Optional[str] | _Unset = UNSET,
    issue_type: str | _Unset = UNSET,
    title: Optional[str] | _Unset = UNSET,
    description: str | _Unset = UNSET,
    status: str | _Unset = UNSET,
    branch: Optional[str] | _Unset = UNSET,
) -> Issue:
    """Update multiple fields on an issue in a single operation.

    Args:
        issue_id: Issue ID to update
        assigned_to: Worker ID string or None to unassign, or UNSET to skip
        issue_type: Issue type ('full' or 'patch'), or UNSET to skip
        title: Issue title or None to clear, or UNSET to skip
        description: Issue description, or UNSET to skip
        status: Issue status ('pending', 'started', 'completed', 'failed'), or UNSET to skip
        branch: Branch name or None to clear, or UNSET to skip

    Returns:
        Updated Issue object

    Raises:
        ValueError: If validation fails, no fields provided, or update fails
        TypeError: If assigned_to is not a string when provided (and not None)
    """
    updates: dict[str, Any] = {}

    # Validate and add assigned_to to updates
    if not isinstance(assigned_to, _Unset):
        if assigned_to is not None:
            if not isinstance(assigned_to, str):
                raise TypeError("Worker ID must be a string")
            assigned_to = assigned_to.strip()
            if not assigned_to:
                raise ValueError("Worker ID cannot be empty")
        updates["assigned_to"] = assigned_to

    # Validate and add issue_type to updates
    if not isinstance(issue_type, _Unset):
        valid_types = {"full", "patch"}
        if issue_type not in valid_types:
            raise ValueError(
                f"Invalid issue_type '{issue_type}'. Must be one of: {', '.join(valid_types)}"
            )
        updates["type"] = issue_type

    # Validate and add title to updates
    if not isinstance(title, _Unset):
        if title is not None:
            title = title.strip()
            if not title:
                raise ValueError("Title cannot be empty/whitespace if provided")
        updates["title"] = title

    # Validate and add description to updates
    if not isinstance(description, _Unset):
        if not description or not description.strip():
            raise ValueError("Description cannot be empty")
        description = description.strip()
        if len(description) < 10:
            raise ValueError("Description must be at least 10 characters")
        updates["description"] = description

    # Validate and add status to updates
    if not isinstance(status, _Unset):
        valid_statuses = {"pending", "started", "completed", "failed"}
        if status not in valid_statuses:
            raise ValueError(
                f"Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}"
            )
        updates["status"] = status

    # Validate and add branch to updates
    if not isinstance(branch, _Unset):
        if branch is not None and (not branch or not branch.strip()):
            raise ValueError("Branch cannot be empty")
        if branch is not None:
            branch = branch.strip()
        updates["branch"] = branch

    # Ensure at least one field is being updated
    if not updates:
        raise ValueError("No fields provided for update")

    try:
        client = get_client()

        # Verify issue exists first
        issue_check = client.table("issues").select("id").eq("id", issue_id).execute()
        if not issue_check.data:
            raise ValueError(f"Issue with id {issue_id} not found")

        response = client.table("issues").update(updates).eq("id", issue_id).execute()
        if not response.data:
            raise ValueError(f"Update failed: issue {issue_id} not returned")

        row = response.data[0]
        if not isinstance(row, dict):
            raise ValueError(f"Invalid response data type for issue {issue_id}")

        return Issue.from_supabase(row)

    except APIError as e:
        logger.exception("Database error updating issue %s", issue_id)
        raise ValueError(f"Failed to update issue {issue_id}: {e}") from e
