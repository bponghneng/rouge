"""Implementation step implementations."""

import logging

from rouge.core.workflow.artifacts import (
    ImplementationArtifact,
    ImplementedPlanFileArtifact,
    PlanFileArtifact,
)
from rouge.core.workflow.implement import implement_plan
from rouge.core.workflow.plan_file import get_plan_file
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult
from rouge.core.workflow.workflow_io import emit_progress_comment

logger = logging.getLogger(__name__)


class ImplementStep(WorkflowStep):
    """Execute implementation of the plan."""

    @property
    def name(self) -> str:
        return "Implementing solution"

    def run(self, context: WorkflowContext) -> StepResult:
        """Implement the plan and store result in context.

        Args:
            context: Workflow context with plan_file

        Returns:
            StepResult with success status and optional error message
        """
        plan_file = context.data.get("plan_file")

        # Try to load from artifact if not in context
        if plan_file is None and context.artifacts_enabled and context.artifact_store is not None:
            try:
                plan_file_artifact = context.artifact_store.read_artifact(
                    "plan_file", PlanFileArtifact
                )
                plan_file = plan_file_artifact.plan_file_data.file_path
                context.data["plan_file"] = plan_file
                logger.debug("Loaded plan_file from artifact")
            except FileNotFoundError:
                # Missing plan_file artifact is acceptable; fall back to handling below.
                logger.debug("No plan_file artifact found; proceeding without loading from artifacts")

        if plan_file is None:
            logger.error("Cannot implement: plan_file not available")
            return StepResult.fail("Cannot implement: plan_file not available")

        implement_response = implement_plan(plan_file, context.issue_id, context.adw_id)

        if not implement_response.success:
            logger.error(f"Error implementing solution: {implement_response.error}")
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
        )

        return StepResult.ok(None)


class FindImplementedPlanStep(WorkflowStep):
    """Find the implemented plan file with fallback to original."""

    @property
    def name(self) -> str:
        return "Finding implemented plan file"

    def run(self, context: WorkflowContext) -> StepResult:
        """Find implemented plan file and store in context.

        Always succeeds (uses fallback to original plan file).

        Args:
            context: Workflow context with implement_data and plan_file

        Returns:
            StepResult (always succeeds with fallback)
        """
        implement_data = context.data.get("implement_data")
        fallback_path = context.data.get("plan_file", "")

        # Try to load from artifacts if not in context
        if context.artifacts_enabled and context.artifact_store is not None:
            if implement_data is None:
                try:
                    impl_artifact = context.artifact_store.read_artifact(
                        "implementation", ImplementationArtifact
                    )
                    implement_data = impl_artifact.implement_data
                    context.data["implement_data"] = implement_data
                    logger.debug("Loaded implementation from artifact")
                except FileNotFoundError:
                    # Missing implementation artifact is acceptable; fall back to checking context below.
                    logger.debug("No implementation artifact found; proceeding without it")

            if not fallback_path:
                try:
                    plan_file_artifact = context.artifact_store.read_artifact(
                        "plan_file", PlanFileArtifact
                    )
                    fallback_path = plan_file_artifact.plan_file_data.file_path
                    context.data["plan_file"] = fallback_path
                    logger.debug("Loaded plan_file from artifact for fallback")
                except FileNotFoundError:
                    # Missing plan_file artifact is acceptable; fallback_path will remain empty.
                    logger.debug("No plan_file artifact found for fallback; proceeding without it")

        if implement_data is None:
            logger.warning("No implementation data, using fallback plan file")
            context.data["implemented_plan_file"] = fallback_path
            self._save_implemented_plan_artifact(context, fallback_path)
            return StepResult.ok(None)

        impl_plan_result = get_plan_file(implement_data.output, context.issue_id, context.adw_id)

        if not impl_plan_result.success:
            logger.error(f"Error finding implemented plan file: {impl_plan_result.error}")
            logger.warning(f"Falling back to original plan file: {fallback_path}")
            context.data["implemented_plan_file"] = fallback_path
            self._save_implemented_plan_artifact(context, fallback_path)
            return StepResult.ok(None)

        if impl_plan_result.data is None:
            logger.warning("Could not determine implemented plan file, using original")
            context.data["implemented_plan_file"] = fallback_path
            self._save_implemented_plan_artifact(context, fallback_path)
            return StepResult.ok(None)

        implemented_plan_path = impl_plan_result.data.file_path
        logger.info(f"Implemented plan file: {implemented_plan_path}")
        context.data["implemented_plan_file"] = implemented_plan_path
        self._save_implemented_plan_artifact(context, implemented_plan_path)

        return StepResult.ok(None)

    def _save_implemented_plan_artifact(self, context: WorkflowContext, file_path: str) -> None:
        """Save the implemented plan file artifact if store is available."""
        if context.artifacts_enabled and context.artifact_store is not None and file_path:
            artifact = ImplementedPlanFileArtifact(
                workflow_id=context.adw_id,
                file_path=file_path,
            )
            context.artifact_store.write_artifact(artifact)
            logger.debug("Saved implemented_plan_file artifact for workflow %s", context.adw_id)
