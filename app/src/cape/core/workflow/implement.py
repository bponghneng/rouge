"""Implementation functionality for workflow orchestration."""

import json
from logging import Logger
from typing import Dict, Optional

from cape.core.agent import execute_implement_plan
from cape.core.agents import AgentExecuteResponse
from cape.core.agents.claude import ClaudeAgentPromptResponse
from cape.core.workflow.shared import AGENT_IMPLEMENTOR


def parse_implement_output(output: str, logger: Logger) -> Optional[Dict]:
    """Parse implementation output as JSON and validate required fields.

    Args:
        output: The raw output from the implementation
        logger: Logger instance

    Returns:
        Parsed dict on success, None if malformed or validation fails
    """
    try:
        # Try to parse the output as JSON
        parsed = json.loads(output)

        # Validate it's a dict
        if not isinstance(parsed, dict):
            logger.error("Implementation output is not a JSON object")
            return None

        # Validate required fields
        required_fields = ["summary", "files_modified", "planPath", "git_diff_stat", "status"]
        missing_fields = []

        for field in required_fields:
            if field not in parsed:
                missing_fields.append(field)

        if missing_fields:
            logger.error(f"Implementation output missing required fields: {missing_fields}")
            return None

        # Validate files_modified is a list
        if not isinstance(parsed["files_modified"], list):
            logger.error("Implementation output 'files_modified' is not a list")
            return None

        logger.debug(f"Successfully parsed implementation output with {len(parsed['files_modified'])} modified files")
        return parsed

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse implementation output as JSON: {e}")
        logger.debug(f"Raw output was: {output[:500]}...")  # Log first 500 chars for debugging
        return None
    except Exception as e:
        logger.error(f"Unexpected error parsing implementation output: {e}")
        return None


def implement_plan(
    plan_file: str, issue_id: int, adw_id: str, logger: Logger
) -> ClaudeAgentPromptResponse:
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

    # Map AgentExecuteResponse to ClaudeAgentPromptResponse for compatibility
    return ClaudeAgentPromptResponse(
        output=response.output,
        success=response.success,
        session_id=response.session_id,
    )