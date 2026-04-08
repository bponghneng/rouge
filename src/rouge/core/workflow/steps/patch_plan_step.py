"""Patch plan building step implementation.

Builds a standalone implementation plan for a patch issue. The patch issue
contains its own description and does not depend on any parent workflow
artifacts (original issue or original plan).
"""

from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.prompts import PromptId
from rouge.core.utils import get_logger
from rouge.core.workflow.plan_common import build_plan_from_template
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult


class PatchPlanStep(WorkflowStep):
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

        Loads the patch issue from the fetch-patch artifact (required).

        Args:
            context: Workflow context with fetch-patch artifact from FetchPatchStep

        Returns:
            StepResult with success status and optional error message
        """
        logger = get_logger(context.adw_id)

        # Load issue from context (required - set by FetchPatchStep)
        if context.issue is None:
            error_msg = "Cannot build patch plan: issue not fetched (context.issue is None)"
            logger.error(error_msg)
            return StepResult.fail(error_msg)
        issue = context.issue

        # Build standalone plan from patch issue description
        plan_response = build_plan_from_template(issue, PromptId.PATCH_PLAN, context.adw_id)

        if not plan_response.success:
            logger.error("Error building patch plan: %s", plan_response.error)
            return StepResult.fail(f"Error building patch plan: {plan_response.error}")

        # Store plan data in context
        context.data["plan_data"] = plan_response.data

        if plan_response.data is None:
            return StepResult.fail("Plan step succeeded but produced no plan data")

        # Build progress comment from parsed plan data
        parsed_data = (plan_response.metadata or {}).get("parsed_data", {})
        # Extract title from one of: chore, bug, feature keys
        title = (
            parsed_data.get("chore")
            or parsed_data.get("bug")
            or parsed_data.get("feature")
            or "Implementation plan created"
        )
        summary = parsed_data.get("summary", "")
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
