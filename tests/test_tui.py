"""Tests for TUI auto-refresh functionality and new widget components."""

from datetime import datetime
from unittest.mock import Mock, PropertyMock, patch

import pytest

from cape.core.models import CapeComment, CapeIssue
from cape.tui.components.comments import Comments
from cape.tui.components.issue_form import IssueForm
from cape.tui.screens.issue_detail_screen import IssueDetailScreen


@pytest.fixture
def mock_issue_started():
    """Create a mock issue with 'started' status."""
    return CapeIssue(
        id=1,
        description="Test issue with started status",
        status="started",
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        updated_at=datetime(2024, 1, 1, 12, 30, 0),
    )


@pytest.fixture
def mock_issue_pending():
    """Create a mock issue with 'pending' status."""
    return CapeIssue(
        id=2,
        description="Test issue with pending status",
        status="pending",
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        updated_at=datetime(2024, 1, 1, 12, 30, 0),
    )


@pytest.fixture
def mock_issue_completed():
    """Create a mock issue with 'completed' status."""
    return CapeIssue(
        id=3,
        description="Test issue with completed status",
        status="completed",
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        updated_at=datetime(2024, 1, 1, 13, 0, 0),
    )


@pytest.fixture
def mock_comments():
    """Create mock comments."""
    return [
        CapeComment(
            id=1,
            issue_id=1,
            comment="First comment",
            created_at=datetime(2024, 1, 1, 12, 10, 0),
        ),
        CapeComment(
            id=2,
            issue_id=1,
            comment="Second comment",
            created_at=datetime(2024, 1, 1, 12, 20, 0),
        ),
    ]


def test_auto_refresh_activates_for_started_status(mock_issue_started, mock_comments):
    """Test that auto-refresh activates when issue status is 'started'."""
    # Create screen instance
    screen = IssueDetailScreen(issue_id=1)

    # Mock set_interval to return a mock timer
    mock_timer = Mock()
    mock_timer.resume = Mock()
    mock_timer.pause = Mock()
    screen.set_interval = Mock(return_value=mock_timer)

    # Mock query_one to avoid widget lookup issues
    screen.query_one = Mock(return_value=Mock())

    # Set initial state
    screen.auto_refresh_active = False
    screen.refresh_timer = mock_timer

    # Simulate data display with started status
    screen._display_data(mock_issue_started, mock_comments)

    # Verify auto-refresh was activated
    assert screen.auto_refresh_active is True
    mock_timer.resume.assert_called_once()


def test_auto_refresh_inactive_for_pending_status(mock_issue_pending, mock_comments):
    """Test that auto-refresh remains inactive when issue status is 'pending'."""
    # Create screen instance
    screen = IssueDetailScreen(issue_id=2)

    # Mock set_interval to return a mock timer
    mock_timer = Mock()
    mock_timer.resume = Mock()
    mock_timer.pause = Mock()

    # Mock query_one to avoid widget lookup issues
    screen.query_one = Mock(return_value=Mock())

    # Set initial state
    screen.auto_refresh_active = False
    screen.refresh_timer = mock_timer

    # Simulate data display with pending status
    screen._display_data(mock_issue_pending, mock_comments)

    # Verify auto-refresh was NOT activated
    assert screen.auto_refresh_active is False
    mock_timer.resume.assert_not_called()


def test_auto_refresh_inactive_for_completed_status(mock_issue_completed, mock_comments):
    """Test that auto-refresh remains inactive when issue status is 'completed'."""
    # Create screen instance
    screen = IssueDetailScreen(issue_id=3)

    # Mock set_interval to return a mock timer
    mock_timer = Mock()
    mock_timer.resume = Mock()
    mock_timer.pause = Mock()

    # Mock query_one to avoid widget lookup issues
    screen.query_one = Mock(return_value=Mock())

    # Set initial state
    screen.auto_refresh_active = False
    screen.refresh_timer = mock_timer

    # Simulate data display with completed status
    screen._display_data(mock_issue_completed, mock_comments)

    # Verify auto-refresh was NOT activated
    assert screen.auto_refresh_active is False
    mock_timer.resume.assert_not_called()


