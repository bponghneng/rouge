"""Reusable prompt-driven JSON workflow step executor.

This module provides :class:`PromptJsonStep`, a config-driven
:class:`WorkflowStep` that runs a packaged prompt template, validates the
resulting JSON payload, persists an output artifact, and emits progress
comments.  The executor is designed to grow by registering new payload
builders via :func:`register_payload_builder`.  ``ImplementPlanStep`` and
``ComposeRequestStep`` migration is tracked as follow-up work.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Type

from rouge.core.agent import execute_template
from rouge.core.agents.claude import (
    ClaudeAgentPromptResponse,
    ClaudeAgentTemplateRequest,
)
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.models import CommentPayload, Issue
from rouge.core.notifications.comments import (
    emit_artifact_comment,
    emit_comment_from_payload,
    log_artifact_comment_status,
)
from rouge.core.utils import get_logger
from rouge.core.workflow.artifacts import (
    ARTIFACT_MODELS,
    Artifact,
    ArtifactType,
    FetchIssueArtifact,
    FetchPatchArtifact,
    PlanArtifact,
)
from rouge.core.workflow.config import PromptJsonStepConfig
from rouge.core.workflow.step_base import StepInputError, WorkflowContext, WorkflowStep
from rouge.core.workflow.types import PlanData, StepResult

# Mapping of ``required_fields`` type names (as used in config files) to the
# Python ``type`` objects expected by ``parse_and_validate_json``.
_REQUIRED_FIELD_TYPE_MAP: Dict[str, Type[Any]] = {
    "str": str,
    "list": list,
    "dict": dict,
    "int": int,
    "float": float,
    "bool": bool,
}


# Callable signature for builder functions.  A builder accepts the parsed JSON
# dict, the agent response, and the workflow (adw) id and returns the
# constructed artifact instance.
ArtifactPayloadBuilder = Callable[[Dict[str, Any], ClaudeAgentPromptResponse, str], Artifact]


# Registry of payload builders keyed by the artifact type they produce.
_PAYLOAD_BUILDERS: Dict[ArtifactType, ArtifactPayloadBuilder] = {}


def register_payload_builder(artifact_type: ArtifactType, builder: ArtifactPayloadBuilder) -> None:
    """Register a payload builder for an artifact type.

    Args:
        artifact_type: The artifact type this builder produces.
        builder: Callable that converts parsed JSON + response + adw_id into
            an :class:`Artifact` instance.
    """
    _PAYLOAD_BUILDERS[artifact_type] = builder


def _build_plan_artifact(
    parsed: Dict[str, Any],
    response: ClaudeAgentPromptResponse,
    adw_id: str,
) -> Artifact:
    """Default builder for ``PlanArtifact`` payloads."""
    return PlanArtifact(
        workflow_id=adw_id,
        plan_data=PlanData(
            plan=parsed.get("plan", ""),
            summary=parsed.get("summary", ""),
            session_id=response.session_id,
        ),
    )


# Register built-in builders at import time.
register_payload_builder("plan", _build_plan_artifact)


class PromptJsonStep(WorkflowStep):
    """Generic ``prompt-json`` workflow step driven by configuration.

    Instances wrap a :class:`PromptJsonStepConfig` and execute the declared
    prompt against the configured agent, validating the resulting JSON and
    writing an output artifact using a registered payload builder.
    """

    def __init__(self, config: PromptJsonStepConfig) -> None:
        """Validate the config's output artifact has a registered builder.

        Args:
            config: The validated configuration for this step.

        Raises:
            ValueError: If ``config.output_artifact`` has no registered builder.
        """
        if config.output_artifact not in _PAYLOAD_BUILDERS:
            raise ValueError(
                f"No payload builder registered for output_artifact "
                f"'{config.output_artifact}'. Register one via "
                f"register_payload_builder() before constructing PromptJsonStep."
            )
        self._config = config

    @property
    def step_id(self) -> str:
        """Return the slug declared in the config."""
        return self._config.step_id

    @property
    def name(self) -> str:
        """Return the human-readable display name from the config."""
        return self._config.display_name

    @property
    def is_critical(self) -> bool:
        """Return whether step failure should abort the workflow."""
        return self._config.critical

    def _convert_required_fields(self) -> Dict[str, Type[Any]]:
        """Translate config string type names to Python types.

        Returns:
            Mapping of field name to the ``type`` expected by
            :func:`parse_and_validate_json`.
        """
        return {
            name: _REQUIRED_FIELD_TYPE_MAP[type_name]
            for name, type_name in self._config.required_fields.items()
        }

    def _load_issue(self, context: WorkflowContext) -> Issue:
        """Load the Issue that supplies the prompt's description argument.

        The source artifact is selected by ``config.issue_binding``.  The
        artifact is loaded as *required* regardless of whether the caller
        declared it in ``config.inputs`` because it is essential for prompt
        execution.
        """
        if self._config.issue_binding == "fetch-issue":
            issue = context.load_required_artifact(
                "issue",
                "fetch-issue",
                FetchIssueArtifact,
                lambda a: a.issue,
            )
        else:  # "fetch-patch"
            issue = context.load_required_artifact(
                "fetch_patch_data",
                "fetch-patch",
                FetchPatchArtifact,
                lambda a: a.patch,
            )
        return issue

    def _load_declared_inputs(self, context: WorkflowContext) -> Dict[str, Any]:
        """Load artifacts declared in ``config.inputs``.

        Required bindings propagate :class:`StepInputError` on missing
        artifacts; optional bindings return ``None`` silently.

        Returns:
            Dict keyed by ``binding.context_key`` with the extracted values.
        """
        loaded: Dict[str, Any] = {}
        for binding in self._config.inputs:
            artifact_class = ARTIFACT_MODELS[binding.artifact_type]
            if binding.required:
                value = context.load_required_artifact(
                    binding.context_key,
                    binding.artifact_type,
                    artifact_class,
                    lambda a: a,
                )
            else:
                value = context.load_optional_artifact(
                    binding.context_key,
                    binding.artifact_type,
                    artifact_class,
                    lambda a: a,
                )
            loaded[binding.context_key] = value
        return loaded

    def run(self, context: WorkflowContext) -> StepResult:
        """Execute the prompt-driven JSON step.

        Args:
            context: Shared workflow context.

        Returns:
            :class:`StepResult` indicating success or failure.  On failure the
            ``rerun_from`` field is populated with ``config.rerun_target``.
        """
        logger = get_logger(context.adw_id)
        rerun_target = self._config.rerun_target

        # 1. Load declared input bindings.  Missing required inputs yield a
        #    StepInputError with an artifact-type-annotated message.
        try:
            self._load_declared_inputs(context)
        except StepInputError as exc:
            logger.error("Cannot run %s: %s", self._config.step_id, exc)
            return StepResult.fail(
                f"Cannot run {self._config.step_id}: {exc}",
                rerun_from=rerun_target,
            )

        # 2. Resolve the issue argument.  The underlying artifact is loaded if
        #    it was not already in config.inputs.
        try:
            issue = self._load_issue(context)
        except StepInputError as exc:
            logger.error("Cannot run %s: %s", self._config.step_id, exc)
            return StepResult.fail(
                f"Cannot run {self._config.step_id}: {exc}",
                rerun_from=rerun_target,
            )

        # 3. Convert required_fields (str -> str) to (str -> type).
        required_fields = self._convert_required_fields()

        # 4. Build and execute the template request.
        request = ClaudeAgentTemplateRequest(
            agent_name=self._config.agent_name,
            prompt_id=self._config.prompt_id,
            args=[issue.description],
            adw_id=context.adw_id,
            issue_id=issue.id,
            model=self._config.model,  # type: ignore[arg-type]
            json_schema=self._config.json_schema,
        )
        logger.debug(
            "%s request: %s",
            self._config.step_id,
            request.model_dump_json(indent=2, by_alias=True),
        )
        response = execute_template(request)
        logger.debug(
            "%s response: %s",
            self._config.step_id,
            response.model_dump_json(indent=2, by_alias=True),
        )

        # 5. Handle agent-layer failures before attempting JSON parsing.
        if not response.success:
            error_msg = response.output or "Agent failure: no output"
            logger.error("Agent failed for %s: %s", self._config.step_id, error_msg)
            return StepResult.fail(error_msg, rerun_from=rerun_target)

        if not response.output:
            logger.error("Empty output from template execution for %s", self._config.step_id)
            return StepResult.fail(
                "No output from template execution",
                rerun_from=rerun_target,
            )

        parse_result = parse_and_validate_json(
            response.output,
            required_fields,
            step_name=self._config.step_id,
        )
        if not parse_result.success:
            error_msg = parse_result.error or "JSON parsing failed"
            logger.error("JSON parse failed for %s: %s", self._config.step_id, error_msg)
            return StepResult.fail(error_msg, rerun_from=rerun_target)

        parsed_data: Dict[str, Any] = parse_result.data or {}

        # 6. Build the output artifact via the registered payload builder.
        builder = _PAYLOAD_BUILDERS[self._config.output_artifact]
        artifact = builder(parsed_data, response, context.adw_id)

        # 7. Persist artifact and mirror plan data into context for downstream
        #    steps that still look up ``context.data["plan_data"]`` directly.
        context.artifact_store.write_artifact(artifact)
        logger.debug("Saved %s artifact for workflow %s", artifact.artifact_type, context.adw_id)

        if isinstance(artifact, PlanArtifact):
            context.data["plan_data"] = artifact.plan_data

        status, msg = emit_artifact_comment(context.issue_id, context.adw_id, artifact)
        log_artifact_comment_status(status, msg)

        # 8. Emit progress comment with the title extracted from one of the
        #    common title fields, matching the reference plan steps.
        title = (
            parsed_data.get("task")
            or parsed_data.get("chore")
            or parsed_data.get("bug")
            or parsed_data.get("feature")
            or "Implementation plan created"
        )
        summary = parsed_data.get("summary", "")
        comment_text = f"{title}\n\n{summary}" if summary else title

        payload = CommentPayload(
            issue_id=issue.id,
            adw_id=context.adw_id,
            text=comment_text,
            raw={"text": comment_text, "parsed": parsed_data},
            source="system",
            kind="workflow",
        )
        status, msg = emit_comment_from_payload(payload)
        if status == "success":
            logger.debug(msg)
        else:
            logger.error(msg)

        return StepResult.ok(None)


__all__ = [
    "ArtifactPayloadBuilder",
    "PromptJsonStep",
    "register_payload_builder",
]
