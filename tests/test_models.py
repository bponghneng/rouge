"""Tests for data models."""

import pytest

from rouge.core.agents.claude import (
    ClaudeAgentPromptRequest,
    ClaudeAgentTemplateRequest,
)
from rouge.core.models import CapeComment, CapeIssue


def test_cape_issue_creation():
    """Test basic CapeIssue creation."""
    issue = CapeIssue(id=1, description="Test issue")
    assert issue.id == 1
    assert issue.description == "Test issue"
    assert issue.status == "pending"


def test_cape_issue_trim_description():
    """Test description whitespace trimming."""
    issue = CapeIssue(id=1, description="  Test issue  ")
    assert issue.description == "Test issue"


def test_cape_issue_empty_description_validation():
    """Test that empty description raises validation error."""
    with pytest.raises(ValueError):
        CapeIssue(id=1, description="")


def test_cape_issue_default_status():
    """Test default status is set to pending."""
    issue = CapeIssue(id=1, description="Test")
    assert issue.status == "pending"


def test_cape_issue_from_supabase():
    """Test creating CapeIssue from Supabase row."""
    row = {
        "id": 1,
        "description": "Test issue",
        "status": "pending",
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
    }
    issue = CapeIssue.from_supabase(row)
    assert issue.id == 1
    assert issue.description == "Test issue"


def test_cape_comment_creation():
    """Test basic CapeComment creation."""
    comment = CapeComment(issue_id=1, comment="Test comment")
    assert comment.issue_id == 1
    assert comment.comment == "Test comment"
    assert comment.id is None


def test_cape_comment_trim():
    """Test comment whitespace trimming."""
    comment = CapeComment(issue_id=1, comment="  Test comment  ")
    assert comment.comment == "Test comment"


def test_cape_comment_empty_validation():
    """Test that empty comment raises validation error."""
    with pytest.raises(ValueError):
        CapeComment(issue_id=1, comment="")


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
