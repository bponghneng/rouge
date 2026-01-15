"""Tests for database operations."""

from unittest.mock import Mock, patch

import pytest

from rouge.core.database import (
    SupabaseConfig,
    create_comment,
    create_issue,
    delete_issue,
    fetch_all_issues,
    fetch_comments,
    fetch_issue,
    get_client,
    update_issue_assignment,
    update_issue_description,
    update_issue_status,
)
from rouge.core.models import Comment


@pytest.fixture
def mock_env(monkeypatch):
    """Mock environment variables."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test_key")


def test_supabase_config_validation_success(mock_env):
    """Test config validation with valid env vars."""
    config = SupabaseConfig()
    config.validate()  # Should not raise


def test_supabase_config_validation_missing_url(monkeypatch):
    """Test config validation fails with missing URL."""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test_key")

    config = SupabaseConfig()
    with pytest.raises(ValueError, match="SUPABASE_URL"):
        config.validate()


def test_supabase_config_validation_missing_key(monkeypatch):
    """Test config validation fails with missing key."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    config = SupabaseConfig()
    with pytest.raises(ValueError, match="SUPABASE_SERVICE_ROLE_KEY"):
        config.validate()


@patch("rouge.core.database.create_client")
def test_get_client(mock_create_client, mock_env):
    """Test get_client creates and returns client."""
    mock_client = Mock()
    mock_create_client.return_value = mock_client

    # Clear cache and global client
    get_client.cache_clear()
    import rouge.core.database

    rouge.core.database._client = None

    client = get_client()
    assert client is mock_client
    mock_create_client.assert_called_once()


@patch("rouge.core.database.get_client")
def test_create_issue_success(mock_get_client):
    """Test successful issue creation."""
    mock_client = Mock()
    mock_table = Mock()
    mock_insert = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.insert.return_value = mock_insert
    mock_execute.data = [{"id": 1, "description": "Test issue", "status": "pending"}]
    mock_insert.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    issue = create_issue("Test issue")
    assert issue.id == 1
    assert issue.description == "Test issue"
    assert issue.status == "pending"


@patch("rouge.core.database.get_client")
def test_create_issue_empty_description(mock_get_client):
    """Test creating issue with empty description fails."""
    with pytest.raises(ValueError, match="cannot be empty"):
        create_issue("")


@patch("rouge.core.database.get_client")
def test_create_issue_whitespace_only(mock_get_client):
    """Test creating issue with whitespace-only description fails."""
    with pytest.raises(ValueError, match="cannot be empty"):
        create_issue("   ")


@patch("rouge.core.database.get_client")
def test_fetch_issue_success(mock_get_client):
    """Test successful issue fetch."""
    mock_client = Mock()
    mock_table = Mock()
    mock_select = Mock()
    mock_eq = Mock()
    mock_maybe_single = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq
    mock_eq.maybe_single.return_value = mock_maybe_single
    mock_execute.data = {"id": 1, "description": "Test issue", "status": "pending"}
    mock_maybe_single.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    issue = fetch_issue(1)
    assert issue.id == 1
    assert issue.description == "Test issue"


@patch("rouge.core.database.get_client")
def test_fetch_issue_not_found(mock_get_client):
    """Test fetching non-existent issue."""
    mock_client = Mock()
    mock_table = Mock()
    mock_select = Mock()
    mock_eq = Mock()
    mock_maybe_single = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq
    mock_eq.maybe_single.return_value = mock_maybe_single
    mock_execute.data = None
    mock_maybe_single.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    with pytest.raises(ValueError, match="not found"):
        fetch_issue(999)


@patch("rouge.core.database.get_client")
def test_fetch_all_issues_success(mock_get_client):
    """Test fetching all issues."""
    mock_client = Mock()
    mock_table = Mock()
    mock_select = Mock()
    mock_order = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_select
    mock_select.order.return_value = mock_order
    mock_execute.data = [
        {"id": 1, "description": "Issue 1", "status": "pending"},
        {"id": 2, "description": "Issue 2", "status": "completed"},
    ]
    mock_order.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    issues = fetch_all_issues()
    assert len(issues) == 2
    assert issues[0].id == 1
    assert issues[1].id == 2


