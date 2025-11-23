"""Issue classification functionality for workflow orchestration."""

import json
from logging import Logger
from typing import Dict, Optional, Tuple, cast

from cape.core.agent import execute_template
from cape.core.agents.claude import ClaudeAgentTemplateRequest
from cape.core.models import CapeIssue, SlashCommand
from cape.core.workflow.shared import AGENT_CLASSIFIER


def classify_issue(
    issue: CapeIssue, adw_id: str, logger: Logger
) -> Tuple[Optional[SlashCommand], Optional[Dict[str, str]], Optional[str]]:
    """Classify issue and return appropriate slash command.

    Returns:
        Tuple of (command, classification_data, error_message)
        where only one of classification_data/error_message is set.
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
    response = execute_template(request)
    logger.debug(
        "classify response: %s",
        response.model_dump_json(indent=2, by_alias=True),
    )

    if not response.success:
        return None, None, response.output

    raw_output = response.output.strip()
    logger.debug("Classifier raw output: %s", raw_output)
    try:
        classification_data = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        logger.error("Classifier JSON decode failed: %s | raw=%s", exc, raw_output)
        return None, None, f"Invalid classification JSON: {exc}"

    if not isinstance(classification_data, dict):
        return None, None, "Invalid classification response type"

    issue_type = classification_data.get("type")
    complexity_level = classification_data.get("level")

    if not isinstance(issue_type, str):
        return None, None, "Classification missing 'type' field"
    if not isinstance(complexity_level, str):
        return None, None, "Classification missing 'level' field"

    normalized_type = issue_type.strip().lower()
    normalized_level = complexity_level.strip().lower()

    valid_types = {"chore", "bug", "feature"}
    valid_levels = {"simple", "average", "complex", "critical"}

    if normalized_type not in valid_types:
        return None, None, f"Invalid issue type selected: {issue_type}"
    if normalized_level not in valid_levels:
        return None, None, f"Invalid complexity level selected: {complexity_level}"

    triage_command = cast(SlashCommand, f"/triage:{normalized_type}")
    normalized_classification = {
        "type": normalized_type,
        "level": normalized_level,
    }

    return triage_command, normalized_classification, None