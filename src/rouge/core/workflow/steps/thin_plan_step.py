"""Shim class for the thin-plan workflow step.

The legacy ``ThinPlanStep`` has been replaced by the config-driven
:class:`~rouge.core.workflow.executors.prompt_json_step.PromptJsonStep`
executor.  This module keeps the ``ThinPlanStep`` symbol in place as a
zero-argument subclass so existing callers that do ``ThinPlanStep()``
continue to work.  The shim constructs a :class:`PromptJsonStep` around
:data:`THIN_PLAN_CONFIG`.
"""

from __future__ import annotations

from rouge.core.workflow.builtin_configs import THIN_PLAN_CONFIG
from rouge.core.workflow.executors.prompt_json_step import PromptJsonStep


class ThinPlanStep(PromptJsonStep):
    """Config-driven plan step wired to the ``thin-plan`` prompt template."""

    def __init__(self) -> None:
        """Initialize the step with the built-in thin-plan config."""
        super().__init__(THIN_PLAN_CONFIG)


__all__ = ["ThinPlanStep"]
