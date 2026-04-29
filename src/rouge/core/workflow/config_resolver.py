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

import logging
import os
from typing import Any, Callable, Dict, List, Optional

from rouge.core.workflow.config import StepInvocation, WorkflowConfig
from rouge.core.workflow.step_base import WorkflowStep
from rouge.core.workflow.step_registry import StepMetadata, get_step_registry

logger = logging.getLogger(__name__)

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
            "input_field": "issue",
            "json_schema_kind": "plan_chore_bug_feature",
            "title_keys": ["chore", "bug", "feature"],
        },
        "patch-plan": {
            "prompt_id": PromptId.PATCH_PLAN,
            "input_artifact": "fetch-patch",
            "input_field": "patch",
            "json_schema_kind": "plan_chore_bug_feature",
            "title_keys": ["chore", "bug", "feature"],
        },
        "claude-code-plan": {
            "prompt_id": PromptId.CLAUDE_CODE_PLAN,
            "input_artifact": "fetch-issue",
            "input_field": "issue",
            "json_schema_kind": "plan_task",
            "title_keys": ["task"],
        },
    }
    if slug not in defaults_by_slug:
        raise ValueError(f"No PromptJsonStep defaults registered for slug '{slug}'")

    merged: Dict[str, Any] = {**defaults_by_slug[slug], **(invocation.settings or {})}
    settings = PromptJsonStepSettings(**merged)

    # ``display_name`` is not passed here; ``resolve_workflow``'s post-construction
    # ``step.name = invocation.display_name`` block is the sole source of the
    # display-name override, avoiding the dual-write that existed before.
    return PromptJsonStep(settings=settings)


def _build_implement_plan_step(
    invocation: StepInvocation,
    previous_invocation: Optional[StepInvocation],
) -> WorkflowStep:
    """Build ``ImplementPlanStep``, resolving ``plan_step_name`` from settings or
    the preceding invocation's ``display_name``.

    Resolution order (plan):
      1. ``settings["plan_step_name"]`` — explicit override in the invocation.
      2. ``previous_invocation.display_name`` — display name of the preceding step;
         avoids repeating the same string in both the plan step and implement step.
      3. ``None`` — ``ImplementPlanStep`` uses its own default.
    """
    # Lazy import: ImplementPlanStep imports heavy dependencies.
    from rouge.core.workflow.steps.implement_step import ImplementPlanStep

    plan_step_name = (invocation.settings or {}).get("plan_step_name")
    if plan_step_name is not None and not isinstance(plan_step_name, str):
        raise ValueError(
            f"implement-plan settings.plan_step_name must be a string, "
            f"got {type(plan_step_name).__name__}"
        )
    # Fall back to the preceding invocation's display_name so the two sources
    # of truth can be collapsed to one; when that is also absent, ImplementPlanStep
    # uses its own default.
    if plan_step_name is None and previous_invocation is not None:
        plan_step_name = previous_invocation.display_name
    return ImplementPlanStep(plan_step_name=plan_step_name)


def _factory_default(
    _invocation: StepInvocation,
    metadata: StepMetadata,
) -> WorkflowStep:
    """Default factory: ``metadata.step_class()`` with no arguments."""
    return metadata.step_class()


# Per-slug factory map.  Slugs not listed here use ``_factory_default``.
# The three plan slugs are registered as lambdas that bind the slug into
# ``_build_prompt_json_step_for_slug``, so adding a new plan slug only
# requires one entry here rather than a separate wrapper function.
# Note: ``implement-plan`` is handled directly in ``resolve_workflow`` so that
# the previous invocation can be passed; it is excluded from this map.
_FACTORIES: Dict[str, StepFactory] = {
    "thin-plan": lambda inv, _meta: _build_prompt_json_step_for_slug("thin-plan", inv),
    "patch-plan": lambda inv, _meta: _build_prompt_json_step_for_slug("patch-plan", inv),
    "claude-code-plan": lambda inv, _meta: _build_prompt_json_step_for_slug(
        "claude-code-plan", inv
    ),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_config_against_registry(config: WorkflowConfig) -> None:
    """Eagerly verify that every ``StepInvocation.id`` in *config* is registered.

    Raises ``ValueError`` immediately (at registry-build time, before any
    run-time invocation) when a slug is missing.  This catches typos in
    :class:`~rouge.core.workflow.config.WorkflowConfig` definitions without
    waiting for the first pipeline build.

    Args:
        config: The declarative workflow configuration to validate.

    Raises:
        ValueError: If any step slug is not registered in the step registry.
    """
    registry = get_step_registry()
    unknown: List[str] = [
        invocation.id
        for invocation in config.steps
        if registry.get_step_metadata_by_slug(invocation.id) is None
    ]
    if unknown:
        raise ValueError(
            f"WorkflowConfig '{config.type_id}' references unregistered step slug(s): "
            f"{unknown}. Register them in the step registry before use."
        )


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
    previous_invocation: Optional[StepInvocation] = None

    for invocation in config.steps:
        if not _evaluate_when(invocation):
            continue

        # Precondition: the caller (or the registry-init path via
        # ``validate_config_against_registry``) should have already verified
        # all slugs.  This guard is a defensive backstop for ``resolve_workflow``
        # callers that bypass ``get_workflow_registry()`` (e.g. tests or YAML
        # loaders that call ``resolve_workflow`` directly).  The same slug check
        # lives in ``validate_config_against_registry``; both ultimately express
        # the same rule so they should be kept consistent.
        metadata: Optional[StepMetadata] = registry.get_step_metadata_by_slug(invocation.id)
        if metadata is None:
            raise ValueError(f"Step slug '{invocation.id}' is not registered in the step registry")

        # ``implement-plan`` needs the previous invocation to resolve
        # ``plan_step_name`` from the preceding step's ``display_name`` when
        # ``settings["plan_step_name"]`` is absent; handle it outside the
        # generic factory map.
        if invocation.id == "implement-plan":
            step: WorkflowStep = _build_implement_plan_step(invocation, previous_invocation)
        else:
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
                # Read-only property on legacy classes; log and skip.
                logger.warning(
                    "Step '%s' (slug '%s') has a read-only 'name' property; "
                    "display_name override '%s' was not applied.",
                    type(step).__name__,
                    invocation.id,
                    invocation.display_name,
                )

        resolved.append(step)
        previous_invocation = invocation

    return resolved
