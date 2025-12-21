"""Find plan file step implementation."""

import logging

from rouge.core.workflow.artifacts import PlanArtifact, PlanFileArtifact
from rouge.core.workflow.plan_file import get_plan_file
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import PlanFileData, StepResult

logger = logging.getLogger(__name__)


class FindPlanFileStep(WorkflowStep):
    """Find the plan file path from plan output."""

    @property
    def name(self) -> str:
        return "Finding plan file"

    def run(self, context: WorkflowContext) -> StepResult:
        """Find plan file path and store in context.

        Args:
            context: Workflow context with plan_data

        Returns:
            StepResult with success status and optional error message
        """
        plan_data = context.data.get("plan_data")

        # Try to load from artifact if not in context
        if plan_data is None and context.artifacts_enabled and context.artifact_store is not None:
            try:
                plan_artifact = context.artifact_store.read_artifact("plan", PlanArtifact)
                plan_data = plan_artifact.plan_data
                context.data["plan_data"] = plan_data
                logger.debug("Loaded plan from artifact")
            except FileNotFoundError:
                # Missing plan artifact is acceptable; fall back to handling absent plan_data.
                logger.debug("Plan artifact not found; proceeding without loaded plan_data")

        if plan_data is None:
            logger.error("Cannot find plan file: plan_data not available")
            return StepResult.fail("Cannot find plan file: plan_data not available")

        plan_file_result = get_plan_file(plan_data.output, context.issue_id, context.adw_id)

        if not plan_file_result.success:
            logger.error(f"Error finding plan file: {plan_file_result.error}")
            return StepResult.fail(f"Error finding plan file: {plan_file_result.error}")

        if plan_file_result.data is None:
            logger.error("Plan file data missing despite successful response")
            return StepResult.fail("Plan file data missing despite successful response")

        plan_file_path = plan_file_result.data.file_path
        logger.info(f"Plan file created: {plan_file_path}")

        # Store plan file path in context
        context.data["plan_file"] = plan_file_path

        # Save artifact if artifact store is available
        if context.artifacts_enabled and context.artifact_store is not None:
            artifact = PlanFileArtifact(
                workflow_id=context.adw_id,
                plan_file_data=PlanFileData(file_path=plan_file_path),
            )
            context.artifact_store.write_artifact(artifact)
            logger.debug("Saved plan_file artifact for workflow %s", context.adw_id)

        return StepResult.ok(None)
