"""Workflow orchestration for adw_plan_build process."""

import json
from logging import Logger
from typing import Dict, Optional, Tuple, cast

from cape.core.agent import execute_template, execute_implement_plan
from cape.core.agents import AgentExecuteResponse
from cape.core.database import fetch_issue, update_issue_status
from cape.core.models import (
    AgentPromptResponse,
    AgentTemplateRequest,
    CapeIssue,
    SlashCommand,
)
from cape.core.notifications import insert_progress_comment

# Agent names
AGENT_IMPLEMENTOR = "sdlc_implementor"
AGENT_PLANNER = "sdlc_planner"
AGENT_CLASSIFIER = "issue_classifier"
AGENT_PLAN_FINDER = "plan_finder"


def update_status(issue_id: int, status: str, logger: Logger) -> None:
    """Update the status of an issue.

    This is a best-effort operation - database failures are logged but never halt
    workflow execution. Successful updates are logged at DEBUG level, failures
    at ERROR level.

    Args:
        issue_id: The Cape issue ID
        status: The new status value ("pending", "started", or "completed")
        logger: Logger instance
    """
    try:
        update_issue_status(issue_id, status)
        logger.debug(f"Issue {issue_id} status updated to '{status}'")
    except Exception as e:
        logger.error(f"Failed to update issue {issue_id} status to '{status}': {e}")


