"""Claude Code-specific data models for agent execution.

These models preserve Claude CLI contracts including model names, flags,
and JSONL result structures. They are renamed from the original models
in cape.core.models to clarify their Claude-specific nature.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel

# Import SlashCommand type directly to avoid circular import
SlashCommand = Literal[
    "/adw-acceptance",
    "/adw-bug-plan",
    "/adw-chore-plan",
    "/adw-classify",
    "/adw-code-quality",
    "/adw-compose-commits",
    "/adw-feature-plan",
    "/adw-find-plan-file",
    "/adw-implement-plan",
    "/adw-implement-review",
    "/adw-patch-plan",
    "/adw-pull-request",
]


class ClaudeAgentPromptRequest(BaseModel):
    """Claude Code agent prompt configuration.

    This model captures all parameters needed to invoke the Claude Code CLI
    with a specific prompt and configuration.
    """

    prompt: str
    adw_id: str
    issue_id: int
    agent_name: str = "ops"
    model: Literal["sonnet", "opus"] = "opus"
    dangerously_skip_permissions: bool = False
    output_file: str


class ClaudeAgentPromptResponse(BaseModel):
    """Claude Code agent response.

    Standard response structure from Claude Code CLI execution,
    including success status and optional session ID for continuations.
    """

    output: str
    success: bool
    session_id: Optional[str] = None


class ClaudeAgentTemplateRequest(BaseModel):
    """Claude Code agent template execution request.

    Used for executing slash commands through the Claude Code CLI
    with specific arguments and configuration.

    Attributes:
        agent_name: Name of the agent executing the command.
        slash_command: The slash command to execute.
        args: List of arguments to pass to the slash command.
        adw_id: Agent Development Workflow identifier.
        issue_id: Optional issue identifier.
        model: Claude model to use (sonnet or opus).
        json_schema: Optional JSON schema string to pass to Claude CLI via
            --json-schema flag. When provided, Claude will structure its
            output according to this schema. Should be a valid JSON string
            representing the schema definition.
    """

    agent_name: str
    slash_command: SlashCommand
    args: List[str]
    adw_id: str
    issue_id: Optional[int]
    model: Literal["sonnet", "opus"] = "sonnet"
    json_schema: Optional[str] = None


class ClaudeAgentResultMessage(BaseModel):
    """Claude Code JSONL result message (last line).

    This model represents the final result message in Claude Code's
    JSONL output format, containing execution metadata and results.
    """

    type: str
    subtype: str
    is_error: bool
    duration_ms: int
    duration_api_ms: int
    num_turns: int
    result: str
    session_id: str
    total_cost_usd: float
