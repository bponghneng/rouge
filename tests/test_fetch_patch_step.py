"""Tests for FetchPatchStep workflow step."""

from unittest.mock import Mock, patch

import pytest

from rouge.core.models import Issue
from rouge.core.workflow.artifacts import FetchPatchArtifact
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.fetch_patch_step import FetchPatchStep


@pytest.fixture
def mock_context():
    """Create a mock workflow context."""
    context = Mock(spec=WorkflowContext)
    context.issue_id = 10
    context.require_issue_id = 10
    context.adw_id = "test-adw-patch"
    context.issue = None
    context.data = {}
    context.artifacts_enabled = True
    context.artifact_store = Mock()
    return context


@pytest.fixture
def sample_patch_issue():
    """Create a sample patch issue."""
    return Issue(
        id=10,
        description="Fix typo in README",
        status="pending",
        type="patch",
        adw_id="abc12345",
    )


@pytest.fixture
def sample_main_issue():
    """Create a sample main issue (not a patch)."""
    return Issue(
        id=10,
        description="Original issue",
        status="started",
        type="main",
        adw_id="abc12345",
    )


@patch("rouge.core.workflow.steps.fetch_patch_step.update_status")
@patch("rouge.core.workflow.steps.fetch_patch_step.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.fetch_patch_step.fetch_issue")
def test_fetch_patch_step_success(
    mock_fetch_issue,
    mock_emit,
    mock_update_status,
    mock_context,
    sample_patch_issue,
):
    """Test successful patch fetch."""
    mock_fetch_issue.return_value = sample_patch_issue
    mock_emit.return_value = ("success", "Comment inserted")

    step = FetchPatchStep()
    result = step.run(mock_context)

    assert result.success is True
    assert mock_context.issue == sample_patch_issue

    # Verify status was updated to "started"
    mock_update_status.assert_called_once_with(10, "started")

    # Verify patch artifact was saved
    assert mock_context.artifact_store.write_artifact.call_count == 1

    # Check the call was FetchPatchArtifact with the patch issue
    artifact_call = mock_context.artifact_store.write_artifact.call_args_list[0][0][0]
    assert isinstance(artifact_call, FetchPatchArtifact)
    assert artifact_call.patch == sample_patch_issue

    # Verify progress comment was emitted with correct text
    mock_emit.assert_called_once()
    payload = mock_emit.call_args[0][0]
    assert payload.text == "Workflow started. Patch fetched and validated."


@patch("rouge.core.workflow.steps.fetch_patch_step.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.fetch_patch_step.fetch_issue")
def test_fetch_patch_step_no_pending_patch(
    mock_fetch_issue,
    mock_emit,
    mock_context,
    sample_main_issue,
):
    """Test fetch patch step fails when issue is not type='patch'."""
    mock_fetch_issue.return_value = sample_main_issue

    step = FetchPatchStep()
    result = step.run(mock_context)

    assert result.success is False
    assert "not a patch issue" in result.error


@patch("rouge.core.workflow.steps.fetch_patch_step.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.fetch_patch_step.fetch_issue")
def test_fetch_patch_step_issue_not_found(
    mock_fetch_issue,
    mock_emit,
    mock_context,
):
    """Test fetch patch step fails when issue not found."""
    mock_fetch_issue.side_effect = ValueError("Issue not found")

    step = FetchPatchStep()
    result = step.run(mock_context)

    assert result.success is False
    assert "Issue not found" in result.error


@patch("rouge.core.workflow.steps.fetch_patch_step.update_status")
@patch("rouge.core.workflow.steps.fetch_patch_step.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.fetch_patch_step.fetch_issue")
def test_fetch_patch_step_without_artifact_store(
    mock_fetch_issue,
    mock_emit,
    mock_update_status,
    mock_context,
    sample_patch_issue,
):
    """Test fetch patch step works without artifact store."""
    mock_context.artifacts_enabled = False
    mock_context.artifact_store = None
    mock_fetch_issue.return_value = sample_patch_issue
    mock_emit.return_value = ("success", "Comment inserted")

    step = FetchPatchStep()
    result = step.run(mock_context)

    assert result.success is True
    assert mock_context.issue == sample_patch_issue


def test_fetch_patch_step_is_critical():
    """Test that FetchPatchStep is marked as critical."""
    step = FetchPatchStep()
    assert step.is_critical is True


def test_fetch_patch_step_name():
    """Test FetchPatchStep has correct name."""
    step = FetchPatchStep()
    assert step.name == "Fetching pending patch"


@patch("rouge.core.workflow.steps.fetch_patch_step.emit_comment_from_payload")
@patch("rouge.core.workflow.steps.fetch_patch_step.fetch_issue")
def test_fetch_patch_step_unexpected_error(
    mock_fetch_issue,
    mock_emit_comment_from_payload,
    mock_context,
):
    """Test FetchPatchStep handles unexpected errors gracefully."""
    # Setup: fetch_issue raises RuntimeError
    mock_fetch_issue.side_effect = RuntimeError("Unexpected DB error")

    # Execute
    step = FetchPatchStep()
    result = step.run(mock_context)

    # Verify
    assert result.success is False
    assert "Unexpected error" in result.error
    mock_fetch_issue.assert_called_once_with(10)
    mock_emit_comment_from_payload.assert_not_called()
