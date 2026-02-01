"""Acceptance validation step implementation."""

import logging
from typing import Optional

from rouge.core.models import CommentPayload
from rouge.core.notifications.agent_stream_handlers import make_progress_comment_handler
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.workflow.acceptance import notify_plan_acceptance
from rouge.core.workflow.artifacts import AcceptanceArtifact, PatchPlanArtifact, PlanArtifact
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult

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

    def _load_plan_text(self, context: WorkflowContext) -> Optional[str]:
        """Load plan text from patch_plan or plan artifact.

        Tries to load patch_plan first (for patch workflows), falling back
        to plan (for main workflows) if patch_plan is not available.

        Args:
            context: Workflow context with artifact store

        Returns:
            Plan text string, or None if neither artifact is available
        """
        # First, try to load patch_plan (for patch workflows)
        patch_plan_data = context.load_artifact_if_missing(
            "patch_plan_data",
            "patch_plan",
            PatchPlanArtifact,
            lambda a: a.patch_plan_data,
        )

        if patch_plan_data is not None:
            logger.info("Using patch_plan for acceptance validation")
            return patch_plan_data.patch_plan_content

        # Fall back to plan (for main workflows)
        plan_data = context.load_artifact_if_missing(
            "plan_data",
            "plan",
            PlanArtifact,
            lambda a: a.plan_data,
        )

        if plan_data is not None:
            logger.info("Using plan for acceptance validation")
            return plan_data.plan

        return None

    def run(self, context: WorkflowContext) -> StepResult:
        """Validate implementation against plan.

        Args:
            context: Workflow context with plan or patch_plan artifact

        Returns:
            StepResult with success status and optional error message
        """
        # Try to load plan content - prefer patch_plan over plan
        plan_text = self._load_plan_text(context)

        if plan_text is None:
            logger.warning("No plan or patch_plan available for acceptance validation")
            return StepResult.fail("No plan or patch_plan available for acceptance validation")

        acceptance_handler = make_progress_comment_handler(context.require_issue_id, context.adw_id)
        acceptance_result = notify_plan_acceptance(
            plan_text,
            context.require_issue_id,
            context.adw_id,
            stream_handler=acceptance_handler,
        )

        if not acceptance_result.success:
            logger.error("Failed to validate plan acceptance: %s", acceptance_result.error)
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
        payload = CommentPayload(
            issue_id=context.require_issue_id,
            adw_id=context.adw_id,
            text="Plan acceptance validation completed",
            raw={"text": "Plan acceptance validation completed."},
            source="system",
            kind="workflow",
        )
        status, msg = emit_comment_from_payload(payload)
        if status == "success":
            logger.debug(msg)
        else:
            logger.error(msg)

        return StepResult.ok(None)
