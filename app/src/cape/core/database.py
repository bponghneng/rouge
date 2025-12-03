"""Supabase client and helper functions for Cape issue workflow."""

import logging
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional, cast

import httpx
from dotenv import load_dotenv
from postgrest.exceptions import APIError
from supabase import Client, create_client
from supabase.lib.client_options import SyncClientOptions

from cape.core.models import CapeComment, CapeIssue

# Load environment variables early so Supabase config picks them up
load_dotenv()

logger = logging.getLogger(__name__)

SupabaseRow = Dict[str, Any]
SupabaseRows = List[SupabaseRow]

# ============================================================================
# Configuration
# ============================================================================


class SupabaseConfig:
    """Configuration for Supabase connection."""

    def __init__(self) -> None:
        self.url: Optional[str] = os.environ.get("SUPABASE_URL")
        self.service_role_key: Optional[str] = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    def validate(self) -> None:
        """Validate required environment variables are set."""
        missing = []

        if not self.url:
            missing.append("SUPABASE_URL")
        if not self.service_role_key:
            missing.append("SUPABASE_SERVICE_ROLE_KEY")

        if missing:
            raise ValueError(
                f"Missing required Supabase environment variables: "
                f"{', '.join(missing)}. "
                f"Please set these in your environment or .env file."
            )


# ============================================================================
# Client Singleton
# ============================================================================

_client: Optional[Client] = None
_HTTPX_CLIENT: Optional[httpx.Client] = None


def _build_http_client() -> httpx.Client:
    """Build an httpx client configured for Supabase interactions."""
    timeout_seconds = float(os.environ.get("SUPABASE_HTTP_TIMEOUT", "30"))
    verify_env = os.environ.get("SUPABASE_HTTP_VERIFY", "true").lower()
    verify = verify_env not in {"0", "false", "no"}
    return httpx.Client(timeout=timeout_seconds, verify=verify)


def _get_http_client() -> httpx.Client:
    global _HTTPX_CLIENT
    if _HTTPX_CLIENT is None:
        _HTTPX_CLIENT = _build_http_client()
    return _HTTPX_CLIENT


@lru_cache()
def get_client() -> Client:
    """Get or create the global Supabase client instance."""
    global _client

    if _client is None:
        config = SupabaseConfig()
        config.validate()

        assert config.url is not None
        assert config.service_role_key is not None

        client_options = SyncClientOptions(httpx_client=_get_http_client())
        _client = create_client(config.url, config.service_role_key, client_options)
        logger.info("Supabase client initialized")

    return _client


# ============================================================================
# Issue Operations
# ============================================================================


def fetch_issue(issue_id: int) -> CapeIssue:
    """Fetch issue from Supabase by ID."""
    client = get_client()

    try:
        response = (
            client.table("cape_issues").select("*").eq("id", issue_id).maybe_single().execute()
        )

        if response is None:
            raise ValueError(f"Empty response when fetching issue {issue_id}")

        response_data = cast(Optional[SupabaseRow], response.data)
        if response_data is None:
            raise ValueError(f"Issue with id {issue_id} not found")

        return CapeIssue.from_supabase(response_data)

    except APIError as e:
        logger.error(f"Database error fetching issue {issue_id}: {e}")
        raise ValueError(f"Failed to fetch issue {issue_id}: {e}") from e


def fetch_all_issues() -> List[CapeIssue]:
    """Fetch all issues ordered by creation date (newest first).

    Returns:
        List of CapeIssue objects. Returns empty list if no issues exist.

    Raises:
        ValueError: If database operation fails.
    """
    client = get_client()

    try:
        response = client.table("cape_issues").select("*").order("created_at", desc=True).execute()

        rows = cast(Optional[SupabaseRows], response.data)
        if not rows:
            return []

        return [CapeIssue.from_supabase(row) for row in rows]

    except APIError as e:
        logger.error(f"Database error fetching all issues: {e}")
        raise ValueError(f"Failed to fetch issues: {e}") from e


# ============================================================================
# Comment Operations
# ============================================================================


