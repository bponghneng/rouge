"""Claude Code agent provider for Rouge."""

from .claude import (
    ClaudeAgent,
    check_claude_installed,
    get_claude_env,
    save_prompt,
)
from .claude_models import (
    ClaudeAgentPromptRequest,
    ClaudeAgentPromptResponse,
    ClaudeAgentResultMessage,
    ClaudeAgentTemplateRequest,
)

__all__ = [
    "ClaudeAgent",
    "check_claude_installed",
    "get_claude_env",
    "save_prompt",
    "ClaudeAgentPromptRequest",
    "ClaudeAgentPromptResponse",
    "ClaudeAgentResultMessage",
    "ClaudeAgentTemplateRequest",
]
