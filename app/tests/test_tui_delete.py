"""Tests for delete functionality in the TUI."""

from unittest.mock import Mock

import pytest

from cape.core.models import CapeIssue
from cape.tui.screens.confirm_delete_modal import ConfirmDeleteModal
from cape.tui.screens.issue_detail_screen import IssueDetailScreen
from cape.tui.screens.issue_list_screen import IssueListScreen


@pytest.fixture
def mock_issue():
    """Create a mock CapeIssue for testing."""
    return CapeIssue(
        id=1,
        description="Test issue for deletion",
        status="pending",
    )


@pytest.fixture
def mock_started_issue():
    """Create a mock CapeIssue with started status."""
    return CapeIssue(
        id=2,
        description="Started issue that should not be deleted",
        status="started",
    )


class TestConfirmDeleteModal:
    """Test cases for ConfirmDeleteModal."""

    def test_modal_initialization(self, mock_issue):
        """Test modal initializes with correct issue data."""
        modal = ConfirmDeleteModal(mock_issue.id, mock_issue.description)
        assert modal.issue_id == mock_issue.id
        assert modal.issue_description == mock_issue.description

    def test_modal_stores_full_description(self):
        """Test that modal stores full description (truncation happens during render)."""
        long_desc = "x" * 150
        modal = ConfirmDeleteModal(1, long_desc)
        # Modal stores the full description
        assert modal.issue_description == long_desc
        # Truncation happens in compose() method when rendering


class TestIssueDetailScreenDelete:
    """Test cases for delete functionality in IssueDetailScreen.

    These are simple unit tests that don't require full app context.
    """

    def test_handle_delete_confirmation_cancelled(self):
        """Test that cancelling delete confirmation does not trigger deletion."""
        screen = IssueDetailScreen(issue_id=1)
        screen.delete_issue_handler = Mock()

        # User cancels
        screen.handle_delete_confirmation(False)

        # Should not call delete handler
        screen.delete_issue_handler.assert_not_called()

    def test_handle_delete_confirmation_accepted(self):
        """Test that accepting delete confirmation triggers deletion."""
        screen = IssueDetailScreen(issue_id=1)
        screen.delete_issue_handler = Mock()

        # User confirms
        screen.handle_delete_confirmation(True)

        # Should call delete handler
        screen.delete_issue_handler.assert_called_once()


class TestIssueListScreenDeleteFlow:
    """Test cases for delete flow in IssueListScreen.

    These are simple unit tests for handler methods.
    """

    def test_handle_delete_confirmation_cancelled_no_deletion(self):
        """Test that cancelling confirmation does not delete the issue."""
        screen = IssueListScreen()
        screen.delete_issue_handler = Mock()

        # User cancels
        screen.handle_delete_confirmation(issue_id=1, row_key="test-key", confirmed=False)

        # Should not call delete handler
        screen.delete_issue_handler.assert_not_called()

    def test_handle_delete_confirmation_accepted_triggers_deletion(self):
        """Test that accepting confirmation triggers the delete handler."""
        screen = IssueListScreen()
        screen.delete_issue_handler = Mock()

        # User confirms
        screen.handle_delete_confirmation(issue_id=1, row_key="test-key", confirmed=True)

        # Should call delete handler with correct parameters
        screen.delete_issue_handler.assert_called_once_with(1, "test-key")


# TODO: Add integration tests using run_test() and Pilot
#
# Integration tests would exercise the complete delete flow end-to-end:
#  - Test deleting pending issues from list screen
#  - Test that started issues show warning when delete is attempted
#  - Test deleting from detail screen
#  - Test cancelling delete confirmation
#
# Challenge: These tests require mocking Textual's @work decorator behavior
# and coordinating async operations with background threads. The current unit
# tests provide good coverage of the delete logic. Full integration tests can
# be added when there's a specific need or when we have better patterns for
# mocking the worker threads.
#
# See AGENTS.md (Testing Strategy section) for examples of how to structure
# these tests using app.run_test() and pilot.