def create_comment(comment: CapeComment) -> CapeComment:
    """Create a comment on an issue from a CapeComment payload."""
    client = get_client()

    comment_data: SupabaseRow = {
        "issue_id": comment.issue_id,
        "comment": comment.comment.strip(),
        "raw": comment.raw or {},
        "source": comment.source,
        "type": comment.type,
    }

    try:
        response = client.table("cape_comments").insert(comment_data).execute()

        rows = cast(Optional[SupabaseRows], response.data)
        if not rows:
            raise ValueError("Comment creation returned no data")

        first_row = cast(SupabaseRow, rows[0])
        return CapeComment(**first_row)

    except APIError as e:
        logger.error("Database error creating comment on issue %s: %s", comment.issue_id, e)
        raise ValueError(f"Failed to create comment on issue {comment.issue_id}: {e}") from e


def fetch_comments(issue_id: int) -> List[CapeComment]:
    """Fetch all comments for an issue in chronological order.

    Args:
        issue_id: The ID of the issue to fetch comments for.

    Returns:
        List of CapeComment objects. Returns empty list if no comments exist.

    Raises:
        ValueError: If database operation fails.
    """
    client = get_client()

    try:
        response = (
            client.table("cape_comments")
            .select("*")
            .eq("issue_id", issue_id)
            .order("created_at", desc=True)
            .execute()
        )

        rows = cast(Optional[SupabaseRows], response.data)
        if not rows:
            return []

        return [CapeComment(**row) for row in rows]

    except APIError as e:
        logger.error(f"Database error fetching comments for issue {issue_id}: {e}")
        raise ValueError(f"Failed to fetch comments for issue {issue_id}: {e}") from e


def create_issue(description: str, title: Optional[str] = None) -> CapeIssue:
    """Create a new Cape issue with the given description.

    Args:
        description: The issue description text. Will be trimmed of leading/trailing whitespace.
                    Must not be empty after trimming.
        title: Optional title for the issue.

    Returns:
        CapeIssue: The created issue with database-generated id and timestamps.

    Raises:
        ValueError: If description is empty after trimming, or if database operation fails.
    """
    description_clean = description.strip()

    description_length = len(description_clean)

    if description_length == 0:
        raise ValueError("Issue description cannot be empty")

    if description_length < 10 or description_length > 10000:
        raise ValueError("Issue description must be between 10 and 10000 characters")

    client = get_client()

    issue_data: SupabaseRow = {
        "description": description_clean,
        "status": "pending",
    }

    if title:
        title_clean = title.strip()
        if len(title_clean) > 255:
            raise ValueError("Issue title cannot exceed 255 characters")
        issue_data["title"] = title_clean

    try:
        response = client.table("cape_issues").insert(issue_data).execute()

        rows = cast(Optional[SupabaseRows], response.data)
        if not rows:
            raise ValueError("Issue creation returned no data")

        first_row = cast(SupabaseRow, rows[0])
        return CapeIssue(**first_row)

    except APIError as e:
        logger.error(f"Database error creating issue: {e}")
        raise ValueError(f"Failed to create issue: {e}") from e


def update_issue_status(issue_id: int, status: str) -> CapeIssue:
    """Update the status of an existing issue.

    Args:
        issue_id: The ID of the issue to update.
        status: The new status value. Must be one of: "pending", "started", "completed".

    Returns:
        CapeIssue: The updated issue with new status and updated timestamp.

    Raises:
        ValueError: If status is invalid, issue not found, or database operation fails.
    """
    valid_statuses = ["pending", "started", "completed"]
    if status not in valid_statuses:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {', '.join(valid_statuses)}")

    client = get_client()

    update_data: SupabaseRow = {
        "status": status,
    }

    try:
        response = client.table("cape_issues").update(update_data).eq("id", issue_id).execute()

        rows = cast(Optional[SupabaseRows], response.data)
        if not rows:
            raise ValueError(f"Issue with id {issue_id} not found")

        first_row = cast(SupabaseRow, rows[0])
        return CapeIssue(**first_row)

    except APIError as e:
        logger.error(f"Database error updating issue {issue_id} status: {e}")
        raise ValueError(f"Failed to update issue {issue_id} status: {e}") from e


