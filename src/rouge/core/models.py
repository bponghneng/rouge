"""Data types for Rouge CLI workflow components.

Agent-specific models moved to rouge.core.agents package.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

# All slash commands used in the Rouge workflow system
SlashCommand = Literal[
    "/implement",
    "/triage:classify",
    "/triage:chore",
    "/triage:bug",
    "/triage:feature",
    "/triage:find-plan-file",
]


class Issue(BaseModel):
    """Issue model matching Supabase schema."""

    id: int
    title: Optional[str] = None
    description: str = Field(..., min_length=1)
    status: Literal["pending", "started", "completed"] = "pending"
    assigned_to: Optional[
        Literal[
            "alleycat-1",
            "alleycat-2",
            "alleycat-3",
            "hailmary-1",
            "hailmary-2",
            "hailmary-3",
            "local-1",
            "local-2",
            "local-3",
            "tydirium-1",
            "tydirium-2",
            "tydirium-3",
        ]
    ] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("description")
    @classmethod
    def trim_description(cls, v: str) -> str:
        """Trim whitespace from description."""
        return v.strip()

    @field_validator("status", mode="before")
    @classmethod
    def default_status(cls, v):
        """Default missing status to pending."""
        return v if v else "pending"

    @classmethod
    def from_supabase(cls, row: dict) -> "Issue":
        """Create Issue from Supabase row."""
        return cls(**row)


class Comment(BaseModel):
    """Comment model matching Supabase schema."""

    id: Optional[int] = None
    issue_id: int
    comment: str = Field(..., min_length=1)
    raw: dict = Field(default_factory=dict)
    source: Optional[str] = None
    type: Optional[str] = None
    created_at: Optional[datetime] = None

    @field_validator("comment")
    @classmethod
    def trim_comment(cls, v: str) -> str:
        """Trim whitespace from comment."""
        return v.strip()


# Backward compatibility aliases
CapeIssue = Issue
CapeComment = Comment
