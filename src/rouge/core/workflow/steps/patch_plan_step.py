"""Shim class for the patch-plan workflow step.

The legacy ``PatchPlanStep`` has been replaced by the config-driven
:class:`~rouge.core.workflow.executors.prompt_json_step.PromptJsonStep`
executor.  This module keeps the ``PatchPlanStep`` symbol in place as a
zero-argument subclass so existing callers that do ``PatchPlanStep()``
continue to work.  The shim constructs a :class:`PromptJsonStep` around
:data:`PATCH_PLAN_CONFIG`.
"""

from __future__ import annotations

from rouge.core.workflow.builtin_configs import PATCH_PLAN_CONFIG
from rouge.core.workflow.executors.prompt_json_step import PromptJsonStep


class PatchPlanStep(PromptJsonStep):
    """Config-driven plan step wired to the ``patch-plan`` prompt template."""

    def __init__(self) -> None:
        """Initialize the step with the built-in patch-plan config."""
        super().__init__(PATCH_PLAN_CONFIG)


__all__ = ["PatchPlanStep"]
