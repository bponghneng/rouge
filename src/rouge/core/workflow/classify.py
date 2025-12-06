"""Issue classification functionality for workflow orchestration."""

from logging import Logger
from typing import Callable, Optional, cast

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.json_parser import parse_and_validate_json
from rouge.core.models import Issue
from rouge.core.workflow.shared import AGENT_CLASSIFIER
from rouge.core.workflow.types import ClassifyData, ClassifySlashCommand, StepResult

# Required fields for classification output JSON
CLASSIFY_REQUIRED_FIELDS = {
    "type": str,
    "level": str,
}


def classify_issue(
    issue: Issue,
    adw_id: str,
    logger: Logger,
    stream_handler: Optional[Callable[[str], None]] = None,
) -> StepResult[ClassifyData]:
    """Classify issue and return appropriate slash command.

    Args:
        issue: The issue to classify
        adw_id: Workflow ID for tracking
        logger: Logger instance
        stream_handler: Optional callback for streaming output

    Returns:
        StepResult with ClassifyData containing command and classification
    """
    request = ClaudeAgentTemplateRequest(
        agent_name=AGENT_CLASSIFIER,
        slash_command="/adw-classify",
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

    logger.debug("Classifier raw output: %s", response.output)

    # Parse and validate JSON output using the shared helper
    parse_result = parse_and_validate_json(
        response.output, CLASSIFY_REQUIRED_FIELDS, logger, step_name="classify"
    )
    if not parse_result.success:
        return StepResult.fail(f"Invalid classification JSON: {parse_result.error}")

    # parse_result.data is guaranteed to be non-None after success check
    classification_data = parse_result.data
    assert (
        classification_data is not None
    ), "classification_data should not be None after success check"
    issue_type = classification_data["type"]
    complexity_level = classification_data["level"]

    normalized_type = issue_type.strip().lower()
    normalized_level = complexity_level.strip().lower()

    valid_types = {"chore", "bug", "feature"}
    valid_levels = {"simple", "average", "complex", "critical"}

    if normalized_type not in valid_types:
        return StepResult.fail(f"Invalid issue type selected: {issue_type}")
    if normalized_level not in valid_levels:
        return StepResult.fail(f"Invalid complexity level selected: {complexity_level}")

    triage_command = cast(ClassifySlashCommand, f"/adw-{normalized_type}-plan")
    normalized_classification = {
        "type": normalized_type,
        "level": normalized_level,
    }

    return StepResult.ok(
        ClassifyData(command=triage_command, classification=normalized_classification)
    )