@patch("rouge.core.database.get_client")
def test_create_comment_success(mock_get_client):
    """Test successful comment creation without adw_id (backward compatibility)."""
    mock_client = Mock()
    mock_table = Mock()
    mock_insert = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.insert.return_value = mock_insert
    mock_execute.data = [
        {
            "id": 1,
            "issue_id": 1,
            "comment": "Test comment",
            "raw": {"test": "data"},
            "source": "test",
            "type": "unit",
            "adw_id": None,
        }
    ]
    mock_insert.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    comment_payload = Comment(
        issue_id=1,
        comment="Test comment",
        raw={"test": "data"},
        source="test",
        type="unit",
    )

    comment = create_comment(comment_payload)
    assert comment.issue_id == 1
    assert comment.comment == "Test comment"
    assert comment.raw == {"test": "data"}
    assert comment.source == "test"
    assert comment.type == "unit"
    assert comment.adw_id is None

    # Verify that adw_id was included in the insert data
    insert_call_args = mock_table.insert.call_args[0][0]
    assert "adw_id" in insert_call_args
    assert insert_call_args["adw_id"] is None


@patch("rouge.core.database.get_client")
def test_create_comment_with_adw_id(mock_get_client):
    """Test successful comment creation with adw_id."""
    mock_client = Mock()
    mock_table = Mock()
    mock_insert = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.insert.return_value = mock_insert
    mock_execute.data = [
        {
            "id": 1,
            "issue_id": 1,
            "comment": "Test comment with ADW ID",
            "raw": {"test": "data"},
            "source": "test",
            "type": "unit",
            "adw_id": "test-adw-123",
        }
    ]
    mock_insert.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    comment_payload = Comment(
        issue_id=1,
        comment="Test comment with ADW ID",
        raw={"test": "data"},
        source="test",
        type="unit",
        adw_id="test-adw-123",
    )

    comment = create_comment(comment_payload)
    assert comment.issue_id == 1
    assert comment.comment == "Test comment with ADW ID"
    assert comment.raw == {"test": "data"}
    assert comment.source == "test"
    assert comment.type == "unit"
    assert comment.adw_id == "test-adw-123"

    # Verify that adw_id was included in the insert data
    insert_call_args = mock_table.insert.call_args[0][0]
    assert "adw_id" in insert_call_args
    assert insert_call_args["adw_id"] == "test-adw-123"


@patch("rouge.core.database.get_client")
def test_fetch_comments_success(mock_get_client):
    """Test fetching comments for an issue."""
    mock_client = Mock()
    mock_table = Mock()
    mock_select = Mock()
    mock_eq = Mock()
    mock_order = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq
    mock_eq.order.return_value = mock_order
    mock_execute.data = [
        {"id": 1, "issue_id": 1, "comment": "Comment 1"},
        {"id": 2, "issue_id": 1, "comment": "Comment 2"},
    ]
    mock_order.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    comments = fetch_comments(1)
    assert len(comments) == 2
    assert comments[0].comment == "Comment 1"
    assert comments[1].comment == "Comment 2"


@patch("rouge.core.database.get_client")
def test_update_issue_status_success(mock_get_client):
    """Test successful status update."""
    mock_client = Mock()
    mock_table = Mock()
    mock_update = Mock()
    mock_eq = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.update.return_value = mock_update
    mock_update.eq.return_value = mock_eq
    mock_execute.data = [{"id": 1, "description": "Test issue", "status": "started"}]
    mock_eq.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    issue = update_issue_status(1, "started")
    assert issue.id == 1
    assert issue.status == "started"
    mock_table.update.assert_called_once_with({"status": "started"})


@patch("rouge.core.database.get_client")
def test_update_issue_status_to_completed(mock_get_client):
    """Test updating status to completed."""
    mock_client = Mock()
    mock_table = Mock()
    mock_update = Mock()
    mock_eq = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.update.return_value = mock_update
    mock_update.eq.return_value = mock_eq
    mock_execute.data = [{"id": 1, "description": "Test issue", "status": "completed"}]
    mock_eq.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    issue = update_issue_status(1, "completed")
    assert issue.status == "completed"


@patch("rouge.core.database.get_client")
def test_update_issue_status_invalid_status(mock_get_client):
    """Test updating with invalid status fails."""
    with pytest.raises(ValueError, match="Invalid status"):
        update_issue_status(1, "invalid_status")