def test_timer_cleanup_on_unmount():
    """Test that timer is properly stopped when screen is unmounted."""
    # Create screen instance
    screen = IssueDetailScreen(issue_id=1)

    # Mock timer
    mock_timer = Mock()
    mock_timer.stop = Mock()
    screen.refresh_timer = mock_timer
    screen.auto_refresh_active = True

    # Simulate unmount
    screen.on_unmount()

    # Verify timer was stopped
    mock_timer.stop.assert_called_once()
    assert screen.auto_refresh_active is False


def test_auto_refresh_deactivates_on_status_change(
    mock_issue_started, mock_issue_completed, mock_comments
):
    """Ensure auto-refresh stops when status changes from started to completed."""
    # Create screen instance
    screen = IssueDetailScreen(issue_id=1)

    # Mock set_interval to return a mock timer
    mock_timer = Mock()
    mock_timer.resume = Mock()
    mock_timer.pause = Mock()

    # Mock query_one to avoid widget lookup issues
    screen.query_one = Mock(return_value=Mock())

    # Set initial state
    screen.auto_refresh_active = False
    screen.refresh_timer = mock_timer

    # Simulate data display with started status
    screen._display_data(mock_issue_started, mock_comments)

    # Verify auto-refresh was activated
    assert screen.auto_refresh_active is True
    mock_timer.resume.assert_called_once()

    # Simulate status change to completed
    screen._display_data(mock_issue_completed, mock_comments)

    # Verify auto-refresh was deactivated
    assert screen.auto_refresh_active is False
    mock_timer.pause.assert_called_once()


# Tests for IssueForm Widget


def test_issue_form_initialization_with_default_text():
    """Test IssueForm initializes with default empty text."""
    form = IssueForm()
    assert form.initial_text == ""
    assert form.on_save_callback is None
    assert form.on_cancel_callback is None


def test_issue_form_initialization_with_custom_text():
    """Test IssueForm initializes with provided initial text."""
    initial_text = "Test issue description"
    form = IssueForm(initial_text=initial_text)
    assert form.initial_text == initial_text


def test_issue_form_validation_empty_description():
    """Test IssueForm rejects empty description."""
    save_callback = Mock()
    form = IssueForm(on_save_callback=save_callback)

    # Mock the screen and TextArea
    mock_screen = Mock()
    mock_textarea = Mock()
    mock_textarea.text = ""
    mock_input = Mock()
    mock_input.value = "Test title"

    # Use PropertyMock to mock the screen property
    with patch.object(type(form), "screen", new_callable=PropertyMock, return_value=mock_screen):
        form.query_one = Mock(side_effect=[mock_input, mock_textarea])

        # Trigger save action
        form.action_save()

        # Verify callback was NOT called and notification was shown
        save_callback.assert_not_called()
        mock_screen.notify.assert_called_once()
        assert "cannot be empty" in mock_screen.notify.call_args[0][0]


def test_issue_form_validation_placeholder_text():
    """Test IssueForm rejects placeholder text."""
    save_callback = Mock()
    form = IssueForm(on_save_callback=save_callback)

    # Mock the screen and TextArea
    mock_screen = Mock()
    mock_textarea = Mock()
    mock_textarea.text = "Enter issue description..."
    mock_input = Mock()
    mock_input.value = "Test title"

    # Use PropertyMock to mock the screen property
    with patch.object(type(form), "screen", new_callable=PropertyMock, return_value=mock_screen):
        form.query_one = Mock(side_effect=[mock_input, mock_textarea])

        # Trigger save action
        form.action_save()

        # Verify callback was NOT called
        save_callback.assert_not_called()
        mock_screen.notify.assert_called_once()


