"""Implementation step implementations."""

import logging
from typing import Optional

from rouge.core.workflow.artifacts import (
    ImplementationArtifact,
    PatchPlanArtifact,
    PlanArtifact,
)
from rouge.core.workflow.implement import implement_plan
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult
from rouge.core.workflow.workflow_io import emit_progress_comment

logger = logging.getLogger(__name__)


class ImplementStep(WorkflowStep):
    """Execute implementation of the plan."""

    @property
    def name(self) -> str:
        return "Implementing solution"

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
            logger.info("Using patch_plan for implementation")
            return patch_plan_data.patch_plan_content

        # Fall back to plan (for main workflows)
        plan_data = context.load_artifact_if_missing(
            "plan_data",
            "plan",
            PlanArtifact,
            lambda a: a.plan_data,
        )

        if plan_data is not None:
            logger.info("Using plan for implementation")
            return plan_data.plan

        return None

    def run(self, context: WorkflowContext) -> StepResult:
        """Implement the plan and store result in context.

        Args:
            context: Workflow context with plan or patch_plan artifact

        Returns:
            StepResult with success status and optional error message
        """
        # Try to load plan content - prefer patch_plan over plan
        plan_text = self._load_plan_text(context)

        if plan_text is None:
            logger.error("Cannot implement: no plan or patch_plan available")
            return StepResult.fail("Cannot implement: no plan or patch_plan available")

        implement_response = implement_plan(plan_text, context.issue_id, context.adw_id)

        if not implement_response.success:
            logger.error("Error implementing solution: %s", implement_response.error)
            return StepResult.fail(f"Error implementing solution: {implement_response.error}")

        logger.info("Solution implemented")

        if implement_response.data is None:
            logger.error("Implementation data missing despite successful response")
            return StepResult.fail("Implementation data missing despite successful response")

        logger.debug("Output preview: %s...", implement_response.data.output[:200])

        # Store implementation data in context
        context.data["implement_data"] = implement_response.data

        # Save artifact if artifact store is available
        if context.artifacts_enabled and context.artifact_store is not None:
            artifact = ImplementationArtifact(
                workflow_id=context.adw_id,
                implement_data=implement_response.data,
            )
            context.artifact_store.write_artifact(artifact)
            logger.debug("Saved implementation artifact for workflow %s", context.adw_id)

        # Insert progress comment - best-effort, non-blocking
        emit_progress_comment(
            context.issue_id,
            "Implementation complete.",
            raw={"text": "Implementation complete."},
            adw_id=context.adw_id,
        )

        return StepResult.ok(None)
