"""Declarative prompt-driven JSON plan executor.

``PromptJsonStep`` consolidates the three legacy plan steps (``ThinPlanStep``,
``PatchPlanStep``, ``ClaudeCodePlanStep``) into a single, configuration-driven
executor.  All three share the same shape:

1. Load an input artifact (``fetch-issue`` or ``fetch-patch``).
2. Execute a prompt template via ``execute_template``.
3. Parse and validate the JSON output against a known required-fields schema.
4. Write a ``PlanArtifact`` and emit a progress comment.

The legacy classes remain registered under their slugs so ``rouge step run``
and any direct callers continue to work; the resolver overrides those slugs at
workflow-build time to instantiate ``PromptJsonStep`` instead.
"""

from typing import Any, List, Literal, Type

from pydantic import BaseModel, Field, field_validator

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import (
    emit_artifact_comment,
    emit_comment_from_payload,
    log_artifact_comment_status,
)
from rouge.core.prompts import PromptId
from rouge.core.utils import get_logger
from rouge.core.workflow.artifacts import (
    Artifact,
    ArtifactType,
    PlanArtifact,
)
from rouge.core.workflow.plan_common import (
    get_input_artifact_class,
    get_plan_json_schema_kind,
)
from rouge.core.workflow.shared import AGENT_PLANNER
from rouge.core.workflow.step_base import (
    StepInputError,
    WorkflowContext,
    WorkflowStep,
)
from rouge.core.workflow.types import PlanData, StepResult

# Default keys to scan when extracting a progress-comment title from the parsed
# JSON output. The first non-empty match wins; this matches the existing
# behaviour of ThinPlanStep / PatchPlanStep.
DEFAULT_TITLE_KEYS: List[str] = ["chore", "bug", "feature", "task"]


class PromptJsonStepSettings(BaseModel):
    """Configuration for :class:`PromptJsonStep`.

    Attributes:
        prompt_id: The packaged prompt template to execute.
        agent_name: Agent profile to use; defaults to the planner agent.
        model: Claude model selector passed through to the template request.
        input_artifact: Artifact-type slug to load as input
            (e.g. ``"fetch-issue"``).
        input_field: Attribute name on the loaded artifact to pass into the
            prompt (e.g. ``"issue"`` or ``"patch"``).
        description_field: Attribute on the extracted input value that holds the
            text description passed as the first argument to the prompt template.
            Defaults to ``"description"`` — the field present on ``Issue``.
        id_field: Attribute on the extracted input value that holds the numeric
            issue ID forwarded to the comment payload.  Defaults to ``"id"``.
        json_schema_kind: Selects the required-fields / JSON-schema variant to
            validate the agent output against.
        title_keys: Keys to scan in the parsed JSON when picking the progress
            comment title; first non-empty match wins.
    """

    prompt_id: PromptId
    agent_name: str = AGENT_PLANNER
    model: Literal["sonnet", "opus", "haiku"] = "sonnet"
    input_artifact: ArtifactType
    input_field: str = Field(min_length=1)
    description_field: str = Field(default="description", min_length=1)
    id_field: str = Field(default="id", min_length=1)
    json_schema_kind: Literal["plan_chore_bug_feature", "plan_task"]
    title_keys: List[str] = Field(default_factory=lambda: list(DEFAULT_TITLE_KEYS))

    @field_validator("input_artifact")
    @classmethod
    def _validate_input_artifact(cls, value: ArtifactType) -> ArtifactType:
        # Force resolution at config-load time so unregistered artifact types
        # fail fast rather than at first run.
        get_input_artifact_class(value)
        return value


