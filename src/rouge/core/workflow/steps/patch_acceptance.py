"""Patch acceptance validation step implementation."""

import logging
from typing import Optional

from rouge.core.models import CommentPayload
from rouge.core.notifications.agent_stream_handlers import make_progress_comment_handler
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.workflow.acceptance import notify_plan_acceptance
from rouge.core.workflow.artifacts import PatchAcceptanceArtifact, PlanArtifact
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import PlanData, StepResult

logger = logging.getLogger(__name__)


class ValidatePatchAcceptanceStep(WorkflowStep):
    """Validate patch acceptance against patch plan.

    This step validates that the patch implementation meets the acceptance
    criteria defined in the patch plan. It reuses the same acceptance
    validation agent as the main workflow but operates on the patch plan
    content instead of the original plan.
    """

    @property
    def name(self) -> str:
        return "Validating patch acceptance"

    @property
    def is_critical(self) -> bool:
        # Acceptance validation is best-effort - workflow continues on failure
        return False

    def run(self, context: WorkflowContext) -> StepResult:
        """Validate patch implementation against patch plan.

        Args:
            context: Workflow context with patch plan artifact

        Returns:
            StepResult with success status and optional error message
        """
        # Load plan content from artifact (BuildPatchPlanStep now produces PlanArtifact)
        plan_data: Optional[PlanData] = context.load_artifact_if_missing(
            "plan_data",
            "plan",
            PlanArtifact,
            lambda a: a.plan_data,
        )

        if plan_data is None:
            logger.warning("No plan available for acceptance validation")
            return StepResult.fail("No plan available for acceptance validation")

        acceptance_handler = make_progress_comment_handler(context.issue_id, context.adw_id)

        # Use the same acceptance validation logic but with plan content
        acceptance_result = notify_plan_acceptance(
            plan_data.plan,
            context.issue_id,
            context.adw_id,
            stream_handler=acceptance_handler,
        )

        if not acceptance_result.success:
            logger.error("Failed to validate patch acceptance: %s", acceptance_result.error)
            # Save artifact even on failure
            if context.artifacts_enabled and context.artifact_store is not None:
                artifact = PatchAcceptanceArtifact(
                    workflow_id=context.adw_id,
                    success=False,
                    message=acceptance_result.error,
                )
                context.artifact_store.write_artifact(artifact)
            return StepResult.fail(
                f"Failed to validate patch acceptance: {acceptance_result.error}"
            )

        logger.info("Patch acceptance validated successfully")

        # Save artifact if artifact store is available
        if context.artifacts_enabled and context.artifact_store is not None:
            artifact = PatchAcceptanceArtifact(
                workflow_id=context.adw_id,
                success=True,
                message="Patch acceptance validated successfully",
            )
            context.artifact_store.write_artifact(artifact)
            logger.debug("Saved patch acceptance artifact for workflow %s", context.adw_id)

        # Insert progress comment - best-effort, non-blocking
        payload = CommentPayload(
            issue_id=context.issue_id,
            adw_id=context.adw_id,
            text="Patch acceptance validation completed",
            raw={"text": "Patch acceptance validation completed."},
            source="system",
            kind="workflow",
        )
        status, msg = emit_comment_from_payload(payload)
        if status == "success":
            logger.debug(msg)
        else:
            logger.error(msg)

        return StepResult.ok(None)
