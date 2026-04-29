"""Resolve a :class:`WorkflowConfig` into a runnable list of workflow steps.

This module is the bridge between the declarative configuration layer
(``WorkflowConfig`` / ``StepInvocation``) and the imperative pipeline executor
(``WorkflowRunner``).  It is intentionally small: no I/O, no orchestration,
no side effects beyond constructing step instances.

Design notes:
    * The resolver overrides the three legacy plan slugs at workflow-build
      time to instantiate :class:`PromptJsonStep` from the executors package.
      The legacy concrete classes remain registered under their slugs so
      ``rouge step run thin-plan`` (and similar) keeps working unchanged.
    * Step factories are looked up via a per-slug map.  The default factory
      simply calls ``step_metadata.step_class()``.  Special-cases live in the
      map so the resolver body stays linear.
    * Imports inside the factory bodies are lazy to avoid pulling step modules
      (and their heavy dependencies) at import time, mirroring the pattern
      already used by ``pipeline.py``.

Default settings for the three plan slugs (see Step 6 of the Phase 2 plan):
    * ``thin-plan``        -> schema kind ``plan_chore_bug_feature``,
                              input ``fetch-issue`` / ``issue``,
                              prompt id ``PromptId.THIN_PLAN``.
    * ``patch-plan``       -> schema kind ``plan_chore_bug_feature``,
                              input ``fetch-patch`` / ``patch``,
                              prompt id ``PromptId.PATCH_PLAN``.
    * ``claude-code-plan`` -> schema kind ``plan_task``,
                              input ``fetch-issue`` / ``issue``,
                              prompt id ``PromptId.CLAUDE_CODE_PLAN``.
"""

from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

from rouge.core.workflow.config import StepInvocation, WorkflowConfig
from rouge.core.workflow.step_base import WorkflowStep
from rouge.core.workflow.step_registry import StepMetadata, get_step_registry

# Type alias for per-slug factories.  A factory receives the
# ``StepInvocation`` (so it can read ``settings``) and the ``StepMetadata``
# resolved from the registry, and returns a constructed ``WorkflowStep``.
StepFactory = Callable[[StepInvocation, StepMetadata], WorkflowStep]


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------


def _evaluate_when(invocation: StepInvocation) -> bool:
    """Return ``True`` if the invocation's ``when`` clause permits execution.

    Semantics (matches the docstring on ``StepCondition``):
        * ``equals=X`` -> include if ``os.environ.get(env) == X``.
        * ``in_=[...]`` -> include if ``os.environ.get(env)`` is in the list.
        * Both ``None`` -> include if ``env`` is set and non-empty.
        * ``when is None`` -> always include.
    """
    condition = invocation.when
    if condition is None:
        return True

    raw_value = os.environ.get(condition.env)

    if condition.equals is not None:
        return raw_value == condition.equals
    if condition.in_ is not None:
        return raw_value in condition.in_
    return bool(raw_value)


# ---------------------------------------------------------------------------
# Step factories
# ---------------------------------------------------------------------------


def _build_prompt_json_step_for_slug(
    slug: str,
    invocation: StepInvocation,
) -> WorkflowStep:
    """Build a ``PromptJsonStep`` for one of the three legacy plan slugs.

    Defaults are populated per ``slug``; ``invocation.settings`` overrides any
    of them.
    """
    # Lazy import to avoid pulling executors at module-import time.
    from rouge.core.prompts import PromptId
    from rouge.core.workflow.executors.prompt_json_step import (
        PromptJsonStep,
        PromptJsonStepSettings,
    )

    defaults_by_slug: Dict[str, Dict[str, Any]] = {
        "thin-plan": {
            "prompt_id": PromptId.THIN_PLAN,
            "input_artifact": "fetch-issue",
            "input_artifact_class_name": "fetch-issue",
            "input_field": "issue",
            "json_schema_kind": "plan_chore_bug_feature",
            "output_artifact_kind": "plan",
            "title_keys": ["chore", "bug", "feature"],
        },
        "patch-plan": {
            "prompt_id": PromptId.PATCH_PLAN,
            "input_artifact": "fetch-patch",
            "input_artifact_class_name": "fetch-patch",
            "input_field": "patch",
            "json_schema_kind": "plan_chore_bug_feature",
            "output_artifact_kind": "plan",
            "title_keys": ["chore", "bug", "feature"],
        },
        "claude-code-plan": {
            "prompt_id": PromptId.CLAUDE_CODE_PLAN,
            "input_artifact": "fetch-issue",
            "input_artifact_class_name": "fetch-issue",
            "input_field": "issue",
            "json_schema_kind": "plan_task",
            "output_artifact_kind": "plan",
            "title_keys": ["task"],
        },
    }
    if slug not in defaults_by_slug:
        raise ValueError(f"No PromptJsonStep defaults registered for slug '{slug}'")

    merged: Dict[str, Any] = {**defaults_by_slug[slug], **(invocation.settings or {})}
    settings = PromptJsonStepSettings(**merged)

    display_name = invocation.display_name
    step = (
        PromptJsonStep(settings=settings, display_name=display_name)
        if display_name
        else PromptJsonStep(settings=settings)
    )
    return step