def test_issue_form_validation_too_short():
    """Test IssueForm rejects description shorter than 10 characters."""
    save_callback = Mock()
    form = IssueForm(on_save_callback=save_callback)

    # Mock the screen and TextArea
    mock_screen = Mock()
    mock_textarea = Mock()
    mock_textarea.text = "Short"  # 5 characters
    mock_input = Mock()
    mock_input.value = "Test title"

    # Use PropertyMock to mock the screen property
    with patch.object(type(form), "screen", new_callable=PropertyMock, return_value=mock_screen):
        form.query_one = Mock(side_effect=[mock_input, mock_textarea])

        # Trigger save action
        form.action_save()

        # Verify callback was NOT called
        save_callback.assert_not_called()
        mock_screen.notify.assert_called_once()
        assert "at least 10 characters" in mock_screen.notify.call_args[0][0]


def test_issue_form_validation_too_long():
    """Test IssueForm rejects description longer than 10,000 characters."""
    save_callback = Mock()
    form = IssueForm(on_save_callback=save_callback)

    # Mock the screen and TextArea
    mock_screen = Mock()
    mock_textarea = Mock()
    mock_textarea.text = "x" * 10001  # 10,001 characters
    mock_input = Mock()
    mock_input.value = "Test title"

    # Use PropertyMock to mock the screen property
    with patch.object(type(form), "screen", new_callable=PropertyMock, return_value=mock_screen):
        form.query_one = Mock(side_effect=[mock_input, mock_textarea])

        # Trigger save action
        form.action_save()

        # Verify callback was NOT called
        save_callback.assert_not_called()
        mock_screen.notify.assert_called_once()
        assert "10,000 characters" in mock_screen.notify.call_args[0][0]


def test_issue_form_validation_valid_description():
    """Test IssueForm accepts valid description."""
    save_callback = Mock()
    form = IssueForm(on_save_callback=save_callback)

    # Mock the TextArea (no screen mock needed for valid case)
    mock_textarea = Mock()
    valid_description = "This is a valid description that is long enough"
    mock_textarea.text = valid_description
    mock_input = Mock()
    mock_input.value = "Valid title"
    form.query_one = Mock(side_effect=[mock_input, mock_textarea])

    # Trigger save action
    form.action_save()

    # Verify callback WAS called with cleaned description
    save_callback.assert_called_once_with(valid_description, "Valid title")


def test_issue_form_cancel_callback():
    """Test IssueForm calls cancel callback."""
    cancel_callback = Mock()
    form = IssueForm(on_cancel_callback=cancel_callback)

    # Trigger cancel action
    form.action_cancel()

    # Verify callback was called
    cancel_callback.assert_called_once()


# Tests for Comments


def test_comments_widget_initialization():
    """Test Comments can be initialized."""
    widget = Comments()
    assert widget is not None


def test_comment_item_factory_default_type(mock_comments):
    """Test create_comment_widget returns DefaultComment for unrecognized types."""
    from cape.tui.components.comment_item import (
        DefaultComment,
        create_comment_widget,
    )

    # Comment without source/type should use DefaultComment
    comment = mock_comments[0]
    widget = create_comment_widget(comment)

    assert isinstance(widget, DefaultComment)
    assert widget.comment == comment
    assert "default-comment" in widget.classes


def test_comment_item_factory_agent_claude():
    """Test create_comment_widget returns AgentClaudeComment for agent/claude type."""
    from cape.tui.components.comment_item import (
        AgentClaudeComment,
        create_comment_widget,
    )

    comment = CapeComment(
        id=1,
        issue_id=1,
        comment="Claude comment",
        source="agent",
        type="claude",
        created_at=datetime(2024, 1, 1, 12, 0, 0),
    )
    widget = create_comment_widget(comment)

    assert isinstance(widget, AgentClaudeComment)
    assert "agent-claude" in widget.classes


