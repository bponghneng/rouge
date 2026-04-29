"""Shared plan-building constants and helpers for plan steps.

Plan steps produce a PlanArtifact from the same JSON schema; centralising the
schema and the template-execution logic avoids divergence across copies.

The helpers exposed here are consumed by both the legacy concrete plan classes
(``ThinPlanStep``, ``PatchPlanStep``, ``ClaudeCodePlanStep``) and the
declarative ``PromptJsonStep`` executor introduced in Phase 2.  Both code paths
must read the same artifact bindings; the shared maps below are the single
source of truth for which artifact class corresponds to a given artifact-type
slug and for the JSON-schema variants.
"""

from typing import Any, Dict, Mapping, Type

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.models import Issue
from rouge.core.prompts import PromptId
from rouge.core.utils import get_logger
from rouge.core.workflow.artifacts import (
    Artifact,
    ArtifactType,
    FetchIssueArtifact,
    FetchPatchArtifact,
)
from rouge.core.workflow.shared import AGENT_PLANNER
from rouge.core.workflow.types import PlanData, StepResult

# Required fields for plan output JSON.
# Plan output must have type, output, plan (inline content), summary.
PLAN_REQUIRED_FIELDS = {
    "type": str,
    "output": str,
    "plan": str,
    "summary": str,
}

PLAN_JSON_SCHEMA = """{
  "type": "object",
  "properties": {
    "type": { "type": "string", "minLength": 1 },
    "output": { "type": "string", "const": "plan" },
    "plan": { "type": "string", "minLength": 1 },
    "summary": { "type": "string", "minLength": 1 }
  },
  "required": ["type", "output", "plan", "summary"]
}"""


# Required fields for the task-keyed plan output JSON used by ClaudeCodePlanStep.
PLAN_TASK_REQUIRED_FIELDS = {
    "task": str,
    "output": str,
    "plan": str,
    "summary": str,
}

PLAN_TASK_JSON_SCHEMA = """{
  "type": "object",
  "properties": {
    "task": { "type": "string", "minLength": 1 },
    "output": { "type": "string", "const": "plan" },
    "plan": { "type": "string", "minLength": 1 },
    "summary": { "type": "string", "minLength": 1 }
  },
  "required": ["task", "output", "plan", "summary"]
}"""


# Map of json-schema kinds used by ``PromptJsonStep`` to (required-fields,
# json-schema) pairs. These mirror the constants defined alongside each legacy
# plan step so all plan paths validate against the same schema.
PLAN_JSON_SCHEMA_KINDS: Dict[str, tuple[Mapping[str, type[Any]], str]] = {
    "plan_chore_bug_feature": (PLAN_REQUIRED_FIELDS, PLAN_JSON_SCHEMA),
    "plan_task": (PLAN_TASK_REQUIRED_FIELDS, PLAN_TASK_JSON_SCHEMA),
}


# Map from artifact-type slug to the concrete artifact model class.  Restricted
# to the artifacts that ``PromptJsonStep`` accepts as input today; extend here
# as new declarative plan inputs are added.
INPUT_ARTIFACT_CLASSES: Dict[ArtifactType, Type[Artifact]] = {
    "fetch-issue": FetchIssueArtifact,
    "fetch-patch": FetchPatchArtifact,
}


def get_input_artifact_class(name: str) -> Type[Artifact]:
    """Look up an input-artifact class by its registered string name.

    Args:
        name: The artifact-type slug (e.g. ``"fetch-issue"``) or class name
            (e.g. ``"FetchIssueArtifact"``).

    Returns:
        The artifact model class registered for the given name.

    Raises:
        ValueError: If the name does not correspond to a registered input
            artifact class.
    """
    # Allow callers to pass either the artifact-type slug or the class __name__
    # so YAML configs can be slightly more forgiving.
    for slug, cls in INPUT_ARTIFACT_CLASSES.items():
        if name == slug or name == cls.__name__:
            return cls
    known_names = sorted(
        {
            *INPUT_ARTIFACT_CLASSES,
            *(c.__name__ for c in INPUT_ARTIFACT_CLASSES.values()),
        }
    )
    raise ValueError(f"Unknown input artifact name '{name}'. Known: {known_names}")


def get_plan_json_schema_kind(kind: str) -> tuple[Mapping[str, type[Any]], str]:
    """Look up the required-fields and JSON-schema string for a schema kind.

    Args:
        kind: One of the keys in ``PLAN_JSON_SCHEMA_KINDS``.

    Returns:
        Tuple of ``(required_fields, json_schema_string)``.

    Raises:
        ValueError: If ``kind`` is not a known plan schema kind.
    """
    try:
        return PLAN_JSON_SCHEMA_KINDS[kind]
    except KeyError as exc:
        raise ValueError(
            f"Unknown plan json_schema_kind '{kind}'. Known: {sorted(PLAN_JSON_SCHEMA_KINDS)}"
        ) from exc


def build_plan_from_template(
    issue: Issue,
    prompt_id: PromptId,
    adw_id: str,
) -> StepResult[PlanData]:
    """Build an implementation plan by executing *prompt_id* against *issue*.

    Shared by plan steps so that schema changes and empty-output
    guards are applied consistently in both paths.

    Args:
        issue: The Rouge issue to plan for.
        prompt_id: The planning prompt to use (e.g. PromptId.PATCH_PLAN).
        adw_id: Workflow ID used for scoped logging.

    Returns:
        StepResult with PlanData containing the plan text and optional session_id.
    """
    logger = get_logger(adw_id)
    request = ClaudeAgentTemplateRequest(
        agent_name=AGENT_PLANNER,
        prompt_id=prompt_id,
        args=[issue.description],
        adw_id=adw_id,
        issue_id=issue.id,
        model="sonnet",
        json_schema=PLAN_JSON_SCHEMA,
    )
    logger.debug(
        "build_plan request: %s",
        request.model_dump_json(indent=2, by_alias=True),
    )
    response = execute_template(request)
    logger.debug(
        "build_plan response: %s",
        response.model_dump_json(indent=2, by_alias=True),
    )

    if not response.success:
        return StepResult.fail(response.output or "Agent failed without message")

    # Guard: ensure output is present before attempting JSON parse.
    if not response.output:
        return StepResult.fail("No output from template execution")

    # Parse and validate JSON output.
    parse_result = parse_and_validate_json(
        response.output, PLAN_REQUIRED_FIELDS, step_name="build_plan"
    )
    if not parse_result.success:
        return StepResult.fail(parse_result.error or "JSON parsing failed")

    parsed_data = parse_result.data or {}
    return StepResult.ok(
        PlanData(
            plan=parsed_data.get("plan", ""),
            summary=parsed_data.get("summary", ""),
            session_id=response.session_id,
        ),
        parsed_data=parsed_data,
    )
