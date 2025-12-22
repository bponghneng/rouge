"""Tests for data models."""

import pytest

from rouge.core.agents.claude import (
    ClaudeAgentPromptRequest,
    ClaudeAgentTemplateRequest,
)
from rouge.core.models import Comment, Issue


def test_issue_creation():
    """Test basic Issue creation."""
    issue = Issue(id=1, description="Test issue")
    assert issue.id == 1
    assert issue.description == "Test issue"
    assert issue.status == "pending"


def test_issue_trim_description():
    """Test description whitespace trimming."""
    issue = Issue(id=1, description="  Test issue  ")
    assert issue.description == "Test issue"


def test_issue_empty_description_validation():
    """Test that empty description raises validation error."""
    with pytest.raises(ValueError):
        Issue(id=1, description="")


def test_issue_default_status():
    """Test default status is set to pending."""
    issue = Issue(id=1, description="Test")
    assert issue.status == "pending"


def test_issue_from_supabase():
    """Test creating Issue from Supabase row."""
    row = {
        "id": 1,
        "description": "Test issue",
        "status": "pending",
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    }
    issue = Issue.from_supabase(row)
    assert issue.id == 1
    assert issue.description == "Test issue"


def test_comment_creation():
    """Test basic Comment creation."""
    comment = Comment(issue_id=1, comment="Test comment")
    assert comment.issue_id == 1
    assert comment.comment == "Test comment"
    assert comment.id is None


def test_comment_trim():
    """Test comment whitespace trimming."""
    comment = Comment(issue_id=1, comment="  Test comment  ")
    assert comment.comment == "Test comment"


def test_comment_empty_validation():
    """Test that empty comment raises validation error."""
    with pytest.raises(ValueError):
        Comment(issue_id=1, comment="")


def test_comment_with_adw_id():
    """Test Comment creation with adw_id field."""
    comment = Comment(
        issue_id=1,
        comment="Test comment with ADW ID",
        adw_id="test-adw-123",
    )
    assert comment.issue_id == 1
    assert comment.comment == "Test comment with ADW ID"
    assert comment.adw_id == "test-adw-123"


def test_comment_default_adw_id():
    """Test Comment defaults adw_id to None when not provided."""
    comment = Comment(issue_id=1, comment="Test comment")
    assert comment.issue_id == 1
    assert comment.comment == "Test comment"
    assert comment.adw_id is None


def test_comment_with_all_fields_including_adw_id():
    """Test Comment with all fields including adw_id."""
    comment = Comment(
        id=42,
        issue_id=1,
        comment="Full comment test",
        raw={"key": "value"},
        source="agent",
        type="workflow",
        adw_id="adw-xyz-456",
    )
    assert comment.id == 42
    assert comment.issue_id == 1
    assert comment.comment == "Full comment test"
    assert comment.raw == {"key": "value"}
    assert comment.source == "agent"
    assert comment.type == "workflow"
    assert comment.adw_id == "adw-xyz-456"


def test_agent_prompt_request():
    """Test ClaudeAgentPromptRequest creation."""
    request = ClaudeAgentPromptRequest(
        prompt="Test prompt",
        adw_id="test123",
        issue_id=42,
        output_file="output.jsonl",
    )
    assert request.prompt == "Test prompt"
    assert request.adw_id == "test123"
    assert request.issue_id == 42
    assert request.agent_name == "ops"
    assert request.model == "opus"
    assert request.output_file == "output.jsonl"


def test_agent_template_request():
    """Test ClaudeAgentTemplateRequest creation."""
    request = ClaudeAgentTemplateRequest(
        agent_name="ops",
        slash_command="/adw-implement-plan",
        args=["plan.md"],
        adw_id="test123",
        issue_id=42,
    )
    assert request.agent_name == "ops"
    assert request.slash_command == "/adw-implement-plan"
    assert request.args == ["plan.md"]
    assert request.adw_id == "test123"
    assert request.issue_id == 42
    assert request.model == "sonnet"
