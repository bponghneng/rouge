"""Issue classification functionality for workflow orchestration."""

import json
from logging import Logger
from typing import Callable, Optional, cast

from cape.core.agent import execute_template
from cape.core.agents.claude import ClaudeAgentTemplateRequest
from cape.core.models import CapeIssue
from cape.core.workflow.shared import AGENT_CLASSIFIER
from cape.core.workflow.types import ClassifyData, ClassifySlashCommand, StepResult


def classify_issue(
    issue: CapeIssue,
    adw_id: str,
    logger: Logger,
    stream_handler: Optional[Callable[[str], None]] = None,
) -> StepResult[ClassifyData]:
    """Classify issue and return appropriate slash command.

    Args:
        issue: The Cape issue to classify
        adw_id: Workflow ID for tracking
        logger: Logger instance
        stream_handler: Optional callback for streaming output

    Returns:
        StepResult with ClassifyData containing command and classification
    """
    request = ClaudeAgentTemplateRequest(
        agent_name=AGENT_CLASSIFIER,
        slash_command="/triage:classify",
        args=[issue.description],
        adw_id=adw_id,
        issue_id=issue.id,
        model="sonnet",
    )
    logger.debug(
        "classify request: %s",
        request.model_dump_json(indent=2, by_alias=True),
    )
    response = execute_template(request, stream_handler=stream_handler)
    logger.debug(
        "classify response: %s",
        response.model_dump_json(indent=2, by_alias=True),
    )

    if not response.success:
        return StepResult.fail(response.output)

    raw_output = response.output.strip()
    logger.debug("Classifier raw output: %s", raw_output)
    try:
        classification_data = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        logger.error("Classifier JSON decode failed: %s | raw=%s", exc, raw_output)
        return StepResult.fail(f"Invalid classification JSON: {exc}")

    if not isinstance(classification_data, dict):
        return StepResult.fail("Invalid classification response type")

    issue_type = classification_data.get("type")
    complexity_level = classification_data.get("level")

    if not isinstance(issue_type, str):
        return StepResult.fail("Classification missing 'type' field")
    if not isinstance(complexity_level, str):
        return StepResult.fail("Classification missing 'level' field")

    normalized_type = issue_type.strip().lower()
    normalized_level = complexity_level.strip().lower()

    valid_types = {"chore", "bug", "feature"}
    valid_levels = {"simple", "average", "complex", "critical"}

    if normalized_type not in valid_types:
        return StepResult.fail(f"Invalid issue type selected: {issue_type}")
    if normalized_level not in valid_levels:
        return StepResult.fail(f"Invalid complexity level selected: {complexity_level}")

    triage_command = cast(ClassifySlashCommand, f"/triage:{normalized_type}")
    normalized_classification = {
        "type": normalized_type,
        "level": normalized_level,
    }

    return StepResult.ok(
        ClassifyData(command=triage_command, classification=normalized_classification)
    )
