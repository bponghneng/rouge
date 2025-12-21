"""Review generation and addressing step implementations."""

import logging

from rouge.core.notifications import make_progress_comment_handler
from rouge.core.workflow.address_review import address_review_issues
from rouge.core.workflow.artifacts import (
    ImplementedPlanFileArtifact,
    ReviewAddressedArtifact,
    ReviewArtifact,
)
from rouge.core.workflow.review import generate_review
from rouge.core.workflow.shared import (
    derive_paths_from_plan,
    get_repo_path,
    get_working_dir,
)
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult
from rouge.core.workflow.workflow_io import emit_progress_comment

logger = logging.getLogger(__name__)


class GenerateReviewStep(WorkflowStep):
    """Generate CodeRabbit review."""

    @property
    def name(self) -> str:
        return "Generating CodeRabbit review"

    @property
    def is_critical(self) -> bool:
        # Review generation is not critical - workflow continues if it fails
        return False

    def run(self, context: WorkflowContext) -> StepResult:
        """Generate review and store result in context.

        Args:
            context: Workflow context with implemented_plan_file

        Returns:
            StepResult with success status and optional error message
        """
        implemented_plan_path = context.data.get("implemented_plan_file", "")

        # Try to load from artifact if not in context
        if (
            not implemented_plan_path
            and context.artifacts_enabled
            and context.artifact_store is not None
        ):
            try:
                impl_plan_artifact = context.artifact_store.read_artifact(
                    "implemented_plan_file", ImplementedPlanFileArtifact
                )
                implemented_plan_path = impl_plan_artifact.file_path
                context.data["implemented_plan_file"] = implemented_plan_path
                logger.debug("Loaded implemented_plan_file from artifact")
            except FileNotFoundError:
                # Implemented plan artifact not found; handled below when checking implemented_plan_path.
                logger.debug("No implemented_plan_file artifact found; proceeding without it")

        if not implemented_plan_path:
            logger.warning("No implemented plan file, skipping review generation")
            return StepResult.fail("No implemented plan file, skipping review generation")

        # Derive paths from the implemented plan file
        paths = derive_paths_from_plan(implemented_plan_path)
        review_file = paths["review_file"]

        # Store for later steps
        context.data["review_file"] = review_file

        working_dir = get_working_dir()
        repo_path = get_repo_path()

        review_result = generate_review(review_file, working_dir, repo_path, context.issue_id)

        if not review_result.success:
            logger.error(f"Failed to generate CodeRabbit review: {review_result.error}")
            return StepResult.fail(f"Failed to generate CodeRabbit review: {review_result.error}")

        if review_result.data is None:
            logger.warning("CodeRabbit review succeeded but no data/review_file was returned")
            return StepResult.fail(
                "CodeRabbit review succeeded but no data/review_file was returned"
            )

        logger.info(f"CodeRabbit review generated successfully at {review_result.data.review_file}")

        # Store review data in context
        context.data["review_data"] = review_result.data

        # Save artifact if artifact store is available
        if context.artifacts_enabled and context.artifact_store is not None:
            artifact = ReviewArtifact(
                workflow_id=context.adw_id,
                review_data=review_result.data,
            )
            context.artifact_store.write_artifact(artifact)
            logger.debug("Saved review artifact for workflow %s", context.adw_id)

        # Insert progress comment - best-effort, non-blocking
        emit_progress_comment(
            context.issue_id,
            "CodeRabbit review complete.",
            raw={"text": "CodeRabbit review complete."},
        )

        return StepResult.ok(None)


class AddressReviewStep(WorkflowStep):
    """Address review issues from CodeRabbit review."""

    @property
    def name(self) -> str:
        return "Addressing review issues"

    @property
    def is_critical(self) -> bool:
        # Addressing review is not critical - workflow continues if it fails
        return False

    def run(self, context: WorkflowContext) -> StepResult:
        """Address review issues.

        Args:
            context: Workflow context with review_file

        Returns:
            StepResult with success status and optional error message
        """
        review_file = context.data.get("review_file", "")
        review_data = context.data.get("review_data")

        # Try to load from artifact if not in context
        if review_data is None and context.artifacts_enabled and context.artifact_store is not None:
            try:
                review_artifact = context.artifact_store.read_artifact("review", ReviewArtifact)
                review_data = review_artifact.review_data
                context.data["review_data"] = review_data
                if not review_file:
                    review_file = review_data.review_file
                    context.data["review_file"] = review_file
                logger.debug("Loaded review from artifact")
            except FileNotFoundError:
                # Missing review artifact is acceptable; fall back to "no review data" behavior.
                logger.debug("No review artifact found; proceeding without preloaded review data")

        # Only proceed if we have review data (review generation succeeded)
        if review_data is None:
            logger.warning("No review data available, skipping address review")
            return StepResult.ok(None)  # Not a failure - just nothing to do

        if not review_file:
            logger.warning("No review file available, skipping address review")
            return StepResult.ok(None)

        review_handler = make_progress_comment_handler(context.issue_id, context.adw_id)
        review_issues_result = address_review_issues(
            review_file,
            context.issue_id,
            context.adw_id,
            stream_handler=review_handler,
        )

        if not review_issues_result.success:
            logger.error(f"Failed to address review issues: {review_issues_result.error}")
            # Save artifact even on failure
            if context.artifacts_enabled and context.artifact_store is not None:
                artifact = ReviewAddressedArtifact(
                    workflow_id=context.adw_id,
                    success=False,
                    message=review_issues_result.error,
                )
                context.artifact_store.write_artifact(artifact)
            return StepResult.fail(f"Failed to address review issues: {review_issues_result.error}")

        logger.info("Review issues addressed successfully")

        # Save artifact if artifact store is available
        if context.artifacts_enabled and context.artifact_store is not None:
            artifact = ReviewAddressedArtifact(
                workflow_id=context.adw_id,
                success=True,
                message="Review issues addressed successfully",
            )
            context.artifact_store.write_artifact(artifact)
            logger.debug("Saved review_addressed artifact for workflow %s", context.adw_id)

        # Insert progress comment - best-effort, non-blocking
        emit_progress_comment(
            context.issue_id,
            "Review issues addressed.",
            raw={"text": "Review issues addressed."},
        )

        return StepResult.ok(None)