def test_comment_item_factory_system_workflow():
    """Test create_comment_widget returns SystemWorkflowComment for system/workflow type."""
    from cape.tui.components.comment_item import (
        SystemWorkflowComment,
        create_comment_widget,
    )

    comment = CapeComment(
        id=1,
        issue_id=1,
        comment="Workflow event",
        source="system",
        type="workflow",
        created_at=datetime(2024, 1, 1, 12, 0, 0),
    )
    widget = create_comment_widget(comment)

    assert isinstance(widget, SystemWorkflowComment)
    assert "system-workflow" in widget.classes


def test_comment_item_stores_comment():
    """Test CommentItem stores the comment reference."""
    from cape.tui.components.comment_item import CommentItem

    comment = CapeComment(
        id=1,
        issue_id=1,
        comment="Test comment",
        created_at=datetime(2024, 1, 1, 12, 0, 0),
    )
    widget = CommentItem(comment)

    assert widget.comment == comment
    assert widget.comment.comment == "Test comment"


def test_agent_claude_comment_text_layout():
    """Test AgentClaudeComment with raw.type='text' layout."""
    from cape.tui.components.comment_item import AgentClaudeComment

    comment = CapeComment(
        id=1,
        issue_id=1,
        comment="Fallback text",
        source="agent",
        type="claude",
        raw={"type": "text", "text": "This is the text content"},
        created_at=datetime(2024, 1, 1, 12, 0, 0),
    )
    widget = AgentClaudeComment(comment)

    # Verify the raw type is accessible
    assert widget.comment.raw["type"] == "text"
    assert widget.comment.raw["text"] == "This is the text content"


def test_agent_claude_comment_tool_use_layout():
    """Test AgentClaudeComment with raw.type='tool_use' layout."""
    from cape.tui.components.comment_item import AgentClaudeComment

    comment = CapeComment(
        id=1,
        issue_id=1,
        comment="Fallback text",
        source="agent",
        type="claude",
        raw={
            "type": "tool_use",
            "input": {
                "todos": [
                    {"status": "completed", "content": "First task"},
                    {"status": "in_progress", "content": "Second task"},
                    {"status": "pending", "content": "Third task"},
                ]
            },
        },
        created_at=datetime(2024, 1, 1, 12, 0, 0),
    )
    widget = AgentClaudeComment(comment)

    # Verify the raw structure is accessible
    assert widget.comment.raw["type"] == "tool_use"
    todos = widget.comment.raw["input"]["todos"]
    assert len(todos) == 3
    assert todos[0]["status"] == "completed"
    assert todos[1]["status"] == "in_progress"
    assert todos[2]["status"] == "pending"


def test_agent_claude_comment_status_emoji_mapping():
    """Test AgentClaudeComment status emoji mapping."""
    from cape.tui.components.comment_item import AgentClaudeComment

    assert AgentClaudeComment._STATUS_EMOJI["completed"] == "✅"
    assert AgentClaudeComment._STATUS_EMOJI["in_progress"] == "🚀"
    assert AgentClaudeComment._STATUS_EMOJI["pending"] == "⏳"


def test_agent_claude_comment_fallback_layout():
    """Test AgentClaudeComment falls back to comment body when raw.type is unknown."""
    from cape.tui.components.comment_item import AgentClaudeComment

    comment = CapeComment(
        id=1,
        issue_id=1,
        comment="This should be displayed",
        source="agent",
        type="claude",
        raw={"type": "unknown_type"},
        created_at=datetime(2024, 1, 1, 12, 0, 0),
    )
    widget = AgentClaudeComment(comment)

    # Verify fallback to comment body
    assert widget.comment.comment == "This should be displayed"


# Tests for Conditional Comments Visibility


