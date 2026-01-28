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

# Valid worker IDs for issue assignment
VALID_WORKER_IDS = frozenset(
    {
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
    }
)


class Issue(BaseModel):
    """Issue model matching Supabase schema.

    Attributes:
        id: Unique identifier for the issue.
        title: Optional title for the issue.
        description: Issue description (required, non-empty).
        status: Workflow status of the issue.
        type: Issue type - 'main' for primary issues, 'patch' for patch issues.
        adw_id: Agent Development Workflow identifier. Must be provided during
            issue creation (via create_issue function).
        branch: Optional branch name for issue work.
        assigned_to: Worker ID assigned to process this issue.
        created_at: Timestamp when the issue was created.
        updated_at: Timestamp when the issue was last updated.
    """

    id: int
    title: Optional[str] = None
    description: str = Field(..., min_length=1)
    status: Literal["pending", "started", "completed", "patch pending", "patched"] = "pending"
    type: Literal["main", "patch"] = "main"
    adw_id: Optional[str] = None
    branch: Optional[str] = None
    assigned_to: Optional[
        Literal[
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

    @field_validator("type", mode="before")
    @classmethod
    def default_type(cls, v):
        """Default missing type to main."""
        return v if v else "main"

    @field_validator("adw_id")
    @classmethod
    def trim_adw_id(cls, v: Optional[str]) -> Optional[str]:
        """Trim whitespace from adw_id if provided."""
        return v.strip() if v else v

    @field_validator("branch")
    @classmethod
    def trim_branch(cls, v: Optional[str]) -> Optional[str]:
        """Trim whitespace from branch if provided."""
        return v.strip() if v else v

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
    adw_id: Optional[str] = None
    created_at: Optional[datetime] = None

    @field_validator("comment")
    @classmethod
    def trim_comment(cls, v: str) -> str:
        """Trim whitespace from comment."""
        return v.strip()

    def to_supabase(self) -> dict:
        """Convert Comment to Supabase insert format."""
        data = {
            "issue_id": self.issue_id,
            "comment": self.comment,
            "raw": self.raw,
            "adw_id": self.adw_id,
        }
        if self.source is not None:
            data["source"] = self.source
        if self.type is not None:
            data["type"] = self.type
        return data

    @classmethod
    def from_supabase(cls, row: dict) -> "Comment":
        """Create Comment from Supabase row."""
        return cls(**row)


# Source types for comment payloads
CommentSource = Literal["system", "agent"]


class CommentPayload(BaseModel):
    """Payload model for creating comments.

    This model is used for constructing comments before persistence.
    The Comment model represents the Supabase persistence shape.
    """

    issue_id: int
    adw_id: Optional[str] = ""
    text: str = Field(..., min_length=1)
    raw: Optional[dict] = None
    source: CommentSource = "system"
    kind: str = Field(..., min_length=1)

    @field_validator("text")
    @classmethod
    def trim_text(cls, v: str) -> str:
        """Trim whitespace from text and ensure non-empty."""
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("text must be non-empty after trimming")
        return trimmed

    @field_validator("kind")
    @classmethod
    def trim_kind(cls, v: str) -> str:
        """Trim whitespace from kind and ensure non-empty."""
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("kind must be non-empty after trimming")
        return trimmed


class Patch(BaseModel):
    """Patch model matching Supabase schema.

    .. deprecated::
        This model is deprecated. Use the Issue model with type='patch' instead.
        The patches table will be removed in a future migration. New patch
        functionality should use Issue records with type='patch'.

    Represents a patch request for an issue.

    Business rules enforced by the database:
    - Patches can only be created when the related issue status is
      'completed' or 'patched' (enforced by trigger).
    - Only one patch per issue is allowed (enforced by unique index).
    """

    id: int
    issue_id: int
    status: Literal["pending", "completed", "failed"] = "pending"
    description: str = Field(..., min_length=1)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("description")
    @classmethod
    def trim_description(cls, v: str) -> str:
        """Trim whitespace from description and ensure non-empty."""
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("description must be non-empty after trimming")
        return trimmed

    @field_validator("status", mode="before")
    @classmethod
    def default_status(cls, v: Optional[str]) -> str:
        """Default missing status to pending."""
        return v if v else "pending"

    @classmethod
    def from_supabase(cls, row: dict) -> "Patch":
        """Create Patch from Supabase row."""
        return cls(**row)


# Backward compatibility aliases
CapeIssue = Issue
CapeComment = Comment
