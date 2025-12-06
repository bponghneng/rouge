"""Claude Code agent provider for Rouge."""

from .claude import (
    ClaudeAgent,
    check_claude_installed,
    convert_jsonl_to_json,
    execute_claude_template,
    get_claude_env,
    iter_assistant_items,
    parse_jsonl_output,
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
    "convert_jsonl_to_json",
    "execute_claude_template",
    "get_claude_env",
    "iter_assistant_items",
    "parse_jsonl_output",
    "save_prompt",
    "ClaudeAgentPromptRequest",
    "ClaudeAgentPromptResponse",
    "ClaudeAgentResultMessage",
    "ClaudeAgentTemplateRequest",
]