def update_issue_description(issue_id: int, description: str) -> CapeIssue:
    """Update the description of an existing issue.

    Args:
        issue_id: The ID of the issue to update.
        description: The new description text. Will be trimmed of leading/trailing whitespace.
                    Must be between 10 and 10000 characters after trimming.

    Returns:
        CapeIssue: The updated issue with new description and updated timestamp.

    Raises:
        ValueError: If description is invalid, issue not found, or database operation fails.
    """
    description_clean = description.strip()

    if not description_clean:
        raise ValueError("Issue description cannot be empty")

    if len(description_clean) < 10:
        raise ValueError("Issue description must be at least 10 characters")

    if len(description_clean) > 10000:
        raise ValueError("Issue description cannot exceed 10000 characters")

    client = get_client()

    update_data: SupabaseRow = {
        "description": description_clean,
    }

    try:
        response = client.table("cape_issues").update(update_data).eq("id", issue_id).execute()

        rows = cast(Optional[SupabaseRows], response.data)
        if not rows:
            raise ValueError(f"Issue with id {issue_id} not found")

        first_row = cast(SupabaseRow, rows[0])
        return CapeIssue(**first_row)

    except APIError as e:
        logger.error(f"Database error updating issue {issue_id} description: {e}")
        raise ValueError(f"Failed to update issue {issue_id} description: {e}") from e


def delete_issue(issue_id: int) -> bool:
    """Delete an issue and its associated comments from the database.

    This operation will cascade delete all comments associated with the issue
    if the database foreign key constraint is configured with ON DELETE CASCADE.

    Args:
        issue_id: The ID of the issue to delete.

    Returns:
        bool: True if the issue was successfully deleted.

    Raises:
        ValueError: If issue not found or database operation fails.
    """
    client = get_client()

    try:
        response = client.table("cape_issues").delete().eq("id", issue_id).execute()

        if not response.data:
            raise ValueError(f"Issue with id {issue_id} not found")

        logger.info(f"Successfully deleted issue {issue_id}")
        return True

    except APIError as e:
        logger.error(f"Database error deleting issue {issue_id}: {e}")
        raise ValueError(f"Failed to delete issue {issue_id}: {e}") from e


def update_issue_assignment(issue_id: int, assigned_to: Optional[str]) -> CapeIssue:
    """Update the worker assignment of an existing issue.

    Args:
        issue_id: The ID of the issue to update.
        assigned_to: The worker ID to assign. Must be one of: None, "alleycat-1",
                    "alleycat-2", "alleycat-3", "hailmary-1", "hailmary-2",
                    "hailmary-3", "tydirium-1", "tydirium-2", "tydirium-3".

    Returns:
        CapeIssue: The updated issue with new assignment and updated timestamp.

    Raises:
        ValueError: If assigned_to is invalid, issue not found, issue is not pending,
                   or database operation fails.
    """
    # Validate assigned_to parameter
    valid_workers = [
        None,
        "alleycat-1",
        "alleycat-2",
        "alleycat-3",
        "hailmary-1",
        "hailmary-2",
        "hailmary-3",
        "tydirium-1",
        "tydirium-2",
        "tydirium-3",
    ]
    if assigned_to not in valid_workers:
        raise ValueError(
            f"Invalid worker ID '{assigned_to}'. Must be one of: "
            f"{', '.join(repr(w) for w in valid_workers)}"
        )

    # First, fetch the issue to check its status
    try:
        current_issue = fetch_issue(issue_id)
    except ValueError as e:
        raise ValueError(f"Failed to fetch issue {issue_id}: {e}") from e

    # Only allow assignment for pending issues
    if current_issue.status != "pending":
        raise ValueError(
            f"Cannot assign worker to issue {issue_id} with status '{current_issue.status}'. "
            f"Only pending issues can be assigned."
        )

    client = get_client()

    update_data: SupabaseRow = {
        "assigned_to": assigned_to,
    }

    try:
        response = client.table("cape_issues").update(update_data).eq("id", issue_id).execute()

        rows = cast(Optional[SupabaseRows], response.data)
        if not rows:
            raise ValueError(f"Issue with id {issue_id} not found")

        first_row = cast(SupabaseRow, rows[0])
        return CapeIssue(**first_row)

    except APIError as e:
        logger.error(f"Database error updating issue {issue_id} assignment: {e}")
        raise ValueError(f"Failed to update issue {issue_id} assignment: {e}") from e