@patch("rouge.core.database.get_client")
def test_update_issue_status_not_found(mock_get_client):
    """Test updating non-existent issue."""
    mock_client = Mock()
    mock_table = Mock()
    mock_update = Mock()
    mock_eq = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.update.return_value = mock_update
    mock_update.eq.return_value = mock_eq
    mock_execute.data = None
    mock_eq.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    with pytest.raises(ValueError, match="not found"):
        update_issue_status(999, "started")


@patch("rouge.core.database.get_client")
def test_update_issue_description_success(mock_get_client):
    """Test successful description update."""
    mock_client = Mock()
    mock_table = Mock()
    mock_update = Mock()
    mock_eq = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.update.return_value = mock_update
    mock_update.eq.return_value = mock_eq
    mock_execute.data = [{"id": 1, "description": "Updated description", "status": "pending"}]
    mock_eq.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    issue = update_issue_description(1, "Updated description")
    assert issue.id == 1
    assert issue.description == "Updated description"
    mock_table.update.assert_called_once_with({"description": "Updated description"})


@patch("rouge.core.database.get_client")
def test_update_issue_description_empty(mock_get_client):
    """Test updating with empty description fails."""
    with pytest.raises(ValueError, match="cannot be empty"):
        update_issue_description(1, "")


@patch("rouge.core.database.get_client")
def test_update_issue_description_whitespace_only(mock_get_client):
    """Test updating with whitespace-only description fails."""
    with pytest.raises(ValueError, match="cannot be empty"):
        update_issue_description(1, "   ")


@patch("rouge.core.database.get_client")
def test_update_issue_description_too_short(mock_get_client):
    """Test updating with too short description fails."""
    with pytest.raises(ValueError, match="at least 10 characters"):
        update_issue_description(1, "Short")


@patch("rouge.core.database.get_client")
def test_update_issue_description_too_long(mock_get_client):
    """Test updating with too long description fails."""
    long_description = "x" * 10001
    with pytest.raises(ValueError, match="cannot exceed 10000 characters"):
        update_issue_description(1, long_description)


@patch("rouge.core.database.get_client")
def test_update_issue_description_not_found(mock_get_client):
    """Test updating description of non-existent issue."""
    mock_client = Mock()
    mock_table = Mock()
    mock_update = Mock()
    mock_eq = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.update.return_value = mock_update
    mock_update.eq.return_value = mock_eq
    mock_execute.data = None
    mock_eq.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    with pytest.raises(ValueError, match="not found"):
        update_issue_description(999, "Valid description text here")


@patch("rouge.core.database.get_client")
def test_delete_issue_success(mock_get_client):
    """Test successful issue deletion."""
    mock_client = Mock()
    mock_table = Mock()
    mock_delete = Mock()
    mock_eq = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.delete.return_value = mock_delete
    mock_delete.eq.return_value = mock_eq
    mock_execute.data = [{"id": 1, "description": "Test issue", "status": "pending"}]
    mock_eq.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    result = delete_issue(1)
    assert result is True
    mock_table.delete.assert_called_once()
    mock_delete.eq.assert_called_once_with("id", 1)


@patch("rouge.core.database.get_client")
def test_delete_issue_not_found(mock_get_client):
    """Test deleting non-existent issue."""
    mock_client = Mock()
    mock_table = Mock()
    mock_delete = Mock()
    mock_eq = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.delete.return_value = mock_delete
    mock_delete.eq.return_value = mock_eq
    mock_execute.data = None
    mock_eq.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    with pytest.raises(ValueError, match="not found"):
        delete_issue(999)


@patch("rouge.core.database.get_client")
def test_delete_issue_with_comments(mock_get_client):
    """Test deleting issue cascades to comments.

    Note: This test verifies the delete operation is called correctly.
    The actual cascade delete behavior is handled by the database
    foreign key constraint with ON DELETE CASCADE.
    """
    mock_client = Mock()
    mock_table = Mock()
    mock_delete = Mock()
    mock_eq = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.delete.return_value = mock_delete
    mock_delete.eq.return_value = mock_eq
    # Simulate successful deletion of issue with comments
    mock_execute.data = [{"id": 1, "description": "Issue with comments", "status": "pending"}]
    mock_eq.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    result = delete_issue(1)
    assert result is True
    # Verify that delete was called on the issues table
    mock_table.delete.assert_called_once()
    # The cascade to comments is handled by the database, not in application code


