"""Resolve :class:`WorkflowConfig` objects into concrete :class:`WorkflowStep` instances.

This module bridges the declarative Pydantic configuration layer (see
:mod:`rouge.core.workflow.config`) with the runtime executor layer.  Given a
validated :class:`WorkflowConfig`, :func:`resolve_workflow` produces the
ordered list of :class:`WorkflowStep` objects the runner should execute,
applying platform-based filtering along the way.

The resolver is intentionally a pure function: it does no I/O beyond reading
environment variables (``DEV_SEC_OPS_PLATFORM`` for platform gating) and
``importlib``-driven class lookup.  Pipeline execution is handled elsewhere.
"""

from __future__ import annotations

import importlib
import logging
import os
from typing import TYPE_CHECKING

from rouge.core.workflow.config import (
    LegacyStepConfig,
    PromptJsonStepConfig,
    StepInvocationConfig,
    WorkflowConfig,
)
from rouge.core.workflow.executors.prompt_json_step import PromptJsonStep
from rouge.core.workflow.step_base import WorkflowStep

if TYPE_CHECKING:
    pass

_logger = logging.getLogger(__name__)


def _instantiate_legacy_step(entry: LegacyStepConfig) -> WorkflowStep:
    """Import and instantiate the class referenced by a LegacyStepConfig entry.

    Args:
        entry: The validated legacy step configuration.

    Returns:
        An instance of the configured :class:`WorkflowStep` subclass,
        constructed with ``entry.init_kwargs``.

    Raises:
        ValueError: If the import path is malformed, the module cannot be
            imported, the attribute does not exist on the module, or the
            resolved class is not a :class:`WorkflowStep` subclass.  The
            raised message always mentions the offending ``step_id``.
    """
    import_path = entry.import_path
    if ":" not in import_path:
        raise ValueError(
            f"Invalid import_path for step_id '{entry.step_id}': "
            f"'{import_path}' is missing ':' separating module and class name"
        )

    module_name, _, class_name = import_path.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ValueError(
            f"Cannot import module '{module_name}' for step_id " f"'{entry.step_id}': {exc}"
        ) from exc

    try:
        cls = getattr(module, class_name)
    except AttributeError as exc:
        raise ValueError(
            f"Module '{module_name}' has no attribute '{class_name}' "
            f"for step_id '{entry.step_id}': {exc}"
        ) from exc

    if not (isinstance(cls, type) and issubclass(cls, WorkflowStep)):
        raise ValueError(
            f"Class '{class_name}' resolved for step_id '{entry.step_id}' "
            f"is not a subclass of WorkflowStep"
        )

    instance = cls(**entry.init_kwargs)
    _logger.debug(
        "Resolved legacy step_id=%s to %s(**%r)",
        entry.step_id,
        class_name,
        entry.init_kwargs,
    )
    return instance


def _instantiate_step(entry: StepInvocationConfig) -> WorkflowStep:
    """Dispatch instantiation based on the concrete config variant.

    Args:
        entry: A validated step invocation configuration.

    Returns:
        The constructed :class:`WorkflowStep` instance.

    Raises:
        ValueError: If the ``kind`` is unrecognized (defensive guard; Pydantic
            will usually catch this at config validation time) or if legacy
            instantiation fails for any reason.
    """
    if isinstance(entry, PromptJsonStepConfig):
        _logger.debug("Resolved prompt-json step_id=%s", entry.step_id)
        return PromptJsonStep(entry)
    if isinstance(entry, LegacyStepConfig):
        return _instantiate_legacy_step(entry)

    # Defensive: if a new config kind is added without executor support, fail
    # loudly with the offending step_id.
    raise ValueError(
        f"Unsupported step configuration kind '{getattr(entry, 'kind', '<unknown>')}' "
        f"for step_id '{getattr(entry, 'step_id', '<unknown>')}'"
    )


def _apply_platform_gate(
    config: WorkflowConfig,
    steps: list[tuple[StepInvocationConfig, WorkflowStep]],
) -> list[WorkflowStep]:
    """Filter resolved steps according to ``config.platform_gate``.

    The active platform is read from the ``DEV_SEC_OPS_PLATFORM`` environment
    variable (case-insensitive).  Any step whose ``step_id`` appears in one or
    more ``platform_gate`` values is considered "gated" and is kept only when
    the active platform lists it.  Non-gated steps always pass through.

    Args:
        config: The workflow configuration (used for ``platform_gate``).
        steps: Ordered list of (config entry, resolved step instance) pairs.

    Returns:
        The filtered list of :class:`WorkflowStep` instances in the original
        relative order.
    """
    gate = config.platform_gate
    if gate is None:
        return [step for _, step in steps]

    active_platform = os.environ.get("DEV_SEC_OPS_PLATFORM", "").lower()

    # All step_ids that appear in any platform_gate value are "gated".
    gated_slugs: set[str] = set()
    for slugs in gate.values():
        gated_slugs.update(slugs)

    allowed_for_active = set(gate.get(active_platform, []))

    filtered: list[WorkflowStep] = []
    for entry, step in steps:
        if entry.step_id in gated_slugs and entry.step_id not in allowed_for_active:
            _logger.debug(
                "Filtering out gated step_id=%s (active platform=%r)",
                entry.step_id,
                active_platform,
            )
            continue
        filtered.append(step)
    return filtered


def resolve_workflow(config: WorkflowConfig) -> list[WorkflowStep]:
    """Resolve a :class:`WorkflowConfig` into an ordered list of runnable steps.

    The resolver instantiates each step config in declaration order:

    - :class:`PromptJsonStepConfig` entries are wrapped in :class:`PromptJsonStep`.
    - :class:`LegacyStepConfig` entries are resolved by importing the target
      module and constructing the referenced class with ``init_kwargs``.

    After instantiation, ``platform_gate`` filtering is applied based on the
    ``DEV_SEC_OPS_PLATFORM`` environment variable.

    Args:
        config: A validated workflow configuration.

    Returns:
        Ordered list of :class:`WorkflowStep` instances ready for the runner.

    Raises:
        ValueError: If any entry cannot be resolved or instantiated.  The
            message always includes the offending ``step_id``.
    """
    resolved: list[tuple[StepInvocationConfig, WorkflowStep]] = []
    for entry in config.steps:
        step = _instantiate_step(entry)
        resolved.append((entry, step))

    return _apply_platform_gate(config, resolved)


__all__ = ["resolve_workflow"]