class PromptJsonStep(WorkflowStep):
    """Declarative plan-building step driven by :class:`PromptJsonStepSettings`.

    Mirrors the run-time behaviour of the legacy plan classes while reading
    everything (prompt id, input artifact, schema kind) from configuration so
    that workflow YAML can wire up new plan variants without subclassing.
    """

    def __init__(
        self,
        settings: PromptJsonStepSettings,
    ) -> None:
        """Initialise the step.

        Args:
            settings: The validated executor configuration.
        """
        super().__init__()
        self._settings = settings
        # Default display name; the resolver overwrites this via ``step.name =
        # invocation.display_name`` after construction, so this value is only
        # visible when the step is constructed outside the resolver (e.g. tests).
        self._display_name = "Building implementation plan"

    @property
    def name(self) -> str:
        return self._display_name

    @name.setter
    def name(self, value: str) -> None:
        # The display name is mutable so the resolver can update it after
        # construction (parallel to setting ``step_id``).
        self._display_name = value

    @property
    def is_critical(self) -> bool:
        # Plan generation is critical: downstream implement steps cannot run
        # without a PlanArtifact.
        return True

    @property
    def settings(self) -> PromptJsonStepSettings:
        """Expose the bound settings for inspection / debugging."""
        return self._settings

    def run(self, context: WorkflowContext) -> StepResult:
        """Load input, execute the prompt, validate JSON, write PlanArtifact."""
        logger = get_logger(context.adw_id)
        settings = self._settings

        # Resolve the input artifact class from the artifact-type slug.
        # Validation in ``PromptJsonStepSettings`` already ensured the slug is registered.
        artifact_class: Type[Artifact] = get_input_artifact_class(settings.input_artifact)

        # Load the input artifact and extract the configured field.  Mirrors
        # the load_required_artifact pattern used by the legacy steps so the
        # missing-artifact error message is identical.
        field_name = settings.input_field

        def _extract(artifact: Artifact) -> Any:
            return getattr(artifact, field_name)

        try:
            input_value: Any = context.load_required_artifact(
                settings.input_field,
                settings.input_artifact,
                artifact_class,
                _extract,
            )
        except StepInputError as exc:
            logger.error("Cannot run %s: %s", self._display_name, exc)
            return StepResult.fail(f"Cannot run {self._display_name}: {exc}")
        except AttributeError as exc:
            logger.error(
                "Configured input_field '%s' missing on artifact '%s': %s",
                settings.input_field,
                settings.input_artifact,
                exc,
            )
            return StepResult.fail(
                f"Configured input_field '{settings.input_field}' missing on "
                f"artifact '{settings.input_artifact}'"
            )

        # The prompt templates expect the issue description as the first arg
        # (matches legacy ThinPlanStep/PatchPlanStep/ClaudeCodePlanStep).
        # ``description_field`` and ``id_field`` are configurable so the executor
        # is not silently coupled to ``Issue``-shaped inputs.
        description = getattr(input_value, settings.description_field, None)
        if description is None:
            return StepResult.fail(
                f"Input '{settings.input_field}' has no "
                f"'{settings.description_field}' attribute; "
                "configure 'description_field' in PromptJsonStepSettings "
                "if your input shape differs."
            )
        issue_id = getattr(input_value, settings.id_field, None)

        required_fields, json_schema_str = get_plan_json_schema_kind(settings.json_schema_kind)

        request = ClaudeAgentTemplateRequest(
            agent_name=settings.agent_name,
            prompt_id=settings.prompt_id,
            args=[description],
            adw_id=context.adw_id,
            issue_id=issue_id,
            model=settings.model,
            json_schema=json_schema_str,
        )
        logger.debug(
            "PromptJsonStep request: %s",
            request.model_dump_json(indent=2, by_alias=True),
        )
        response = execute_template(request)
        logger.debug(
            "PromptJsonStep response: %s",
            response.model_dump_json(indent=2, by_alias=True),
        )

        if not response.success:
            error = response.output or "Agent failed without message"
            logger.error("Error running %s: %s", self._display_name, error)
            return StepResult.fail(f"Error running {self._display_name}: {error}")

        if not response.output:
            logger.error("%s: no output from template execution", self._display_name)
            return StepResult.fail("No output from template execution")

        parse_result = parse_and_validate_json(
            response.output, required_fields, step_name=self._display_name
        )
        if not parse_result.success:
            return StepResult.fail(parse_result.error or "JSON parsing failed")

        parsed_data = parse_result.data or {}

        plan_data = PlanData(
            plan=parsed_data.get("plan", ""),
            summary=parsed_data.get("summary", ""),
            session_id=response.session_id,
        )
        # Cache the plan data on the context so downstream legacy code that
        # reads ``context.data["plan_data"]`` keeps working.
        context.data["plan_data"] = plan_data

        artifact = PlanArtifact(
            workflow_id=context.adw_id,
            plan_data=plan_data,
        )
        context.artifact_store.write_artifact(artifact)
        logger.debug("Saved plan artifact for workflow %s", context.adw_id)

        # ``emit_artifact_comment`` is best-effort: comment emission failures are
        # logged by ``log_artifact_comment_status`` but do not propagate to the
        # step result.  The ``PlanArtifact`` has already been written at this
        # point, so the plan data is not lost even if the comment fails.
        status, msg = emit_artifact_comment(context.issue_id, context.adw_id, artifact)
        log_artifact_comment_status(status, msg)

        # Build a progress comment using the configured title-key precedence.
        title = next(
            (
                parsed_data[key]
                for key in settings.title_keys
                if isinstance(parsed_data.get(key), str) and parsed_data[key]
            ),
            "Implementation plan created",
        )
        summary = parsed_data.get("summary", "")
        comment_text = f"{title}\n\n{summary}" if summary else title

        payload = CommentPayload(
            issue_id=issue_id if isinstance(issue_id, int) else context.issue_id,
            adw_id=context.adw_id,
            text=comment_text,
            raw={"text": comment_text, "parsed": parsed_data},
            source="system",
            kind="workflow",
        )
        comment_status, comment_msg = emit_comment_from_payload(payload)
        if comment_status == "success":
            logger.debug(comment_msg)
        else:
            logger.error(comment_msg)

        return StepResult.ok(None)
