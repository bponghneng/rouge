"""Shim class for the claude-code-plan workflow step.

The legacy ``ClaudeCodePlanStep`` has been replaced by the config-driven
:class:`~rouge.core.workflow.executors.prompt_json_step.PromptJsonStep`
executor.  This module keeps the ``ClaudeCodePlanStep`` symbol in place as a
zero-argument subclass so existing callers that do ``ClaudeCodePlanStep()``
continue to work.  The shim simply constructs a :class:`PromptJsonStep`
around :data:`CLAUDE_CODE_PLAN_CONFIG`.
"""

from __future__ import annotations

from rouge.core.workflow.builtin_configs import CLAUDE_CODE_PLAN_CONFIG
from rouge.core.workflow.executors.prompt_json_step import PromptJsonStep


class ClaudeCodePlanStep(PromptJsonStep):
    """Config-driven plan step wired to the ``claude-code-plan`` prompt template."""

    def __init__(self) -> None:
        """Initialize the step with the built-in claude-code-plan config."""
        super().__init__(CLAUDE_CODE_PLAN_CONFIG)


__all__ = ["ClaudeCodePlanStep"]