@patch("rouge.core.database.fetch_issue")
@patch("rouge.core.database.get_client")
def test_update_issue_assignment_success(mock_get_client, mock_fetch_issue):
    """Test successful worker assignment."""
    # Mock fetch_issue to return a pending issue
    mock_issue = Mock()
    mock_issue.status = "pending"
    mock_fetch_issue.return_value = mock_issue

    # Mock the database client
    mock_client = Mock()
    mock_table = Mock()
    mock_update = Mock()
    mock_eq = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.update.return_value = mock_update
    mock_update.eq.return_value = mock_eq
    mock_execute.data = [
        {
            "id": 1,
            "description": "Test issue",
            "status": "pending",
            "assigned_to": "tydirium-1",
        }
    ]
    mock_eq.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    issue = update_issue_assignment(1, "tydirium-1")
    assert issue.id == 1
    assert issue.assigned_to == "tydirium-1"
    mock_table.update.assert_called_once_with({"assigned_to": "tydirium-1"})


@patch("rouge.core.database.fetch_issue")
@patch("rouge.core.database.get_client")
def test_update_issue_assignment_to_none(mock_get_client, mock_fetch_issue):
    """Test unassigning a worker (setting to None)."""
    # Mock fetch_issue to return a pending issue
    mock_issue = Mock()
    mock_issue.status = "pending"
    mock_fetch_issue.return_value = mock_issue

    # Mock the database client
    mock_client = Mock()
    mock_table = Mock()
    mock_update = Mock()
    mock_eq = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.update.return_value = mock_update
    mock_update.eq.return_value = mock_eq
    mock_execute.data = [
        {
            "id": 1,
            "description": "Test issue",
            "status": "pending",
            "assigned_to": None,
        }
    ]
    mock_eq.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    issue = update_issue_assignment(1, None)
    assert issue.id == 1
    assert issue.assigned_to is None
    mock_table.update.assert_called_once_with({"assigned_to": None})


@patch("rouge.core.database.fetch_issue")
def test_update_issue_assignment_rejects_started_issue(mock_fetch_issue):
    """Test that assignment is rejected for started issues."""
    # Mock fetch_issue to return a started issue
    mock_issue = Mock()
    mock_issue.status = "started"
    mock_fetch_issue.return_value = mock_issue

    with pytest.raises(ValueError, match="Only pending issues can be assigned"):
        update_issue_assignment(1, "tydirium-1")


@patch("rouge.core.database.fetch_issue")
def test_update_issue_assignment_rejects_completed_issue(mock_fetch_issue):
    """Test that assignment is rejected for completed issues."""
    # Mock fetch_issue to return a completed issue
    mock_issue = Mock()
    mock_issue.status = "completed"
    mock_fetch_issue.return_value = mock_issue

    with pytest.raises(ValueError, match="Only pending issues can be assigned"):
        update_issue_assignment(1, "alleycat-1")


@patch("rouge.core.database.get_client")
def test_update_issue_assignment_rejects_invalid_worker(mock_get_client):
    """Test that assignment is rejected for invalid worker IDs."""
    with pytest.raises(ValueError, match="Invalid worker ID"):
        update_issue_assignment(1, "invalid-worker")


@patch("rouge.core.database.fetch_issue")
def test_update_issue_assignment_nonexistent_issue(mock_fetch_issue):
    """Test assignment fails for non-existent issue."""
    mock_fetch_issue.side_effect = ValueError("Issue not found")

    with pytest.raises(ValueError, match="Failed to fetch issue"):
        update_issue_assignment(999, "tydirium-1")


@patch("rouge.core.database.fetch_issue")
@patch("rouge.core.database.get_client")
def test_update_issue_assignment_new_workers(mock_get_client, mock_fetch_issue):
    """Test assignment to new expanded worker pool IDs."""
    # Mock fetch_issue to return a pending issue
    mock_issue = Mock()
    mock_issue.status = "pending"
    mock_fetch_issue.return_value = mock_issue

    # Mock the database client
    mock_client = Mock()
    mock_table = Mock()
    mock_update = Mock()
    mock_eq = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.update.return_value = mock_update
    mock_update.eq.return_value = mock_eq
    mock_get_client.return_value = mock_client

    # Test all new worker IDs
    new_worker_ids = [
        "alleycat-2",
        "alleycat-3",
        "local-1",
        "local-2",
        "local-3",
        "tydirium-2",
        "tydirium-3",
    ]

    for worker_id in new_worker_ids:
        mock_execute.data = [
            {
                "id": 1,
                "description": "Test issue",
                "status": "pending",
                "assigned_to": worker_id,
            }
        ]
        mock_eq.execute.return_value = mock_execute

        issue = update_issue_assignment(1, worker_id)
        assert issue.assigned_to == worker_id


