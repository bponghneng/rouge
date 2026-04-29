"""Declarative workflow configuration models.

This module defines the Pydantic models that describe a workflow as a list of
``StepInvocation`` entries plus optional metadata. These models are pure data
schemas: they do not load YAML, do not resolve step classes, and do not execute
anything. Phase 2/3 work will introduce a separate resolver/executor layer that
turns a ``WorkflowConfig`` into a runnable pipeline and a registry build-time
check that every ``StepInvocation.id`` is registered in ``step_registry``.

Notes for downstream phases:
    * Cross-cutting validation (e.g. verifying that each ``StepInvocation.id``
      exists in the step registry) is intentionally NOT performed here. Those
      checks belong with the resolver/registry build step so this module stays
      free of registry imports and can be loaded eagerly without side effects.
    * Field ordering and naming follow the rest of the workflow package
      (Pydantic v2 ``BaseModel`` with ``Field`` for descriptions/defaults and
      ``field_validator``/``model_validator`` for normalization).
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class StepCondition(BaseModel):
    """Minimal gating clause for a step invocation.

    Today this only supports environment-variable equality / membership checks.
    The intent is to keep the surface area small while real conditions can be
    expressed at the YAML level. Future kinds of conditions (boolean
    combinators, expression evaluation, etc.) can be added as additional
    optional fields without breaking existing configs.

    Attributes:
        env: Name of the environment variable to inspect. Required.
        equals: When set, the condition matches if ``os.environ[env] == equals``.
            When ``equals`` is ``None`` and ``in_`` is ``None``, the condition
            matches when ``env`` is set and non-empty.
        in_: When set, the condition matches if the env var's value is one of
            the listed strings. Serialized/parsed under the YAML-friendly key
            ``in`` (Python's ``in`` is a reserved keyword, hence the alias).
    """

    env: str = Field(
        description="Name of the environment variable to inspect",
        min_length=1,
    )
    equals: Optional[str] = Field(
        default=None,
        description="Match when the env var equals this exact string",
    )
    in_: Optional[List[str]] = Field(
        default=None,
        alias="in",
        description="Match when the env var's value is one of the listed strings",
    )

    @field_validator("env")
    @classmethod
    def _trim_env(cls, value: str) -> str:
        """Trim whitespace from env name and ensure non-empty."""
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("env must be non-empty after trimming")
        return trimmed

    model_config = {
        # Allow consumers to construct the model with either ``in`` (alias, the
        # YAML-facing key) or ``in_`` (the Python attribute) so both forms work
        # in tests and resolver code.
        "populate_by_name": True,
    }


class StepInvocation(BaseModel):
    """One entry in a workflow's step list.

    A ``StepInvocation`` is a declarative reference to a step registered in the
    step registry. It carries a stable ``id`` (the registry slug), an optional
    human-readable ``display_name`` for logs/comments, executor-specific
    ``settings``, and an optional ``when`` clause that gates execution.

    Attributes:
        id: Stable slug for the step. Must match a slug registered in
            ``step_registry``. Validation that the slug exists is performed at
            registry build time (Phase 2/3), not in this model.
        display_name: Optional human-readable override for log lines and
            comment output. When ``None``, the step's own ``name`` is used.
        settings: Free-form executor-specific configuration. The executor for
            a given step decides how (or whether) to interpret these values.
        when: Optional condition clause. When ``None``, the step always runs.
    """

    id: str = Field(
        description="Stable slug; must match an entry in step_registry",
        min_length=1,
    )
    display_name: Optional[str] = Field(
        default=None,
        description="Optional human-readable override for logs/comments",
    )
    settings: Dict[str, Any] = Field(
        default_factory=dict,
        description="Executor-specific configuration values",
    )
    when: Optional[StepCondition] = Field(
        default=None,
        description="Optional gating clause (platform/env)",
    )

    @field_validator("id")
    @classmethod
    def _trim_id(cls, value: str) -> str:
        """Trim whitespace from id and ensure non-empty after trimming."""
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("id must be non-empty after trimming")
        return trimmed

    @field_validator("display_name")
    @classmethod
    def _trim_display_name(cls, value: Optional[str]) -> Optional[str]:
        """Trim whitespace from display_name when provided."""
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed if trimmed else None


class WorkflowConfig(BaseModel):
    """Declarative description of a workflow.

    A ``WorkflowConfig`` is a pure data structure: it lists the steps that make
    up a workflow in execution order along with a ``type_id`` used to register
    the workflow in higher-level registries. Resolving step IDs to concrete
    classes and constructing a runnable pipeline is the job of the resolver
    layer in Phase 2/3.

    Attributes:
        type_id: Stable identifier for this workflow type (e.g. ``"full"``,
            ``"thin"``, ``"patch"``). Used by routing/registry layers.
        description: Optional short description of the workflow's purpose.
        steps: Ordered list of step invocations. Must be non-empty and step IDs
            must be unique within the workflow.
    """

    type_id: str = Field(
        description="Stable identifier for the workflow type",
        min_length=1,
    )
    description: str = Field(
        default="",
        description="Optional short description of the workflow",
    )
    steps: List[StepInvocation] = Field(
        description="Ordered list of step invocations (must be non-empty)",
    )

    @field_validator("type_id")
    @classmethod
    def _trim_type_id(cls, value: str) -> str:
        """Trim whitespace from type_id and ensure non-empty after trimming."""
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("type_id must be non-empty after trimming")
        return trimmed

    @model_validator(mode="after")
    def _validate_steps(self) -> "WorkflowConfig":
        """Ensure steps is non-empty and step IDs are unique."""
        if not self.steps:
            raise ValueError("steps must be a non-empty list")

        seen: Dict[str, int] = {}
        for index, invocation in enumerate(self.steps):
            if invocation.id in seen:
                raise ValueError(
                    f"duplicate step id '{invocation.id}' at indexes "
                    f"{seen[invocation.id]} and {index}; step ids must be unique "
                    f"within a workflow"
                )
            seen[invocation.id] = index
        return self
