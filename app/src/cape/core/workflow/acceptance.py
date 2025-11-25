"""Plan acceptance validation functionality for workflow orchestration."""

import os
from logging import Logger
from typing import Callable, Optional

from cape.core.agent import execute_template
from cape.core.agents.claude import ClaudeAgentTemplateRequest
from cape.core.models import CapeComment
from cape.core.notifications import insert_progress_comment
from cape.core.workflow.shared import AGENT_IMPLEMENTOR
from cape.core.workflow.types import StepResult


def notify_plan_acceptance(
    plan_path: str,
    issue_id: int,
    adw_id: str,
    logger: Logger,
    stream_handler: Optional[Callable[[str], None]] = None,
) -> StepResult[None]:
    """Notify the /plan-acceptance template with the plan file to validate.

    Validates implementation against plan.

    Args:
        plan_path: Path to the plan file to validate
        issue_id: Cape issue ID for tracking
        adw_id: Workflow ID for tracking
        logger: Logger instance
        stream_handler: Optional callback for streaming output

    Returns:
        StepResult with None data (success/failure only)
    """
    try:
        # Validate plan file exists
        if not os.path.exists(plan_path):
            logger.error(f"Plan file does not exist: {plan_path}")
            return StepResult.fail(f"Plan file does not exist: {plan_path}")

        logger.debug(f"Invoking /plan-acceptance template with plan file: {plan_path}")

        # Create template request
        request = ClaudeAgentTemplateRequest(
            agent_name=AGENT_IMPLEMENTOR,
            slash_command="/plan-acceptance",
            args=[plan_path],
            adw_id=adw_id,
            issue_id=issue_id,
            model="sonnet",
        )

        logger.debug(
            "notify_plan_acceptance request: %s",
            request.model_dump_json(indent=2, by_alias=True),
        )

        # Execute template
        response = execute_template(request, stream_handler=stream_handler)

        logger.debug(
            "notify_plan_acceptance response: success=%s",
            response.success,
        )

        if not response.success:
            logger.error(f"Failed to execute /plan-acceptance template: {response.output}")
            return StepResult.fail(
                f"Failed to execute /plan-acceptance template: {response.output}"
            )

        # Insert progress comment with artifact
        comment = CapeComment(
            issue_id=issue_id,
            comment="Plan acceptance validation completed",
            raw={"validation_output": response.output[:1000]},  # First 1000 chars of output
            source="system",
            type="artifact",
        )
        status, msg = insert_progress_comment(comment)
        if status != "success":
            logger.error(f"Failed to insert plan acceptance comment: {msg}")
        else:
            logger.debug(f"Plan acceptance comment inserted: {msg}")

        return StepResult.ok(None)

    except Exception as e:
        logger.error(f"Failed to notify plan acceptance template: {e}")
        return StepResult.fail(f"Failed to notify plan acceptance template: {e}")