def test_comments_section_hidden_for_pending_issue(mock_issue_pending, mock_comments):
    """Test that comments section is not shown for pending issues."""
    screen = IssueDetailScreen(issue_id=2)

    # Mock query_one to simulate no Comments exists
    def mock_query_side_effect(selector, *args):
        if selector == Comments:
            raise Exception("Widget not found")
        return Mock()

    screen.query_one = Mock(side_effect=mock_query_side_effect)
    screen.refresh_timer = Mock()

    # Display data with pending status
    screen._display_data(mock_issue_pending, mock_comments)

    # Verify that no attempt was made to update comments
    # (because widget shouldn't exist for pending issues)
    assert screen.issue.status == "pending"


def test_comments_section_visible_for_started_issue(mock_issue_started, mock_comments):
    """Test that comments section is shown for started issues."""
    screen = IssueDetailScreen(issue_id=1)

    # Mock widgets
    mock_comments_widget = Mock(spec=Comments)
    mock_container = Mock()

    def mock_query_side_effect(selector, *args):
        if selector == "#issue-content":
            return Mock()
        elif selector == Comments:
            return mock_comments_widget
        elif selector == "#detail-container":
            return mock_container
        return Mock()

    screen.query_one = Mock(side_effect=mock_query_side_effect)
    screen.refresh_timer = Mock()
    screen.refresh_timer.resume = Mock()

    # Display data with started status
    screen._display_data(mock_issue_started, mock_comments)

    # Verify comments widget was updated
    mock_comments_widget.update_comments.assert_called_once_with(mock_comments)


def test_comments_section_visible_for_completed_issue(mock_issue_completed, mock_comments):
    """Test that comments section is shown for completed issues."""
    screen = IssueDetailScreen(issue_id=3)

    # Mock widgets
    mock_comments_widget = Mock(spec=Comments)
    mock_container = Mock()

    def mock_query_side_effect(selector, *args):
        if selector == "#issue-content":
            return Mock()
        elif selector == Comments:
            return mock_comments_widget
        elif selector == "#detail-container":
            return mock_container
        return Mock()

    screen.query_one = Mock(side_effect=mock_query_side_effect)
    screen.refresh_timer = Mock()

    # Display data with completed status
    screen._display_data(mock_issue_completed, mock_comments)

    # Verify comments widget was updated
    mock_comments_widget.update_comments.assert_called_once_with(mock_comments)


# Tests for 'v' Key Binding


def test_v_key_triggers_view_detail():
    """Test that 'v' key binding triggers action_view_detail method."""
    from cape.tui.screens.issue_list_screen import IssueListScreen

    # Create screen instance
    screen = IssueListScreen()

    # Verify 'v' key is in bindings
    binding_keys = [binding[0] for binding in screen.BINDINGS]
    assert "v" in binding_keys

    # Verify 'v' maps to 'view_detail' action
    v_binding = next(b for b in screen.BINDINGS if b[0] == "v")
    assert v_binding[1] == "view_detail"
    assert v_binding[2] == "View Details"


def test_enter_key_still_works():
    """Test that existing 'enter' key binding still works after adding 'v'."""
    from cape.tui.screens.issue_list_screen import IssueListScreen

    # Create screen instance
    screen = IssueListScreen()

    # Verify 'enter' key is still in bindings
    binding_keys = [binding[0] for binding in screen.BINDINGS]
    assert "enter" in binding_keys

    # Verify 'enter' still maps to 'view_detail' action
    enter_binding = next(b for b in screen.BINDINGS if b[0] == "enter")
    assert enter_binding[1] == "view_detail"
    assert enter_binding[2] == "View Details"


def test_both_keys_map_to_same_action():
    """Test that both 'enter' and 'v' map to the same action."""
    from cape.tui.screens.issue_list_screen import IssueListScreen

    screen = IssueListScreen()

    # Get bindings for both keys
    enter_binding = next(b for b in screen.BINDINGS if b[0] == "enter")
    v_binding = next(b for b in screen.BINDINGS if b[0] == "v")

    # Verify they map to the same action
    assert enter_binding[1] == v_binding[1]
    assert enter_binding[1] == "view_detail"
