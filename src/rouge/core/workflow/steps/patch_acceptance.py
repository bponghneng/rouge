"""Patch acceptance validation step implementation."""

import logging
from typing import Optional

from rouge.core.notifications.agent_stream_handlers import make_progress_comment_handler
from rouge.core.workflow.acceptance import notify_plan_acceptance
from rouge.core.workflow.artifacts import PatchAcceptanceArtifact, PatchPlanArtifact
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import PatchPlanData, StepResult
from rouge.core.workflow.workflow_io import emit_progress_comment

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
        # Load patch plan content from artifact
        patch_plan_data: Optional[PatchPlanData] = context.load_artifact_if_missing(
            "patch_plan_data",
            "patch_plan",
            PatchPlanArtifact,
            lambda a: a.patch_plan_data,
        )

        if patch_plan_data is None:
            logger.warning("No patch plan available for acceptance validation")
            return StepResult.fail("No patch plan available for acceptance validation")

        acceptance_handler = make_progress_comment_handler(context.issue_id, context.adw_id)

        # Use the same acceptance validation logic but with patch plan content
        acceptance_result = notify_plan_acceptance(
            patch_plan_data.patch_plan_content,
            context.issue_id,
            context.adw_id,
            stream_handler=acceptance_handler,
        )

        if not acceptance_result.success:
            logger.error(f"Failed to validate patch acceptance: {acceptance_result.error}")
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
        emit_progress_comment(
            context.issue_id,
            "Patch acceptance validation completed",
            raw={"text": "Patch acceptance validation completed."},
            adw_id=context.adw_id,
        )

        return StepResult.ok(None)
