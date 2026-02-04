"""Patch plan building step implementation.

Builds a standalone implementation plan for a patch issue. The patch issue
contains its own description and does not depend on any parent workflow
artifacts (original issue or original plan).
"""

import logging
from collections.abc import Callable
from typing import Optional

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.models import CommentPayload, Issue
from rouge.core.notifications.agent_stream_handlers import make_progress_comment_handler
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.workflow.artifacts import (
    PlanArtifact,
)
from rouge.core.workflow.shared import AGENT_PATCH_PLANNER
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import PlanData, StepResult

logger = logging.getLogger(__name__)


def build_patch_plan(
    issue: Issue,
    adw_id: str,
    stream_handler: Optional[Callable[[str], None]] = None,
) -> StepResult[PlanData]:
    """Build a standalone implementation plan for a patch issue.

    Args:
        issue: The patch issue (type='patch') with its own description
        adw_id: Workflow ID for tracking
        stream_handler: Optional callback for streaming output

    Returns:
        StepResult with PlanData containing the implementation plan
    """
    # Build prompt from the patch issue description
    patch_context = f"""## Issue Description
{issue.description}
"""

    request = ClaudeAgentTemplateRequest(
        agent_name=AGENT_PATCH_PLANNER,
        slash_command="/adw-patch-plan",
        args=[patch_context],
        adw_id=adw_id,
        issue_id=issue.id,
        model="sonnet",
    )
    logger.debug(
        "build_patch_plan request: %s",
        request.model_dump_json(indent=2, by_alias=True),
    )

    # Execute template without requiring JSON - plan is markdown output
    response = execute_template(request, stream_handler=stream_handler, require_json=False)
    logger.debug(
        "build_patch_plan response: %s",
        response.model_dump_json(indent=2, by_alias=True),
    )

    if not response.success:
        return StepResult.fail(response.output or "Unknown error")

    # Guard against None output even when success is True
    if response.output is None:
        error_msg = "Patch plan agent returned success but no output"
        logger.error(error_msg)
        return StepResult.fail(error_msg, session_id=response.session_id)

    # Build PlanData from response - generate summary from issue description
    summary = f"Plan for patch: {issue.description[:100]}"
    return StepResult.ok(
        PlanData(
            plan=response.output,
            summary=summary,
            session_id=response.session_id,
        ),
        session_id=response.session_id,
    )


class BuildPatchPlanStep(WorkflowStep):
    """Standalone plan building step for patch issues.

    This step builds an implementation plan directly from the patch issue
    description, without referencing any parent workflow artifacts. It:
    1. Uses the patch issue from context (set by FetchPatchStep on context.issue)
    2. Generates a standalone implementation plan via the patch planner agent
    3. Stores the result in context and as a PlanArtifact
    """

    @property
    def name(self) -> str:
        return "Building patch plan"

    @property
    def is_critical(self) -> bool:
        """Patch planning is critical - workflow cannot proceed without it."""
        return True

    def run(self, context: WorkflowContext) -> StepResult:
        """Build standalone plan for patch issue and store in context.

        Uses the patch issue already set on context.issue by FetchPatchStep.

        Args:
            context: Workflow context with patch issue from FetchPatchStep

        Returns:
            StepResult with success status and optional error message
        """
        # The patch issue is set on context.issue by FetchPatchStep
        issue = context.issue

        if issue is None:
            logger.error("Cannot build patch plan: patch issue not available")
            return StepResult.fail("Cannot build patch plan: patch issue not available")

        # Create progress comment handler
        plan_handler = make_progress_comment_handler(issue.id, context.adw_id)

        # Build standalone plan from patch issue description
        plan_response = build_patch_plan(
            issue,
            context.adw_id,
            stream_handler=plan_handler,
        )

        if not plan_response.success:
            logger.error("Error building patch plan: %s", plan_response.error)
            return StepResult.fail(f"Error building patch plan: {plan_response.error}")

        # Store plan data in context
        context.data["plan_data"] = plan_response.data

        # Save artifact if artifact store is available
        if (
            context.artifacts_enabled
            and context.artifact_store is not None
            and plan_response.data is not None
        ):
            artifact = PlanArtifact(
                workflow_id=context.adw_id,
                plan_data=plan_response.data,
            )
            context.artifact_store.write_artifact(artifact)
            logger.debug("Saved plan artifact for workflow %s", context.adw_id)

        # Emit progress comment with plan summary
        plan_data_result = plan_response.data
        comment_text = (
            f"Patch plan created: {plan_data_result.summary}"
            if plan_data_result
            else "Patch plan created"
        )

        payload = CommentPayload(
            issue_id=issue.id,
            adw_id=context.adw_id,
            text=comment_text,
            raw={
                "issue_id": issue.id,
                "issue_description": issue.description,
            },
            source="system",
            kind="workflow",
        )
        status, msg = emit_comment_from_payload(payload)
        if status == "success":
            logger.debug(msg)
        else:
            logger.error(msg)

        # Return the result from build_patch_plan to preserve session_id
        return plan_response
