"""
Database configuration and client initialization.
"""

import logging
import os
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from postgrest.exceptions import APIError
from supabase import Client, ClientOptions, create_client

from rouge.core.models import VALID_WORKER_IDS, Comment, Issue, Patch

logger = logging.getLogger(__name__)


def init_db_env(dotenv_path: Optional[Path] = None) -> None:
    """Initialize database environment variables.

    Args:
        dotenv_path: Optional path to .env file
    """
    if dotenv_path:
        load_dotenv(dotenv_path)
    else:
        load_dotenv()


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


def fetch_all_issues() -> list[Issue]:
    """Fetch all issues ordered by creation date (newest first).

    Returns:
        List of Issue objects

    Raises:
        ValueError: If fetch fails
    """
    try:
        client = get_client()
        response = client.table("issues").select("*").order("created_at", desc=True).execute()

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


def fetch_comments(issue_id: int) -> list[Comment]:
    """Fetch comments for an issue ordered by creation date.

    Args:
        issue_id: ID of the issue to fetch comments for

    Returns:
        List of Comment objects

    Raises:
        ValueError: If fetch fails
    """
    try:
        client = get_client()
        response = (
            client.table("comments")
            .select("*")
            .eq("issue_id", issue_id)
            .order("created_at")
            .execute()
        )

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
        logger.exception("Database error fetching comments for issue %s", issue_id)
        raise ValueError(f"Failed to fetch comments for issue {issue_id}: {e}") from e


# ============================================================================
# Issue Updates
# ============================================================================


def create_issue(description: str, title: Optional[str] = None) -> Issue:
    """Create a new issue.

    Args:
        description: Issue description/body
        title: Optional issue title

    Returns:
        Created Issue object

    Raises:
        ValueError: If creation fails
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

        data = {"description": description, "status": "pending"}
        if title:
            data["title"] = title

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


def update_issue_status(issue_id: int, status: str) -> Issue:
    """Update issue status.

    Args:
        issue_id: Issue ID to update
        status: New status (pending, started, completed)

    Returns:
        Updated Issue object

    Raises:
        ValueError: If status is invalid or update fails
    """
    valid_statuses = {"pending", "started", "completed", "patch pending", "patched"}
    if status not in valid_statuses:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}")

    try:
        client = get_client()

        # Verify issue exists first
        issue_check = client.table("issues").select("id").eq("id", issue_id).execute()
        if not issue_check.data:
            raise ValueError(f"Issue with id {issue_id} not found")

        response = client.table("issues").update({"status": status}).eq("id", issue_id).execute()
        if not response.data:
            raise ValueError(f"Update failed: issue {issue_id} not returned")

        row = response.data[0]
        if not isinstance(row, dict):
            raise ValueError(f"Invalid response data type for issue {issue_id}")

        return Issue.from_supabase(row)

    except APIError as e:
        logger.exception("Database error updating status for issue %s", issue_id)
        raise ValueError(f"Failed to update issue {issue_id} status: {e}") from e


def update_issue_description(issue_id: int, description: str) -> Issue:
    """Update issue description.

    Args:
        issue_id: Issue ID to update
        description: New description

    Raises:
        ValueError: If description is empty or update fails

    Returns:
        Updated Issue object
    """
    if not description or not description.strip():
        raise ValueError("Description cannot be empty")

    if len(description.strip()) < 10:
        raise ValueError("Description must be at least 10 characters")

    if len(description) > 10000:
        raise ValueError("Description cannot exceed 10000 characters")

    try:
        client = get_client()
        response = (
            client.table("issues").update({"description": description}).eq("id", issue_id).execute()
        )

        if not response.data:
            raise ValueError(f"Issue with id {issue_id} not found")

        response_data = response.data[0]
        if not isinstance(response_data, dict):
            raise ValueError(f"Expected dict from database, got {type(response_data)}")

        return Issue.from_supabase(response_data)

    except APIError as e:
        logger.exception("Database error updating description for issue %s", issue_id)
        raise ValueError(f"Failed to update issue {issue_id} description: {e}") from e


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


def update_issue_assignment(issue_id: int, assigned_to: Optional[str]) -> Issue:
    """Update issue worker assignment.

    Args:
        issue_id: Issue ID to update
        assigned_to: Worker ID string or None to unassign

    Returns:
        Updated Issue object

    Raises:
        ValueError: If inputs invalid or update fails
    """
    if assigned_to is not None and not isinstance(assigned_to, str):
        raise TypeError("Worker ID must be a string")

    if assigned_to is not None:
        assigned_to = assigned_to.strip()

    if assigned_to is not None and not assigned_to:
        raise ValueError("Worker ID cannot be empty")

    # Validate worker ID if provided
    if assigned_to is not None and assigned_to not in VALID_WORKER_IDS:
        valid_workers_str = ", ".join(sorted(VALID_WORKER_IDS))
        raise ValueError(f"Invalid worker ID '{assigned_to}'. Must be one of: {valid_workers_str}")

    try:
        client = get_client()

        # Validate issue exists and status
        try:
            issue = fetch_issue(issue_id)
        except ValueError as e:
            raise ValueError(f"Failed to fetch issue {issue_id}: {e}") from e

        if issue.status != "pending":
            raise ValueError(
                f"Only pending issues can be assigned; issue {issue_id} has status '{issue.status}'"
            )

        response = (
            client.table("issues").update({"assigned_to": assigned_to}).eq("id", issue_id).execute()
        )
        if not response.data:
            raise ValueError(f"Update failed: issue {issue_id} not returned")

        row = response.data[0]
        if not isinstance(row, dict):
            raise ValueError(f"Invalid response data type for issue {issue_id}")

        return Issue.from_supabase(row)

    except APIError as e:
        logger.exception("Database error assigning issue %s", issue_id)
        raise ValueError(f"Failed to assign issue {issue_id}: {e}") from e


# ============================================================================
# Patch Operations
# ============================================================================


def fetch_pending_patch(issue_id: int) -> Optional[Patch]:
    """Fetch the oldest pending patch for an issue.

    Args:
        issue_id: Issue ID to find patch for

    Returns:
        Patch object if found, None otherwise
    """
    try:
        client = get_client()
        response = (
            client.table("patches")
            .select("*")
            .eq("issue_id", issue_id)
            .eq("status", "pending")
            .order("created_at", desc=False)  # Oldest first (FIFO)
            .limit(1)
            .execute()
        )

        if response.data and len(response.data) > 0:
            row = response.data[0]
            if isinstance(row, dict):
                return Patch.from_supabase(row)

        return None

    except APIError:
        logger.exception("Database error fetching pending patch for issue %s", issue_id)
        # Don't raise, just return None as "no patch found"
        return None


def update_patch_status(patch_id: int, status: str, log: Optional[logging.Logger] = None) -> None:
    """Update patch status.

    Args:
        patch_id: ID of patch to update
        status: New status (pending, completed, failed)
        log: Optional logger to use (defaults to module logger)

    Raises:
        ValueError: If status invalid or update fails
    """
    valid_statuses = {"pending", "completed", "failed"}
    if status not in valid_statuses:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}")

    _log = log or logger

    try:
        client = get_client()

        # Verify exists
        check = client.table("patches").select("id").eq("id", patch_id).execute()
        if not check.data:
            raise ValueError(f"Patch with id {patch_id} not found")

        client.table("patches").update({"status": status}).eq("id", patch_id).execute()
        _log.info(f"Updated patch {patch_id} status to {status}")

    except APIError as e:
        _log.exception(f"Database error updating patch {patch_id} status: {e}")
        raise ValueError(f"Failed to update patch {patch_id} status: {e}") from e
