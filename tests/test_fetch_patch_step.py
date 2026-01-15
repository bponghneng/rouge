"""Tests for FetchPatchStep workflow step."""

from unittest.mock import Mock, patch

import pytest

from rouge.core.models import Issue, Patch
from rouge.core.workflow.artifacts import PatchArtifact
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.fetch_patch import FetchPatchStep
from rouge.core.workflow.types import StepResult


@pytest.fixture
def mock_context():
    """Create a mock workflow context."""
    context = Mock(spec=WorkflowContext)
    context.issue_id = 10
    context.adw_id = "test-adw-patch"
    context.issue = None
    context.data = {}
    context.artifacts_enabled = True
    context.artifact_store = Mock()
    return context


@pytest.fixture
def sample_issue():
    """Create a sample issue."""
    return Issue(
        id=10,
        description="Original issue",
        status="patched",
    )


@pytest.fixture
def sample_patch():
    """Create a sample patch."""
    return Patch(
        id=1,
        issue_id=10,
        description="Fix typo in README",
        status="pending",
    )


@patch("rouge.core.workflow.steps.fetch_patch.emit_progress_comment")
@patch("rouge.core.workflow.steps.fetch_patch.fetch_pending_patch")
@patch("rouge.core.workflow.steps.fetch_patch.fetch_issue")
def test_fetch_patch_step_success(
    mock_fetch_issue,
    mock_fetch_patch,
    mock_emit,
    mock_context,
    sample_issue,
    sample_patch,
):
    """Test successful patch fetch."""
    mock_fetch_issue.return_value = sample_issue
    mock_fetch_patch.return_value = sample_patch

    step = FetchPatchStep()
    result = step.run(mock_context)

    assert result.success is True
    assert mock_context.issue == sample_issue
    assert mock_context.data["patch"] == sample_patch

    # Verify artifact was saved
    mock_context.artifact_store.write_artifact.assert_called_once()
    artifact = mock_context.artifact_store.write_artifact.call_args[0][0]
    assert isinstance(artifact, PatchArtifact)
    assert artifact.patch == sample_patch

    # Verify progress comment was emitted
    mock_emit.assert_called_once()


@patch("rouge.core.workflow.steps.fetch_patch.emit_progress_comment")
@patch("rouge.core.workflow.steps.fetch_patch.fetch_pending_patch")
@patch("rouge.core.workflow.steps.fetch_patch.fetch_issue")
def test_fetch_patch_step_no_pending_patch(
    mock_fetch_issue,
    mock_fetch_patch,
    mock_emit,
    mock_context,
    sample_issue,
):
    """Test fetch patch step fails when no pending patch exists."""
    mock_fetch_issue.return_value = sample_issue
    mock_fetch_patch.side_effect = ValueError("No pending patch found")

    step = FetchPatchStep()
    result = step.run(mock_context)

    assert result.success is False
    assert "No pending patch found" in result.error


@patch("rouge.core.workflow.steps.fetch_patch.emit_progress_comment")
@patch("rouge.core.workflow.steps.fetch_patch.fetch_pending_patch")
@patch("rouge.core.workflow.steps.fetch_patch.fetch_issue")
def test_fetch_patch_step_issue_not_found(
    mock_fetch_issue,
    mock_fetch_patch,
    mock_emit,
    mock_context,
):
    """Test fetch patch step fails when issue not found."""
    mock_fetch_issue.side_effect = ValueError("Issue not found")

    step = FetchPatchStep()
    result = step.run(mock_context)

    assert result.success is False
    assert "Issue not found" in result.error


@patch("rouge.core.workflow.steps.fetch_patch.emit_progress_comment")
@patch("rouge.core.workflow.steps.fetch_patch.fetch_pending_patch")
@patch("rouge.core.workflow.steps.fetch_patch.fetch_issue")
def test_fetch_patch_step_without_artifact_store(
    mock_fetch_issue,
    mock_fetch_patch,
    mock_emit,
    mock_context,
    sample_issue,
    sample_patch,
):
    """Test fetch patch step works without artifact store."""
    mock_context.artifacts_enabled = False
    mock_context.artifact_store = None
    mock_fetch_issue.return_value = sample_issue
    mock_fetch_patch.return_value = sample_patch

    step = FetchPatchStep()
    result = step.run(mock_context)

    assert result.success is True
    assert mock_context.issue == sample_issue
    assert mock_context.data["patch"] == sample_patch


def test_fetch_patch_step_is_critical():
    """Test that FetchPatchStep is marked as critical."""
    step = FetchPatchStep()
    assert step.is_critical is True


def test_fetch_patch_step_name():
    """Test FetchPatchStep has correct name."""
    step = FetchPatchStep()
    assert step.name == "Fetching pending patch"
