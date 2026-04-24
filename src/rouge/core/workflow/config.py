"""Declarative Pydantic configuration models for workflow pipeline assembly.

This module defines the data schema used to describe workflow pipelines in
configuration (as opposed to hand-coded Python). The models here are the
source of truth for pipeline composition; runtime wiring is implemented in
a separate executor layer and is NOT part of this module.

Models
------
- :class:`ArtifactBindingConfig`: describes one input artifact consumed by a
  step, including its context key and whether the step treats it as required.
- :class:`ExecutorConfigBase`: common fields shared by every executor config.
- :class:`PromptJsonStepConfig`: config for a prompt-driven step that runs a
  packaged prompt and validates the resulting JSON payload.
- :class:`LegacyStepConfig`: config for wrapping an existing
  :class:`~rouge.core.workflow.step_base.WorkflowStep` implementation.
- :class:`WorkflowConfig`: top-level container holding an ordered list of step
  invocations plus optional platform gating rules.

All models use Pydantic v2 style (``@field_validator``,
``@model_validator(mode="after")``, ``model_dump``, ``model_validate``).
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from rouge.core.prompts import PromptId
from rouge.core.workflow.artifacts import ARTIFACT_MODELS, ArtifactType

# Kebab-case slug pattern: lowercase letter start, then lowercase alphanumerics or hyphens.
_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")

# Module-level qualified path pattern: ``module.path:ClassName``. Requires exactly one colon
# separating a dotted Python module path from a Python identifier.
_IMPORT_PATH_PATTERN = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*:[A-Za-z_][A-Za-z0-9_]*$"
)

# Values allowed in ``PromptJsonStepConfig.required_fields`` mapping.
_ALLOWED_REQUIRED_FIELD_TYPES = frozenset({"str", "list", "dict", "int", "float", "bool"})


class ArtifactBindingConfig(BaseModel):
    """Describe a single artifact input consumed by a step.

    Attributes:
        context_key: The key the step expects this artifact to be bound to
            inside the workflow execution context.
        artifact_type: The artifact type name (must be a key in
            :data:`rouge.core.workflow.artifacts.ARTIFACT_MODELS`).
        required: Whether the step requires this artifact to be present.
    """

    model_config = ConfigDict(extra="forbid")

    context_key: str
    artifact_type: ArtifactType
    required: bool = True

    @field_validator("context_key")
    @classmethod
    def _validate_context_key(cls, value: str) -> str:
        """Reject empty or whitespace-only context keys."""
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("context_key cannot be empty or whitespace-only")
        return trimmed

    @field_validator("artifact_type")
    @classmethod
    def _validate_artifact_type(cls, value: str) -> str:
        """Ensure artifact_type is a known registered artifact."""
        if value not in ARTIFACT_MODELS:
            raise ValueError(
                f"Unknown artifact_type '{value}'. "
                f"Must be one of: {sorted(ARTIFACT_MODELS.keys())}"
            )
        return value


class ExecutorConfigBase(BaseModel):
    """Common configuration shared by every executor variant.

    Subclasses override ``kind`` with a ``Literal`` value so Pydantic can
    resolve the correct concrete type via a discriminated union.

    Attributes:
        kind: Discriminator identifying the executor subtype.
        step_id: Unique kebab-case slug identifying this step invocation
            within a workflow. Must match ``^[a-z][a-z0-9-]*$``.
        display_name: Human-readable name used in logs and CLI output.
        critical: When True, workflow aborts on failure. When False, failure
            is non-fatal and the pipeline continues.
        outputs: Artifact types this step is expected to produce.
        inputs: Artifact bindings describing required/optional inputs.
    """

    model_config = ConfigDict(extra="forbid")

    kind: str
    step_id: str
    display_name: str
    critical: bool = True
    outputs: list[ArtifactType] = Field(default_factory=list)
    inputs: list[ArtifactBindingConfig] = Field(default_factory=list)

    @field_validator("step_id")
    @classmethod
    def _validate_step_id(cls, value: str) -> str:
        """Enforce kebab-case slug format on step_id."""
        if not _SLUG_PATTERN.fullmatch(value):
            raise ValueError(
                f"step_id '{value}' must be kebab-case: start with a lowercase "
                f"letter and contain only lowercase letters, digits, and hyphens"
            )
        return value

    @field_validator("display_name")
    @classmethod
    def _validate_display_name(cls, value: str) -> str:
        """Reject empty or whitespace-only display names."""
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("display_name cannot be empty or whitespace-only")
        return trimmed

    @field_validator("outputs")
    @classmethod
    def _validate_outputs(cls, value: list[str]) -> list[str]:
        """Ensure every output is a known registered artifact type."""
        for artifact_type in value:
            if artifact_type not in ARTIFACT_MODELS:
                raise ValueError(
                    f"Unknown output artifact_type '{artifact_type}'. "
                    f"Must be one of: {sorted(ARTIFACT_MODELS.keys())}"
                )
        return value


class PromptJsonStepConfig(ExecutorConfigBase):
    """Configuration for a prompt-driven step that returns validated JSON.

    Attributes:
        kind: Always ``"prompt-json"``.
        prompt_id: Identifier of the packaged prompt template to render.
        agent_name: Name of the agent registry entry to invoke.
        model: Claude model alias to use (defaults to ``"sonnet"``).
        json_schema: Name of the JSON schema the prompt response must satisfy.
        required_fields: Mapping of field name to expected Python type name.
            Values are restricted to
            ``{"str", "list", "dict", "int", "float", "bool"}``.
        issue_binding: Which artifact supplies the ``issue`` argument passed
            to the prompt template. Only ``"fetch-issue"`` and
            ``"fetch-patch"`` are supported in Phase 1.
        output_artifact: Artifact type produced by this step.
        rerun_target: Optional slug of an earlier step to rewind to when
            response validation fails.
    """

    kind: Literal["prompt-json"] = "prompt-json"
    prompt_id: PromptId
    agent_name: str
    model: str = "sonnet"
    json_schema: str
    required_fields: dict[str, str]
    issue_binding: Literal["fetch-issue", "fetch-patch"]
    output_artifact: ArtifactType
    rerun_target: str | None = None

    @field_validator("agent_name", "json_schema")
    @classmethod
    def _validate_non_empty_str(cls, value: str) -> str:
        """Reject empty or whitespace-only values."""
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("value cannot be empty or whitespace-only")
        return trimmed

    @field_validator("model")
    @classmethod
    def _validate_model(cls, value: str) -> str:
        """Reject empty or whitespace-only model aliases."""
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("model cannot be empty or whitespace-only")
        return trimmed

    @field_validator("required_fields")
    @classmethod
    def _validate_required_fields(cls, value: dict[str, str]) -> dict[str, str]:
        """Ensure required_fields values are restricted to the allowed type set."""
        for field_name, type_name in value.items():
            if not isinstance(field_name, str) or not field_name.strip():
                raise ValueError("required_fields keys must be non-empty strings")
            if type_name not in _ALLOWED_REQUIRED_FIELD_TYPES:
                raise ValueError(
                    f"required_fields['{field_name}'] has value '{type_name}', "
                    f"must be one of: {sorted(_ALLOWED_REQUIRED_FIELD_TYPES)}"
                )
        return value

    @field_validator("output_artifact")
    @classmethod
    def _validate_output_artifact(cls, value: str) -> str:
        """Ensure output_artifact is a known registered artifact type."""
        if value not in ARTIFACT_MODELS:
            raise ValueError(
                f"Unknown output_artifact '{value}'. "
                f"Must be one of: {sorted(ARTIFACT_MODELS.keys())}"
            )
        return value

    @field_validator("rerun_target")
    @classmethod
    def _validate_rerun_target(cls, value: str | None) -> str | None:
        """Validate rerun_target is a kebab-case slug if provided."""
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("rerun_target cannot be empty or whitespace-only")
        if not _SLUG_PATTERN.fullmatch(trimmed):
            raise ValueError(
                f"rerun_target '{value}' must be kebab-case: start with a lowercase "
                f"letter and contain only lowercase letters, digits, and hyphens"
            )
        return trimmed


class LegacyStepConfig(ExecutorConfigBase):
    """Configuration that wraps an existing :class:`WorkflowStep` class.

    Attributes:
        kind: Always ``"legacy"``.
        import_path: Fully-qualified target of the form
            ``"package.module:ClassName"``. Must contain exactly one colon
            separating a dotted module path from a Python identifier.
        init_kwargs: Keyword arguments to pass when constructing the wrapped
            step class.
    """

    kind: Literal["legacy"] = "legacy"
    import_path: str
    init_kwargs: dict[str, Any] = Field(default_factory=dict)

    @field_validator("import_path")
    @classmethod
    def _validate_import_path(cls, value: str) -> str:
        """Validate the ``module.path:ClassName`` format."""
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("import_path cannot be empty or whitespace-only")
        if trimmed.count(":") != 1:
            raise ValueError(
                f"import_path '{value}' must contain exactly one ':' separating "
                f"the module path from the class name (e.g. 'pkg.mod:ClassName')"
            )
        if not _IMPORT_PATH_PATTERN.fullmatch(trimmed):
            raise ValueError(
                f"import_path '{value}' is not a valid dotted module path followed by "
                f"':ClassName'"
            )
        return trimmed


# Discriminated union for step invocation configs. Pydantic uses the ``kind``
# field to select the correct concrete subclass during validation.
StepInvocationConfig = Annotated[
    Union[PromptJsonStepConfig, LegacyStepConfig],
    Field(discriminator="kind"),
]


class WorkflowConfig(BaseModel):
    """Top-level configuration for a workflow pipeline.

    Attributes:
        type_id: Stable identifier for this workflow type (e.g. ``"full"``).
        description: Optional human-readable description.
        steps: Ordered list of step invocations composing the pipeline.
        platform_gate: Optional map of platform name to the list of step
            slugs that should only run on that platform. All slugs listed
            here must correspond to a ``step_id`` present in ``steps``.
    """

    model_config = ConfigDict(extra="forbid")

    type_id: str
    description: str = ""
    steps: list[StepInvocationConfig]
    platform_gate: dict[str, list[str]] | None = None

    @field_validator("type_id")
    @classmethod
    def _validate_type_id(cls, value: str) -> str:
        """Reject empty or whitespace-only type IDs."""
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("type_id cannot be empty or whitespace-only")
        return trimmed

    @model_validator(mode="after")
    def _validate_unique_step_ids(self) -> "WorkflowConfig":
        """Ensure step_id values are unique across steps."""
        seen: set[str] = set()
        duplicates: set[str] = set()
        for step in self.steps:
            if step.step_id in seen:
                duplicates.add(step.step_id)
            seen.add(step.step_id)
        if duplicates:
            raise ValueError(
                f"Duplicate step_id values in WorkflowConfig.steps: {sorted(duplicates)}"
            )
        return self

    @model_validator(mode="after")
    def _validate_platform_gate_refs(self) -> "WorkflowConfig":
        """Ensure every slug in platform_gate exists in steps[*].step_id."""
        if self.platform_gate is None:
            return self

        known_slugs = {step.step_id for step in self.steps}
        unknown: list[tuple[str, str]] = []
        for platform, slugs in self.platform_gate.items():
            if not isinstance(platform, str) or not platform.strip():
                raise ValueError("platform_gate keys must be non-empty strings")
            for slug in slugs:
                if slug not in known_slugs:
                    unknown.append((platform, slug))

        if unknown:
            formatted = ", ".join(f"{platform!r} -> {slug!r}" for platform, slug in unknown)
            raise ValueError(
                f"platform_gate references unknown step slugs: {formatted}. "
                f"Known slugs: {sorted(known_slugs)}"
            )
        return self


__all__ = [
    "ArtifactBindingConfig",
    "ExecutorConfigBase",
    "LegacyStepConfig",
    "PromptJsonStepConfig",
    "StepInvocationConfig",
    "WorkflowConfig",
]
