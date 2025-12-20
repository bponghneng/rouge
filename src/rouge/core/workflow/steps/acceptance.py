"""Acceptance validation step implementation."""

import logging

from rouge.core.notifications import make_progress_comment_handler
from rouge.core.workflow.acceptance import notify_plan_acceptance
from rouge.core.workflow.artifacts import AcceptanceArtifact, ImplementedPlanFileArtifact
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult
from rouge.core.workflow.workflow_io import emit_progress_comment

logger = logging.getLogger(__name__)


class ValidateAcceptanceStep(WorkflowStep):
    """Validate plan acceptance."""

    @property
    def name(self) -> str:
        return "Validating plan acceptance"

    @property
    def is_critical(self) -> bool:
        # Acceptance validation is not critical - workflow continues on failure
        return False

    def run(self, context: WorkflowContext) -> StepResult:
        """Validate implementation against plan.

        Args:
            context: Workflow context with implemented_plan_file

        Returns:
            StepResult with success status and optional error message
        """
        plan_path = context.data.get("implemented_plan_file", "")

        # Try to load from artifact if not in context
        if not plan_path and context.artifacts_enabled and context.artifact_store is not None:
            try:
                impl_plan_artifact = context.artifact_store.read_artifact(
                    "implemented_plan_file", ImplementedPlanFileArtifact
                )
                plan_path = impl_plan_artifact.file_path
                context.data["implemented_plan_file"] = plan_path
                logger.debug("Loaded implemented_plan_file from artifact")
            except FileNotFoundError:
                pass

        if not plan_path:
            logger.warning("No plan file available for acceptance validation")
            return StepResult.fail("No plan file available for acceptance validation")

        acceptance_handler = make_progress_comment_handler(context.issue_id, context.adw_id)
        acceptance_result = notify_plan_acceptance(
            plan_path,
            context.issue_id,
            context.adw_id,
            stream_handler=acceptance_handler,
        )

        if not acceptance_result.success:
            logger.error(f"Failed to validate plan acceptance: {acceptance_result.error}")
            # Save artifact even on failure
            if context.artifacts_enabled and context.artifact_store is not None:
                artifact = AcceptanceArtifact(
                    workflow_id=context.adw_id,
                    success=False,
                    message=acceptance_result.error,
                )
                context.artifact_store.write_artifact(artifact)
            return StepResult.fail(f"Failed to validate plan acceptance: {acceptance_result.error}")

        logger.info("Plan acceptance validated successfully")

        # Save artifact if artifact store is available
        if context.artifacts_enabled and context.artifact_store is not None:
            artifact = AcceptanceArtifact(
                workflow_id=context.adw_id,
                success=True,
                message="Plan acceptance validated successfully",
            )
            context.artifact_store.write_artifact(artifact)
            logger.debug("Saved acceptance artifact for workflow %s", context.adw_id)

        # Insert progress comment - best-effort, non-blocking
        emit_progress_comment(
            context.issue_id,
            "Plan acceptance validation completed",
            raw={"text": "Plan acceptance validation completed."},
        )

        return StepResult.ok(None)