def classify_issue(
    issue: CapeIssue, adw_id: str, logger: Logger
) -> Tuple[Optional[SlashCommand], Optional[Dict[str, str]], Optional[str]]:
    """Classify issue and return appropriate slash command.

    Returns:
        Tuple of (command, classification_data, error_message)
        where only one of classification_data/error_message is set.
    """
    request = AgentTemplateRequest(
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


def build_plan(
    issue: CapeIssue, command: SlashCommand, adw_id: str, logger: Logger
) -> AgentPromptResponse:
    """Build implementation plan for the issue using the specified command.

    Args:
        issue: The Cape issue to plan for
        command: The triage command to use (e.g., /triage:feature)
        adw_id: Workflow ID for tracking
        logger: Logger instance

    Returns:
        Agent response with plan output
    """
    request = AgentTemplateRequest(
        agent_name=AGENT_PLANNER,
        slash_command=command,
        args=[issue.description],
        adw_id=adw_id,
        issue_id=issue.id,
        model="sonnet",
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
    return response


def get_plan_file(
    plan_output: str, issue_id: int, adw_id: str, logger: Logger
) -> Tuple[Optional[str], Optional[str]]:
    """Get the path to the plan file that was just created.

    Args:
        plan_output: The output from the build_plan step
        adw_id: Workflow ID for tracking
        logger: Logger instance

    Returns:
        Tuple of (file_path, error_message) where one will be None
    """
    request = AgentTemplateRequest(
        agent_name=AGENT_PLAN_FINDER,
        slash_command="/triage:find-plan-file",
        args=[plan_output],
        adw_id=adw_id,
        issue_id=issue_id,
        model="sonnet",
    )
    logger.debug(
        "get_plan_file request: %s",
        request.model_dump_json(indent=2, by_alias=True),
    )
    response = execute_template(request)
    logger.debug(
        "get_plan_file response: %s",
        response.model_dump_json(indent=2, by_alias=True),
    )

    if not response.success:
        return None, response.output

    # Clean up the response - get just the file path
    file_path = response.output.strip()

    # Validate it looks like a file path
    if file_path and file_path != "0" and "/" in file_path:
        return file_path, None
    elif file_path == "0":
        return None, "No plan file found in output"
    else:
        # If response doesn't look like a path, return error
        return None, f"Invalid file path response: {file_path}"


def implement_plan(
    plan_file: str, issue_id: int, adw_id: str, logger: Logger
) -> AgentPromptResponse:
    """Implement the plan using configured provider.

    Uses the provider configured via CAPE_IMPLEMENT_PROVIDER environment variable.
    Defaults to Claude if not set.

    Args:
        plan_file: Path to the plan file to implement
        issue_id: Cape issue ID for tracking
        adw_id: Workflow ID for tracking
        logger: Logger instance

    Returns:
        Agent response with implementation results
    """
    # Use new execute_implement_plan helper which handles provider selection
    response: AgentExecuteResponse = execute_implement_plan(
        plan_file=plan_file,
        issue_id=issue_id,
        adw_id=adw_id,
        agent_name=AGENT_IMPLEMENTOR,
        logger=logger,
    )

    logger.debug(
        "implement response: success=%s, session_id=%s",
        response.success,
        response.session_id,
    )

    # Map AgentExecuteResponse to AgentPromptResponse for compatibility
    return AgentPromptResponse(
        output=response.output,
        success=response.success,
        session_id=response.session_id,
    )


def execute_workflow(
    issue_id: int,
    adw_id: str,
    logger: Logger,
) -> bool:
    """Execute complete workflow for an issue.

    This is the main orchestration function that runs all workflow steps:
    1. Fetch issue from database
    2. Classify the issue
    3. Build implementation plan
    4. Find plan file
    5. Implement the plan

    Progress comments are inserted at 4 key points (best-effort, non-blocking).

    Args:
        issue_id: The Cape issue ID to process
        adw_id: Workflow ID for tracking
        logger: Logger instance

    Returns:
        True if workflow completed successfully, False otherwise
    """
    logger.info(f"ADW ID: {adw_id}")
    logger.info(f"Processing issue ID: {issue_id}")

    # Fetch issue from Supabase
    logger.info("\n=== Fetching issue from Supabase ===")
    try:
        issue = fetch_issue(issue_id)
        logger.info(f"Issue fetched: ID={issue.id}, Status={issue.status}")
    except ValueError as e:
        logger.error(f"Error fetching issue: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error fetching issue: {e}")
        return False

    # Update status to "started" - best-effort, non-blocking
    update_status(issue_id, "started", logger)

    # Insert progress comment - best-effort, non-blocking
    insert_progress_comment(issue_id, "Workflow started - Issue fetched and validated", logger)

    # Classify the issue
    logger.info("\n=== Classifying issue ===")
    issue_command, classification_data, error = classify_issue(issue, adw_id, logger)
    if error:
        logger.error(f"Error classifying issue: {error}")
        return False
    if issue_command is None:
        logger.error("Classifier did not return a command")
        return False

    if classification_data:
        logger.info(
            "Issue classified as %s (%s) -> %s",
            classification_data["type"],
            classification_data["level"],
            issue_command,
        )
    else:
        logger.info(f"Issue classified as: {issue_command}")

    # Insert progress comment - best-effort, non-blocking
    if classification_data:
        comment_text = (
            f"Issue classified as {classification_data['type']} "
            f"({classification_data['level']}) -> {issue_command}"
        )
    else:
        comment_text = f"Issue classified as {issue_command}"
    insert_progress_comment(issue_id, comment_text, logger)

    # Build the implementation plan
    logger.info("\n=== Building implementation plan ===")
    plan_response = build_plan(issue, issue_command, adw_id, logger)
    if not plan_response.success:
        logger.error(f"Error building plan: {plan_response.output}")
        return False
    logger.info(" Implementation plan created")

    # Insert progress comment - best-effort, non-blocking
    insert_progress_comment(issue_id, "Implementation plan created successfully", logger)

    # Get the path to the plan file that was created
    logger.info("\n=== Finding plan file ===")
    plan_file_path, error = get_plan_file(plan_response.output, issue_id, adw_id, logger)
    if error:
        logger.error(f"Error finding plan file: {error}")
        return False
    if plan_file_path is None:
        logger.error("Plan file path missing despite successful response")
        return False
    logger.info(f"Plan file created: {plan_file_path}")

    # Implement the plan
    logger.info("\n=== Implementing solution ===")
    implement_response = implement_plan(plan_file_path, issue_id, adw_id, logger)
    if not implement_response.success:
        logger.error(f"Error implementing solution: {implement_response.output}")
        return False
    logger.info(" Solution implemented")

    # Update status to "completed" - best-effort, non-blocking
    update_status(issue_id, "completed", logger)

    # Insert progress comment - best-effort, non-blocking
    insert_progress_comment(issue_id, "Solution implemented successfully", logger)

    logger.info("\n=== Workflow completed successfully ===")
    return True
