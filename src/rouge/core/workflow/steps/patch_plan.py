"""Patch plan building step implementation.

Builds a standalone implementation plan for a patch issue. The patch issue
contains its own description and does not depend on any parent workflow
artifacts (original issue or original plan).
"""

import logging

from rouge.core.models import CommentPayload
from rouge.core.notifications.agent_stream_handlers import make_progress_comment_handler
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.workflow.artifacts import PlanArtifact
from rouge.core.workflow.plan import build_plan
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult

logger = logging.getLogger(__name__)


class BuildPatchPlanStep(WorkflowStep):
    """Standalone plan building step for patch issues.

    This step builds an implementation plan directly from the patch issue
    description, without referencing any parent workflow artifacts. It:
    1. Uses the patch issue from context (set by FetchPatchStep on context.issue)
    2. Generates a standalone implementation plan via the shared plan builder
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
        plan_response = build_plan(issue, "/adw-patch-plan", context.adw_id, plan_handler)

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

        # Build progress comment from parsed plan data
        parsed_data = plan_response.metadata.get("parsed_data", {})
        summary = parsed_data.get("summary", "")
        # Derive title from first non-empty line of summary, or use a default
        title = summary.split("\n")[0].strip() if summary else "Patch plan generated"
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
