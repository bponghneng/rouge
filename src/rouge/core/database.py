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

from rouge.core.models import Comment, Issue, Patch

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
        options = ClientOptions(postgrest_client_timeout=10, storage_client_timeout=10)
        _client = create_client(config.url, config.key, options=options)
        # Monkey patch the http_client on the postgrest client directly
        # since supabase-py doesn't expose a clean way to pass custom httpx client
        _client.postgrest.http_client = _get_http_client()
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
        response = (
            client.table("issues")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )

        rows = response.data
        if not rows:
            return []

        return [Issue.from_supabase(row) for row in rows]

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

        return Comment.from_supabase(response.data[0])

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

        return [Comment.from_supabase(row) for row in response.data]

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
            raise ValueError("Description is required")

        if title and not title.strip():
            raise ValueError("Title cannot be empty/whitespace if provided")

        data = {"description": description, "status": "pending"}
        if title:
            data["title"] = title

        response = client.table("issues").insert(data).execute()

        if not response.data:
            raise ValueError("Issue creation returned no data")

        return Issue.from_supabase(response.data[0])

    except APIError as e:
        logger.exception("Database error creating issue")
        raise ValueError(f"Failed to create issue: {e}") from e


def update_issue_status(issue_id: int, status: str) -> None:
    """Update issue status.

    Args:
        issue_id: Issue ID to update
        status: New status (pending, started, completed)

    Raises:
        ValueError: If status is invalid or update fails
    """
    valid_statuses = {"pending", "started", "completed", "patch pending", "patched"}
    if status not in valid_statuses:
        raise ValueError(
            f"Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}"
        )

    try:
        client = get_client()

        # Verify issue exists first
        issue_check = client.table("issues").select("id").eq("id", issue_id).execute()
        if not issue_check.data:
            raise ValueError(f"Issue with id {issue_id} not found")

        response = (
            client.table("issues").update({"status": status}).eq("id", issue_id).execute()
        )
        if not response.data:
            raise ValueError(f"Update failed: issue {issue_id} not returned")

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

    try:
        client = get_client()
        response = client.table("issues").update({"description": description}).eq(
            "id", issue_id
        ).execute()

        if not response.data:
            raise ValueError(f"Issue with id {issue_id} not found")

        return Issue.from_supabase(response.data[0])

    except APIError as e:
        logger.exception("Database error updating description for issue %s", issue_id)
        raise ValueError(f"Failed to update issue {issue_id} description: {e}") from e


def delete_issue(issue_id: int) -> None:
    """Delete an issue.

    Args:
        issue_id: Issue ID to delete

    Raises:
        ValueError: If deletion fails
    """
    try:
        client = get_client()
        client.table("issues").delete().eq("id", issue_id).execute()
        # Note: PostgREST delete returns rows, but if ID didn't exist, it returns []
        # We don't necessarily want to fail if it didn't exist (idempotency)

    except APIError as e:
        logger.exception("Database error deleting issue %s", issue_id)
        raise ValueError(f"Failed to delete issue {issue_id}: {e}") from e


def update_issue_assignment(issue_id: int, assigned_to: str) -> None:
    """Update issue worker assignment.

    Args:
        issue_id: Issue ID to update
        assigned_to: Worker ID string

    Raises:
        ValueError: If inputs invalid or update fails
    """
    if not assigned_to or not assigned_to.strip():
        raise ValueError("Worker ID cannot be empty")

    try:
        client = get_client()

        # Validate issue exists and status
        issue = fetch_issue(issue_id)
        if issue.status == "completed":
            logger.warning("Updating assignment for completed issue %s", issue_id)

        client.table("issues").update({"assigned_to": assigned_to}).eq(
            "id", issue_id
        ).execute()

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
            return Patch.from_supabase(response.data[0])

        return None

    except APIError:
        logger.exception("Database error fetching pending patch for issue %s", issue_id)
        # Don't raise, just return None as "no patch found"
        return None


def update_patch_status(
    patch_id: int, status: str, log: Optional[logging.Logger] = None
) -> None:
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
        raise ValueError(
            f"Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}"
        )

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