@patch("rouge.core.database.get_client")
def test_update_issue_assignment_rejects_invalid_new_worker(mock_get_client):
    """Test that assignment is rejected for invalid worker IDs not in expanded pool."""
    invalid_workers = ["alleycat-4", "local-4", "tydirium-4", "unknown-1"]

    for worker_id in invalid_workers:
        with pytest.raises(ValueError, match="Invalid worker ID"):
            update_issue_assignment(1, worker_id)


# Patch database operations tests


@patch("rouge.core.database.get_client")
def test_fetch_pending_patch_success(mock_get_client):
    """Test successful pending patch fetch."""
    from rouge.core.database import fetch_pending_patch

    mock_client = Mock()
    mock_table = Mock()
    mock_select = Mock()
    mock_eq1 = Mock()
    mock_eq2 = Mock()
    mock_order = Mock()
    mock_limit = Mock()
    mock_maybe_single = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq1
    mock_eq1.eq.return_value = mock_eq2
    mock_eq2.order.return_value = mock_order
    mock_order.limit.return_value = mock_limit
    mock_limit.maybe_single.return_value = mock_maybe_single
    mock_execute.data = {
        "id": 1,
        "issue_id": 10,
        "description": "Fix typo",
        "status": "pending",
    }
    mock_maybe_single.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    patch = fetch_pending_patch(10)
    assert patch.id == 1
    assert patch.issue_id == 10
    assert patch.description == "Fix typo"
    assert patch.status == "pending"


@patch("rouge.core.database.get_client")
def test_fetch_pending_patch_not_found(mock_get_client):
    """Test fetch_pending_patch raises ValueError when no pending patch exists."""
    from rouge.core.database import fetch_pending_patch

    mock_client = Mock()
    mock_table = Mock()
    mock_select = Mock()
    mock_eq1 = Mock()
    mock_eq2 = Mock()
    mock_order = Mock()
    mock_limit = Mock()
    mock_maybe_single = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq1
    mock_eq1.eq.return_value = mock_eq2
    mock_eq2.order.return_value = mock_order
    mock_order.limit.return_value = mock_limit
    mock_limit.maybe_single.return_value = mock_maybe_single
    mock_execute.data = None
    mock_maybe_single.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    with pytest.raises(ValueError, match="No pending patch found"):
        fetch_pending_patch(10)


@patch("rouge.core.database.get_client")
def test_update_patch_status_success(mock_get_client):
    """Test successful patch status update."""
    from rouge.core.database import update_patch_status

    mock_client = Mock()
    mock_table = Mock()
    mock_update = Mock()
    mock_eq = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.update.return_value = mock_update
    mock_update.eq.return_value = mock_eq
    mock_execute.data = [
        {
            "id": 1,
            "issue_id": 10,
            "description": "Fix typo",
            "status": "completed",
        }
    ]
    mock_eq.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    # Should not raise
    update_patch_status(1, "completed")


@patch("rouge.core.database.get_client")
def test_update_patch_status_invalid_status(mock_get_client):
    """Test update_patch_status raises ValueError for invalid status."""
    from rouge.core.database import update_patch_status

    with pytest.raises(ValueError, match="Invalid status"):
        update_patch_status(1, "invalid")


@patch("rouge.core.database.get_client")
def test_update_patch_status_not_found(mock_get_client):
    """Test update_patch_status raises ValueError when patch not found."""
    from rouge.core.database import update_patch_status

    mock_client = Mock()
    mock_table = Mock()
    mock_update = Mock()
    mock_eq = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.update.return_value = mock_update
    mock_update.eq.return_value = mock_eq
    mock_execute.data = []
    mock_eq.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    with pytest.raises(ValueError, match="not found"):
        update_patch_status(999, "completed")
