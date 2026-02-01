"""Review generation and addressing step implementations."""

import logging

from rouge.core.models import CommentPayload
from rouge.core.notifications.agent_stream_handlers import make_progress_comment_handler
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.workflow.address_review import address_review_issues
from rouge.core.workflow.artifacts import PlanArtifact, ReviewAddressedArtifact, ReviewArtifact
from rouge.core.workflow.review import generate_review
from rouge.core.workflow.shared import get_repo_path
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult

logger = logging.getLogger(__name__)

# Module-level constant for step name used in rerun_from references
GENERATE_REVIEW_STEP_NAME = "Generating CodeRabbit review"


def is_clean_review(review_text: str) -> bool:
    """Determine whether a review indicates no actionable issues.

    A review is considered clean when it contains the phrase
    "Review completed" (signalling the reviewer finished successfully)
    **and** does not contain "File:" (which precedes per-file comments
    that require attention).

    Args:
        review_text: The full text output from the code review.

    Returns:
        True if the review is clean (no issues), False otherwise.
    """
    return "Review completed" in review_text and "File:" not in review_text


class GenerateReviewStep(WorkflowStep):
    """Generate CodeRabbit review."""

    @property
    def name(self) -> str:
        return GENERATE_REVIEW_STEP_NAME

    @property
    def is_critical(self) -> bool:
        # Review generation is not critical - workflow continues if it fails
        return False

    def run(self, context: WorkflowContext) -> StepResult:
        """Generate review and store result in context.

        Args:
            context: Workflow context with plan artifact

        Returns:
            StepResult with success status and optional error message
        """
        plan_data = context.load_artifact_if_missing(
            "plan_data",
            "plan",
            PlanArtifact,
            lambda a: a.plan_data,
        )

        if plan_data is None:
            logger.warning("No plan data available, skipping review generation")
            return StepResult.fail("No plan data available, skipping review generation")

        repo_path = get_repo_path()

        base_commit = context.data.get("base_commit")

        review_result = generate_review(
            repo_path, context.issue_id, context.adw_id, base_commit=base_commit
        )

        if not review_result.success:
            logger.error("Failed to generate CodeRabbit review: %s", review_result.error)
            return StepResult.fail(f"Failed to generate CodeRabbit review: {review_result.error}")

        if review_result.data is None:
            logger.warning("CodeRabbit review succeeded but no data was returned")
            return StepResult.fail("CodeRabbit review succeeded but no data was returned")

        logger.info("CodeRabbit review generated successfully")

        # Store review data in context
        context.data["review_data"] = review_result.data

        # Detect whether the review is clean (no actionable issues)
        is_clean = is_clean_review(review_result.data.review_text)
        context.data["review_is_clean"] = is_clean
        if is_clean:
            logger.info("Review is clean — no actionable issues detected")
        else:
            logger.info("Review contains issues that need to be addressed")

        # Save artifact if artifact store is available
        if context.artifacts_enabled and context.artifact_store is not None:
            artifact = ReviewArtifact(
                workflow_id=context.adw_id,
                review_data=review_result.data,
            )
            context.artifact_store.write_artifact(artifact)
            logger.debug("Saved review artifact for workflow %s", context.adw_id)

        # Insert progress comment - best-effort, non-blocking
        if context.issue_id is not None:
            payload = CommentPayload(
                issue_id=context.issue_id,
                adw_id=context.adw_id,
                text="CodeRabbit review complete.",
                raw={"text": "CodeRabbit review complete."},
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.error(msg)

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

        If the review was clean (no actionable issues), returns early with
        a success result.  Otherwise addresses the issues and signals the
        pipeline to rerun from the review-generation step so the fixes
        can be re-evaluated.

        Args:
            context: Workflow context with review_data

        Returns:
            StepResult with success status and optional error message.
            When issues are addressed, ``rerun_from`` is set to the
            GenerateReviewStep name so the pipeline re-reviews.
        """
        # Short-circuit: nothing to do when the review is clean
        if context.data.get("review_is_clean", False):
            logger.info("Review is clean, no issues to address")
            return StepResult.ok(None)

        # Try to load review_data from artifact if not in context
        review_data = context.load_artifact_if_missing(
            "review_data",
            "review",
            ReviewArtifact,
            lambda a: a.review_data,
        )

        # Only proceed if we have review data (review generation succeeded)
        if review_data is None:
            logger.warning("No review data available, skipping address review")
            return StepResult.ok(None)  # Not a failure - just nothing to do

        review_text = review_data.review_text.strip()
        if not review_text:
            logger.warning("No review text available, skipping address review")
            return StepResult.ok(None)

        # Only create handler if we have an issue_id
        review_handler = (
            make_progress_comment_handler(context.issue_id, context.adw_id)
            if context.issue_id is not None
            else None
        )

        review_issues_result = address_review_issues(
            context.issue_id,
            context.adw_id,
            review_text,
            stream_handler=review_handler,
        )

        if not review_issues_result.success:
            logger.error("Failed to address review issues: %s", review_issues_result.error)
            # Save artifact even on failure
            if context.artifacts_enabled and context.artifact_store is not None:
                artifact = ReviewAddressedArtifact(
                    workflow_id=context.adw_id,
                    success=False,
                    message=review_issues_result.error,
                )
                context.artifact_store.write_artifact(artifact)
            return StepResult.fail(f"Failed to address review issues: {review_issues_result.error}")

        logger.info("Review issues addressed successfully, requesting re-review")

        # Save artifact if artifact store is available
        if context.artifacts_enabled and context.artifact_store is not None:
            artifact = ReviewAddressedArtifact(
                workflow_id=context.adw_id,
                success=True,
                message="Review issues addressed, re-running review",
            )
            context.artifact_store.write_artifact(artifact)
            logger.debug("Saved review_addressed artifact for workflow %s", context.adw_id)

        # Insert progress comment - best-effort, non-blocking
        if context.issue_id is not None:
            payload = CommentPayload(
                issue_id=context.issue_id,
                adw_id=context.adw_id,
                text="Review issues addressed, re-running review.",
                raw={"text": "Review issues addressed, re-running review."},
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.error(msg)

        return StepResult.ok(None, rerun_from=GENERATE_REVIEW_STEP_NAME)
