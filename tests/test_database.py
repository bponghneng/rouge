"""Tests for database operations."""

from unittest.mock import Mock, patch

import pytest

from rouge.core.database import (
    UNSET,
    SupabaseConfig,
    create_comment,
    create_issue,
    delete_issue,
    fetch_all_issues,
    fetch_comments,
    fetch_issue,
    get_client,
    update_issue,
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
    # Properties should not raise when accessed
    assert config.url == "https://test.supabase.co"
    assert config.key == "test_key"


def test_supabase_config_validation_missing_url(monkeypatch):
    """Test config validation fails with missing URL."""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test_key")

    config = SupabaseConfig()
    with pytest.raises(ValueError, match="SUPABASE_URL"):
        _ = config.url


def test_supabase_config_validation_missing_key(monkeypatch):
    """Test config validation fails with missing key."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    config = SupabaseConfig()
    with pytest.raises(ValueError, match="SUPABASE_SERVICE_ROLE_KEY"):
        _ = config.key


@patch("rouge.core.database.create_client")
def test_get_client(mock_create_client, mock_env):
    """Test get_client creates and returns client."""
    mock_client = Mock()
    mock_create_client.return_value = mock_client

    # Clear global client
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
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq
    mock_execute.data = [{"id": 1, "description": "Test issue", "status": "pending"}]
    mock_eq.execute.return_value = mock_execute
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
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.select.return_value = mock_select
    mock_select.eq.return_value = mock_eq
    mock_execute.data = []
    mock_eq.execute.return_value = mock_execute
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




# ============================================================================
# create_issue with issue_type and adw_id tests
# ============================================================================


@patch("rouge.core.database.get_client")
def test_create_issue_with_explicit_type_main(mock_get_client):
    """Test creating issue with explicit type='main'."""
    mock_client = Mock()
    mock_table = Mock()
    mock_insert = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.insert.return_value = mock_insert
    mock_execute.data = [
        {
            "id": 1,
            "description": "Test issue with type",
            "status": "pending",
            "type": "main",
            "adw_id": "abc12345",
        }
    ]
    mock_insert.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    issue = create_issue("Test issue with type", issue_type="main")
    assert issue.id == 1
    assert issue.description == "Test issue with type"
    assert issue.type == "main"

    # Verify the insert data included the type
    insert_call_args = mock_table.insert.call_args[0][0]
    assert insert_call_args["type"] == "main"


@patch("rouge.core.database.get_client")
def test_create_issue_with_explicit_type_patch(mock_get_client):
    """Test creating issue with explicit type='patch'."""
    mock_client = Mock()
    mock_table = Mock()
    mock_insert = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.insert.return_value = mock_insert
    mock_execute.data = [
        {
            "id": 2,
            "description": "Patch issue for bug fix",
            "status": "pending",
            "type": "patch",
            "adw_id": "xyz98765",
        }
    ]
    mock_insert.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    issue = create_issue("Patch issue for bug fix", issue_type="patch")
    assert issue.id == 2
    assert issue.description == "Patch issue for bug fix"
    assert issue.type == "patch"

    # Verify the insert data included the type
    insert_call_args = mock_table.insert.call_args[0][0]
    assert insert_call_args["type"] == "patch"


@patch("rouge.core.database.get_client")
def test_create_issue_with_explicit_adw_id(mock_get_client):
    """Test creating issue with explicit adw_id."""
    mock_client = Mock()
    mock_table = Mock()
    mock_insert = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.insert.return_value = mock_insert
    mock_execute.data = [
        {
            "id": 3,
            "description": "Test issue with custom adw_id",
            "status": "pending",
            "type": "main",
            "adw_id": "custom-adw-id",
        }
    ]
    mock_insert.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    issue = create_issue("Test issue with custom adw_id", adw_id="custom-adw-id")
    assert issue.id == 3
    assert issue.adw_id == "custom-adw-id"

    # Verify the insert data included the explicit adw_id
    insert_call_args = mock_table.insert.call_args[0][0]
    assert insert_call_args["adw_id"] == "custom-adw-id"


@patch("rouge.core.database.get_client")
def test_create_issue_with_type_and_adw_id(mock_get_client):
    """Test creating issue with both explicit type and adw_id."""
    mock_client = Mock()
    mock_table = Mock()
    mock_insert = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.insert.return_value = mock_insert
    mock_execute.data = [
        {
            "id": 4,
            "description": "Patch issue with custom ID",
            "status": "pending",
            "type": "patch",
            "adw_id": "patch-adw-123",
        }
    ]
    mock_insert.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    issue = create_issue("Patch issue with custom ID", issue_type="patch", adw_id="patch-adw-123")
    assert issue.id == 4
    assert issue.type == "patch"
    assert issue.adw_id == "patch-adw-123"

    # Verify both type and adw_id were included in insert data
    insert_call_args = mock_table.insert.call_args[0][0]
    assert insert_call_args["type"] == "patch"
    assert insert_call_args["adw_id"] == "patch-adw-123"


@patch("rouge.core.database.get_client")
def test_create_issue_default_type_is_main(mock_get_client):
    """Test that issue type defaults to 'main' when not specified."""
    mock_client = Mock()
    mock_table = Mock()
    mock_insert = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.insert.return_value = mock_insert
    mock_execute.data = [
        {
            "id": 5,
            "description": "Issue without explicit type",
            "status": "pending",
            "type": "main",
            "adw_id": "generated123",
        }
    ]
    mock_insert.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    issue = create_issue("Issue without explicit type")
    assert issue.type == "main"

    # Verify the insert data defaulted to 'main'
    insert_call_args = mock_table.insert.call_args[0][0]
    assert insert_call_args["type"] == "main"


@patch("rouge.core.database.get_client")
def test_create_issue_auto_generates_adw_id(mock_get_client):
    """Test that adw_id is auto-generated when not provided."""
    mock_client = Mock()
    mock_table = Mock()
    mock_insert = Mock()
    mock_execute = Mock()

    mock_client.table.return_value = mock_table
    mock_table.insert.return_value = mock_insert
    mock_execute.data = [
        {
            "id": 6,
            "description": "Issue with auto-generated adw_id",
            "status": "pending",
            "type": "main",
            "adw_id": "auto1234",
        }
    ]
    mock_insert.execute.return_value = mock_execute
    mock_get_client.return_value = mock_client

    create_issue("Issue with auto-generated adw_id")

    # Verify an adw_id was included in insert data (auto-generated)
    insert_call_args = mock_table.insert.call_args[0][0]
    assert "adw_id" in insert_call_args
    assert insert_call_args["adw_id"] is not None
    assert len(insert_call_args["adw_id"]) == 8  # make_adw_id generates 8-char IDs


@patch("rouge.core.database.get_client")
def test_create_issue_invalid_type(_mock_get_client):
    """Test creating issue with invalid type raises ValueError."""
    with pytest.raises(ValueError, match="Invalid issue_type"):
        create_issue("Test issue", issue_type="invalid")


# ============================================================================
# update_issue_branch tests
# ============================================================================




# ============================================================================
# update_issue tests
# ============================================================================


@patch("rouge.core.database.get_client")
def test_update_issue_single_field_assigned_to(mock_get_client):
    """Test updating only assigned_to field."""
    mock_client = Mock()
    mock_table = Mock()

    # Mock for the select check
    mock_select_check = Mock()
    mock_eq_check = Mock()
    mock_execute_check = Mock()
    mock_execute_check.data = [{"id": 1}]
    mock_eq_check.execute.return_value = mock_execute_check
    mock_select_check.eq.return_value = mock_eq_check

    # Mock for the update
    mock_update = Mock()
    mock_eq_update = Mock()
    mock_execute_update = Mock()
    mock_execute_update.data = [
        {
            "id": 1,
            "description": "Test issue",
            "status": "pending",
            "type": "main",
            "assigned_to": "tydirium-1",
        }
    ]
    mock_eq_update.execute.return_value = mock_execute_update
    mock_update.eq.return_value = mock_eq_update

    mock_table.select.return_value = mock_select_check
    mock_table.update.return_value = mock_update
    mock_client.table.return_value = mock_table
    mock_get_client.return_value = mock_client

    issue = update_issue(1, assigned_to="tydirium-1")
    assert issue.id == 1
    assert issue.assigned_to == "tydirium-1"
    mock_table.update.assert_called_once_with({"assigned_to": "tydirium-1"})


@patch("rouge.core.database.get_client")
def test_update_issue_single_field_issue_type(mock_get_client):
    """Test updating only issue_type field."""
    mock_client = Mock()
    mock_table = Mock()

    # Mock for the select check
    mock_select_check = Mock()
    mock_eq_check = Mock()
    mock_execute_check = Mock()
    mock_execute_check.data = [{"id": 1}]
    mock_eq_check.execute.return_value = mock_execute_check
    mock_select_check.eq.return_value = mock_eq_check

    # Mock for the update
    mock_update = Mock()
    mock_eq_update = Mock()
    mock_execute_update = Mock()
    mock_execute_update.data = [
        {
            "id": 1,
            "description": "Test issue",
            "status": "pending",
            "type": "patch",
        }
    ]
    mock_eq_update.execute.return_value = mock_execute_update
    mock_update.eq.return_value = mock_eq_update

    mock_table.select.return_value = mock_select_check
    mock_table.update.return_value = mock_update
    mock_client.table.return_value = mock_table
    mock_get_client.return_value = mock_client

    issue = update_issue(1, issue_type="patch")
    assert issue.id == 1
    assert issue.type == "patch"
    mock_table.update.assert_called_once_with({"type": "patch"})


@patch("rouge.core.database.get_client")
def test_update_issue_single_field_title(mock_get_client):
    """Test updating only title field."""
    mock_client = Mock()
    mock_table = Mock()

    # Mock for the select check
    mock_select_check = Mock()
    mock_eq_check = Mock()
    mock_execute_check = Mock()
    mock_execute_check.data = [{"id": 1}]
    mock_eq_check.execute.return_value = mock_execute_check
    mock_select_check.eq.return_value = mock_eq_check

    # Mock for the update
    mock_update = Mock()
    mock_eq_update = Mock()
    mock_execute_update = Mock()
    mock_execute_update.data = [
        {
            "id": 1,
            "description": "Test issue",
            "status": "pending",
            "title": "Updated Title",
        }
    ]
    mock_eq_update.execute.return_value = mock_execute_update
    mock_update.eq.return_value = mock_eq_update

    mock_table.select.return_value = mock_select_check
    mock_table.update.return_value = mock_update
    mock_client.table.return_value = mock_table
    mock_get_client.return_value = mock_client

    issue = update_issue(1, title="Updated Title")
    assert issue.id == 1
    assert issue.title == "Updated Title"
    mock_table.update.assert_called_once_with({"title": "Updated Title"})


@patch("rouge.core.database.get_client")
def test_update_issue_single_field_description(mock_get_client):
    """Test updating only description field."""
    mock_client = Mock()
    mock_table = Mock()

    # Mock for the select check
    mock_select_check = Mock()
    mock_eq_check = Mock()
    mock_execute_check = Mock()
    mock_execute_check.data = [{"id": 1}]
    mock_eq_check.execute.return_value = mock_execute_check
    mock_select_check.eq.return_value = mock_eq_check

    # Mock for the update
    mock_update = Mock()
    mock_eq_update = Mock()
    mock_execute_update = Mock()
    mock_execute_update.data = [
        {
            "id": 1,
            "description": "Updated description text",
            "status": "pending",
        }
    ]
    mock_eq_update.execute.return_value = mock_execute_update
    mock_update.eq.return_value = mock_eq_update

    mock_table.select.return_value = mock_select_check
    mock_table.update.return_value = mock_update
    mock_client.table.return_value = mock_table
    mock_get_client.return_value = mock_client

    issue = update_issue(1, description="Updated description text")
    assert issue.id == 1
    assert issue.description == "Updated description text"
    mock_table.update.assert_called_once_with({"description": "Updated description text"})


@patch("rouge.core.database.get_client")
def test_update_issue_multi_field_assigned_to_and_type(mock_get_client):
    """Test updating assigned_to and issue_type together."""
    mock_client = Mock()
    mock_table = Mock()

    # Mock for the select check
    mock_select_check = Mock()
    mock_eq_check = Mock()
    mock_execute_check = Mock()
    mock_execute_check.data = [{"id": 1}]
    mock_eq_check.execute.return_value = mock_execute_check
    mock_select_check.eq.return_value = mock_eq_check

    # Mock for the update
    mock_update = Mock()
    mock_eq_update = Mock()
    mock_execute_update = Mock()
    mock_execute_update.data = [
        {
            "id": 1,
            "description": "Test issue",
            "status": "pending",
            "type": "patch",
            "assigned_to": "alleycat-1",
        }
    ]
    mock_eq_update.execute.return_value = mock_execute_update
    mock_update.eq.return_value = mock_eq_update

    mock_table.select.return_value = mock_select_check
    mock_table.update.return_value = mock_update
    mock_client.table.return_value = mock_table
    mock_get_client.return_value = mock_client

    issue = update_issue(1, assigned_to="alleycat-1", issue_type="patch")
    assert issue.id == 1
    assert issue.assigned_to == "alleycat-1"
    assert issue.type == "patch"
    mock_table.update.assert_called_once_with({"assigned_to": "alleycat-1", "type": "patch"})


@patch("rouge.core.database.get_client")
def test_update_issue_multi_field_title_and_description(mock_get_client):
    """Test updating title and description together."""
    mock_client = Mock()
    mock_table = Mock()

    # Mock for the select check
    mock_select_check = Mock()
    mock_eq_check = Mock()
    mock_execute_check = Mock()
    mock_execute_check.data = [{"id": 1}]
    mock_eq_check.execute.return_value = mock_execute_check
    mock_select_check.eq.return_value = mock_eq_check

    # Mock for the update
    mock_update = Mock()
    mock_eq_update = Mock()
    mock_execute_update = Mock()
    mock_execute_update.data = [
        {
            "id": 1,
            "description": "New description here",
            "status": "pending",
            "title": "New Title",
        }
    ]
    mock_eq_update.execute.return_value = mock_execute_update
    mock_update.eq.return_value = mock_eq_update

    mock_table.select.return_value = mock_select_check
    mock_table.update.return_value = mock_update
    mock_client.table.return_value = mock_table
    mock_get_client.return_value = mock_client

    issue = update_issue(1, title="New Title", description="New description here")
    assert issue.id == 1
    assert issue.title == "New Title"
    assert issue.description == "New description here"
    mock_table.update.assert_called_once_with({"title": "New Title", "description": "New description here"})


@patch("rouge.core.database.get_client")
def test_update_issue_all_fields(mock_get_client):
    """Test updating all fields together."""
    mock_client = Mock()
    mock_table = Mock()

    # Mock for the select check
    mock_select_check = Mock()
    mock_eq_check = Mock()
    mock_execute_check = Mock()
    mock_execute_check.data = [{"id": 1}]
    mock_eq_check.execute.return_value = mock_execute_check
    mock_select_check.eq.return_value = mock_eq_check

    # Mock for the update
    mock_update = Mock()
    mock_eq_update = Mock()
    mock_execute_update = Mock()
    mock_execute_update.data = [
        {
            "id": 1,
            "description": "All fields updated",
            "status": "pending",
            "type": "patch",
            "assigned_to": "executor-1",
            "title": "Complete Update",
        }
    ]
    mock_eq_update.execute.return_value = mock_execute_update
    mock_update.eq.return_value = mock_eq_update

    mock_table.select.return_value = mock_select_check
    mock_table.update.return_value = mock_update
    mock_client.table.return_value = mock_table
    mock_get_client.return_value = mock_client

    issue = update_issue(
        1,
        assigned_to="executor-1",
        issue_type="patch",
        title="Complete Update",
        description="All fields updated",
    )
    assert issue.id == 1
    assert issue.assigned_to == "executor-1"
    assert issue.type == "patch"
    assert issue.title == "Complete Update"
    assert issue.description == "All fields updated"
    mock_table.update.assert_called_once_with(
        {
            "assigned_to": "executor-1",
            "type": "patch",
            "title": "Complete Update",
            "description": "All fields updated",
        }
    )


@patch("rouge.core.database.get_client")
def test_update_issue_partial_with_unset(mock_get_client):
    """Test partial update with UNSET - omitted fields remain unchanged."""
    mock_client = Mock()
    mock_table = Mock()

    # Mock for the select check
    mock_select_check = Mock()
    mock_eq_check = Mock()
    mock_execute_check = Mock()
    mock_execute_check.data = [{"id": 1}]
    mock_eq_check.execute.return_value = mock_execute_check
    mock_select_check.eq.return_value = mock_eq_check

    # Mock for the update
    mock_update = Mock()
    mock_eq_update = Mock()
    mock_execute_update = Mock()
    mock_execute_update.data = [
        {
            "id": 1,
            "description": "Unchanged description",
            "status": "pending",
            "type": "patch",
            "title": "Unchanged title",
        }
    ]
    mock_eq_update.execute.return_value = mock_execute_update
    mock_update.eq.return_value = mock_eq_update

    mock_table.select.return_value = mock_select_check
    mock_table.update.return_value = mock_update
    mock_client.table.return_value = mock_table
    mock_get_client.return_value = mock_client

    # Only update issue_type, leave others as UNSET (default)
    issue = update_issue(1, issue_type="patch")
    assert issue.id == 1
    assert issue.type == "patch"
    # Only type should be in the update dict
    mock_table.update.assert_called_once_with({"type": "patch"})


@patch("rouge.core.database.get_client")
def test_update_issue_clear_assigned_to(mock_get_client):
    """Test clearing assigned_to by setting to None."""
    mock_client = Mock()
    mock_table = Mock()

    # Mock for the select check
    mock_select_check = Mock()
    mock_eq_check = Mock()
    mock_execute_check = Mock()
    mock_execute_check.data = [{"id": 1}]
    mock_eq_check.execute.return_value = mock_execute_check
    mock_select_check.eq.return_value = mock_eq_check

    # Mock for the update
    mock_update = Mock()
    mock_eq_update = Mock()
    mock_execute_update = Mock()
    mock_execute_update.data = [
        {
            "id": 1,
            "description": "Test issue",
            "status": "pending",
            "assigned_to": None,
        }
    ]
    mock_eq_update.execute.return_value = mock_execute_update
    mock_update.eq.return_value = mock_eq_update

    mock_table.select.return_value = mock_select_check
    mock_table.update.return_value = mock_update
    mock_client.table.return_value = mock_table
    mock_get_client.return_value = mock_client

    issue = update_issue(1, assigned_to=None)
    assert issue.id == 1
    assert issue.assigned_to is None
    mock_table.update.assert_called_once_with({"assigned_to": None})


@patch("rouge.core.database.get_client")
def test_update_issue_clear_title(mock_get_client):
    """Test clearing title by setting to None."""
    mock_client = Mock()
    mock_table = Mock()

    # Mock for the select check
    mock_select_check = Mock()
    mock_eq_check = Mock()
    mock_execute_check = Mock()
    mock_execute_check.data = [{"id": 1}]
    mock_eq_check.execute.return_value = mock_execute_check
    mock_select_check.eq.return_value = mock_eq_check

    # Mock for the update
    mock_update = Mock()
    mock_eq_update = Mock()
    mock_execute_update = Mock()
    mock_execute_update.data = [
        {
            "id": 1,
            "description": "Test issue",
            "status": "pending",
            "title": None,
        }
    ]
    mock_eq_update.execute.return_value = mock_execute_update
    mock_update.eq.return_value = mock_eq_update

    mock_table.select.return_value = mock_select_check
    mock_table.update.return_value = mock_update
    mock_client.table.return_value = mock_table
    mock_get_client.return_value = mock_client

    issue = update_issue(1, title=None)
    assert issue.id == 1
    assert issue.title is None
    mock_table.update.assert_called_once_with({"title": None})


@patch("rouge.core.database.get_client")
def test_update_issue_invalid_worker_id(mock_get_client):
    """Test validation error for invalid worker ID."""
    with pytest.raises(ValueError, match="Invalid worker ID 'invalid-worker'"):
        update_issue(1, assigned_to="invalid-worker")


@patch("rouge.core.database.get_client")
def test_update_issue_invalid_type(mock_get_client):
    """Test validation error for invalid issue type."""
    with pytest.raises(ValueError, match="Invalid issue_type 'invalid'"):
        update_issue(1, issue_type="invalid")


@patch("rouge.core.database.get_client")
def test_update_issue_empty_title(mock_get_client):
    """Test validation error for empty title."""
    with pytest.raises(ValueError, match="Title cannot be empty/whitespace"):
        update_issue(1, title="")


@patch("rouge.core.database.get_client")
def test_update_issue_whitespace_only_title(mock_get_client):
    """Test validation error for whitespace-only title."""
    with pytest.raises(ValueError, match="Title cannot be empty/whitespace"):
        update_issue(1, title="   ")


@patch("rouge.core.database.get_client")
def test_update_issue_empty_description(mock_get_client):
    """Test validation error for empty description."""
    with pytest.raises(ValueError, match="Description cannot be empty"):
        update_issue(1, description="")


@patch("rouge.core.database.get_client")
def test_update_issue_whitespace_only_description(mock_get_client):
    """Test validation error for whitespace-only description."""
    with pytest.raises(ValueError, match="Description cannot be empty"):
        update_issue(1, description="   ")


@patch("rouge.core.database.get_client")
def test_update_issue_description_too_short(mock_get_client):
    """Test validation error for description that is too short."""
    with pytest.raises(ValueError, match="Description must be at least 10 characters"):
        update_issue(1, description="Short")


@patch("rouge.core.database.get_client")
def test_update_issue_empty_worker_id(mock_get_client):
    """Test validation error for empty worker ID string."""
    with pytest.raises(ValueError, match="Worker ID cannot be empty"):
        update_issue(1, assigned_to="")


@patch("rouge.core.database.get_client")
def test_update_issue_whitespace_only_worker_id(mock_get_client):
    """Test validation error for whitespace-only worker ID."""
    with pytest.raises(ValueError, match="Worker ID cannot be empty"):
        update_issue(1, assigned_to="   ")


@patch("rouge.core.database.get_client")
def test_update_issue_worker_id_type_error(mock_get_client):
    """Test type error for non-string worker ID."""
    with pytest.raises(TypeError, match="Worker ID must be a string"):
        update_issue(1, assigned_to=123)


@patch("rouge.core.database.get_client")
def test_update_issue_no_fields_provided(mock_get_client):
    """Test validation error when no fields are provided for update."""
    with pytest.raises(ValueError, match="No fields provided for update"):
        update_issue(1)


@patch("rouge.core.database.get_client")
def test_update_issue_all_fields_unset(mock_get_client):
    """Test validation error when all fields are explicitly UNSET."""
    with pytest.raises(ValueError, match="No fields provided for update"):
        update_issue(1, assigned_to=UNSET, issue_type=UNSET, title=UNSET, description=UNSET)


@patch("rouge.core.database.get_client")
def test_update_issue_not_found(mock_get_client):
    """Test error when updating non-existent issue."""
    mock_client = Mock()
    mock_table = Mock()

    # Mock for the select check (returns empty list)
    mock_select_check = Mock()
    mock_eq_check = Mock()
    mock_execute_check = Mock()
    mock_execute_check.data = []
    mock_eq_check.execute.return_value = mock_execute_check
    mock_select_check.eq.return_value = mock_eq_check

    mock_table.select.return_value = mock_select_check
    mock_client.table.return_value = mock_table
    mock_get_client.return_value = mock_client

    with pytest.raises(ValueError, match="Issue with id 999 not found"):
        update_issue(999, title="New Title")


@patch("rouge.core.database.get_client")
def test_update_issue_trims_whitespace(mock_get_client):
    """Test that string fields are trimmed of whitespace."""
    mock_client = Mock()
    mock_table = Mock()

    # Mock for the select check
    mock_select_check = Mock()
    mock_eq_check = Mock()
    mock_execute_check = Mock()
    mock_execute_check.data = [{"id": 1}]
    mock_eq_check.execute.return_value = mock_execute_check
    mock_select_check.eq.return_value = mock_eq_check

    # Mock for the update
    mock_update = Mock()
    mock_eq_update = Mock()
    mock_execute_update = Mock()
    mock_execute_update.data = [
        {
            "id": 1,
            "description": "Trimmed description",
            "status": "pending",
            "title": "Trimmed title",
            "assigned_to": "tydirium-1",
        }
    ]
    mock_eq_update.execute.return_value = mock_execute_update
    mock_update.eq.return_value = mock_eq_update

    mock_table.select.return_value = mock_select_check
    mock_table.update.return_value = mock_update
    mock_client.table.return_value = mock_table
    mock_get_client.return_value = mock_client

    issue = update_issue(
        1,
        assigned_to="  tydirium-1  ",
        title="  Trimmed title  ",
        description="  Trimmed description  ",
    )
    assert issue.title == "Trimmed title"
    assert issue.description == "Trimmed description"
    assert issue.assigned_to == "tydirium-1"
    # Verify trimmed values were passed to database
    mock_table.update.assert_called_once_with(
        {
            "assigned_to": "tydirium-1",
            "title": "Trimmed title",
            "description": "Trimmed description",
        }
    )


@patch("rouge.core.database.get_client")
def test_update_issue_valid_worker_ids(mock_get_client):
    """Test updating with all valid worker IDs."""
    mock_client = Mock()
    mock_table = Mock()

    # Mock for the select check
    mock_select_check = Mock()
    mock_eq_check = Mock()
    mock_execute_check = Mock()
    mock_execute_check.data = [{"id": 1}]
    mock_eq_check.execute.return_value = mock_execute_check
    mock_select_check.eq.return_value = mock_eq_check

    # Mock for the update
    mock_update = Mock()
    mock_eq_update = Mock()
    mock_execute_update = Mock()

    mock_table.select.return_value = mock_select_check
    mock_table.update.return_value = mock_update
    mock_update.eq.return_value = mock_eq_update
    mock_client.table.return_value = mock_table
    mock_get_client.return_value = mock_client

    valid_workers = [
        "alleycat-1",
        "alleycat-2",
        "alleycat-3",
        "executor-1",
        "executor-2",
        "executor-3",
        "local-1",
        "local-2",
        "local-3",
        "tydirium-1",
        "tydirium-2",
        "tydirium-3",
        "xwing-1",
        "xwing-2",
        "xwing-3",
    ]

    for worker_id in valid_workers:
        mock_execute_update.data = [
            {
                "id": 1,
                "description": "Test issue",
                "status": "pending",
                "assigned_to": worker_id,
            }
        ]
        mock_eq_update.execute.return_value = mock_execute_update

        issue = update_issue(1, assigned_to=worker_id)
        assert issue.assigned_to == worker_id


@patch("rouge.core.database.get_client")
def test_update_issue_both_types(mock_get_client):
    """Test updating with both valid issue types (main and patch)."""
    mock_client = Mock()
    mock_table = Mock()

    # Mock for the select check
    mock_select_check = Mock()
    mock_eq_check = Mock()
    mock_execute_check = Mock()
    mock_execute_check.data = [{"id": 1}]
    mock_eq_check.execute.return_value = mock_execute_check
    mock_select_check.eq.return_value = mock_eq_check

    # Mock for the update
    mock_update = Mock()
    mock_eq_update = Mock()
    mock_execute_update = Mock()

    mock_table.select.return_value = mock_select_check
    mock_table.update.return_value = mock_update
    mock_update.eq.return_value = mock_eq_update
    mock_client.table.return_value = mock_table
    mock_get_client.return_value = mock_client

    for issue_type in ["main", "patch"]:
        mock_execute_update.data = [
            {
                "id": 1,
                "description": "Test issue",
                "status": "pending",
                "type": issue_type,
            }
        ]
        mock_eq_update.execute.return_value = mock_execute_update

        issue = update_issue(1, issue_type=issue_type)
        assert issue.type == issue_type


@patch("rouge.core.database.get_client")
def test_update_issue_single_field_status(mock_get_client):
    """Test updating only status field."""
    mock_client = Mock()
    mock_table = Mock()

    # Mock for the select check
    mock_select_check = Mock()
    mock_eq_check = Mock()
    mock_execute_check = Mock()
    mock_execute_check.data = [{"id": 1}]
    mock_eq_check.execute.return_value = mock_execute_check
    mock_select_check.eq.return_value = mock_eq_check

    # Mock for the update
    mock_update = Mock()
    mock_eq_update = Mock()
    mock_execute_update = Mock()
    mock_execute_update.data = [
        {
            "id": 1,
            "description": "Test issue",
            "status": "completed",
        }
    ]
    mock_eq_update.execute.return_value = mock_execute_update
    mock_update.eq.return_value = mock_eq_update

    mock_table.select.return_value = mock_select_check
    mock_table.update.return_value = mock_update
    mock_client.table.return_value = mock_table
    mock_get_client.return_value = mock_client

    issue = update_issue(1, status="completed")
    assert issue.id == 1
    assert issue.status == "completed"
    mock_table.update.assert_called_once_with({"status": "completed"})


@patch("rouge.core.database.get_client")
def test_update_issue_single_field_branch(mock_get_client):
    """Test updating only branch field."""
    mock_client = Mock()
    mock_table = Mock()

    # Mock for the select check
    mock_select_check = Mock()
    mock_eq_check = Mock()
    mock_execute_check = Mock()
    mock_execute_check.data = [{"id": 1}]
    mock_eq_check.execute.return_value = mock_execute_check
    mock_select_check.eq.return_value = mock_eq_check

    # Mock for the update
    mock_update = Mock()
    mock_eq_update = Mock()
    mock_execute_update = Mock()
    mock_execute_update.data = [
        {
            "id": 1,
            "description": "Test issue",
            "status": "started",
            "branch": "adw-12345678",
        }
    ]
    mock_eq_update.execute.return_value = mock_execute_update
    mock_update.eq.return_value = mock_eq_update

    mock_table.select.return_value = mock_select_check
    mock_table.update.return_value = mock_update
    mock_client.table.return_value = mock_table
    mock_get_client.return_value = mock_client

    issue = update_issue(1, branch="adw-12345678")
    assert issue.id == 1
    assert issue.branch == "adw-12345678"
    mock_table.update.assert_called_once_with({"branch": "adw-12345678"})


@patch("rouge.core.database.get_client")
def test_update_issue_status_and_branch(mock_get_client):
    """Test updating status and branch together."""
    mock_client = Mock()
    mock_table = Mock()

    # Mock for the select check
    mock_select_check = Mock()
    mock_eq_check = Mock()
    mock_execute_check = Mock()
    mock_execute_check.data = [{"id": 1}]
    mock_eq_check.execute.return_value = mock_execute_check
    mock_select_check.eq.return_value = mock_eq_check

    # Mock for the update
    mock_update = Mock()
    mock_eq_update = Mock()
    mock_execute_update = Mock()
    mock_execute_update.data = [
        {
            "id": 1,
            "description": "Test issue",
            "status": "started",
            "branch": "feature/new-branch",
        }
    ]
    mock_eq_update.execute.return_value = mock_execute_update
    mock_update.eq.return_value = mock_eq_update

    mock_table.select.return_value = mock_select_check
    mock_table.update.return_value = mock_update
    mock_client.table.return_value = mock_table
    mock_get_client.return_value = mock_client

    issue = update_issue(1, status="started", branch="feature/new-branch")
    assert issue.id == 1
    assert issue.status == "started"
    assert issue.branch == "feature/new-branch"
    mock_table.update.assert_called_once_with({"status": "started", "branch": "feature/new-branch"})


@patch("rouge.core.database.get_client")
def test_update_issue_invalid_status(mock_get_client):
    """Test validation error for invalid status."""
    with pytest.raises(ValueError, match="Invalid status 'invalid'"):
        update_issue(1, status="invalid")


@patch("rouge.core.database.get_client")
def test_update_issue_all_valid_statuses(mock_get_client):
    """Test updating with all valid statuses."""
    mock_client = Mock()
    mock_table = Mock()

    # Mock for the select check
    mock_select_check = Mock()
    mock_eq_check = Mock()
    mock_execute_check = Mock()
    mock_execute_check.data = [{"id": 1}]
    mock_eq_check.execute.return_value = mock_execute_check
    mock_select_check.eq.return_value = mock_eq_check

    # Mock for the update
    mock_update = Mock()
    mock_eq_update = Mock()
    mock_execute_update = Mock()

    mock_table.select.return_value = mock_select_check
    mock_table.update.return_value = mock_update
    mock_update.eq.return_value = mock_eq_update
    mock_client.table.return_value = mock_table
    mock_get_client.return_value = mock_client

    valid_statuses = ["pending", "started", "completed", "failed"]

    for status in valid_statuses:
        mock_execute_update.data = [
            {
                "id": 1,
                "description": "Test issue",
                "status": status,
            }
        ]
        mock_eq_update.execute.return_value = mock_execute_update

        issue = update_issue(1, status=status)
        assert issue.status == status


@patch("rouge.core.database.get_client")
def test_update_issue_empty_branch(mock_get_client):
    """Test validation error for empty branch."""
    with pytest.raises(ValueError, match="Branch cannot be empty"):
        update_issue(1, branch="")


@patch("rouge.core.database.get_client")
def test_update_issue_whitespace_only_branch(mock_get_client):
    """Test validation error for whitespace-only branch."""
    with pytest.raises(ValueError, match="Branch cannot be empty"):
        update_issue(1, branch="   ")


@patch("rouge.core.database.get_client")
def test_update_issue_branch_trims_whitespace(mock_get_client):
    """Test that branch is trimmed of whitespace."""
    mock_client = Mock()
    mock_table = Mock()

    # Mock for the select check
    mock_select_check = Mock()
    mock_eq_check = Mock()
    mock_execute_check = Mock()
    mock_execute_check.data = [{"id": 1}]
    mock_eq_check.execute.return_value = mock_execute_check
    mock_select_check.eq.return_value = mock_eq_check

    # Mock for the update
    mock_update = Mock()
    mock_eq_update = Mock()
    mock_execute_update = Mock()
    mock_execute_update.data = [
        {
            "id": 1,
            "description": "Test issue",
            "status": "started",
            "branch": "trimmed-branch",
        }
    ]
    mock_eq_update.execute.return_value = mock_execute_update
    mock_update.eq.return_value = mock_eq_update

    mock_table.select.return_value = mock_select_check
    mock_table.update.return_value = mock_update
    mock_client.table.return_value = mock_table
    mock_get_client.return_value = mock_client

    issue = update_issue(1, branch="  trimmed-branch  ")
    assert issue.branch == "trimmed-branch"
    # Verify trimmed value was passed to database
    mock_table.update.assert_called_once_with({"branch": "trimmed-branch"})
