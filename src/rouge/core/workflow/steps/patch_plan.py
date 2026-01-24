"""Patch plan building step implementation."""

import logging
from typing import Callable, Optional

from rouge.core.agent import execute_template
from rouge.core.agents.claude import ClaudeAgentTemplateRequest
from rouge.core.models import Issue, Patch
from rouge.core.notifications.agent_stream_handlers import make_progress_comment_handler
from rouge.core.workflow.artifacts import (
    IssueArtifact,
    PatchArtifact,
    PatchPlanArtifact,
    PlanArtifact,
)
from rouge.core.workflow.shared import AGENT_PATCH_PLANNER
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import PatchPlanData, PlanData, StepResult

logger = logging.getLogger(__name__)


def build_patch_plan(
    issue: Issue,
    patch: Patch,
    original_plan: PlanData,
    adw_id: str,
    stream_handler: Optional[Callable[[str], None]] = None,
) -> StepResult[PatchPlanData]:
    """Build patch-specific plan by contextualizing patch against original plan.

    Args:
        issue: The Rouge issue being patched
        patch: The patch request with description
        original_plan: The original plan data from the main workflow
        adw_id: Workflow ID for tracking
        stream_handler: Optional callback for streaming output

    Returns:
        StepResult with PatchPlanData containing the patch-specific plan
    """
    # Build prompt that contextualizes patch against original plan
    patch_context = f"""## Original Issue
{issue.description}

## Original Plan
{original_plan.plan}

## Patch Request
{patch.description}
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

    # Execute template without requiring JSON - patch plan is markdown output
    response = execute_template(request, stream_handler=stream_handler, require_json=False)
    logger.debug(
        "build_patch_plan response: %s",
        response.model_dump_json(indent=2, by_alias=True),
    )

    if not response.success:
        return StepResult.fail(response.output)

    # Build PatchPlanData from response
    return StepResult.ok(
        PatchPlanData(
            patch_description=patch.description,
            original_plan_reference=adw_id,
            patch_plan_content=response.output,
        ),
        session_id=response.session_id,
    )


class BuildPatchPlanStep(WorkflowStep):
    """Patch plan building step implementation.

    This step builds a patch-specific plan by contextualizing the patch request
    against the original implementation plan. It:
    1. Loads the patch from context (set by FetchPatchStep)
    2. Loads the original plan from the parent workflow artifact
    3. Loads the issue from the parent workflow artifact
    4. Generates a patch-specific plan via the patch planner agent
    5. Stores the result in context and as an artifact
    """

    @property
    def name(self) -> str:
        return "Building patch plan"

    @property
    def is_critical(self) -> bool:
        """Patch planning is critical - workflow cannot proceed without it."""
        return True

    def run(self, context: WorkflowContext) -> StepResult:
        """Build patch plan and store in context.

        Args:
            context: Workflow context with patch data from FetchPatchStep

        Returns:
            StepResult with success status and optional error message
        """
        # Load patch from context (should be set by FetchPatchStep)
        patch: Optional[Patch] = context.data.get("patch")
        if patch is None:
            # Try to load from artifact if not in context
            patch = context.load_artifact_if_missing(
                "patch",
                "patch",
                PatchArtifact,
                lambda a: a.patch,
            )

        if patch is None:
            logger.error("Cannot build patch plan: patch not fetched")
            return StepResult.fail("Cannot build patch plan: patch not fetched")

        # Load issue from context or parent workflow artifact
        issue = context.load_issue_artifact_if_missing(IssueArtifact, lambda a: a.issue)

        if issue is None:
            logger.error("Cannot build patch plan: issue not available")
            return StepResult.fail("Cannot build patch plan: issue not available")

        # Load original plan from parent workflow artifact
        plan_data: Optional[PlanData] = context.load_artifact_if_missing(
            "plan_data",
            "plan",
            PlanArtifact,
            lambda a: a.plan_data,
        )

        if plan_data is None:
            logger.error("Cannot build patch plan: original plan not available")
            return StepResult.fail("Cannot build patch plan: original plan not available")

        # Create progress comment handler
        plan_handler = make_progress_comment_handler(issue.id, context.adw_id)

        # Build patch plan using agent
        patch_plan_response = build_patch_plan(
            issue,
            patch,
            plan_data,
            context.adw_id,
            stream_handler=plan_handler,
        )

        if not patch_plan_response.success:
            logger.error(f"Error building patch plan: {patch_plan_response.error}")
            return StepResult.fail(f"Error building patch plan: {patch_plan_response.error}")

        # Store patch plan data in context
        context.data["patch_plan_data"] = patch_plan_response.data

        # Save artifact if artifact store is available
        if (
            context.artifacts_enabled
            and context.artifact_store is not None
            and patch_plan_response.data is not None
        ):
            artifact = PatchPlanArtifact(
                workflow_id=context.adw_id,
                patch_plan_data=patch_plan_response.data,
            )
            context.artifact_store.write_artifact(artifact)
            logger.debug("Saved patch plan artifact for workflow %s", context.adw_id)

        # Emit progress comment with patch plan summary
        from rouge.core.workflow.workflow_io import emit_progress_comment

        patch_plan_data = patch_plan_response.data
        comment_text = (
            f"Patch plan created for: {patch_plan_data.patch_description[:100]}"
            if patch_plan_data
            else "Patch plan created"
        )

        emit_progress_comment(
            issue.id,
            comment_text,
            raw={
                "patch_id": patch.id,
                "patch_description": patch.description,
                "original_plan_reference": (
                    patch_plan_data.original_plan_reference if patch_plan_data else None
                ),
            },
            adw_id=context.adw_id,
        )

        return StepResult.ok(None)
