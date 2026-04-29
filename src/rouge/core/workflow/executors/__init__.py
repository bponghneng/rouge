"""Declarative workflow step executors.

Executors are step classes that read configuration (via ``settings``) instead
of hard-coding artifact names and prompt IDs. The resolver layer in
``rouge.core.workflow.config_resolver`` instantiates these executors from a
``WorkflowConfig`` to produce a runnable pipeline.

Today this package exposes ``PromptJsonStep`` for plan-style steps that share
the same shape: load an input artifact, execute a prompt template, parse JSON,
and write a ``PlanArtifact``.
"""

from rouge.core.workflow.executors.prompt_json_step import (
    PromptJsonStep,
    PromptJsonStepSettings,
)

__all__ = ["PromptJsonStep", "PromptJsonStepSettings"]