def _factory_implement_plan(
    invocation: StepInvocation,
    _metadata: StepMetadata,
) -> WorkflowStep:
    """Build ``ImplementPlanStep`` honouring ``settings['plan_step_name']``."""
    # Lazy import: ImplementPlanStep imports heavy dependencies.
    from rouge.core.workflow.steps.implement_step import ImplementPlanStep

    plan_step_name = (invocation.settings or {}).get("plan_step_name")
    if plan_step_name is not None and not isinstance(plan_step_name, str):
        raise ValueError(
            f"implement-plan settings.plan_step_name must be a string, "
            f"got {type(plan_step_name).__name__}"
        )
    return ImplementPlanStep(plan_step_name=plan_step_name)


def _factory_default(
    _invocation: StepInvocation,
    metadata: StepMetadata,
) -> WorkflowStep:
    """Default factory: ``metadata.step_class()`` with no arguments."""
    return metadata.step_class()


def _factory_thin_plan(
    invocation: StepInvocation,
    _metadata: StepMetadata,
) -> WorkflowStep:
    return _build_prompt_json_step_for_slug("thin-plan", invocation)


def _factory_patch_plan(
    invocation: StepInvocation,
    _metadata: StepMetadata,
) -> WorkflowStep:
    return _build_prompt_json_step_for_slug("patch-plan", invocation)


def _factory_claude_code_plan(
    invocation: StepInvocation,
    _metadata: StepMetadata,
) -> WorkflowStep:
    return _build_prompt_json_step_for_slug("claude-code-plan", invocation)


# Per-slug factory map.  Slugs not listed here use ``_factory_default``.
_FACTORIES: Dict[str, StepFactory] = {
    "implement-plan": _factory_implement_plan,
    "thin-plan": _factory_thin_plan,
    "patch-plan": _factory_patch_plan,
    "claude-code-plan": _factory_claude_code_plan,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_workflow(config: WorkflowConfig) -> List[WorkflowStep]:
    """Resolve a :class:`WorkflowConfig` into an ordered list of steps.

    For each :class:`StepInvocation`:
        * Skip the entry if its ``when`` clause evaluates to ``False``.
        * Look up the slug in the global step registry; raise ``ValueError``
          if unknown.
        * Build the step instance via the per-slug factory map.
        * Tag the instance with ``step_id = invocation.id`` so the runner can
          resolve resume / rerun targets by stable ID.
        * If the invocation provides ``display_name``, set it on the instance
          (currently meaningful for :class:`PromptJsonStep`, which exposes a
          settable ``name`` attribute; legacy steps may not honour overrides).

    Args:
        config: The declarative workflow configuration.

    Returns:
        Ordered list of constructed ``WorkflowStep`` instances ready for the
        runner.

    Raises:
        ValueError: If any step slug is missing from the registry.
    """
    registry = get_step_registry()
    resolved: List[WorkflowStep] = []

    for invocation in config.steps:
        if not _evaluate_when(invocation):
            continue

        metadata: Optional[StepMetadata] = registry.get_step_metadata_by_slug(invocation.id)
        if metadata is None:
            raise ValueError(f"Step slug '{invocation.id}' is not registered in the step registry")

        factory: StepFactory = _FACTORIES.get(invocation.id, _factory_default)
        step = factory(invocation, metadata)

        # Tag with stable ID so the runner can use it for resume/rerun lookup.
        step.step_id = invocation.id

        # Apply display_name override when the instance supports it.  The
        # legacy step classes implement ``name`` as a fixed property without a
        # setter, so we silently skip them rather than raise.
        if invocation.display_name:
            try:
                step.name = invocation.display_name  # type: ignore[misc]
            except AttributeError:
                # Read-only property on legacy classes; no-op.
                pass

        resolved.append(step)

    return resolved
