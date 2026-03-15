"""Rouge-owned prompt registry and loader.

Provides a packaged prompt system that renders workflow prompt templates
without relying on external slash commands.
"""

from rouge.core.prompts.prompt_id import PromptId
from rouge.core.prompts.registry import PromptRegistry, get_registry, render_prompt

__all__ = ["PromptId", "PromptRegistry", "get_registry", "render_prompt"]
